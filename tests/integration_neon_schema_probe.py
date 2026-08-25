"""Rollback-only contract probe for the explicitly approved development Neon schema."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg

from royal_glass_validator.config import (
    load_development_database_target,
    load_settings,
    validate_development_database_target,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def expect_rejection(cursor: psycopg.Cursor[object], statement: str, parameters: tuple[object, ...]) -> None:
    cursor.execute("SAVEPOINT contract_probe")
    try:
        cursor.execute(statement, parameters)
    except psycopg.Error:
        cursor.execute("ROLLBACK TO SAVEPOINT contract_probe")
    else:
        cursor.execute("ROLLBACK TO SAVEPOINT contract_probe")
        raise AssertionError("Expected the development schema to reject the invalid state transition.")


def main() -> None:
    settings = load_settings(PROJECT_ROOT)
    target = load_development_database_target(PROJECT_ROOT)
    validate_development_database_target(settings, target, confirmed=True)
    if settings.database_environment != "development" or not settings.database_url:
        raise RuntimeError("This rollback-only probe may run only against the configured development database.")

    failed_run_id = uuid4()
    audited_run_id = uuid4()
    source_record_id = uuid4()
    alternate_source_record_id = uuid4()
    decision_id = uuid4()
    evidence_id = uuid4()
    entity_id = uuid4()

    with psycopg.connect(settings.database_url) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO validation_runs (id, input_workbook_name, input_workbook_sha256, input_provenance, rule_version)
                    VALUES (%s, 'contract-probe.xlsx', %s, '{}'::jsonb, 'contract-probe')
                    """,
                    (failed_run_id, "a" * 64),
                )
                cursor.execute(
                    "UPDATE validation_runs SET outcome = 'failed', completed_at = now() WHERE id = %s",
                    (failed_run_id,),
                )
                expect_rejection(
                    cursor,
                    "UPDATE validation_runs SET outcome = 'completed' WHERE id = %s",
                    (failed_run_id,),
                )

                cursor.execute(
                    """
                    INSERT INTO validation_runs (id, input_workbook_name, input_workbook_sha256, input_provenance, rule_version)
                    VALUES (%s, 'contract-probe.xlsx', %s, '{}'::jsonb, 'contract-probe')
                    """,
                    (audited_run_id, "b" * 64),
                )
                cursor.execute(
                    """
                    INSERT INTO source_records (
                        id, validation_run_id, source_system, source_locator, input_row_number, original_values, original_value_hash
                    ) VALUES (%s, %s, 'contract-probe', 'row-1', 1, '{}'::jsonb, %s)
                    """,
                    (source_record_id, audited_run_id, "c" * 64),
                )
                expect_rejection(
                    cursor,
                    "UPDATE validation_runs SET outcome = 'completed', completed_at = now() WHERE id = %s",
                    (audited_run_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO classification_decisions (
                        id, source_record_id, validation_run_id, proposed_classification, proposed_outcome,
                        confidence_band, rationale, rule_version, requires_human_review
                    ) VALUES (%s, %s, %s, NULL, 'review_required', 'low', 'contract probe', 'contract-probe', true)
                    """,
                    (decision_id, source_record_id, audited_run_id),
                )
                cursor.execute(
                    """
                    INSERT INTO page_evidence (
                        id, source_record_id, validation_run_id, url, evidence_snippet, fetched_at,
                        content_sha256, source_type
                    ) VALUES (%s, %s, %s, 'https://example.test/', 'contract probe', now(), %s, 'official_site')
                    """,
                    (evidence_id, source_record_id, audited_run_id, "d" * 64),
                )
                cursor.execute(
                    """
                    INSERT INTO page_evidence_source_records (page_evidence_id, source_record_id, validation_run_id)
                    VALUES (%s, %s, %s)
                    """,
                    (evidence_id, source_record_id, audited_run_id),
                )
                cursor.execute(
                    """
                    INSERT INTO competitor_entities (id, legal_name, display_name, normalized_name)
                    VALUES (%s, 'Contract Probe Glass Limited', 'Contract Probe Glass', 'contractprobeglass')
                    """,
                    (entity_id,),
                )
                expect_rejection(
                    cursor,
                    """
                    INSERT INTO human_overrides (
                        id, competitor_entity_id, classification_decision_id, source_record_id,
                        classification, rationale, reviewer_identity
                    ) VALUES (%s, %s, %s, %s, 'adjacent', 'contract probe', 'contract probe reviewer')
                    """,
                    (uuid4(), entity_id, decision_id, source_record_id),
                )
                cursor.execute(
                    """
                    INSERT INTO entity_links (
                        id, competitor_entity_id, source_record_id, link_method, certainty, linked_by, rationale
                    ) VALUES (%s, %s, %s, 'reviewer_resolved', 'reviewer_confirmed', 'reviewer', 'contract probe')
                    """,
                    (uuid4(), entity_id, source_record_id),
                )
                expect_rejection(
                    cursor,
                    """
                    INSERT INTO human_overrides (
                        id, competitor_entity_id, classification_decision_id, source_record_id,
                        classification, rationale, reviewer_identity
                    ) VALUES (%s, %s, %s, %s, 'adjacent', 'contract probe', 'contract probe reviewer')
                    """,
                    (uuid4(), entity_id, decision_id, alternate_source_record_id),
                )
                cursor.execute(
                    """
                    INSERT INTO human_overrides (
                        id, competitor_entity_id, classification_decision_id, source_record_id,
                        classification, rationale, reviewer_identity
                    ) VALUES (%s, %s, %s, %s, 'adjacent', 'contract probe', 'contract probe reviewer')
                    """,
                    (uuid4(), entity_id, decision_id, source_record_id),
                )
                cursor.execute(
                    "UPDATE validation_runs SET outcome = 'completed', completed_at = now() WHERE id = %s",
                    (audited_run_id,),
                )
                expect_rejection(
                    cursor,
                    """
                    INSERT INTO source_records (
                        id, validation_run_id, source_system, source_locator, input_row_number, original_values, original_value_hash
                    ) VALUES (%s, %s, 'contract-probe', 'row-2', 2, '{}'::jsonb, %s)
                    """,
                    (uuid4(), audited_run_id, "e" * 64),
                )
        finally:
            connection.rollback()

    print("Development Neon schema contract probe passed; all probe changes were rolled back.")


if __name__ == "__main__":
    main()
