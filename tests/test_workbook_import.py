from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from royal_glass_validator.postgres_import import PostgresImportRepository
from royal_glass_validator.workbook_import import ImportValidationError, import_workbook


class RecordingImportRepository:
    def __init__(self) -> None:
        self.imports: list[tuple[object, tuple[object, ...]]] = []

    def import_records(self, run: object, records: tuple[object, ...]) -> None:
        self.imports.append((run, records))


class NeedsValidationWorkbookImportTests(unittest.TestCase):
    def test_imports_only_needs_validation_sheet_rows_and_preserves_every_original_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbook_path = Path(temporary_directory) / "royal-glass.xlsx"
            _write_workbook(
                workbook_path,
                needs_validation_rows=[
                    ("RG-C0204", "Hi Class Glass Ltd", "Needs Validation - Strong Candidate", 3.9),
                    ("RG-C0215", "New Concept Glass Ltd", "Needs Validation", None),
                ],
                confirmed_rows=[("RG-C0001", "Confirmed Glass", "Confirmed Competitor", 4.8)],
            )
            repository = RecordingImportRepository()

            summary = import_workbook(workbook_path, repository, rule_version="2026-08-24.1")

        self.assertEqual(summary.imported_record_count, 2)
        self.assertEqual(len(repository.imports), 1)
        run, records = repository.imports[0]
        self.assertEqual(run.input_workbook_name, "royal-glass.xlsx")
        self.assertEqual(run.input_provenance["worksheet"], "Needs Validation")
        self.assertEqual([record.entity_id for record in records], ["RG-C0204", "RG-C0215"])
        self.assertEqual(records[0].input_row_number, 2)
        self.assertEqual(
            records[0].original_values,
            {
                "Entity ID": "RG-C0204",
                "Canonical Name": "Hi Class Glass Ltd",
                "Decision Group": "Needs Validation - Strong Candidate",
                "Google Rating": 3.9,
            },
        )
        self.assertEqual(records[1].original_values["Google Rating"], None)

    def test_rejects_an_ambiguous_needs_validation_workbook_before_altering_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbook_path = Path(temporary_directory) / "royal-glass.xlsx"
            _write_workbook(
                workbook_path,
                needs_validation_rows=[
                    ("RG-C0204", "Hi Class Glass Ltd", "Needs Validation", 3.9),
                    ("RG-C0204", "Duplicate", "Needs Validation", 4.2),
                ],
                confirmed_rows=[],
            )
            repository = RecordingImportRepository()

            with self.assertRaisesRegex(ImportValidationError, "duplicate Entity ID"):
                import_workbook(workbook_path, repository, rule_version="2026-08-24.1")

        self.assertEqual(repository.imports, [])

    def test_rejects_a_non_cohort_row_on_the_needs_validation_sheet_before_altering_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbook_path = Path(temporary_directory) / "royal-glass.xlsx"
            _write_workbook(
                workbook_path,
                needs_validation_rows=[("RG-C0204", "Hi Class Glass Ltd", "Confirmed Competitor", 3.9)],
                confirmed_rows=[],
            )
            repository = RecordingImportRepository()

            with self.assertRaisesRegex(ImportValidationError, "not in the Needs Validation cohort"):
                import_workbook(workbook_path, repository, rule_version="2026-08-24.1")

        self.assertEqual(repository.imports, [])


class PostgresWorkbookImportRepositoryTests(unittest.TestCase):
    def test_writes_the_run_and_source_records_inside_one_transaction(self) -> None:
        from royal_glass_validator.workbook_import import ImportedRun, ImportedSourceRecord
        from uuid import uuid4

        run_id = uuid4()
        run = ImportedRun(
            id=run_id,
            input_workbook_name="royal-glass.xlsx",
            input_workbook_sha256="a" * 64,
            input_provenance={"worksheet": "Needs Validation"},
            rule_version="2026-08-24.1",
        )
        record = ImportedSourceRecord(
            id=uuid4(),
            validation_run_id=run_id,
            entity_id="RG-C0204",
            source_system="royal_glass_competitor_workbook",
            source_locator="Needs Validation",
            input_row_number=2,
            original_values={"Entity ID": "RG-C0204"},
            original_value_hash="b" * 64,
        )
        connection = RecordingConnection()

        PostgresImportRepository(connection).import_records(run, (record,))

        self.assertEqual(connection.transaction_entries, 1)
        self.assertEqual(len(connection.statements), 2)
        self.assertIn("INSERT INTO validation_runs", connection.statements[0])
        self.assertIn("INSERT INTO source_records", connection.statements[1])


def _write_workbook(
    workbook_path: Path,
    *,
    needs_validation_rows: list[tuple[str, str, str, float | None]],
    confirmed_rows: list[tuple[str, str, str, float | None]],
) -> None:
    workbook = Workbook()
    needs_validation = workbook.active
    needs_validation.title = "Needs Validation"
    confirmed = workbook.create_sheet("Confirmed Competitors")
    headers = ["Entity ID", "Canonical Name", "Decision Group", "Google Rating"]
    needs_validation.append(headers)
    confirmed.append(headers)
    for row in needs_validation_rows:
        needs_validation.append(row)
    for row in confirmed_rows:
        confirmed.append(row)
    workbook.save(workbook_path)


class RecordingTransaction:
    def __init__(self, connection: "RecordingConnection") -> None:
        self.connection = connection

    def __enter__(self) -> None:
        self.connection.transaction_entries += 1

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


class RecordingCursor:
    def __init__(self, connection: "RecordingConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.connection.statements.append(query)


class RecordingConnection:
    def __init__(self) -> None:
        self.transaction_entries = 0
        self.statements: list[str] = []

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)
