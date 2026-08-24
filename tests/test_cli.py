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

