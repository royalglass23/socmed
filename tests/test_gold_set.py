from __future__ import annotations

from collections import Counter
import unittest


class GoldSetGateTests(unittest.TestCase):
    def test_has_five_cases_for_each_phase_four_outcome_and_the_required_failure_scenarios(self) -> None:
        from royal_glass_validator.gold_set import GOLD_SET, verify_gold_set

        classifications = Counter(case.expected_classification or "review_required" for case in GOLD_SET)

        self.assertEqual(len(GOLD_SET), 25)
        self.assertEqual(classifications, {
            "direct": 5,
            "adjacent": 5,
            "supplier_ecosystem": 5,
            "irrelevant": 5,
            "review_required": 5,
        })
        self.assertEqual(
            {case.failure_scenario for case in GOLD_SET if case.failure_scenario},
            {"dead_site", "timeout", "block", "javascript_only", "conflicting_sources"},
        )
        verify_gold_set()
