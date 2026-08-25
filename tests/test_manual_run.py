from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4


class ManualComparisonPlanTests(unittest.TestCase):
    def test_selects_only_new_changed_direct_adjacent_unresolved_and_failed_records(self) -> None:
        from royal_glass_validator.manual_run import ComparisonRecord, plan_manual_comparison

        plan = plan_manual_comparison(
            (
                ComparisonRecord("new", "new-hash"),
                ComparisonRecord("changed", "new-hash", previous_value_hash="old-hash"),
                ComparisonRecord("direct", "same-hash", previous_value_hash="same-hash", previous_classification="direct"),
                ComparisonRecord("adjacent", "same-hash", previous_value_hash="same-hash", previous_classification="adjacent"),
                ComparisonRecord("unresolved", "same-hash", previous_value_hash="same-hash", previous_outcome="review_required"),
                ComparisonRecord("failed", "same-hash", previous_value_hash="same-hash", had_fetch_failure=True),
                ComparisonRecord("supplier", "same-hash", previous_value_hash="same-hash", previous_classification="supplier_ecosystem"),
            )
        )

        self.assertEqual(plan.selected_entity_ids, ("new", "changed", "direct", "adjacent", "unresolved", "failed"))
        self.assertEqual(plan.new_record_count, 1)
        self.assertEqual(plan.changed_record_count, 1)
        self.assertEqual(plan.direct_recheck_count, 1)
        self.assertEqual(plan.adjacent_recheck_count, 1)
        self.assertEqual(plan.unresolved_recheck_count, 1)
        self.assertEqual(plan.failed_recheck_count, 1)

    def test_identifies_a_changed_supplier_without_automatically_refetching_it(self) -> None:
        from royal_glass_validator.manual_run import ComparisonRecord, plan_manual_comparison

        plan = plan_manual_comparison((
            ComparisonRecord(
                "supplier", "new-hash", previous_value_hash="old-hash", previous_classification="supplier_ecosystem"
            ),
        ))

        self.assertEqual(plan.selected_entity_ids, ())
        self.assertEqual(plan.changed_record_count, 1)


class ManualRunExecutionTests(unittest.TestCase):
    def test_runs_only_the_comparison_plan_and_returns_a_compact_structured_summary(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification
        from royal_glass_validator.manual_run import ComparisonCandidate, run_manual_comparison
        from royal_glass_validator.website_fetch import FetchSummary
        from royal_glass_validator.workbook_import import ImportedRun, ImportedSourceRecord

        run_id = uuid4()
        direct_id = uuid4()
        failed_id = uuid4()
        repository = FakeManualRunRepository(
            candidates=(
                ComparisonCandidate(direct_id, run_id, {"Entity ID": "RG-DIRECT"}, "RG-DIRECT", "direct-hash"),
                ComparisonCandidate(failed_id, run_id, {"Entity ID": "RG-FAILED"}, "RG-FAILED", "failed-hash", previous_value_hash="failed-hash", had_fetch_failure=True),
            ),
            records=(
                SourceRecordForClassification(
                    id=direct_id,
                    validation_run_id=run_id,
                    original_values={"Entity ID": "RG-DIRECT"},
                    evidence=(EvidenceFact("https://direct.example", "official_site", "We install glass pool fencing in New Zealand.", {"services": ["pool_fencing"]}, {"regions": ["new_zealand"]}),),
                ),
                SourceRecordForClassification(
                    id=failed_id,
                    validation_run_id=run_id,
                    original_values={"Entity ID": "RG-FAILED"},
                    evidence=(),
                    has_fetch_failure=True,
                ),
            ),
        )
        fetcher = FakeFetcher((FetchSummary(direct_id, 1, 0), FetchSummary(failed_id, 0, 1)))
        imported_run = ImportedRun(run_id, "royal-glass.xlsx", "a" * 64, {"cohort": "Needs Validation"}, "2026-08-24.1")
        imported_records = (
            ImportedSourceRecord(direct_id, run_id, "RG-DIRECT", "workbook", "Needs Validation", 2, {"Entity ID": "RG-DIRECT"}, "direct-hash"),
            ImportedSourceRecord(failed_id, run_id, "RG-FAILED", "workbook", "Needs Validation", 3, {"Entity ID": "RG-FAILED"}, "failed-hash"),
        )

        summary = run_manual_comparison(
            Path("royal-glass.xlsx"), repository, fetcher, rule_version="2026-08-24.1", import_plan=(imported_run, imported_records)
        )

        self.assertEqual(repository.imported, (imported_run, imported_records))
        self.assertEqual(fetcher.record_ids, (direct_id, failed_id))
        self.assertEqual(summary.as_dict(), {
            "validation_run_id": str(run_id), "input_workbook_name": "royal-glass.xlsx", "imported_record_count": 2,
            "selected_record_count": 2, "new_record_count": 1, "changed_record_count": 0, "direct_recheck_count": 0,
            "adjacent_recheck_count": 0, "unresolved_recheck_count": 0, "failed_recheck_count": 1,
            "evidence_page_count": 1, "fetch_failure_count": 1, "classified_record_count": 2,
            "auto_approved_count": 1, "review_required_count": 1, "outcome": "completed",
        })
        self.assertEqual(len(repository.decisions), 2)
        self.assertEqual(repository.completed_summary, summary)

    def test_resumes_an_existing_running_import_without_creating_duplicate_source_records(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification
        from royal_glass_validator.manual_run import ComparisonCandidate, resume_manual_comparison
        from royal_glass_validator.website_fetch import FetchSummary

        run_id = uuid4()
        source_record_id = uuid4()
        repository = FakeManualRunRepository(
            candidates=(ComparisonCandidate(source_record_id, run_id, {"Entity ID": "RG-RESUME"}, "RG-RESUME", "hash"),),
            records=(SourceRecordForClassification(
                id=source_record_id, validation_run_id=run_id, original_values={"Entity ID": "RG-RESUME"},
                evidence=(EvidenceFact("https://resume.example", "official_site", "We install glass pool fencing in New Zealand.", {"services": ["pool_fencing"]}, {"regions": ["new_zealand"]}),),
            ),),
            running_context=("Needs-Validation.xlsx", 686),
        )

        summary = resume_manual_comparison(
            run_id, repository, FakeFetcher((FetchSummary(source_record_id, 1, 0),)), rule_version="2026-08-24.1"
        )

        self.assertIsNone(repository.imported)
        self.assertEqual(summary.input_workbook_name, "Needs-Validation.xlsx")
        self.assertEqual(summary.imported_record_count, 686)
        self.assertEqual(summary.selected_record_count, 1)

    def test_resume_does_not_refetch_a_selected_record_with_a_durable_current_run_outcome(self) -> None:
        from royal_glass_validator.manual_run import ComparisonCandidate, resume_manual_comparison

        run_id = uuid4()
        source_record_id = uuid4()
        repository = FakeManualRunRepository(
            candidates=(ComparisonCandidate(source_record_id, run_id, {"Entity ID": "RG-DONE"}, "RG-DONE", "hash"),),
            records=(),
            running_context=("Needs-Validation.xlsx", 686),
            unfetched_source_ids=(),
        )
        fetcher = FakeFetcher(())

        resume_manual_comparison(run_id, repository, fetcher, rule_version="2026-08-24.1")

        self.assertEqual(fetcher.record_ids, ())

    def test_bounded_resume_classifies_only_one_durable_record_and_keeps_the_run_open(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification
        from royal_glass_validator.manual_run import ComparisonCandidate, resume_manual_comparison

        run_id = uuid4()
        first_id = uuid4()
        second_id = uuid4()
        evidence = EvidenceFact(
            "https://resume.example", "official_site", "Glass pool fencing in New Zealand.",
            {"services": ["pool_fencing"]}, {"regions": ["new_zealand"]},
        )
        repository = FakeManualRunRepository(
            candidates=(
                ComparisonCandidate(first_id, run_id, {"Entity ID": "RG-ONE"}, "RG-ONE", "one"),
                ComparisonCandidate(second_id, run_id, {"Entity ID": "RG-TWO"}, "RG-TWO", "two"),
            ),
            records=(
                SourceRecordForClassification(first_id, run_id, {"Entity ID": "RG-ONE"}, evidence=(evidence,)),
                SourceRecordForClassification(second_id, run_id, {"Entity ID": "RG-TWO"}, evidence=(evidence,)),
            ),
            initial_records=(
                SourceRecordForClassification(first_id, run_id, {"Entity ID": "RG-ONE"}, evidence=(evidence,)),
                SourceRecordForClassification(second_id, run_id, {"Entity ID": "RG-TWO"}, evidence=(evidence,)),
            ),
            running_context=("Needs-Validation.xlsx", 686),
            unfetched_source_ids=(),
        )

        summary = resume_manual_comparison(
            run_id, repository, FakeFetcher(()), rule_version="2026-08-24.1", max_records=1
        )

        self.assertEqual(summary.outcome, "running")
        self.assertEqual(summary.classified_record_count, 1)
        self.assertEqual(len(repository.decisions), 1)
        self.assertIsNone(repository.completed_summary)


class PostgresManualRunRepositoryTests(unittest.TestCase):
    def test_loads_latest_history_for_each_entity_and_completes_with_only_compact_summary(self) -> None:
        from royal_glass_validator.manual_run import ManualRunSummary
        from royal_glass_validator.postgres_manual_run import PostgresManualRunRepository

        run_id = uuid4()
        source_record_id = uuid4()
        connection = RecordingConnection(rows=[(
            source_record_id, run_id, {"Entity ID": "RG-C0204", "Website": "https://clearview.example"},
            "RG-C0204", "new-hash", "old-hash", "direct", "direct", False,
        )])
        repository = PostgresManualRunRepository(connection, json_wrapper=lambda value: value)

        candidates = repository.load_comparison_candidates(run_id)
        summary = ManualRunSummary(run_id, "royal-glass.xlsx", 1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 0)
        repository.complete_run(run_id, summary)

        self.assertEqual(candidates[0].entity_id, "RG-C0204")
        self.assertEqual(candidates[0].previous_value_hash, "old-hash")
        comparison_query, comparison_parameters = connection.statements[0]
        self.assertIn("DISTINCT ON", comparison_query)
        self.assertIn("original_values ->> 'Entity ID'", comparison_query)
        self.assertEqual(comparison_parameters, (run_id, run_id, run_id))
        completion_query, completion_parameters = connection.statements[1]
        self.assertIn("UPDATE validation_runs", completion_query)
        self.assertIn("outcome = 'completed'", completion_query)
        self.assertEqual(completion_parameters[0], summary.as_dict())
        self.assertEqual(completion_parameters[1], run_id)

    def test_loads_only_a_running_run_context_for_resume(self) -> None:
        from royal_glass_validator.postgres_manual_run import PostgresManualRunRepository

        run_id = uuid4()
        connection = RecordingConnection(rows=[], fetchone_rows=[("Needs-Validation.xlsx", 686)])

        context = PostgresManualRunRepository(connection).load_running_run_context(run_id)

        self.assertEqual(context, ("Needs-Validation.xlsx", 686))
        query, parameters = connection.statements[0]
        self.assertIn("outcome = 'running'", query)
        self.assertEqual(parameters, (run_id,))


class FakeFetcher:
    def __init__(self, summaries: tuple[object, ...]) -> None:
        self._summaries = summaries
        self.record_ids: tuple[object, ...] = ()

    def fetch_records(self, records: tuple[object, ...]) -> tuple[object, ...]:
        self.record_ids = tuple(record.id for record in records)
        return self._summaries


class FakeManualRunRepository:
    def __init__(
        self,
        *,
        candidates: tuple[object, ...],
        records: tuple[object, ...],
        initial_records: tuple[object, ...] | None = None,
        running_context: tuple[str, int] | None = None,
        unfetched_source_ids: tuple[object, ...] | None = None,
    ) -> None:
        self._candidates = candidates
        self._records = records
        self._initial_records = initial_records
        self._classification_load_count = 0
        self._running_context = running_context
        self._unfetched_source_ids = unfetched_source_ids
        self.imported: tuple[object, object] | None = None
        self.decisions: list[tuple[object, object]] = []
        self.completed_summary: object | None = None

    def import_records(self, run: object, records: object) -> None:
        self.imported = (run, records)

    def load_comparison_candidates(self, validation_run_id: object) -> tuple[object, ...]:
        return self._candidates

    def load_running_run_context(self, validation_run_id: object) -> tuple[str, int]:
        if self._running_context is None:
            raise AssertionError("No running context configured.")
        return self._running_context

    def load_unfetched_selected_source_records(
        self, validation_run_id: object, source_record_ids: tuple[object, ...]
    ) -> tuple[object, ...]:
        from royal_glass_validator.website_fetch import FetchSourceRecord

        allowed = set(source_record_ids if self._unfetched_source_ids is None else self._unfetched_source_ids)
        return tuple(
            FetchSourceRecord(candidate.source_record_id, candidate.validation_run_id, candidate.original_values)
            for candidate in self._candidates
            if candidate.source_record_id in allowed
        )

    def load_existing_identities(self) -> tuple[object, ...]:
        return ()

    def load_classification_records(self, validation_run_id: object, source_record_ids: tuple[object, ...]) -> tuple[object, ...]:
        self._classification_load_count += 1
        if self._classification_load_count == 1:
            return self._initial_records or ()
        return self._records

    def record_decision(self, **kwargs: object) -> None:
        self.decisions.append((kwargs["source_record_id"], kwargs["result"]))

    def complete_run(self, validation_run_id: object, summary: object) -> None:
        self.completed_summary = summary


class RecordingCursor:
    def __init__(self, connection: "RecordingConnection") -> None:
        self._connection = connection

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self._connection.statements.append((query, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._connection.rows

    def fetchone(self) -> tuple[object, ...] | None:
        if not self._connection.fetchone_rows:
            return None
        return self._connection.fetchone_rows.pop(0)


class RecordingTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


class RecordingConnection:
    def __init__(self, *, rows: list[tuple[object, ...]], fetchone_rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows = rows
        self.fetchone_rows = fetchone_rows or []
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction()
