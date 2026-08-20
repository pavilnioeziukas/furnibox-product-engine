from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from refresh_reform_pricing import (
    read_pricing_status,
    refresh,
    write_blocker_report,
    write_furnibox_purchase_prices,
)


class RefreshReformPricingTests(unittest.TestCase):
    def test_refresh_passes_generated_target_dataset_to_pricing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bom = base / "BOM_for Furnibox_v10.xlsx"
            bom.write_bytes(b"source")
            output = base / "result"
            calls = []

            def fake_run_step(title, *args):
                calls.append((title, args))
                if "reconciliation" in title.lower():
                    reconciliation_path = Path(args[args.index("--output") + 1])
                    reconciliation_path.write_text(
                        json.dumps({
                            "mode": "READ_ONLY",
                            "environment": "production",
                            "summary": {
                                "product_statuses": {"BLOCKED": 4},
                                "bom_statuses": {"BLOCKED": 46},
                            },
                        }),
                        encoding="utf-8",
                    )

            with (
                patch(
                    "refresh_reform_pricing.run_step",
                    side_effect=fake_run_step,
                ),
                patch(
                    "refresh_reform_pricing.read_pricing_status",
                    return_value=({"COMPLETE": 1}, []),
                ),
                patch("refresh_reform_pricing.write_furnibox_purchase_prices"),
                patch("refresh_reform_pricing.shutil.copy2"),
            ):
                self.assertEqual(refresh(bom, output), 0)

            self.assertIn("Pilnas Furnibox Target Dataset", calls[0][0])
            self.assertIn("--local-only", calls[0][1])
            self.assertIn("reconciliation", calls[1][0].lower())
            pricing_args = calls[-1][1]
            self.assertIn("--dataset", pricing_args)
            dataset_index = pricing_args.index("--dataset") + 1
            self.assertEqual(
                Path(pricing_args[dataset_index]),
                output / "Furnibox_Target_Dataset.json",
            )
            result = json.loads(
                (output / "Reform_Pricing_Result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                result["target_reconciliation"]["bom_statuses"]["BLOCKED"],
                46,
            )

    def make_result(self, path: Path, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "SO LINE PRICES"
        sheet.append(["SKU", "Position Type", "Status", "Issues"])
        for row in rows:
            sheet.append(row)
        workbook.save(path)

    def test_complete_result_passes_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.xlsx"
            self.make_result(path, [["SKU-1", "BOM", "COMPLETE", ""]])
            statuses, blocked = read_pricing_status(path)
            self.assertEqual(statuses["COMPLETE"], 1)
            self.assertEqual(blocked, [])

    def test_blocked_result_creates_report_and_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            result = base / "result.xlsx"
            report = base / "blocked.xlsx"
            self.make_result(
                result,
                [["SKU-1", "BOM", "BLOCKED", "Missing component price: PART-1"]],
            )
            statuses, blocked = read_pricing_status(result)
            write_blocker_report(report, statuses, blocked)
            self.assertEqual(len(blocked), 1)
            self.assertTrue(report.exists())

    def test_publishes_tamara_purchase_price_as_explicit_column(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.xlsx"
            destination = base / "purchase.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "REFORM PRICE LIST"
            sheet.append([
                "Internal Reference", "Name", "Price Source",
                "Vendor / Supply Source", "Real Furnibox Purchase Price",
                "Adjusted Furnibox Purchase Price", "Status / BOM Source",
            ])
            sheet.append(["PART-1", "Part", "PO", "Vendor", 10, 12, "OK"])
            workbook.save(source)

            write_furnibox_purchase_prices(source, destination)
            published = load_workbook(destination, data_only=True, read_only=True)
            result = published["FURNIBOX PURCHASE PRICES"]
            header = [cell.value for cell in result[1]]
            self.assertIn("Furnibox (Tamara) Purchase Price", header)
            self.assertEqual(result.cell(2, header.index("Furnibox (Tamara) Purchase Price") + 1).value, 12)
            published.close()


if __name__ == "__main__":
    unittest.main()
