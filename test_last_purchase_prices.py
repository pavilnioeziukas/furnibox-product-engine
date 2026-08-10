from pathlib import Path
import sys
import tempfile
import types
import unittest

from openpyxl import load_workbook

config_stub = types.ModuleType("config")
config_stub.load_settings = lambda: None
sys.modules.setdefault("config", config_stub)

from last_purchase_prices import write_purchase_prices


class ComponentPriceWorkbookTests(unittest.TestCase):
    def test_workbook_contains_editable_component_pricing_inputs_and_reform_formula(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "Last_Purchase_Prices.xlsx"
            write_purchase_prices(
                output,
                [
                    {
                        "Internal Reference": "ACCS-TEST",
                        "Name": "Test component",
                        "Product Category/Name": "All / Components / CABINET HARDWARE",
                        "Purchase Order": "P00001",
                        "Vendor": "Test vendor",
                        "Ordered Quantity": 100,
                        "Last Purchase Price": 2.5,
                        "Order Date": "2026-08-10 12:00:00",
                    }
                ],
                {
                    "url": "https://example.test",
                    "db": "test",
                    "login": "test@example.test",
                    "uid": 1,
                },
            )

            workbook = load_workbook(output, data_only=False)
            self.assertEqual(
                workbook.sheetnames,
                ["INFO", "PRICING RULES", "TAMARA ADJUSTMENTS", "COMPONENT PRICES"],
            )
            prices = workbook["COMPONENT PRICES"]
            headers = {cell.value: cell.column for cell in prices[1]}
            self.assertIn("Real Purchase Price", headers)
            self.assertNotIn("Last Purchase Price", headers)

            self.assertEqual(
                prices.cell(2, headers["Adjusted Purchase Price"]).value,
                "='TAMARA ADJUSTMENTS'!B2",
            )
            self.assertEqual(prices.cell(2, headers["Markup Factor"]).value, 1.0)
            self.assertEqual(
                prices.cell(2, headers["Reform Price"]).value,
                '=IF(I2="",G2,I2)*J2',
            )
            adjustments = workbook["TAMARA ADJUSTMENTS"]
            self.assertEqual(adjustments["A2"].value, "ACCS-TEST")
            self.assertEqual(adjustments["B2"].value, 2.5)
            self.assertEqual(workbook.calculation.calcMode, "auto")

            adjustments["B2"] = 3.25
            workbook.save(output)

            write_purchase_prices(
                output,
                [
                    {
                        "Internal Reference": "ACCS-TEST",
                        "Name": "Test component",
                        "Product Category/Name": "All / Components / CABINET HARDWARE",
                        "Purchase Order": "P00002",
                        "Vendor": "Reform Supply & Logistics, UAB",
                        "Ordered Quantity": 50,
                        "Last Purchase Price": 2.75,
                        "Order Date": "2026-08-11 12:00:00",
                    }
                ],
                {
                    "url": "https://example.test",
                    "db": "test",
                    "login": "test@example.test",
                    "uid": 1,
                },
            )
            regenerated = load_workbook(output, data_only=False)
            self.assertEqual(regenerated["TAMARA ADJUSTMENTS"]["B2"].value, 3.25)
            self.assertEqual(regenerated["TAMARA ADJUSTMENTS"]["C2"].value, 2.75)
            self.assertEqual(regenerated["COMPONENT PRICES"]["J2"].value, 1.05)


if __name__ == "__main__":
    unittest.main()
