from __future__ import annotations

import unittest
from uuid import uuid4


class PostgresClassificationRepositoryTests(unittest.TestCase):
    def test_persists_an_auto_approved_decision_and_its_high_certainty_identity_link_in_one_transaction(self) -> None:
        from royal_glass_validator.classification import ClassificationResult, IdentityLink
        from royal_glass_validator.postgres_classification import PostgresClassificationRepository

        source_record_id = uuid4()
        validation_run_id = uuid4()
        entity_id = uuid4()
        connection = RecordingConnection()

        PostgresClassificationRepository(connection).record_decision(
            source_record_id=source_record_id,
            validation_run_id=validation_run_id,
            result=ClassificationResult(
                proposed_classification="direct",
                proposed_outcome="direct",
                confidence_band="high",
                rationale="Official evidence confirms Tier 1 service.",
                tags=("pool-fencing",),
                auto_approved=True,
                requires_human_review=False,
            ),
            rule_version="2026-08-24.1",
            identity_link=IdentityLink(
                competitor_entity_id=entity_id,
                link_method="normalized_domain",
                rationale="One compatible observed official domain match.",
            ),
        )

        self.assertEqual(connection.transaction_entries, 1)
        self.assertEqual(len(connection.statements), 2)
        link_query, link_parameters = connection.statements[0]
        decision_query, decision_parameters = connection.statements[1]
        self.assertIn("INSERT INTO entity_links", link_query)
        self.assertEqual(link_parameters[1], entity_id)
        self.assertEqual(link_parameters[2], source_record_id)
        self.assertIn("INSERT INTO classification_decisions", decision_query)
        self.assertEqual(decision_parameters[1], source_record_id)
        self.assertEqual(decision_parameters[2], entity_id)
        self.assertEqual(decision_parameters[5], "direct")
        self.assertTrue(decision_parameters[12])

    def test_elevates_a_linked_entity_to_auckland_monitoring_priority_without_downgrading_it(self) -> None:
        from royal_glass_validator.classification import ClassificationResult, IdentityLink
        from royal_glass_validator.postgres_classification import PostgresClassificationRepository

        connection = RecordingConnection()
        entity_id = uuid4()
        PostgresClassificationRepository(connection).record_decision(
            source_record_id=uuid4(),
            validation_run_id=uuid4(),
            result=ClassificationResult(
                proposed_classification="adjacent",
                proposed_outcome="adjacent",
                confidence_band="high",
                rationale="Official Auckland evidence.",
                tags=(),
                auto_approved=True,
                requires_human_review=False,
                market_priority="auckland_high",
            ),
            rule_version="2026-08-24.1",
            identity_link=IdentityLink(entity_id, "normalized_domain", "Compatible domain and name."),
        )

        priority_query, priority_parameters = connection.statements[1]
        self.assertIn("UPDATE competitor_entities", priority_query)
        self.assertEqual(priority_parameters, (entity_id,))
        self.assertIn("market_priority = 'auckland_high'", priority_query)

    def test_loads_unclassified_open_records_with_all_retained_evidence_and_failures(self) -> None:
        from royal_glass_validator.postgres_classification import PostgresClassificationRepository

        source_record_id = uuid4()
        validation_run_id = uuid4()
        connection = RecordingConnection(
            rows=[
                (
                    source_record_id,
                    validation_run_id,
                    {"Canonical Name": "Clear View Glass"},
                    "https://clearview.example/services",
                    "official_site",
                    "Glass balustrades in Auckland.",
                    {"services": ["balustrades"]},
                    {"regions": ["auckland"]},
                    True,
                )
            ]
        )

        records = PostgresClassificationRepository(connection).load_unclassified_source_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, source_record_id)
        self.assertTrue(records[0].has_fetch_failure)
        self.assertEqual(records[0].evidence[0].service_facts["services"], ["balustrades"])
        self.assertIn("page_evidence_source_records", connection.statements[0][0])
        self.assertIn("classification_decisions", connection.statements[0][0])

    def test_loads_only_selected_comparison_records_for_one_manual_run(self) -> None:
        from royal_glass_validator.postgres_classification import PostgresClassificationRepository

        source_record_id = uuid4()
        validation_run_id = uuid4()
        connection = RecordingConnection(rows=[(
            source_record_id, validation_run_id, {"Canonical Name": "Clear View Glass"},
            "https://clearview.example/services", "official_site", "Glass balustrades in Auckland.",
            {"services": ["balustrades"]}, {"regions": ["auckland"]}, False,
        )])

        records = PostgresClassificationRepository(connection).load_records_for_classification(
            validation_run_id, (source_record_id,)
        )

        self.assertEqual([record.id for record in records], [source_record_id])
        query, parameters = connection.statements[0]
        self.assertIn("source.validation_run_id = %s", query)
        self.assertIn("source.id = ANY(%s)", query)
        self.assertEqual(parameters, (validation_run_id, [source_record_id]))


class RecordingTransaction:
    def __init__(self, connection: "RecordingConnection") -> None:
        self._connection = connection

    def __enter__(self) -> None:
        self._connection.transaction_entries += 1

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None


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


class RecordingConnection:
    def __init__(self, *, rows: list[tuple[object, ...]] | None = None) -> None:
        self.transaction_entries = 0
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.rows = rows or []

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)
