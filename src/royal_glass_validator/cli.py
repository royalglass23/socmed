"""Command-line boundary for the Phase 4 schema and rules foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

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
    fetch_parser = subcommands.add_parser("fetch", help="capture bounded official-site evidence for unfetched source records")
    fetch_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    run_parser = subcommands.add_parser(
        "run", help="manually compare the authoritative workbook and emit a compact structured summary"
    )
    run_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    resume_parser = subcommands.add_parser(
        "resume", help="continue one interrupted manual comparison without importing another workbook"
    )
    resume_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    resume_parser.add_argument("--run-id", type=UUID, required=True, help="still-running validation run UUID to continue")
    resume_parser.add_argument(
        "--max-records", type=_positive_int, help="durably process at most this many pending source records before returning"
    )
    classify_parser = subcommands.add_parser(
        "classify", help="classify fetched source records and link only high-certainty existing identities"
    )
    classify_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    export_parser = subcommands.add_parser("export", help="create a dated, one-way reviewer Excel export")
    export_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    export_parser.add_argument(
        "--output-directory",
        type=Path,
        default=PROJECT_ROOT / "exports",
        help="local directory for the dated reviewer workbook (default: exports)",
    )
    override_parser = subcommands.add_parser("override", help="append a protected, attributed reviewer override")
    override_parser.add_argument(
        "--confirm-development-neon",
        action="store_true",
        help="confirm that the configured target is the explicitly approved development Neon database",
    )
    override_parser.add_argument("--decision-id", type=UUID, required=True, help="classification decision UUID to override")
    override_parser.add_argument(
        "--classification",
        choices=("direct", "adjacent", "supplier_ecosystem", "irrelevant"),
        required=True,
        help="reviewer classification that remains authoritative until explicitly superseded",
    )
    override_parser.add_argument("--rationale", required=True, help="reviewer's evidence-backed reason for this decision")
    override_parser.add_argument("--reviewer", required=True, help="attributable reviewer identity")
    override_parser.add_argument("--supersedes-override-id", type=UUID, help="active override UUID being explicitly superseded")
    resolve_parser = subcommands.add_parser("resolve-identity", help="explicitly link or create an entity before a protected override")
    resolve_parser.add_argument("--confirm-development-neon", action="store_true", help="confirm the approved development Neon database")
    resolve_parser.add_argument("--decision-id", type=UUID, required=True, help="unlinked classification decision UUID")
    resolve_parser.add_argument("--entity-id", type=UUID, help="existing Competitor Entity UUID to link")
    resolve_parser.add_argument("--legal-name", help="legal name when creating a new Competitor Entity")
    resolve_parser.add_argument("--display-name", help="display name when creating a new Competitor Entity")
    resolve_parser.add_argument("--primary-domain", help="optional official domain for a new Competitor Entity")
    resolve_parser.add_argument("--verified-phone", help="optional verified phone for a new Competitor Entity")
    resolve_parser.add_argument("--rationale", required=True, help="reviewer's evidence-backed identity rationale")
    resolve_parser.add_argument("--reviewer", required=True, help="attributable reviewer identity")
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
        if args.command == "run":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            workbook_path = _discover_authoritative_workbook(INPUT_DIRECTORY)
            ruleset = load_ruleset(settings.ruleset_path)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before running a manual comparison.") from error
            try:
                from royal_glass_validator.manual_run import run_manual_comparison
                from royal_glass_validator.postgres_manual_run import PostgresManualRunRepository
                from royal_glass_validator.website_fetch import WebsiteEvidenceFetcher

                with _open_durable_write_connection(psycopg, settings.database_url) as connection:
                    repository = PostgresManualRunRepository(connection)
                    summary = run_manual_comparison(
                        workbook_path,
                        repository,
                        WebsiteEvidenceFetcher(repository),
                        rule_version=ruleset.version,
                    )
            except Exception as error:
                raise MigrationError("Could not complete the manual comparison run; inspect the local database client securely.") from error
            print(_format_manual_run_summary(summary))
            return 0
        if args.command == "resume":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            ruleset = load_ruleset(settings.ruleset_path)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before resuming a manual comparison.") from error
            try:
                from royal_glass_validator.manual_run import resume_manual_comparison
                from royal_glass_validator.postgres_manual_run import PostgresManualRunRepository
                from royal_glass_validator.website_fetch import WebsiteEvidenceFetcher

                with _open_durable_write_connection(psycopg, settings.database_url) as connection:
                    repository = PostgresManualRunRepository(connection)
                    summary = resume_manual_comparison(
                        args.run_id,
                        repository,
                        WebsiteEvidenceFetcher(repository),
                        rule_version=ruleset.version,
                        max_records=args.max_records,
                    )
            except Exception as error:
                raise MigrationError("Could not resume the manual comparison run; inspect the local database client securely.") from error
            print(_format_manual_run_summary(summary))
            return 0
        if args.command == "fetch":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before fetching website evidence.") from error
            try:
                from royal_glass_validator.postgres_evidence import PostgresEvidenceRepository
                from royal_glass_validator.website_fetch import WebsiteEvidenceFetcher

                with _open_durable_write_connection(psycopg, settings.database_url) as connection:
                    repository = PostgresEvidenceRepository(connection)
                    summaries = WebsiteEvidenceFetcher(repository).fetch_records(repository.load_unfetched_source_records())
            except Exception as error:
                raise MigrationError("Could not capture website evidence; inspect the local database client securely.") from error
            evidence_count = sum(summary.evidence_count for summary in summaries)
            failure_count = sum(summary.failure_count for summary in summaries)
            print(f"Captured {evidence_count} evidence page(s) and {failure_count} fetch failure(s) for {len(summaries)} source record(s).")
            return 0
        if args.command == "classify":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            ruleset = load_ruleset(settings.ruleset_path)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before classifying source records.") from error
            try:
                from royal_glass_validator.classification import classify_source_record, find_high_certainty_identity_match
                from royal_glass_validator.postgres_classification import PostgresClassificationRepository

                with _open_durable_write_connection(psycopg, settings.database_url) as connection:
                    repository = PostgresClassificationRepository(connection)
                    identities = repository.load_existing_identities()
                    records = repository.load_unclassified_source_records()
                    results = []
                    for record in records:
                        result = classify_source_record(record, rule_version=ruleset.version)
                        identity_link = find_high_certainty_identity_match(record, identities)
                        repository.record_decision(
                            source_record_id=record.id,
                            validation_run_id=record.validation_run_id,
                            result=result,
                            rule_version=ruleset.version,
                            identity_link=identity_link,
                        )
                        results.append((result, identity_link))
            except Exception as error:
                raise MigrationError("Could not classify source records; inspect the local database client securely.") from error
            auto_approved_count = sum(result.auto_approved for result, _ in results)
            linked_count = sum(identity_link is not None for _, identity_link in results)
            print(
                f"Classified {len(results)} source record(s): {auto_approved_count} auto-approved, "
                f"{len(results) - auto_approved_count} requiring review, {linked_count} high-certainty identity link(s)."
            )
            return 0
        if args.command == "export":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before exporting a reviewer workbook.") from error
            try:
                from royal_glass_validator.postgres_review import PostgresReviewerRepository
                from royal_glass_validator.reviewer_export import export_reviewer_workbook

                with psycopg.connect(settings.database_url) as connection:
                    rows = PostgresReviewerRepository(connection).load_reviewer_rows()
                output_path = export_reviewer_workbook(rows, args.output_directory)
            except Exception as error:
                raise MigrationError("Could not export the reviewer workbook; inspect the local database client securely.") from error
            print(f"Exported {len(rows)} review record(s) to {output_path}.")
            return 0
        if args.command == "override":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before recording a reviewer override.") from error
            try:
                from royal_glass_validator.postgres_review import PostgresReviewerRepository

                with psycopg.connect(settings.database_url) as connection:
                    PostgresReviewerRepository(connection).record_override(
                        classification_decision_id=args.decision_id,
                        classification=args.classification,
                        rationale=args.rationale,
                        reviewer_identity=args.reviewer,
                        supersedes_override_id=args.supersedes_override_id,
                    )
            except Exception as error:
                raise MigrationError("Could not record the protected reviewer override; inspect the local database client securely.") from error
            print(f"Recorded protected override for classification decision {args.decision_id}.")
            return 0
        if args.command == "resolve-identity":
            development_target = load_development_database_target(PROJECT_ROOT)
            validate_development_database_target(settings, development_target, confirmed=args.confirm_development_neon)
            try:
                import psycopg
            except ImportError as error:
                raise ConfigurationError("Install the project dependencies before resolving a reviewer identity.") from error
            try:
                from royal_glass_validator.postgres_review import PostgresReviewerRepository

                with psycopg.connect(settings.database_url) as connection:
                    entity_id = PostgresReviewerRepository(connection).resolve_identity(
                        classification_decision_id=args.decision_id,
                        existing_entity_id=args.entity_id,
                        legal_name=args.legal_name,
                        display_name=args.display_name,
                        primary_domain=args.primary_domain,
                        verified_phone=args.verified_phone,
                        rationale=args.rationale,
                        reviewer_identity=args.reviewer,
                    )
            except Exception as error:
                raise MigrationError("Could not resolve the reviewer identity; inspect the local database client securely.") from error
            print(f"Resolved classification decision {args.decision_id} to Competitor Entity {entity_id}.")
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


def _format_manual_run_summary(summary: object) -> str:
    """Serialize the manual-run result for future callers without adding an integration."""
    return json.dumps(summary.as_dict(), sort_keys=True, separators=(",", ":"))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _open_durable_write_connection(psycopg_module: Any, database_url: str) -> Any:
    """Ensure every explicit repository transaction commits before the next network request."""
    return psycopg_module.connect(database_url, autocommit=True)
