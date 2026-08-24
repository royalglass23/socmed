from __future__ import annotations

from pathlib import Path
import unittest


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "001_phase4_foundation.sql"


class PhaseFourSchemaContractTests(unittest.TestCase):
    def test_review_required_is_an_outcome_and_a_decision_has_a_source_record(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("proposed_outcome text NOT NULL", schema)
        self.assertIn("source_record_id uuid NOT NULL", schema)
        self.assertIn("CHECK (proposed_outcome IN ('direct', 'adjacent', 'supplier_ecosystem', 'irrelevant', 'review_required'))", schema)

    def test_override_decision_cannot_belong_to_a_different_entity(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("FOREIGN KEY (classification_decision_id, competitor_entity_id)", schema)
        self.assertIn("REFERENCES classification_decisions(id, competitor_entity_id)", schema)

    def test_completion_requires_a_decision_and_captured_evidence_or_failure_for_every_source_record(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("validator_require_completed_run_audit_history", schema)
        self.assertIn("FROM source_records AS source", schema)
        self.assertIn("FROM classification_decisions AS decision", schema)

    def test_run_must_start_open_and_audit_rows_cannot_be_added_after_completion(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("validator_require_new_run_to_start_running", schema)
        self.assertIn("validator_require_open_run_for_source_record", schema)
        self.assertIn("validator_require_open_run_for_audit_insert", schema)

    def test_failed_or_completed_runs_cannot_transition_back_to_completed_processing(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("validator_enforce_validation_run_lifecycle", schema)
        self.assertIn("terminal validation run cannot transition", schema)
