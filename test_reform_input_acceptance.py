"""Regressions for approved Reform input drift detection."""

from pathlib import Path
import unittest
from unittest.mock import patch

from reform_input_acceptance import (
    audit_generated_boms,
    audit_input,
    compare_boms,
    read_selected_boms,
)
from reform_map import PartColumns


class ReformInputAcceptanceTests(unittest.TestCase):
    def test_duplicate_new_source_bom_is_detected(self):
        with (
            patch("reform_input_acceptance.load_workbook") as workbook,
            patch("reform_input_acceptance.find_sheet") as find_sheet,
            patch("reform_input_acceptance.find_header", return_value=(1, ("BOM SKU Code", "Part 1 Code", "Part 1 Qty"))),
            patch("reform_input_acceptance.detect_columns", return_value=(0, [PartColumns(1, 1, 2)])),
        ):
            find_sheet.return_value.iter_rows.return_value = [
                ("NEW-SKU", "PART", 1),
                ("NEW-SKU", "PART", 1),
            ]
            actual, issues, _ = read_selected_boms(Path("future.xlsx"), set())
            workbook.return_value.close.assert_called_once()
        self.assertEqual(actual, {})
        self.assertEqual(issues[0]["type"], "DUPLICATE_SOURCE_BOM")

    def test_changed_workbook_layout_reports_review(self):
        with patch("reform_input_acceptance.read_selected_boms", side_effect=ValueError("missing BOM SKU Code")):
            report = audit_input(Path("future_reform.xlsx"))
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["issues"][0]["type"], "INVALID_REFORM_INPUT_FORMAT")

    def test_matching_components_pass(self):
        self.assertEqual(compare_boms({"A": {"PART": 2}}, {"A": {"PART": 2}}), [])

    def test_missing_bom_is_distinct_from_changed_quantity(self):
        issues = compare_boms(
            {"B": {"PART": 1}},
            {"A": {"PART": 1}, "B": {"PART": 2}},
        )
        self.assertEqual([issue["type"] for issue in issues], [
            "MISSING_APPROVED_BOM", "CONFLICTING_BOM_COMPONENT",
        ])
        self.assertEqual(issues[1]["actual_qty"], 1)
        self.assertEqual(issues[1]["expected_qty"], 2)

    def test_extra_component_is_not_silently_accepted(self):
        issues = compare_boms({"A": {"PART": 1, "EXTRA": 1}}, {"A": {"PART": 1}})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["component"], "EXTRA")

    def test_approved_workbook_passes_when_available(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "outputs"
            / "Reform_V10_pagrindu_kainodaros_ivestis_Tamaros_korekcijos_be_dvigubo_HRD-A.xlsx"
        )
        if not path.exists():
            self.skipTest("V10 approved workbook is a local acceptance fixture")
        report = audit_input(path)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["matched_boms"], 8)
        self.assertIn("approved_bom_components", report["validated_at_input"])
        self.assertIn("purchase_price_adjustments", report["requires_downstream_price_validation"])
        self.assertEqual(report["persistent_rule_coverage"], {
            "purchased_non_bom_skus": 72,
            "approved_supplier_aliases": 4,
            "reviewed_pricing_corrections": 22,
            "apack_hrd_family_rules": 12,
            "approved_purchase_prices": 12,
        })
        self.assertEqual(len(report["purchased_source_boms_to_ignore"]), 63)
        self.assertIn(
            "UNI-P-ACC03-MIS015",
            {row["sku"] for row in report["purchased_source_boms_to_ignore"]},
        )

    def test_generated_hrd_a_has_only_approved_components(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "outputs"
            / "Furnibox_pilnas_kainodaros_failas_V10_pagrindu_Tamaros_perziurai_2026-09-17.xlsx"
        )
        if not path.exists():
            self.skipTest("V10 completed pricing workbook is a local acceptance fixture")
        report = audit_generated_boms(path)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["checked_parent_boms"], 11)


if __name__ == "__main__":
    unittest.main()
