"""Locked Phase 4 classifier gate exercised before every manual comparison run."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record


class GoldSetGateError(RuntimeError):
    """Raised when the tracked Phase 4 classifier examples no longer satisfy their expected outcomes."""


@dataclass(frozen=True)
class GoldSetCase:
    """One compact, evidence-backed rule example from the Phase 4 acceptance contract."""

    case_id: str
    evidence: tuple[EvidenceFact, ...]
    expected_classification: str | None
    expected_outcome: str
    expected_confidence: str
    has_fetch_failure: bool = False
    failure_scenario: str | None = None


def _official(snippet: str, services: tuple[str, ...] = (), regions: tuple[str, ...] = ("new_zealand",)) -> EvidenceFact:
    return EvidenceFact(
        url="https://gold-set.example/services",
        source_type="official_site",
        evidence_snippet=snippet,
        service_facts={"services": list(services)},
        region_facts={"regions": list(regions)},
    )


GOLD_SET: tuple[GoldSetCase, ...] = (
    GoldSetCase("direct-pool", (_official("We install glass pool fencing throughout New Zealand.", ("pool_fencing",)),), "direct", "direct", "high"),
    GoldSetCase("direct-balustrades", (_official("We supply and install glass balustrades for Auckland homes.", ("balustrades",), ("auckland",)),), "direct", "direct", "high"),
    GoldSetCase("direct-both", (_official("Our team installs pool fencing and glass balustrades throughout New Zealand.", ("pool_fencing", "balustrades")),), "direct", "direct", "high"),
    GoldSetCase("direct-broad-glazier", (_official("Our glazier team installs glass pool fencing in Auckland.", ("pool_fencing",), ("auckland",)),), "direct", "direct", "high"),
    GoldSetCase("direct-supplier-installer", (_official("We supply and install commercial glass balustrades across New Zealand.", ("balustrades",)),), "direct", "direct", "high"),
    GoldSetCase("adjacent-shower-screens", (_official("We design custom shower screens for New Zealand homes."),), "adjacent", "adjacent", "high"),
    GoldSetCase("adjacent-splashbacks", (_official("Splashback design and installation for New Zealand kitchens."),), "adjacent", "adjacent", "high"),
    GoldSetCase("adjacent-architectural", (_official("Architectural glass design for New Zealand projects."),), "adjacent", "adjacent", "high"),
    GoldSetCase("adjacent-windows", (_official("Window installation for Auckland homeowners.", (), ("auckland",)),), "adjacent", "adjacent", "high"),
    GoldSetCase("adjacent-doors", (_official("Door installation for New Zealand commercial sites."),), "adjacent", "adjacent", "high"),
    GoldSetCase("supplier-pool-hardware", (_official("Wholesale supplier of glass pool fencing hardware to New Zealand trade customers."),), "supplier_ecosystem", "supplier_ecosystem", "high"),
    GoldSetCase("supplier-balustrade-hardware", (_official("Supplier of balustrade fittings for New Zealand trade customers."),), "supplier_ecosystem", "supplier_ecosystem", "high"),
    GoldSetCase("supplier-glazing", (_official("Wholesale supplier of glazing products for New Zealand trade customers."),), "supplier_ecosystem", "supplier_ecosystem", "high"),
    GoldSetCase("supplier-pool-material", (_official("Trade customer supplier of pool-fencing glass in New Zealand."),), "supplier_ecosystem", "supplier_ecosystem", "high"),
    GoldSetCase("supplier-glass", (_official("New Zealand wholesale glass supplier for commercial trade customers."),), "supplier_ecosystem", "supplier_ecosystem", "high"),
    GoldSetCase("irrelevant-coffee", (_official("Independent New Zealand coffee roaster and cafe."),), "irrelevant", "review_required", "medium"),
    GoldSetCase("irrelevant-dentist", (_official("Auckland dentist for family dental care.", (), ("auckland",)),), "irrelevant", "review_required", "medium"),
    GoldSetCase("irrelevant-restaurant", (_official("New Zealand restaurant and cafe."),), "irrelevant", "review_required", "medium"),
    GoldSetCase("irrelevant-hotel", (_official("Auckland hotel accommodation and restaurant.", (), ("auckland",)),), "irrelevant", "review_required", "medium"),
    GoldSetCase("irrelevant-cafe", (_official("Independent Auckland cafe." , (), ("auckland",)),), "irrelevant", "review_required", "medium"),
    GoldSetCase("review-dead-site", (), None, "review_required", "low", has_fetch_failure=True, failure_scenario="dead_site"),
    GoldSetCase("review-timeout", (), None, "review_required", "low", has_fetch_failure=True, failure_scenario="timeout"),
    GoldSetCase("review-block", (), None, "review_required", "low", has_fetch_failure=True, failure_scenario="block"),
    GoldSetCase("review-javascript", (), None, "review_required", "low", has_fetch_failure=True, failure_scenario="javascript_only"),
    GoldSetCase("review-conflict", (_official("We install glass pool fencing across New Zealand.", ("pool_fencing",)), _official("Independent cafe in New Zealand.")), None, "review_required", "low", failure_scenario="conflicting_sources"),
)


def verify_gold_set(*, rule_version: str = "phase4-gold-set") -> None:
    """Fail closed if any of the 25 acceptance examples regress."""
    failures: list[str] = []
    for case in GOLD_SET:
        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": case.case_id},
                evidence=case.evidence,
                has_fetch_failure=case.has_fetch_failure,
            ),
            rule_version=rule_version,
        )
        actual = (result.proposed_classification, result.proposed_outcome, result.confidence_band)
        expected = (case.expected_classification, case.expected_outcome, case.expected_confidence)
        if actual != expected:
            failures.append(f"{case.case_id}: expected {expected}, got {actual}")
    if failures:
        raise GoldSetGateError("Phase 4 gold-set gate failed: " + "; ".join(failures))
