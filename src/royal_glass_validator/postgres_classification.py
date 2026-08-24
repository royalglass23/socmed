"""PostgreSQL persistence for Phase 4 classification decisions and safe entity links."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from royal_glass_validator.classification import (
    ClassificationResult,
    CompetitorIdentity,
    EvidenceFact,
    IdentityLink,
    SourceRecordForClassification,
)


class PostgresClassificationRepository:
    """Load unclassified evidence and append classification audit history atomically."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def record_decision(
        self,
        *,
        source_record_id: object,
        validation_run_id: object,
        result: ClassificationResult,
        rule_version: str,
        identity_link: IdentityLink | None,
    ) -> None:
        """Append a decision and, if certain, link its existing Competitor Entity in one transaction."""
        decision_id = uuid4()
        competitor_entity_id = identity_link.competitor_entity_id if identity_link else None
        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                if identity_link:
                    cursor.execute(
                        """
                        INSERT INTO entity_links (
                            id, competitor_entity_id, source_record_id, link_method, certainty, linked_by, rationale
                        ) VALUES (%s, %s, %s, %s, 'high', 'automation', %s)
                        """,
                        (
                            uuid4(),
                            identity_link.competitor_entity_id,
                            source_record_id,
                            identity_link.link_method,
                            identity_link.rationale,
                        ),
                    )
                    if result.market_priority == "auckland_high":
                        cursor.execute(
                            """
                            UPDATE competitor_entities
                               SET market_priority = 'auckland_high', updated_at = now()
                             WHERE id = %s AND market_priority = 'standard'
                            """,
                            (identity_link.competitor_entity_id,),
                        )
                cursor.execute(
                    """
                    INSERT INTO classification_decisions (
                        id, source_record_id, competitor_entity_id, validation_run_id, proposed_classification,
                        proposed_outcome, confidence_band, rationale, tags, rule_version, approval_status,
                        requires_human_review, auto_approved
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        decision_id,
                        source_record_id,
                        competitor_entity_id,
                        validation_run_id,
                        result.proposed_classification,
                        result.proposed_outcome,
                        result.confidence_band,
                        result.rationale,
                        list(result.tags),
                        rule_version,
                        "auto_approved" if result.auto_approved else "proposed",
                        result.requires_human_review,
                        result.auto_approved,
                    ),
                )

    def load_existing_identities(self) -> tuple[CompetitorIdentity, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, display_name, primary_domain, verified_phone
                  FROM competitor_entities
                 ORDER BY id
                """,
                (),
            )
            rows = cursor.fetchall()
        return tuple(CompetitorIdentity(*row) for row in rows)

    def load_unclassified_source_records(self) -> tuple[SourceRecordForClassification, ...]:
        """Return every open Source Record with retained evidence/failure state and no decision."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT source.id,
                       source.validation_run_id,
                       source.original_values,
                       evidence.url,
                       evidence.source_type,
                       evidence.evidence_snippet,
                       evidence.service_facts,
                       evidence.region_facts,
                       EXISTS (
                           SELECT 1
                             FROM fetch_failures AS failure
                            WHERE failure.source_record_id = source.id
                              AND failure.validation_run_id = source.validation_run_id
                       ) AS has_fetch_failure
                  FROM source_records AS source
                  JOIN validation_runs AS run ON run.id = source.validation_run_id
                  LEFT JOIN page_evidence_source_records AS evidence_link
                    ON evidence_link.source_record_id = source.id
                   AND evidence_link.validation_run_id = source.validation_run_id
                  LEFT JOIN page_evidence AS evidence ON evidence.id = evidence_link.page_evidence_id
                 WHERE run.outcome = 'running'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM classification_decisions AS decision
                        WHERE decision.source_record_id = source.id
                          AND decision.validation_run_id = source.validation_run_id
                   )
                 ORDER BY source.validation_run_id, source.input_row_number, evidence.fetched_at, evidence.id
                """,
                (),
            )
            rows = cursor.fetchall()

        records: dict[object, SourceRecordForClassification] = {}
        for row in rows:
            source_record_id, validation_run_id, original_values, url, source_type, snippet, service_facts, region_facts, has_failure = row
            current = records.get(source_record_id)
            evidence = current.evidence if current else ()
            if url is not None:
                evidence += (
                    EvidenceFact(
                        url=str(url),
                        source_type=str(source_type),
                        evidence_snippet=str(snippet),
                        service_facts=service_facts,
                        region_facts=region_facts,
                    ),
                )
            records[source_record_id] = SourceRecordForClassification(
                id=source_record_id,
                validation_run_id=validation_run_id,
                original_values=original_values,
                evidence=evidence,
                has_fetch_failure=bool(has_failure),
            )
        return tuple(records.values())
