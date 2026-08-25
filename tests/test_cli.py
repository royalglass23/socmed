from __future__ import annotations

import unittest

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
