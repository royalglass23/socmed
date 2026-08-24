from __future__ import annotations

import unittest
from uuid import uuid4


class ClassificationTests(unittest.TestCase):
    def test_auto_approves_direct_when_official_evidence_proves_tier_one_service_and_new_zealand_delivery(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://clearview.example/services",
                        source_type="official_site",
                        evidence_snippet="We install glass pool fencing and glass balustrades throughout New Zealand.",
                        service_facts={"services": ["pool_fencing", "balustrades"]},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "direct")
        self.assertEqual(result.proposed_outcome, "direct")
        self.assertEqual(result.confidence_band, "high")
        self.assertTrue(result.auto_approved)
        self.assertFalse(result.requires_human_review)
        self.assertEqual(result.tags, ("both", "pool-fencing", "balustrades"))
        self.assertEqual(result.market_priority, "standard")

    def test_auto_approves_adjacent_when_official_new_zealand_evidence_is_relevant_but_not_tier_one(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Shower Screen Studio"},
                evidence=(
                    EvidenceFact(
                        url="https://studio.example/services",
                        source_type="official_site",
                        evidence_snippet="We design and install custom shower screens for New Zealand homes.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "adjacent")
        self.assertEqual(result.proposed_outcome, "adjacent")
        self.assertEqual(result.confidence_band, "high")
        self.assertTrue(result.auto_approved)
        self.assertEqual(result.tags, ("residential",))

    def test_auto_approves_supplier_ecosystem_when_official_new_zealand_evidence_has_no_installation_delivery(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Glass Hardware Supply"},
                evidence=(
                    EvidenceFact(
                        url="https://supplier.example/",
                        source_type="official_site",
                        evidence_snippet="Wholesale supplier of glass pool-fencing hardware to New Zealand trade customers.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "supplier_ecosystem")
        self.assertEqual(result.proposed_outcome, "supplier_ecosystem")
        self.assertEqual(result.confidence_band, "high")
        self.assertTrue(result.auto_approved)
        self.assertEqual(result.tags, ("pool-fencing",))

    def test_marks_supplier_with_verified_tier_one_installation_as_direct(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Complete Glass Supply"},
                evidence=(
                    EvidenceFact(
                        url="https://complete.example/",
                        source_type="official_site",
                        evidence_snippet="We supply and install glass balustrades for Auckland homes.",
                        service_facts={"services": ["balustrades"]},
                        region_facts={"regions": ["auckland"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "direct")
        self.assertEqual(result.tags, ("balustrades", "supplier-with-installation", "residential"))
        self.assertEqual(result.market_priority, "auckland_high")

    def test_marks_a_broad_glazier_with_verified_tier_one_installation_as_direct(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Everyday Glazing"},
                evidence=(
                    EvidenceFact(
                        url="https://glazing.example/",
                        source_type="official_site",
                        evidence_snippet="Our glazier team installs glass pool fencing across New Zealand.",
                        service_facts={"services": ["pool_fencing"]},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "direct")
        self.assertEqual(result.tags, ("pool-fencing", "broad-glazier"))

    def test_routes_evidenced_irrelevant_business_to_review_without_auto_approval(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Harbour Coffee"},
                evidence=(
                    EvidenceFact(
                        url="https://coffee.example/",
                        source_type="official_site",
                        evidence_snippet="Independent Auckland coffee roaster and cafe.",
                        service_facts={"services": []},
                        region_facts={"regions": ["auckland"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "irrelevant")
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "medium")
        self.assertFalse(result.auto_approved)
        self.assertTrue(result.requires_human_review)

    def test_routes_relevant_evidence_without_new_zealand_delivery_to_medium_confidence_review(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Shower Screens International"},
                evidence=(
                    EvidenceFact(
                        url="https://screens.example/",
                        source_type="official_site",
                        evidence_snippet="Custom shower screens for homes and apartments.",
                        service_facts={"services": []},
                        region_facts={"regions": []},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertEqual(result.proposed_classification, "adjacent")
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "medium")
        self.assertFalse(result.auto_approved)

    def test_routes_fetch_failure_to_low_confidence_review_even_when_other_evidence_looks_direct(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Interrupted Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://interrupted.example/",
                        source_type="official_site",
                        evidence_snippet="We install glass pool fencing in New Zealand.",
                        service_facts={"services": ["pool_fencing"]},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
                has_fetch_failure=True,
            ),
            rule_version="2026-08-24.1",
        )

        self.assertIsNone(result.proposed_classification)
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "low")
        self.assertFalse(result.auto_approved)

    def test_does_not_auto_approve_a_broad_keyword_mention_as_adjacent(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Door Handle Workshop"},
                evidence=(
                    EvidenceFact(
                        url="https://handles.example/",
                        source_type="official_site",
                        evidence_snippet="We hand-make door handles for New Zealand homes.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertIsNone(result.proposed_classification)
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "low")

    def test_routes_materially_conflicting_retained_evidence_to_review(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://clearview.example/services",
                        source_type="official_site",
                        evidence_snippet="We install glass pool fencing across New Zealand.",
                        service_facts={"services": ["pool_fencing"]},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                    EvidenceFact(
                        url="https://listing.example/clear-view",
                        source_type="business_listing",
                        evidence_snippet="Independent coffee cafe.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertIsNone(result.proposed_classification)
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "low")

    def test_does_not_pool_separate_official_keywords_into_high_confidence_direct_delivery(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Advice Only Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://advice.example/services",
                        source_type="official_site",
                        evidence_snippet="Installation advice for glass pool fencing.",
                        service_facts={"services": ["pool_fencing"]},
                        region_facts={"regions": []},
                    ),
                    EvidenceFact(
                        url="https://advice.example/contact",
                        source_type="official_site",
                        evidence_snippet="New Zealand customer support.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertIsNone(result.proposed_classification)
        self.assertEqual(result.proposed_outcome, "review_required")
        self.assertEqual(result.confidence_band, "low")

    def test_routes_contradictory_official_evidence_to_review(self) -> None:
        from royal_glass_validator.classification import EvidenceFact, SourceRecordForClassification, classify_source_record

        result = classify_source_record(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://clearview.example/services",
                        source_type="official_site",
                        evidence_snippet="We install glass pool fencing across New Zealand.",
                        service_facts={"services": ["pool_fencing"]},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                    EvidenceFact(
                        url="https://clearview.example/cafe",
                        source_type="official_site",
                        evidence_snippet="Independent coffee cafe.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            rule_version="2026-08-24.1",
        )

        self.assertIsNone(result.proposed_classification)
        self.assertEqual(result.proposed_outcome, "review_required")

    def test_links_an_existing_entity_only_when_normalized_domain_and_name_agree(self) -> None:
        from royal_glass_validator.classification import (
            CompetitorIdentity,
            EvidenceFact,
            SourceRecordForClassification,
            find_high_certainty_identity_match,
        )

        entity_id = uuid4()
        match = find_high_certainty_identity_match(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass Ltd"},
                evidence=(
                    EvidenceFact(
                        url="https://www.clearviewglass.example/services",
                        source_type="official_site",
                        evidence_snippet="Glass services in New Zealand.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            (CompetitorIdentity(id=entity_id, display_name="Clear View Glass", primary_domain="clearviewglass.example", verified_phone=None),),
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.competitor_entity_id, entity_id)
        self.assertEqual(match.link_method, "normalized_domain")

    def test_leaves_duplicate_domain_matches_unlinked_for_review(self) -> None:
        from royal_glass_validator.classification import (
            CompetitorIdentity,
            EvidenceFact,
            SourceRecordForClassification,
            find_high_certainty_identity_match,
        )

        match = find_high_certainty_identity_match(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass"},
                evidence=(
                    EvidenceFact(
                        url="https://clearviewglass.example/",
                        source_type="official_site",
                        evidence_snippet="Glass services in New Zealand.",
                        service_facts={"services": []},
                        region_facts={"regions": ["new_zealand"]},
                    ),
                ),
            ),
            (
                CompetitorIdentity(id=uuid4(), display_name="Clear View Glass", primary_domain="clearviewglass.example", verified_phone=None),
                CompetitorIdentity(id=uuid4(), display_name="Clear View Glass Ltd", primary_domain="clearviewglass.example", verified_phone=None),
            ),
        )

        self.assertIsNone(match)

    def test_links_matching_verified_phone_and_name_without_a_domain_match(self) -> None:
        from royal_glass_validator.classification import CompetitorIdentity, SourceRecordForClassification, find_high_certainty_identity_match

        entity_id = uuid4()
        match = find_high_certainty_identity_match(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass", "Verified Phone": "+64 9 123 4567"},
                evidence=(),
            ),
            (CompetitorIdentity(id=entity_id, display_name="Clear View Glass Ltd", primary_domain=None, verified_phone="09 123-4567"),),
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.competitor_entity_id, entity_id)
        self.assertEqual(match.link_method, "verified_phone_and_name")

    def test_leaves_conflicting_domain_and_verified_phone_matches_unlinked_for_review(self) -> None:
        from royal_glass_validator.classification import (
            CompetitorIdentity,
            EvidenceFact,
            SourceRecordForClassification,
            find_high_certainty_identity_match,
        )

        match = find_high_certainty_identity_match(
            SourceRecordForClassification(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Canonical Name": "Clear View Glass", "Verified Phone": "+64 9 123 4567"},
                evidence=(
                    EvidenceFact(
                        url="https://clearview-a.example/",
                        source_type="official_site",
                        evidence_snippet="Glass services.",
                        service_facts={"services": []},
                        region_facts={"regions": []},
                    ),
                ),
            ),
            (
                CompetitorIdentity(id=uuid4(), display_name="Clear View Glass", primary_domain="clearview-a.example", verified_phone="09 999 9999"),
                CompetitorIdentity(id=uuid4(), display_name="Clear View Glass", primary_domain="clearview-b.example", verified_phone="09 123 4567"),
            ),
        )

        self.assertIsNone(match)
