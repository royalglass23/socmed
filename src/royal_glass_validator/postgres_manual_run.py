"""PostgreSQL adapter for manual Phase 4 comparison runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from royal_glass_validator.manual_run import ComparisonCandidate, ManualRunSummary
from royal_glass_validator.postgres_classification import PostgresClassificationRepository
from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository
from royal_glass_validator.postgres_import import PostgresImportRepository


class PostgresManualRunRepository:
    """Compose established persistence adapters with history-based comparison selection."""

    def __init__(self, connection: Any, *, json_wrapper: Callable[[dict[str, object]], object] | None = None) -> None:
        self._connection = connection
        self._json_wrapper = json_wrapper or _postgres_jsonb
        self._imports = PostgresImportRepository(connection)
        self._evidence = PostgresEvidenceRepository(connection)
        self._classification = PostgresClassificationRepository(connection)

    def import_records(self, run: object, records: object) -> None:
        self._imports.import_records(run, records)

    def record_evidence(self, evidence: object) -> None:
        self._evidence.record_evidence(evidence)

    def record_failure(self, failure: object) -> None:
        self._evidence.record_failure(failure)

    def load_comparison_candidates(self, validation_run_id: UUID) -> tuple[ComparisonCandidate, ...]:
        """Load current records with their latest prior Entity ID outcome, never mutating history."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                WITH current_records AS (
                    SELECT source.id, source.validation_run_id, source.original_values,
                           source.original_values ->> 'Entity ID' AS entity_id, source.original_value_hash
                      FROM source_records AS source
                     WHERE source.validation_run_id = %s
                ), previous_records AS (
                    SELECT DISTINCT ON (source.original_values ->> 'Entity ID')
                           source.original_values ->> 'Entity ID' AS entity_id,
                           source.original_value_hash
                      FROM source_records AS source
                     WHERE source.validation_run_id <> %s
                       AND NULLIF(source.original_values ->> 'Entity ID', '') IS NOT NULL
                     ORDER BY source.original_values ->> 'Entity ID', source.created_at DESC, source.id DESC
                )
                SELECT current.id, current.validation_run_id, current.original_values, current.entity_id,
                       current.original_value_hash, previous.original_value_hash,
                       decision.proposed_classification, decision.proposed_outcome,
                       COALESCE(decision.had_fetch_failure, FALSE)
                  FROM current_records AS current
                  LEFT JOIN previous_records AS previous ON previous.entity_id = current.entity_id
                  LEFT JOIN LATERAL (
                      SELECT classified.proposed_classification, classified.proposed_outcome,
                             EXISTS (
                                 SELECT 1
                                   FROM fetch_failures AS failure
                                  WHERE failure.source_record_id = classified.source_record_id
                                    AND failure.validation_run_id = classified.validation_run_id
                             ) AS had_fetch_failure
                        FROM classification_decisions AS classified
                        JOIN source_records AS classified_source
                          ON classified_source.id = classified.source_record_id
                         AND classified_source.validation_run_id = classified.validation_run_id
                       WHERE classified_source.validation_run_id <> %s
                         AND classified_source.original_values ->> 'Entity ID' = current.entity_id
                       ORDER BY classified.created_at DESC, classified.id DESC
                       LIMIT 1
                  ) AS decision ON TRUE
                 ORDER BY current.entity_id, current.id
                """,
                (validation_run_id, validation_run_id, validation_run_id),
            )
            rows = cursor.fetchall()
        return tuple(
            ComparisonCandidate(
                source_record_id=row[0],
                validation_run_id=row[1],
                original_values=dict(row[2]),
                entity_id=str(row[3]),
                original_value_hash=str(row[4]),
                previous_value_hash=str(row[5]) if row[5] is not None else None,
                previous_classification=str(row[6]) if row[6] is not None else None,
                previous_outcome=str(row[7]) if row[7] is not None else None,
                had_fetch_failure=bool(row[8]),
            )
            for row in rows
        )

    def load_running_run_context(self, validation_run_id: UUID) -> tuple[str, int]:
        """Return immutable input facts only while the requested run remains resumable."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run.input_workbook_name, COUNT(source.id)
                  FROM validation_runs AS run
                  LEFT JOIN source_records AS source ON source.validation_run_id = run.id
                 WHERE run.id = %s AND run.outcome = 'running'
                 GROUP BY run.input_workbook_name
                """,
                (validation_run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError("The requested validation run is not available for resume.")
        return str(row[0]), int(row[1])

    def load_unfetched_selected_source_records(
        self, validation_run_id: UUID, source_record_ids: tuple[UUID, ...]
    ) -> tuple[object, ...]:
        return self._evidence.load_unfetched_selected_source_records(validation_run_id, source_record_ids)

    def load_existing_identities(self) -> tuple[object, ...]:
        return self._classification.load_existing_identities()

    def load_classification_records(self, validation_run_id: UUID, source_record_ids: tuple[UUID, ...]) -> tuple[object, ...]:
        return self._classification.load_records_for_classification(validation_run_id, source_record_ids)

    def record_decision(self, **kwargs: object) -> None:
        self._classification.record_decision(**kwargs)

    def complete_run(self, validation_run_id: UUID, summary: ManualRunSummary) -> None:
        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE validation_runs
                       SET outcome = 'completed', completed_at = now(), summary = %s
                     WHERE id = %s AND outcome = 'running'
                    """,
                    (self._json_wrapper(summary.as_dict()), validation_run_id),
                )


def _postgres_jsonb(value: dict[str, object]) -> object:
    from psycopg.types.json import Jsonb

    return Jsonb(value)
