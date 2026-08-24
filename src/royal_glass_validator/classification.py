"""Deterministic, evidence-backed Phase 4 competitor classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from uuid import UUID


@dataclass(frozen=True)
class EvidenceFact:
    """Compact evidence required to make one reproducible classification decision."""

    url: str
    source_type: str
    evidence_snippet: str
    service_facts: Mapping[str, object]
    region_facts: Mapping[str, object]


@dataclass(frozen=True)
class SourceRecordForClassification:
    """An immutable Source Record and its retained official evidence."""

    id: UUID
    validation_run_id: UUID
    original_values: Mapping[str, object]
    evidence: tuple[EvidenceFact, ...]
    has_fetch_failure: bool = False


@dataclass(frozen=True)
class ClassificationResult:
    proposed_classification: str | None
    proposed_outcome: str
    confidence_band: str
    rationale: str
    tags: tuple[str, ...]
    auto_approved: bool
    requires_human_review: bool
    market_priority: str = "standard"


@dataclass(frozen=True)
class CompetitorIdentity:
    """An existing Competitor Entity eligible for a conservative Source Record link."""

    id: UUID
    display_name: str
    primary_domain: str | None
    verified_phone: str | None


@dataclass(frozen=True)
class IdentityLink:
    competitor_entity_id: UUID
    link_method: str
    rationale: str


def classify_source_record(record: SourceRecordForClassification, *, rule_version: str) -> ClassificationResult:
    """Return the conservative Phase 4 decision permitted by retained evidence."""
    del rule_version  # The caller persists the version alongside this deterministic result.
    official_evidence = tuple(evidence for evidence in record.evidence if evidence.source_type == "official_site")
    service_facts = _string_facts(official_evidence, "service_facts", "services")
    region_facts = _string_facts(official_evidence, "region_facts", "regions")
    has_new_zealand_delivery = bool({"new_zealand", "auckland"} & region_facts)
    market_priority = "auckland_high" if "auckland" in region_facts else "standard"
    evidence_text = _evidence_text(official_evidence)
    has_material_conflict = _has_material_conflict(record.evidence, official_evidence)

    if (
        not record.has_fetch_failure
        and not has_material_conflict
        and _has_clear_direct_delivery(official_evidence)
    ):
        return ClassificationResult(
            proposed_classification="direct",
            proposed_outcome="direct",
            confidence_band="high",
            rationale="Official evidence confirms Tier 1 glass service delivery in New Zealand.",
            tags=_direct_tags(service_facts, evidence_text),
            auto_approved=True,
            requires_human_review=False,
            market_priority=market_priority,
        )

    if not record.has_fetch_failure and not has_material_conflict and _contains_any(evidence_text, _IRRELEVANT_TERMS):
        return ClassificationResult(
            proposed_classification="irrelevant",
            proposed_outcome="review_required",
            confidence_band="medium",
            rationale="Official evidence indicates an activity outside the Royal Glass competitor universe; v1 requires review.",
            tags=(),
            auto_approved=False,
            requires_human_review=True,
            market_priority=market_priority,
        )

    if (
        not record.has_fetch_failure
        and not has_material_conflict
        and has_new_zealand_delivery
        and _contains_any(evidence_text, _SUPPLIER_TERMS)
        and _contains_any(evidence_text, _ECOSYSTEM_SERVICE_TERMS)
    ):
        return ClassificationResult(
            proposed_classification="supplier_ecosystem",
            proposed_outcome="supplier_ecosystem",
            confidence_band="high",
            rationale="Official evidence confirms New Zealand supply or trade-support activity without Tier 1 installation delivery.",
            tags=_supplier_tags(evidence_text),
            auto_approved=True,
            requires_human_review=False,
            market_priority=market_priority,
        )

    if not record.has_fetch_failure and not has_material_conflict and has_new_zealand_delivery and _contains_any(evidence_text, _ADJACENT_TERMS):
        return ClassificationResult(
            proposed_classification="adjacent",
            proposed_outcome="adjacent",
            confidence_band="high",
            rationale="Official evidence confirms a related New Zealand glass-project service without Tier 1 delivery.",
            tags=_context_tags(evidence_text),
            auto_approved=True,
            requires_human_review=False,
            market_priority=market_priority,
        )

    if not record.has_fetch_failure and _contains_any(evidence_text, _ADJACENT_TERMS):
        return ClassificationResult(
            proposed_classification="adjacent",
            proposed_outcome="review_required",
            confidence_band="medium",
            rationale="Official evidence is relevant but does not establish New Zealand delivery.",
            tags=_context_tags(evidence_text),
            auto_approved=False,
            requires_human_review=True,
            market_priority=market_priority,
        )

    return ClassificationResult(
        proposed_classification=None,
        proposed_outcome="review_required",
        confidence_band="low",
        rationale="Retained evidence does not safely establish a Phase 4 classification.",
        tags=(),
        auto_approved=False,
        requires_human_review=True,
        market_priority=market_priority,
    )


def find_high_certainty_identity_match(
    record: SourceRecordForClassification, candidates: tuple[CompetitorIdentity, ...]
) -> IdentityLink | None:
    """Return one safe automatic link, leaving uncertain or multiple matches reviewable."""
    source_name = _source_name(record.original_values)
    if not source_name:
        return None
    source_domains = {_normalized_domain(evidence.url) for evidence in record.evidence if evidence.source_type == "official_site"}
    domain_matches = [
        candidate
        for candidate in candidates
        if candidate.primary_domain
        and _normalized_domain(candidate.primary_domain) in source_domains
        and _names_are_compatible(source_name, candidate.display_name)
    ]
    source_phone = _source_phone(record.original_values)
    phone_matches = [
        candidate
        for candidate in candidates
        if source_phone
        and candidate.verified_phone
        and _normalized_phone(candidate.verified_phone) == source_phone
        and _names_are_compatible(source_name, candidate.display_name)
    ]
    if domain_matches and phone_matches:
        if len(domain_matches) != 1 or len(phone_matches) != 1 or domain_matches[0].id != phone_matches[0].id:
            return None
        return IdentityLink(
            competitor_entity_id=domain_matches[0].id,
            link_method="normalized_domain",
            rationale="Observed official-site domain plus verified phone and normalized business name match one Competitor Entity.",
        )
    if len(domain_matches) == 1:
        return IdentityLink(
            competitor_entity_id=domain_matches[0].id,
            link_method="normalized_domain",
            rationale="Observed official-site domain and normalized business name match one existing Competitor Entity.",
        )
    if len(phone_matches) == 1:
        return IdentityLink(
            competitor_entity_id=phone_matches[0].id,
            link_method="verified_phone_and_name",
            rationale="Verified phone and normalized business name match one existing Competitor Entity.",
        )
    return None


def _string_facts(evidence: tuple[EvidenceFact, ...], facts_name: str, key: str) -> set[str]:
    values: set[str] = set()
    for item in evidence:
        facts = getattr(item, facts_name)
        raw_values = facts.get(key, ())
        if isinstance(raw_values, (list, tuple)):
            values.update(str(value) for value in raw_values)
    return values


def _direct_tags(service_facts: set[str], evidence_text: str) -> tuple[str, ...]:
    tags: list[str] = []
    if {"pool_fencing", "balustrades"} <= service_facts:
        tags.append("both")
    if "pool_fencing" in service_facts:
        tags.append("pool-fencing")
    if "balustrades" in service_facts:
        tags.append("balustrades")
    if _contains_any(evidence_text, _SUPPLIER_INSTALLATION_TERMS) and _contains_any(evidence_text, _INSTALLATION_TERMS):
        tags.append("supplier-with-installation")
    if "glazier" in evidence_text:
        tags.append("broad-glazier")
    tags.extend(_context_tags(evidence_text))
    return tuple(tags)


_ADJACENT_TERMS = ("shower screen", "splashback", "architectural glass", "window installation", "door installation")
_SUPPLIER_TERMS = ("supplier", "wholesale", "trade customer")
_SUPPLIER_INSTALLATION_TERMS = _SUPPLIER_TERMS + ("supply",)
_ECOSYSTEM_SERVICE_TERMS = ("glass", "pool fencing", "pool-fencing", "balustrade", "glazing")
_INSTALLATION_TERMS = ("install", "installation")
_DELIVERY_TERMS = ("we install", "we supply and install", "supply and install", "installs", "installation service")
_IRRELEVANT_TERMS = ("coffee roaster", "cafe", "dentist", "restaurant", "hotel")


def _evidence_text(evidence: tuple[EvidenceFact, ...]) -> str:
    return " ".join(item.evidence_snippet for item in evidence).casefold()


def _has_material_conflict(all_evidence: tuple[EvidenceFact, ...], official_evidence: tuple[EvidenceFact, ...]) -> bool:
    """Treat contradictory supporting sources as review-required, never an auto-approval."""
    evidence_texts = tuple(_evidence_text((item,)) for item in all_evidence)
    has_relevant_evidence = any(_contains_any(text, _ECOSYSTEM_SERVICE_TERMS) for text in evidence_texts)
    has_irrelevant_evidence = any(_contains_any(text, _IRRELEVANT_TERMS) for text in evidence_texts)
    return has_relevant_evidence and has_irrelevant_evidence


def _has_clear_direct_delivery(evidence: tuple[EvidenceFact, ...]) -> bool:
    for item in evidence:
        services = _string_facts((item,), "service_facts", "services")
        regions = _string_facts((item,), "region_facts", "regions")
        text = _evidence_text((item,))
        if (
            bool({"pool_fencing", "balustrades"} & services)
            and bool({"new_zealand", "auckland"} & regions)
            and _contains_any(text, _DELIVERY_TERMS)
        ):
            return True
    return False


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _context_tags(evidence_text: str) -> tuple[str, ...]:
    tags: list[str] = []
    if "residential" in evidence_text or "home" in evidence_text:
        tags.append("residential")
    if "commercial" in evidence_text:
        tags.append("commercial")
    if "regional" in evidence_text:
        tags.append("regional")
    return tuple(tags)


def _supplier_tags(evidence_text: str) -> tuple[str, ...]:
    tags: list[str] = []
    if "pool fencing" in evidence_text or "pool-fencing" in evidence_text:
        tags.append("pool-fencing")
    if "balustrade" in evidence_text:
        tags.append("balustrades")
    return tuple(tags)


def _source_name(values: Mapping[str, object]) -> str | None:
    normalized_values = {str(key).strip().casefold(): value for key, value in values.items()}
    for key in ("canonical name", "business name", "company name", "name"):
        value = normalized_values.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _source_phone(values: Mapping[str, object]) -> str | None:
    normalized_values = {str(key).strip().casefold(): value for key, value in values.items()}
    for key in ("verified phone", "verified_phone"):
        value = normalized_values.get(key)
        if isinstance(value, str) and value.strip():
            return _normalized_phone(value)
    return None


def _normalized_domain(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _names_are_compatible(left: str, right: str) -> bool:
    return _normalized_name(left) == _normalized_name(right)


def _normalized_name(value: str) -> str:
    lowered = re.sub(r"\b(limited|ltd|nz)\b", "", value.casefold())
    return "".join(character for character in lowered if character.isalnum())


def _normalized_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if digits.startswith("64"):
        return f"0{digits[2:]}"
    return digits
