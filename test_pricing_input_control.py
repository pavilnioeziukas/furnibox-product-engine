import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from pricing_input_control import (
    build_pricing_input_snapshot,
    validate_pricing_input_snapshot,
)


def write_pricing_workbook(
    path: Path,
    component_price: float = 1.25,
    component_source: str = "APPROVED PURCHASE PRICE ADJUSTMENT",
) -> None:
    workbook = Workbook()
    components = workbook.active
    components.title = "BOM COMPONENT COSTS"
    components.append([
        "Purchased Component SKU", "Purchase Unit Price", "Cost Source",
    ])
    components.append(["PART-B", 2.5, "APPROVED PURCHASE PRICE ADJUSTMENT"])
    components.append(["PART-A", component_price, component_source])
    components.append(["PART-A", component_price, component_source])
    non_bom = workbook.create_sheet("NON-BOM RULES")
    non_bom.append(["SKU", "Purchase Price"])
    non_bom.append(["DIRECT-1", 4.0])
    workbook.save(path)


class PricingInputControlTests(unittest.TestCase):
    def test_snapshot_is_unique_and_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "pricing.xlsx"
            write_pricing_workbook(workbook)
            snapshot = build_pricing_input_snapshot(workbook)
            self.assertEqual(snapshot["record_count"], 3)
            self.assertEqual(
                [(row["rule"], row["sku"], row["price"]) for row in snapshot["records"]],
                [
                    ("R001", "PART-A", "1.25"),
                    ("R001", "PART-B", "2.5"),
                    ("R007", "DIRECT-1", "4"),
                ],
            )

    def test_snapshot_hash_tracks_prices_not_source_wording(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first = base / "first.xlsx"
            second = base / "second.xlsx"
            write_pricing_workbook(first)
            write_pricing_workbook(
                second,
                component_source="PRODUCTION ODOO LAST PURCHASE PRICE",
            )
            self.assertEqual(
                build_pricing_input_snapshot(first)["sha256"],
                build_pricing_input_snapshot(second)["sha256"],
            )

    def test_validation_writes_pass_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workbook = base / "pricing.xlsx"
            output = base / "snapshot.json"
            expected = base / "expected.json"
            write_pricing_workbook(workbook)
            snapshot = build_pricing_input_snapshot(workbook)
            expected.write_text(json.dumps({
                "expected_sha256": snapshot["sha256"],
                "expected_record_count": snapshot["record_count"],
                "reference": {"pricing_run": "TEST"},
                "approved_overlays": [],
            }), encoding="utf-8")
            result = validate_pricing_input_snapshot(workbook, output, expected)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "PASS")

    def test_validation_blocks_changed_price_and_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workbook = base / "pricing.xlsx"
            changed = base / "changed.xlsx"
            output = base / "snapshot.json"
            expected = base / "expected.json"
            write_pricing_workbook(workbook)
            snapshot = build_pricing_input_snapshot(workbook)
            expected.write_text(json.dumps({
                "expected_sha256": snapshot["sha256"],
                "expected_record_count": snapshot["record_count"],
            }), encoding="utf-8")
            write_pricing_workbook(changed, component_price=1.26)
            with self.assertRaisesRegex(ValueError, "R001/R007"):
                validate_pricing_input_snapshot(changed, output, expected)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "BLOCKED")
            self.assertNotEqual(evidence["sha256"], evidence["expected_sha256"])


if __name__ == "__main__":
    unittest.main()
