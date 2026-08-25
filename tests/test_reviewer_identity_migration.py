from __future__ import annotations

from pathlib import Path
import unittest


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "003_reviewer_identity_resolution.sql"


class ReviewerIdentityMigrationTests(unittest.TestCase):
    def test_preserves_existing_overrides_and_requires_a_reviewer_entity_link_for_each_override(self) -> None:
        schema = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("ADD COLUMN source_record_id uuid", schema)
        self.assertIn("UPDATE human_overrides", schema)
        self.assertIn("DROP CONSTRAINT human_overrides_classification_decision_id_competitor_enti_fkey", schema)
        self.assertIn("FOREIGN KEY (source_record_id) REFERENCES source_records(id)", schema)
        self.assertIn("validator_require_override_entity_link", schema)
        self.assertIn("entity_links", schema)
        self.assertIn("NEW.competitor_entity_id", schema)
        self.assertIn("decision_source_record_id IS DISTINCT FROM NEW.source_record_id", schema)

    def test_rollback_only_neon_probe_exercises_the_new_override_guards(self) -> None:
        probe = (Path(__file__).resolve().parents[1] / "tests" / "integration_neon_schema_probe.py").read_text(encoding="utf-8")

        self.assertIn("INSERT INTO human_overrides", probe)
        self.assertIn("INSERT INTO entity_links", probe)
        self.assertIn("INSERT INTO page_evidence_source_records", probe)
        self.assertIn("alternate_source_record_id", probe)
