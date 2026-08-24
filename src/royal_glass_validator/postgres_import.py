"""PostgreSQL persistence adapter for a validated workbook import plan."""

from __future__ import annotations

from typing import Any

from royal_glass_validator.workbook_import import ImportedRun, ImportedSourceRecord


class PostgresImportRepository:
    """Write one validation run and all of its immutable source records atomically."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def import_records(self, run: ImportedRun, records: tuple[ImportedSourceRecord, ...]) -> None:
        from psycopg.types.json import Jsonb

        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO validation_runs (
                        id, input_workbook_name, input_workbook_sha256, input_provenance, rule_version
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        run.id,
                        run.input_workbook_name,
                        run.input_workbook_sha256,
                        Jsonb(dict(run.input_provenance)),
                        run.rule_version,
                    ),
                )
                for record in records:
                    cursor.execute(
                        """
                        INSERT INTO source_records (
                            id, validation_run_id, source_system, source_locator,
                            input_row_number, original_values, original_value_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.id,
                            record.validation_run_id,
                            record.source_system,
                            record.source_locator,
                            record.input_row_number,
                            Jsonb(dict(record.original_values)),
                            record.original_value_hash,
                        ),
                    )
