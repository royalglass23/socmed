from __future__ import annotations

import unittest
from uuid import uuid4


class PostgresReviewerRepositoryTests(unittest.TestCase):
    def test_resolves_an_unlinked_decision_to_an_existing_entity_before_override(self) -> None:
        from royal_glass_validator.postgres_review import PostgresReviewerRepository

        decision_id = uuid4()
        source_record_id = uuid4()
        entity_id = uuid4()
        connection = RecordingConnection(rows=[], fetchone_rows=[(source_record_id,), None, (entity_id,)])

        resolved_entity_id = PostgresReviewerRepository(connection).resolve_identity(
            classification_decision_id=decision_id,
            existing_entity_id=entity_id,
            legal_name=None,
            display_name=None,
            primary_domain=None,
            verified_phone=None,
            rationale="Reviewer confirmed the record belongs to this business.",
            reviewer_identity="Aroha Reviewer",
        )

        self.assertEqual(resolved_entity_id, entity_id)
        self.assertEqual(connection.transaction_entries, 1)
        self.assertIn("FROM classification_decisions", connection.statements[0][0])
        self.assertIn("FROM entity_links", connection.statements[1][0])
        self.assertIn("FROM competitor_entities", connection.statements[2][0])
        link_query, link_parameters = connection.statements[3]
        self.assertIn("INSERT INTO entity_links", link_query)
        self.assertEqual(link_parameters[1:4], (entity_id, source_record_id, "reviewer_resolved"))
        self.assertEqual(link_parameters[4], "Reviewer confirmed the record belongs to this business.")

    def test_creates_an_entity_and_link_before_accepting_a_protected_override(self) -> None:
        from royal_glass_validator.postgres_review import PostgresReviewerRepository

        source_record_id = uuid4()
        connection = RecordingConnection(rows=[], fetchone_rows=[(source_record_id,), None])

        entity_id = PostgresReviewerRepository(connection).resolve_identity(
            classification_decision_id=uuid4(),
            existing_entity_id=None,
            legal_name="Clear View Glass Limited",
            display_name="Clear View Glass",
            primary_domain="clearview.example",
            verified_phone="09 123 4567",
            rationale="Reviewer confirmed this is a distinct business.",
            reviewer_identity="Aroha Reviewer",
        )

        create_query, create_parameters = connection.statements[2]
        link_query, link_parameters = connection.statements[3]
        self.assertIn("INSERT INTO competitor_entities", create_query)
        self.assertEqual(create_parameters[0], entity_id)
        self.assertEqual(create_parameters[1:4], ("Clear View Glass Limited", "Clear View Glass", "clearviewglass"))
        self.assertIn("INSERT INTO entity_links", link_query)
        self.assertEqual(link_parameters[1], entity_id)

    def test_loads_structured_evidence_and_flags_a_later_conflicting_decision_without_replacing_override(self) -> None:
        from royal_glass_validator.postgres_review import PostgresReviewerRepository

        source_record_id = uuid4()
        decision_id = uuid4()
        override_id = uuid4()
        connection = RecordingConnection(rows=[(
            source_record_id, decision_id, uuid4(), 12, {"Canonical Name": "Clear View Glass"}, "direct", "direct",
            "high", "Official evidence confirms installation.", ["pool-fencing"],
            [{"url": "https://clearview.example/services", "title": "About — Royal Glass\nServices", "snippet": "Evidence with a newline\nand delimiter — retained."}],
            ["timeout: https://clearview.example/contact (attempt 1)"], "High-certainty link: Clear View Glass (normalized_domain).",
            "adjacent", override_id, "Reviewer evidence is authoritative.", "Aroha Reviewer",
        )])

        rows = PostgresReviewerRepository(connection).load_reviewer_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].classification_decision_id, decision_id)
        self.assertTrue(rows[0].override_conflict)
        self.assertEqual(rows[0].active_override_id, override_id)
        self.assertEqual(rows[0].evidence[0].title, "About — Royal Glass\nServices")
        self.assertEqual(rows[0].evidence[0].snippet, "Evidence with a newline\nand delimiter — retained.")
        self.assertIn("jsonb_agg", connection.statements[0][0])
        self.assertNotIn("concat_ws", connection.statements[0][0])

    def test_records_a_named_override_with_rationale_and_explicit_supersession_only(self) -> None:
        from royal_glass_validator.postgres_review import PostgresReviewerRepository

        source_record_id = uuid4()
        entity_id = uuid4()
        connection = RecordingConnection(rows=[], fetchone_rows=[(source_record_id, entity_id)])
        decision_id = uuid4()
        superseded_override_id = uuid4()

        PostgresReviewerRepository(connection).record_override(
            classification_decision_id=decision_id,
            classification="adjacent",
            rationale="Official evidence confirms an adjacent service only.",
            reviewer_identity="Aroha Reviewer",
            supersedes_override_id=superseded_override_id,
        )

        self.assertEqual(connection.transaction_entries, 1)
        lookup_query, lookup_parameters = connection.statements[0]
        insert_query, insert_parameters = connection.statements[1]
        self.assertIn("FROM classification_decisions", lookup_query)
        self.assertEqual(lookup_parameters, (decision_id,))
        self.assertIn("INSERT INTO human_overrides", insert_query)
        self.assertEqual(insert_parameters[1], entity_id)
        self.assertEqual(insert_parameters[2], decision_id)
        self.assertEqual(insert_parameters[3], source_record_id)
        self.assertEqual(insert_parameters[4:7], ("adjacent", "Official evidence confirms an adjacent service only.", "Aroha Reviewer"))
        self.assertEqual(insert_parameters[7], superseded_override_id)

    def test_rejects_an_override_for_an_unlinked_automated_decision(self) -> None:
        from royal_glass_validator.postgres_review import OverrideValidationError, PostgresReviewerRepository

        connection = RecordingConnection(rows=[], fetchone_rows=[])

        with self.assertRaisesRegex(OverrideValidationError, "Resolve the source record identity"):
            PostgresReviewerRepository(connection).record_override(
                classification_decision_id=uuid4(),
                classification="direct",
                rationale="Reviewer confirmed a direct competitor.",
                reviewer_identity="Aroha Reviewer",
                supersedes_override_id=None,
            )

        self.assertEqual(len(connection.statements), 1)


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

    def fetchone(self) -> tuple[object, ...] | None:
        return self._connection.fetchone_rows.pop(0) if self._connection.fetchone_rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._connection.rows


class RecordingConnection:
    def __init__(self, *, rows: list[tuple[object, ...]], fetchone_rows: list[tuple[object, ...] | None] | None = None) -> None:
        self.rows = rows
        self.fetchone_rows = list(rows if fetchone_rows is None else fetchone_rows)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.transaction_entries = 0

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction(self)

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)
