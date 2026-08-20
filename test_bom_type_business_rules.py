from __future__ import annotations

import unittest

from bom_type_inference_v3 import business_rule


class BomTypeBusinessRuleTests(unittest.TestCase):
    def test_reform_v10_eub_waste_sorting_is_manufacture(self):
        for sku in (
            "EUB-P-ACC02-MIS030",
            "EUB-P-ACC02-MIS031",
            "EUB-P-ACC02-MIS032",
        ):
            proposed, reason = business_rule("INTERIOR STORAGE", sku)
            self.assertEqual(proposed, "normal")
            self.assertIn("ATLIEKŲ RŪŠIAVIMO", reason)

    def test_rule_does_not_cover_unreviewed_eub_codes(self):
        self.assertIsNone(
            business_rule("INTERIOR STORAGE", "EUB-P-ACC02-MIS033")
        )


if __name__ == "__main__":
    unittest.main()
