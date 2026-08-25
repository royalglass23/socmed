from __future__ import annotations

import json
import unittest
from uuid import uuid4

from royal_glass_validator.cli import build_parser


class CommandLineTests(unittest.TestCase):
    def test_classify_command_requires_the_existing_development_neon_confirmation_gate(self) -> None:
        parser = build_parser()

        without_confirmation = parser.parse_args(["classify"])
        with_confirmation = parser.parse_args(["classify", "--confirm-development-neon"])

        self.assertEqual(without_confirmation.command, "classify")
        self.assertFalse(without_confirmation.confirm_development_neon)
        self.assertTrue(with_confirmation.confirm_development_neon)

    def test_export_and_override_commands_require_the_development_confirmation_gate(self) -> None:
        parser = build_parser()

        export = parser.parse_args(["export", "--confirm-development-neon"])
        override = parser.parse_args(
            [
                "override",
                "--confirm-development-neon",
                "--decision-id",
                "48a9e4ec-3c75-4e5d-a1e1-fba7a11c25c7",
                "--classification",
                "adjacent",
                "--rationale",
                "Evidence supports only an adjacent service.",
                "--reviewer",
                "Aroha Reviewer",
            ]
        )

        self.assertEqual(export.command, "export")
        self.assertTrue(export.confirm_development_neon)
        self.assertEqual(override.command, "override")
        self.assertEqual(override.classification, "adjacent")
        self.assertEqual(override.reviewer, "Aroha Reviewer")

    def test_identity_resolution_requires_an_explicit_existing_entity_or_new_entity_details(self) -> None:
        parser = build_parser()

        existing = parser.parse_args(
            [
                "resolve-identity", "--confirm-development-neon", "--decision-id", "48a9e4ec-3c75-4e5d-a1e1-fba7a11c25c7",
                "--entity-id", "f6319f13-7b80-48ef-b939-dc82332205fd", "--rationale", "Reviewer verified the identity.",
                "--reviewer", "Aroha Reviewer",
            ]
        )

        self.assertEqual(existing.command, "resolve-identity")
        self.assertEqual(str(existing.entity_id), "f6319f13-7b80-48ef-b939-dc82332205fd")

    def test_run_command_uses_the_development_confirmation_gate_and_emits_machine_readable_json(self) -> None:
        from royal_glass_validator.cli import _format_manual_run_summary
        from royal_glass_validator.manual_run import ManualRunSummary

        parser = build_parser()
        run = parser.parse_args(["run", "--confirm-development-neon"])
        summary = ManualRunSummary(
            uuid4(), "royal-glass.xlsx", 3, 2, 1, 0, 1, 0, 0, 0, 2, 0, 2, 1, 1
        )

        payload = json.loads(_format_manual_run_summary(summary))

        self.assertEqual(run.command, "run")
        self.assertTrue(run.confirm_development_neon)
        self.assertEqual(payload["input_workbook_name"], "royal-glass.xlsx")
        self.assertEqual(payload["outcome"], "completed")

    def test_resume_command_requires_a_specific_running_run_and_development_confirmation(self) -> None:
        parser = build_parser()

        resume = parser.parse_args([
            "resume", "--confirm-development-neon", "--run-id", "48a9e4ec-3c75-4e5d-a1e1-fba7a11c25c7",
        ])

        self.assertEqual(resume.command, "resume")
        self.assertTrue(resume.confirm_development_neon)
        self.assertEqual(str(resume.run_id), "48a9e4ec-3c75-4e5d-a1e1-fba7a11c25c7")

    def test_resume_command_accepts_a_positive_bounded_batch_size(self) -> None:
        parser = build_parser()

        resume = parser.parse_args([
            "resume", "--confirm-development-neon", "--run-id", "48a9e4ec-3c75-4e5d-a1e1-fba7a11c25c7", "--max-records", "5",
        ])

        self.assertEqual(resume.max_records, 5)

    def test_manual_comparison_writes_use_autocommit_so_each_explicit_transaction_is_durable(self) -> None:
        from royal_glass_validator.cli import _open_durable_write_connection

        fake_psycopg = RecordingPsycopg()

        connection = _open_durable_write_connection(fake_psycopg, "postgresql://development-target")

        self.assertIs(connection, fake_psycopg.connection)
        self.assertEqual(fake_psycopg.connect_calls, [("postgresql://development-target", {"autocommit": True})])


class RecordingPsycopg:
    def __init__(self) -> None:
        self.connection = object()
        self.connect_calls: list[tuple[str, dict[str, object]]] = []

    def connect(self, database_url: str, **kwargs: object) -> object:
        self.connect_calls.append((database_url, kwargs))
        return self.connection
