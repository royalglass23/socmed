from __future__ import annotations

from datetime import datetime, timezone
import unittest
from uuid import uuid4


class PostgresEvidenceRepositoryTests(unittest.TestCase):
    def test_writes_compact_evidence_and_fetch_failures_using_the_phase_four_contract(self) -> None:
        from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository
        from royal_glass_validator.website_fetch import FetchFailure, PageEvidence

        evidence_id = uuid4()
        connection = RecordingConnection(fetchone_rows=[(evidence_id,)])
        repository = PostgresEvidenceRepository(connection, json_wrapper=lambda value: value)
        source_record_id = uuid4()
        validation_run_id = uuid4()
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)

        repository.record_evidence(
            PageEvidence(
                id=evidence_id,
                source_record_id=source_record_id,
                validation_run_id=validation_run_id,
                url="https://example.test/services",
                page_title="Services",
                evidence_snippet="Glass balustrades in New Zealand.",
                snapshot_body="Glass balustrades in New Zealand.",
                fetched_at=now,
                content_sha256="a" * 64,
                service_facts={"services": ["balustrades"]},
                region_facts={"regions": ["new_zealand"]},
            )
        )
        repository.record_failure(
            FetchFailure(
                id=uuid4(),
                source_record_id=source_record_id,
                validation_run_id=validation_run_id,
                attempted_url="https://example.test/contact",
                failure_type="blocked",
                attempt_number=1,
                response_status=403,
                detail="HTTP 403.",
                occurred_at=now,
            )
        )

        self.assertEqual(len(connection.statements), 4)
        evidence_query, evidence_parameters = connection.statements[0]
        association_query, association_parameters = connection.statements[1]
        snapshot_query, snapshot_parameters = connection.statements[2]
        failure_query, failure_parameters = connection.statements[3]
        self.assertIn("INSERT INTO page_evidence", evidence_query)
        self.assertIn("source_type", evidence_query)
        self.assertEqual(evidence_parameters[3], "https://example.test/services")
        self.assertEqual(evidence_parameters[10], "official_site")
        self.assertIn("page_evidence_source_records", association_query)
        self.assertEqual(association_parameters[1], source_record_id)
        self.assertIn("INSERT INTO raw_page_snapshots", snapshot_query)
        self.assertEqual(snapshot_parameters[2], "Glass balustrades in New Zealand.")
        self.assertIn("INSERT INTO fetch_failures", failure_query)
        self.assertEqual(failure_parameters[3], "https://example.test/contact")
        self.assertEqual(failure_parameters[4], "blocked")
        self.assertEqual(failure_parameters[6], 403)

    def test_loads_only_open_source_records_without_any_prior_fetch_outcome(self) -> None:
        from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository

        source_record_id = uuid4()
        validation_run_id = uuid4()
        connection = RecordingConnection(
            rows=[(source_record_id, validation_run_id, {"Website": "https://example.test/"})]
        )

        records = PostgresEvidenceRepository(connection, json_wrapper=lambda value: value).load_unfetched_source_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, source_record_id)
        self.assertEqual(records[0].validation_run_id, validation_run_id)
        self.assertEqual(records[0].original_values, {"Website": "https://example.test/"})
        self.assertIn("validation_runs", connection.statements[0][0])
        self.assertIn("page_evidence_source_records", connection.statements[0][0])
        self.assertIn("fetch_failures", connection.statements[0][0])

    def test_loads_only_selected_records_that_have_no_current_run_fetch_outcome_for_resume(self) -> None:
        from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository

        source_record_id = uuid4()
        validation_run_id = uuid4()
        connection = RecordingConnection(rows=[(source_record_id, validation_run_id, {"Website": "https://example.test/"})])

        records = PostgresEvidenceRepository(connection, json_wrapper=lambda value: value).load_unfetched_selected_source_records(
            validation_run_id, (source_record_id,)
        )

        self.assertEqual([record.id for record in records], [source_record_id])
        query, parameters = connection.statements[0]
        self.assertIn("source.id = ANY(%s)", query)
        self.assertEqual(parameters, (validation_run_id, [source_record_id]))

    def test_reuses_existing_page_evidence_for_a_second_source_record_with_the_same_page(self) -> None:
        from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository
        from royal_glass_validator.website_fetch import PageEvidence

        first_evidence_id = uuid4()
        validation_run_id = uuid4()
        second_source_record_id = uuid4()
        connection = RecordingConnection(fetchone_rows=[(first_evidence_id,), None, (first_evidence_id,)])
        repository = PostgresEvidenceRepository(connection, json_wrapper=lambda value: value)
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        first = PageEvidence(
            id=first_evidence_id,
            source_record_id=uuid4(),
            validation_run_id=validation_run_id,
            url="https://example.test/services",
            page_title="Services",
            evidence_snippet="Glass balustrades in New Zealand.",
            snapshot_body="Glass balustrades in New Zealand.",
            fetched_at=now,
            content_sha256="a" * 64,
            service_facts={"services": ["balustrades"]},
            region_facts={"regions": ["new_zealand"]},
        )

        repository.record_evidence(first)
        repository.record_evidence(
            PageEvidence(
                id=uuid4(),
                source_record_id=second_source_record_id,
                validation_run_id=validation_run_id,
                url=first.url,
                page_title=first.page_title,
                evidence_snippet=first.evidence_snippet,
                snapshot_body=first.snapshot_body,
                fetched_at=now,
                content_sha256=first.content_sha256,
                service_facts=first.service_facts,
                region_facts=first.region_facts,
            )
        )

        self.assertEqual(sum("INSERT INTO page_evidence (" in query for query, _ in connection.statements), 2)
        association_parameters = [parameters for query, parameters in connection.statements if "page_evidence_source_records" in query]
        self.assertEqual([parameters[1] for parameters in association_parameters], [first.source_record_id, second_source_record_id])
        self.assertEqual(sum("raw_page_snapshots" in query for query, _ in connection.statements), 1)

    def test_commits_each_retained_fetch_failure_in_its_own_transaction(self) -> None:
        from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository
        from royal_glass_validator.website_fetch import FetchFailure

        connection = RecordingConnection()
        PostgresEvidenceRepository(connection, json_wrapper=lambda value: value).record_failure(
            FetchFailure(
                id=uuid4(), source_record_id=uuid4(), validation_run_id=uuid4(), attempted_url="https://timeout.example/",
                failure_type="timeout", attempt_number=1, response_status=None, detail="Request timed out.",
                occurred_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(connection.transaction_entries, 1)


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
    def __init__(self, connection: "RecordingConnection") -> None:
        self._connection = connection

    def __enter__(self) -> None:
        self._connection.transaction_entries += 1

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


class RecordingConnection:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        fetchone_rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.rows = rows or []
        self.fetchone_rows = fetchone_rows or []
        self.transaction_entries = 0

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)
