"""Deterministic selection rules for one manual Phase 4 comparison run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from royal_glass_validator.classification import (
    CompetitorIdentity,
    SourceRecordForClassification,
    classify_source_record,
    find_high_certainty_identity_match,
)
from royal_glass_validator.website_fetch import FetchSourceRecord, FetchSummary
from royal_glass_validator.workbook_import import ImportedRun, ImportedSourceRecord, prepare_workbook_import


@dataclass(frozen=True)
class ComparisonRecord:
    """Current immutable input compared with the latest retained record for one Entity ID."""

    entity_id: str
    original_value_hash: str
    previous_value_hash: str | None = None
    previous_classification: str | None = None
    previous_outcome: str | None = None
    had_fetch_failure: bool = False


@dataclass(frozen=True)
class ManualComparisonPlan:
    """The compact, reproducible recheck selection for a manual run."""

    selected_entity_ids: tuple[str, ...]
    new_record_count: int
    changed_record_count: int
    direct_recheck_count: int
    adjacent_recheck_count: int
    unresolved_recheck_count: int
    failed_recheck_count: int


@dataclass(frozen=True)
class ComparisonCandidate:
    """A newly imported Source Record together with the latest retained comparison facts."""

    source_record_id: UUID
    validation_run_id: UUID
    original_values: dict[str, object]
    entity_id: str
    original_value_hash: str
    previous_value_hash: str | None = None
    previous_classification: str | None = None
    previous_outcome: str | None = None
    had_fetch_failure: bool = False

    def comparison_record(self) -> ComparisonRecord:
        return ComparisonRecord(
            entity_id=self.entity_id,
            original_value_hash=self.original_value_hash,
            previous_value_hash=self.previous_value_hash,
            previous_classification=self.previous_classification,
            previous_outcome=self.previous_outcome,
            had_fetch_failure=self.had_fetch_failure,
        )


@dataclass(frozen=True)
class ManualRunSummary:
    """Compact, future-caller-safe result of one manually invoked comparison run."""

    validation_run_id: UUID
    input_workbook_name: str
    imported_record_count: int
    selected_record_count: int
    new_record_count: int
    changed_record_count: int
    direct_recheck_count: int
    adjacent_recheck_count: int
    unresolved_recheck_count: int
    failed_recheck_count: int
    evidence_page_count: int
    fetch_failure_count: int
    classified_record_count: int
    auto_approved_count: int
    review_required_count: int
    outcome: str = "completed"

    def as_dict(self) -> dict[str, int | str]:
        """Return only stable scalar facts so later callers need not parse terminal text."""
        return {
            "validation_run_id": str(self.validation_run_id),
            "input_workbook_name": self.input_workbook_name,
            "imported_record_count": self.imported_record_count,
            "selected_record_count": self.selected_record_count,
            "new_record_count": self.new_record_count,
            "changed_record_count": self.changed_record_count,
            "direct_recheck_count": self.direct_recheck_count,
            "adjacent_recheck_count": self.adjacent_recheck_count,
            "unresolved_recheck_count": self.unresolved_recheck_count,
            "failed_recheck_count": self.failed_recheck_count,
            "evidence_page_count": self.evidence_page_count,
            "fetch_failure_count": self.fetch_failure_count,
            "classified_record_count": self.classified_record_count,
            "auto_approved_count": self.auto_approved_count,
            "review_required_count": self.review_required_count,
            "outcome": self.outcome,
        }


class ManualRunRepository(Protocol):
    """The narrow persistence boundary used by the manual comparison workflow."""

    def import_records(self, run: ImportedRun, records: tuple[ImportedSourceRecord, ...]) -> None: ...

    def load_comparison_candidates(self, validation_run_id: UUID) -> tuple[ComparisonCandidate, ...]: ...

    def load_running_run_context(self, validation_run_id: UUID) -> tuple[str, int]: ...

    def load_unfetched_selected_source_records(
        self, validation_run_id: UUID, source_record_ids: tuple[UUID, ...]
    ) -> tuple[FetchSourceRecord, ...]: ...

    def load_existing_identities(self) -> tuple[CompetitorIdentity, ...]: ...

    def load_classification_records(
        self, validation_run_id: UUID, source_record_ids: tuple[UUID, ...]
    ) -> tuple[SourceRecordForClassification, ...]: ...

    def record_decision(self, **kwargs: object) -> None: ...

    def complete_run(self, validation_run_id: UUID, summary: ManualRunSummary) -> None: ...


class EvidenceFetcher(Protocol):
    def fetch_records(self, records: tuple[FetchSourceRecord, ...]) -> tuple[FetchSummary, ...]: ...


def plan_manual_comparison(records: tuple[ComparisonRecord, ...]) -> ManualComparisonPlan:
    """Select the narrow Phase 4 cohort that is due for an ordinary-HTTP recheck.

    Supplier / Ecosystem records remain stored but are intentionally not monitored by default.
    Each record receives one primary selection reason so summary counts remain compact.
    """
    selected: list[str] = []
    counts = {
        "new": 0,
        "changed": 0,
        "direct": 0,
        "adjacent": 0,
        "unresolved": 0,
        "failed": 0,
    }
    seen_entity_ids: set[str] = set()
    for record in records:
        if not record.entity_id.strip():
            raise ValueError("Comparison records require a non-empty Entity ID.")
        if record.entity_id in seen_entity_ids:
            raise ValueError(f"Comparison records contain duplicate Entity ID: {record.entity_id}")
        seen_entity_ids.add(record.entity_id)

        if record.previous_value_hash is not None and record.original_value_hash != record.previous_value_hash:
            counts["changed"] += 1
            if record.previous_classification == "supplier_ecosystem":
                continue
            selected.append(record.entity_id)
            continue
        reason = _selection_reason(record)
        if reason is None:
            continue
        selected.append(record.entity_id)
        counts[reason] += 1

    return ManualComparisonPlan(
        selected_entity_ids=tuple(selected),
        new_record_count=counts["new"],
        changed_record_count=counts["changed"],
        direct_recheck_count=counts["direct"],
        adjacent_recheck_count=counts["adjacent"],
        unresolved_recheck_count=counts["unresolved"],
        failed_recheck_count=counts["failed"],
    )


def run_manual_comparison(
    workbook_path: Path,
    repository: ManualRunRepository,
    fetcher: EvidenceFetcher,
    *,
    rule_version: str,
    import_plan: tuple[ImportedRun, tuple[ImportedSourceRecord, ...]] | None = None,
) -> ManualRunSummary:
    """Import one workbook, recheck its selected cohort, and append a compact audit summary.

    This intentionally has no scheduler or external caller integration. Protected human overrides
    are never read or changed here; later automated decisions may only appear as revalidation
    conflicts in the reviewer view.
    """
    from royal_glass_validator.gold_set import verify_gold_set

    verify_gold_set(rule_version=rule_version)
    run, imported_records = import_plan or prepare_workbook_import(workbook_path, rule_version=rule_version)
    repository.import_records(run, imported_records)
    return _execute_manual_comparison(
        run.id, run.input_workbook_name, len(imported_records), repository, fetcher, rule_version=rule_version
    )


def resume_manual_comparison(
    validation_run_id: UUID,
    repository: ManualRunRepository,
    fetcher: EvidenceFetcher,
    *,
    rule_version: str,
    max_records: int | None = None,
) -> ManualRunSummary:
    """Continue a previously imported, still-running manual comparison without duplicating provenance."""
    from royal_glass_validator.gold_set import verify_gold_set

    verify_gold_set(rule_version=rule_version)
    input_workbook_name, imported_record_count = repository.load_running_run_context(validation_run_id)
    return _execute_manual_comparison(
        validation_run_id,
        input_workbook_name,
        imported_record_count,
        repository,
        fetcher,
        rule_version=rule_version,
        max_records=max_records,
    )


def _execute_manual_comparison(
    validation_run_id: UUID,
    input_workbook_name: str,
    imported_record_count: int,
    repository: ManualRunRepository,
    fetcher: EvidenceFetcher,
    *,
    rule_version: str,
    max_records: int | None = None,
) -> ManualRunSummary:
    if max_records is not None and max_records <= 0:
        raise ValueError("max_records must be greater than zero when supplied.")
    candidates = repository.load_comparison_candidates(validation_run_id)
    plan = plan_manual_comparison(tuple(candidate.comparison_record() for candidate in candidates))
    candidates_by_entity_id = {candidate.entity_id: candidate for candidate in candidates}
    selected_candidates = tuple(candidates_by_entity_id[entity_id] for entity_id in plan.selected_entity_ids)
    selected_source_record_ids = tuple(candidate.source_record_id for candidate in selected_candidates)
    batch_size = max_records or max(len(selected_source_record_ids), 1)
    retained_records = tuple(
        record
        for record in repository.load_classification_records(validation_run_id, selected_source_record_ids)
        if record.evidence or record.has_fetch_failure
    )
    if retained_records:
        records = retained_records[:batch_size]
        fetch_summaries: tuple[FetchSummary, ...] = ()
        pending_work = len(retained_records) > len(records) or bool(
            repository.load_unfetched_selected_source_records(validation_run_id, selected_source_record_ids)
        )
    else:
        unfetched_records = repository.load_unfetched_selected_source_records(validation_run_id, selected_source_record_ids)
        fetch_records = unfetched_records[:batch_size]
        fetch_summaries = fetcher.fetch_records(fetch_records)
        records = repository.load_classification_records(
            validation_run_id, tuple(record.id for record in fetch_records)
        )
        pending_work = len(unfetched_records) > len(fetch_records)
    identities = repository.load_existing_identities()
    results = []
    for record in records:
        result = classify_source_record(record, rule_version=rule_version)
        repository.record_decision(
            source_record_id=record.id,
            validation_run_id=record.validation_run_id,
            result=result,
            rule_version=rule_version,
            identity_link=find_high_certainty_identity_match(record, identities),
        )
        results.append(result)

    summary = ManualRunSummary(
        validation_run_id=validation_run_id,
        input_workbook_name=input_workbook_name,
        imported_record_count=imported_record_count,
        selected_record_count=len(selected_candidates),
        new_record_count=plan.new_record_count,
        changed_record_count=plan.changed_record_count,
        direct_recheck_count=plan.direct_recheck_count,
        adjacent_recheck_count=plan.adjacent_recheck_count,
        unresolved_recheck_count=plan.unresolved_recheck_count,
        failed_recheck_count=plan.failed_recheck_count,
        evidence_page_count=sum(item.evidence_count for item in fetch_summaries),
        fetch_failure_count=sum(item.failure_count for item in fetch_summaries),
        classified_record_count=len(results),
        auto_approved_count=sum(result.auto_approved for result in results),
        review_required_count=sum(result.requires_human_review for result in results),
        outcome="running" if pending_work else "completed",
    )
    if summary.outcome == "completed":
        repository.complete_run(validation_run_id, summary)
    return summary


def _selection_reason(record: ComparisonRecord) -> str | None:
    if record.previous_value_hash is None:
        return "new"
    if record.had_fetch_failure:
        return "failed"
    if record.previous_outcome == "review_required" or record.previous_classification is None:
        return "unresolved"
    if record.previous_classification == "direct":
        return "direct"
    if record.previous_classification == "adjacent":
        return "adjacent"
    return None
