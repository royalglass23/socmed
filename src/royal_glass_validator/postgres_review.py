"""PostgreSQL review reads and append-only protected human overrides."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from royal_glass_validator.classification import _normalized_name

from royal_glass_validator.reviewer_export import ReviewerEvidence, ReviewerExportRow, protected_override_conflict


class OverrideValidationError(ValueError):
    """Raised before an invalid override can be sent to persistent storage."""


class PostgresReviewerRepository:
    """Expose the reviewer view and append protected human decisions."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def resolve_identity(
        self,
        *,
        classification_decision_id: UUID,
        existing_entity_id: UUID | None,
        legal_name: str | None,
        display_name: str | None,
        primary_domain: str | None,
        verified_phone: str | None,
        rationale: str,
        reviewer_identity: str,
    ) -> UUID:
        """Explicitly link a reviewed source record to one existing or new entity."""
        if not rationale.strip() or not reviewer_identity.strip():
            raise OverrideValidationError("An identity resolution requires both a rationale and reviewer identity.")
        creating_entity = existing_entity_id is None
        if creating_entity and (not legal_name or not legal_name.strip() or not display_name or not display_name.strip()):
            raise OverrideValidationError("Creating an entity requires both legal name and display name.")
        if not creating_entity and any(value is not None for value in (legal_name, display_name, primary_domain, verified_phone)):
            raise OverrideValidationError("Choose either an existing entity or new entity details, not both.")

        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT source_record_id FROM classification_decisions WHERE id = %s", (classification_decision_id,))
                decision = cursor.fetchone()
                if decision is None:
                    raise OverrideValidationError("The classification decision does not exist.")
                source_record_id = decision[0]
                cursor.execute("SELECT competitor_entity_id FROM entity_links WHERE source_record_id = %s", (source_record_id,))
                if cursor.fetchone() is not None:
                    raise OverrideValidationError("The source record is already linked; do not replace an identity link silently.")
                if creating_entity:
                    entity_id = uuid4()
                    cursor.execute(
                        """
                        INSERT INTO competitor_entities (
                            id, legal_name, display_name, normalized_name, primary_domain, verified_phone, identity_facts
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            entity_id,
                            legal_name.strip(),
                            display_name.strip(),
                            _normalized_name(display_name),
                            primary_domain.strip() if primary_domain else None,
                            verified_phone.strip() if verified_phone else None,
                            json.dumps({"identity_resolution": "reviewer_created"}),
                        ),
                    )
                else:
                    entity_id = existing_entity_id
                    cursor.execute("SELECT id FROM competitor_entities WHERE id = %s", (entity_id,))
                    if cursor.fetchone() is None:
                        raise OverrideValidationError("The selected Competitor Entity does not exist.")
                cursor.execute(
                    """
                    INSERT INTO entity_links (
                        id, competitor_entity_id, source_record_id, link_method, certainty, linked_by, rationale
                    ) VALUES (%s, %s, %s, %s, 'reviewer_confirmed', 'reviewer', %s)
                    """,
                    (uuid4(), entity_id, source_record_id, "reviewer_resolved", rationale.strip()),
                )
        return entity_id

    def record_override(self, *, classification_decision_id: UUID, classification: str, rationale: str, reviewer_identity: str, supersedes_override_id: UUID | None) -> None:
        """Append a named override; the database trigger enforces supersession safety."""
        if classification not in {"direct", "adjacent", "supplier_ecosystem", "irrelevant"}:
            raise OverrideValidationError("Override classification is not valid for the Royal Glass ruleset.")
        if not rationale.strip() or not reviewer_identity.strip():
            raise OverrideValidationError("An override requires both a rationale and reviewer identity.")
        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                cursor.execute("""
                    SELECT decision.source_record_id, link.competitor_entity_id
                      FROM classification_decisions AS decision
                      JOIN entity_links AS link ON link.source_record_id = decision.source_record_id
                     WHERE decision.id = %s
                """, (classification_decision_id,))
                decision = cursor.fetchone()
                if decision is None:
                    raise OverrideValidationError("Resolve the source record identity before recording a protected override.")
                cursor.execute("""
                    INSERT INTO human_overrides (
                        id, competitor_entity_id, classification_decision_id, source_record_id, classification, rationale,
                        reviewer_identity, supersedes_override_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (uuid4(), decision[1], classification_decision_id, decision[0], classification, rationale.strip(), reviewer_identity.strip(), supersedes_override_id))

    def load_reviewer_rows(self) -> tuple[ReviewerExportRow, ...]:
        """Load latest decisions with compact audit history and any active override."""
        with self._connection.cursor() as cursor:
            cursor.execute("""
                WITH latest_decisions AS (
                    SELECT DISTINCT ON (source_record_id)
                           id, source_record_id, competitor_entity_id, validation_run_id, proposed_classification,
                           proposed_outcome, confidence_band, rationale, tags
                      FROM classification_decisions
                     ORDER BY source_record_id, created_at DESC, id DESC
                ), active_overrides AS (
                    SELECT override.id, override.competitor_entity_id, override.classification,
                           override.rationale, override.reviewer_identity
                      FROM human_overrides AS override
                     WHERE NOT EXISTS (SELECT 1 FROM human_overrides AS successor WHERE successor.supersedes_override_id = override.id)
                )
                SELECT source.id, decision.id, decision.validation_run_id, source.input_row_number, source.original_values,
                       decision.proposed_classification, decision.proposed_outcome, decision.confidence_band,
                       decision.rationale, decision.tags,
                       COALESCE((SELECT jsonb_agg(
                                   jsonb_build_object('url', item.url, 'title', item.page_title, 'snippet', item.evidence_snippet)
                                   ORDER BY item.fetched_at, item.id
                               ) FROM (
                            SELECT evidence.id, evidence.fetched_at, evidence.url, evidence.page_title, evidence.evidence_snippet
                              FROM page_evidence_source_records AS evidence_link
                              JOIN page_evidence AS evidence ON evidence.id = evidence_link.page_evidence_id
                             WHERE evidence_link.source_record_id = source.id AND evidence_link.validation_run_id = decision.validation_run_id
                       ) AS item), '[]'::jsonb),
                       COALESCE((SELECT array_agg(failure.failure_type || ': ' || failure.attempted_url || ' (attempt ' || failure.attempt_number || ')' ORDER BY failure.occurred_at, failure.id)
                                   FROM fetch_failures AS failure
                                  WHERE failure.source_record_id = source.id AND failure.validation_run_id = decision.validation_run_id), ARRAY[]::text[]),
                       CASE WHEN link.id IS NULL THEN NULL ELSE 'High-certainty link: ' || entity.display_name || ' (' || link.link_method || ').' END,
                       active_override.classification, active_override.id, active_override.rationale, active_override.reviewer_identity
                  FROM latest_decisions AS decision
                  JOIN source_records AS source ON source.id = decision.source_record_id
                  LEFT JOIN entity_links AS link ON link.source_record_id = source.id
                  LEFT JOIN competitor_entities AS entity ON entity.id = link.competitor_entity_id
                  LEFT JOIN active_overrides AS active_override ON active_override.competitor_entity_id = COALESCE(decision.competitor_entity_id, link.competitor_entity_id)
                 ORDER BY decision.validation_run_id, source.input_row_number, source.id
            """, ())
            rows = cursor.fetchall()
        result: list[ReviewerExportRow] = []
        for row in rows:
            (source_record_id, decision_id, validation_run_id, input_row_number, original_values, proposed_classification, proposed_outcome, confidence_band, rationale, tags, evidence_items, failures, duplicate_link, override_classification, override_id, override_rationale, override_reviewer) = row
            evidence = tuple(ReviewerEvidence(url=str(item["url"]), title=item.get("title"), snippet=str(item["snippet"])) for item in evidence_items)
            result.append(ReviewerExportRow(source_record_id=source_record_id, classification_decision_id=decision_id, validation_run_id=validation_run_id, input_row_number=input_row_number, original_values=original_values, proposed_classification=proposed_classification, proposed_outcome=proposed_outcome, confidence_band=confidence_band, rationale=rationale, tags=tuple(tags), evidence=evidence, fetch_failures=tuple(failures), duplicate_link=duplicate_link, active_override_classification=override_classification, active_override_id=override_id, active_override_rationale=override_rationale, active_override_reviewer=override_reviewer, override_conflict=protected_override_conflict(proposed_classification, override_classification)))
        return tuple(result)
