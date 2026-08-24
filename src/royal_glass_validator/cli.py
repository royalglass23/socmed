"""Command-line boundary for the Phase 4 schema and rules foundation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from royal_glass_validator.config import (
    ConfigurationError,
    load_development_database_target,
    load_ruleset,
    load_settings,
    validate_development_database_target,
)
from royal_glass_validator.migrations import MigrationError, apply_migrations, discover_migrations
from royal_glass_validator.workbook_import import ImportValidationError, import_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIRECTORY = PROJECT_ROOT / "migrations"
INPUT_DIRECTORY = PROJECT_ROOT / "data" / "input"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="royal-glass-validator")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("rules", help="validate and display the active tracked ruleset")
    subcommands.add_parser("migrations", help="list checksum-protected local migrations")
    migrate_parser = subcommands.add_parser("migrate", help="apply pending migrations using the approved development DATABASE_URL")
    migrate_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    import_parser = subcommands.add_parser("import", help="import the single authoritative Needs Validation workbook")
    import_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        settings = load_settings(PROJECT_ROOT)
        if args.command == "rules":
            ruleset = load_ruleset(settings.ruleset_path)
            print(f"Ruleset {ruleset.version} is valid: {settings.ruleset_path.relative_to(PROJECT_ROOT)}")
            return 0
        migrations = discover_migrations(MIGRATIONS_DIRECTORY)
        if args.command == "migrations":
            for migration in migrations:
                print(f"{migration.name}  {migration.checksum}")
            return 0
        if args.command == "import":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            workbook_path = _discover_authoritative_workbook(INPUT_DIRECTORY)
            ruleset = load_ruleset(settings.ruleset_path)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before importing a workbook.") from error
            try:
                from royal_glass_validator.postgres_import import PostgresImportRepository

                with psycopg.connect(settings.database_url) as connection:
                    summary = import_workbook(workbook_path, PostgresImportRepository(connection), rule_version=ruleset.version)
            except ImportValidationError:
                raise
            except Exception as error:
                raise MigrationError("Could not import the workbook; inspect the local database client securely.") from error
            print(f"Imported {summary.imported_record_count} source record(s) from {summary.input_workbook_name}.")
            return 0
        development_target = load_development_database_target(PROJECT_ROOT)
        validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
        try:
            import psycopg
        except ImportError as error:
            raise ConfigurationError("Install the project dependencies before applying migrations.") from error
        try:
            with psycopg.connect(settings.database_url) as connection:
                applied = apply_migrations(connection, migrations)
        except Exception as error:
            raise MigrationError("Could not apply migrations; inspect the local database client securely.") from error
        print(f"Applied {len(applied)} schema migration(s).")
        return 0
    except (ConfigurationError, ImportValidationError, MigrationError) as error:
        print(f"Configuration error: {error}")
        return 2


def _discover_authoritative_workbook(input_directory: Path) -> Path:
    workbooks = sorted(path for path in input_directory.glob("*.xlsx") if path.is_file())
    if len(workbooks) != 1:
        raise ImportValidationError("data/input must contain exactly one authoritative .xlsx workbook.")
    return workbooks[0]
