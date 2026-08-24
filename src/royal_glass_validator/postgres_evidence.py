"""PostgreSQL persistence adapter for compact website evidence and fetch failures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from royal_glass_validator.website_fetch import FetchFailure, FetchSourceRecord, PageEvidence


class PostgresEvidenceRepository:
    """Persist compact and 90-day raw Phase 4 website evidence with source provenance."""

    def __init__(self, connection: Any, *, json_wrapper: Callable[[dict[str, object]], object] | None = None) -> None:
        self._connection = connection
        self._json_wrapper = json_wrapper or _postgres_jsonb

    def record_evidence(self, evidence: PageEvidence) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO page_evidence (
                    id, source_record_id, validation_run_id, url, page_title, evidence_snippet,
                    fetched_at, content_sha256, service_facts, region_facts, source_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (validation_run_id, url, content_sha256) DO NOTHING
                RETURNING id
                """,
                (
                    evidence.id,
                    evidence.source_record_id,
                    evidence.validation_run_id,
                    evidence.url,
                    evidence.page_title,
                    evidence.evidence_snippet,
                    evidence.fetched_at,
                    evidence.content_sha256,
                    self._json_wrapper(dict(evidence.service_facts)),
                    self._json_wrapper(dict(evidence.region_facts)),
                    evidence.source_type,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    """
                    SELECT id
                      FROM page_evidence
                     WHERE validation_run_id = %s AND url = %s AND content_sha256 = %s
                    """,
                    (evidence.validation_run_id, evidence.url, evidence.content_sha256),
                )
                existing = cursor.fetchone()
                if existing is None:
                    raise RuntimeError("Page evidence conflict could not be resolved.")
                page_evidence_id = existing[0]
            else:
                page_evidence_id = inserted[0]

            cursor.execute(
                """
                INSERT INTO page_evidence_source_records (page_evidence_id, source_record_id, validation_run_id)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (page_evidence_id, evidence.source_record_id, evidence.validation_run_id),
            )
            if inserted is not None:
                cursor.execute(
                    """
                    INSERT INTO raw_page_snapshots (id, page_evidence_id, snapshot_body)
                    VALUES (%s, %s, %s)
                    """,
                    (evidence.id, page_evidence_id, evidence.snapshot_body),
                )

    def record_failure(self, failure: FetchFailure) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO fetch_failures (
                    id, source_record_id, validation_run_id, attempted_url, failure_type,
                    attempt_number, response_status, detail, occurred_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    failure.id,
                    failure.source_record_id,
                    failure.validation_run_id,
                    failure.attempted_url,
                    failure.failure_type,
                    failure.attempt_number,
                    failure.response_status,
                    failure.detail,
                    failure.occurred_at,
                ),
            )

    def load_unfetched_source_records(self) -> tuple[FetchSourceRecord, ...]:
        """Return deterministic open-run Source Records with no prior evidence or failure."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT source.id, source.validation_run_id, source.original_values
                  FROM source_records AS source
                  JOIN validation_runs AS run ON run.id = source.validation_run_id
                 WHERE run.outcome = 'running'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM page_evidence_source_records AS evidence_link
                        WHERE evidence_link.source_record_id = source.id
                          AND evidence_link.validation_run_id = source.validation_run_id
                   )
                   AND NOT EXISTS (
                       SELECT 1
                         FROM fetch_failures AS failure
                        WHERE failure.source_record_id = source.id
                          AND failure.validation_run_id = source.validation_run_id
                   )
                 ORDER BY source.validation_run_id, source.input_row_number
                """,
                (),
            )
            rows = cursor.fetchall()
        return tuple(
            FetchSourceRecord(id=source_record_id, validation_run_id=validation_run_id, original_values=original_values)
            for source_record_id, validation_run_id, original_values in rows
        )


def _postgres_jsonb(value: dict[str, object]) -> object:
    from psycopg.types.json import Jsonb

    return Jsonb(value)
