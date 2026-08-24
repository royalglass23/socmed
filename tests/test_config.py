from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from royal_glass_validator.config import (
    ConfigurationError,
    DevelopmentDatabaseTarget,
    ValidatorSettings,
    load_settings,
    load_ruleset,
    validate_development_database_target,
)


class RuleSetContractTests(unittest.TestCase):
    def test_load_settings_selects_the_development_connection_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = load_settings(
                Path(temporary_directory),
                {
                    "VALIDATOR_DATABASE_ENVIRONMENT": "development",
                    "DATABASE_URL_DEV": "postgresql://development.example/socmed_dev",
                    "DATABASE_URL_PROD": "postgresql://production.example/socmed_prod",
                },
            )

        self.assertEqual(settings.database_url, "postgresql://development.example/socmed_dev")

    def test_load_settings_selects_the_production_connection_key_only_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = load_settings(
                Path(temporary_directory),
                {
                    "VALIDATOR_DATABASE_ENVIRONMENT": "production",
                    "DATABASE_URL_DEV": "postgresql://development.example/socmed_dev",
                    "DATABASE_URL_PROD": "postgresql://production.example/socmed_prod",
                },
            )

        self.assertEqual(settings.database_url, "postgresql://production.example/socmed_prod")

    def test_rejects_a_database_target_until_a_code_reviewed_development_identity_exists(self) -> None:
        settings = ValidatorSettings(
            database_url="postgresql://user:password@development.example/neondb",
            ruleset_path=Path("config/rules/v1.toml"),
            database_environment="development",
        )
        target = DevelopmentDatabaseTarget(
            target_id="UNCONFIGURED",
            host="development.example",
            database_name="neondb",
        )

        with self.assertRaisesRegex(ConfigurationError, "code-reviewed development target"):
            validate_development_database_target(settings, target, confirmed=True)

    def test_rejects_a_ruleset_for_another_brand(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ruleset_path = Path(temporary_directory) / "wrong-brand.toml"
            ruleset_path.write_text(
                """
version = "test"
brand = "Blue Haven"
country = "NZ"
[outcomes]
classifications = ["direct", "adjacent", "supplier_ecosystem", "irrelevant"]
confidence_bands = ["high"]
tags = ["regional"]
review_outcome = "review_required"
[safeguards]
fetch_failure_outcome = "review_required"
irrelevant_requires_human_review = true
protected_override_is_authoritative = true
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "Royal Glass"):
                load_ruleset(ruleset_path)

    def test_rejects_a_ruleset_for_another_country(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ruleset_path = Path(temporary_directory) / "wrong-country.toml"
            ruleset_path.write_text(
                """
version = "test"
brand = "Royal Glass"
country = "AU"
[outcomes]
classifications = ["direct", "adjacent", "supplier_ecosystem", "irrelevant"]
confidence_bands = ["high"]
tags = ["regional"]
review_outcome = "review_required"
[safeguards]
fetch_failure_outcome = "review_required"
irrelevant_requires_human_review = true
protected_override_is_authoritative = true
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "NZ"):
                load_ruleset(ruleset_path)

    def test_rejects_a_ruleset_that_allows_fetch_failures_to_be_irrelevant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ruleset_path = Path(temporary_directory) / "unsafe.toml"
            ruleset_path.write_text(
                """
version = "test"
brand = "Royal Glass"
country = "NZ"
[outcomes]
classifications = ["direct", "adjacent", "supplier_ecosystem", "irrelevant"]
confidence_bands = ["low"]
tags = ["regional"]
review_outcome = "review_required"
[safeguards]
fetch_failure_outcome = "irrelevant"
irrelevant_requires_human_review = true
protected_override_is_authoritative = true
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "Fetch failures"):
                load_ruleset(ruleset_path)

    def test_rejects_a_ruleset_that_weakens_protected_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            ruleset_path = Path(temporary_directory) / "unsafe.toml"
            ruleset_path.write_text(
                """
version = "test"
brand = "Royal Glass"
country = "NZ"
[outcomes]
classifications = ["direct", "adjacent", "supplier_ecosystem", "irrelevant"]
confidence_bands = ["low"]
tags = ["regional"]
review_outcome = "review_required"
[safeguards]
fetch_failure_outcome = "review_required"
irrelevant_requires_human_review = true
protected_override_is_authoritative = false
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "human overrides"):
                load_ruleset(ruleset_path)
