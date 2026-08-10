from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

from reform_so_line_prices import build_from_application_config, build_reform_so_line_prices
from so_pricing_rules import load_config, migrate_legacy_workbook, save_config


class ReformSoLinePriceTests(unittest.TestCase):
    def test_bom_category_breakdown_and_non_bom_logic(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            model = base / "model.xlsx"
            prices = base / "Reform_Final_Prices.xlsx"
            output = base / "Reform_SO_Line_Prices.xlsx"

            wb = Workbook()
            ws = wb.active
            ws.title = "bomai"
            ws.append([None] * 24)
            ws.append(["lv1", None, None, "lv2", None, "qty2", "lv3", "qty3"])
            ws.append(["TOP-1", "TOP-1", "CABINET", "SUB-1", "PACK", 2, "PART-1", 3])
            ws.append([None, "TOP-1", "CABINET", None, "PACK", None, "PART-2", 1])
            ws.append(["TOP-1", "TOP-1", "CABINET", "DIRECT-1", "HARDWARE", 4, None, None])
            rules = wb.create_sheet("Kainodaros kategorijos")
            rules.append(["SKU", "ID", "Name", "Odoo", "Assembly", "Storage", "Packaging", "Pallet", "Other", "Markup", "Total"])
            rules.append(["SUB-1", 8, "PACK", "", 1, 2, 3, 4, 5, 6, 21])
            rules.append(["DIRECT-1", 7, "HARDWARE", "", 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 2.1])
            rules.append(["TOP-1", 1, "CABINET", "", 10, 20, 30, 40, 50, 60, 210])
            non_bom = wb.create_sheet("Ne BOM pozicijos")
            non_bom.append(["SKU", "Description", "Group", "Category", "Cost", "New price", "Preparation", "Storage", "Bag", "Sticker", "Total"])
            non_bom.append(["ACC-1", "Accessory", "ACC", 11, 0, 0, 0.1, 0.2, 0.03, 0.02, 0])
            wb.save(model)

            wb = Workbook()
            ws = wb.active
            ws.title = "REFORM PRICE LIST"
            ws.append(["Internal Reference", "Name", "Adjusted Furnibox Purchase Price", "Reform Markup Factor", "Reform Purchase Price"])
            ws.append(["PART-1", "Part 1", 2, 1, 2])
            ws.append(["PART-2", "Part 2", 5, 1, 5])
            ws.append(["DIRECT-1", "Direct", 7, 1, 7])
            ws.append(["ACC-1", "Accessory", 10, 1, 10])
            wb.save(prices)

            counts = build_reform_so_line_prices(model, prices, output)
            self.assertEqual(counts, (1, 1, 0))
            result = load_workbook(output, data_only=True)
            self.assertEqual(result.sheetnames, [
                "SO LINE PRICES", "BOM COMPONENT COSTS", "BOM CATEGORY BREAKDOWN", "CATEGORY RULES",
                "NON-BOM RULES", "DIAGNOSTICS", "INFO",
            ])
            sheet = result["SO LINE PRICES"]
            headers = {cell.value: cell.column for cell in sheet[1]}
            rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
            bom = rows["TOP-1"]
            # Components: (2*3 + 5*1)*2 + 7*4 = 50
            self.assertAlmostEqual(sheet.cell(bom, headers["Component / Purchase Cost"]).value, 50)
            # Add-ons: SUB-1*2 + DIRECT-1 once + TOP-1 once = 254.1
            self.assertAlmostEqual(sheet.cell(bom, headers["Pricing Add-ons Total"]).value, 254.1)
            self.assertAlmostEqual(sheet.cell(bom, headers["Adjustment Amount"]).value, -17.787)
            self.assertAlmostEqual(sheet.cell(bom, headers["Final Reform SO Unit Price"]).value, 286.313)
            non = rows["ACC-1"]
            self.assertAlmostEqual(sheet.cell(non, headers["Final Reform SO Unit Price"]).value, 10.35)
            self.assertEqual(sheet.cell(non, headers["Status"]).value, "COMPLETE")

            components = result["BOM COMPONENT COSTS"]
            component_headers = {cell.value: cell.column for cell in components[1]}
            component_rows = {
                components.cell(row, component_headers["Purchased Component SKU"]).value: row
                for row in range(2, components.max_row + 1)
            }
            part_1 = component_rows["PART-1"]
            self.assertEqual(components.cell(part_1, component_headers["Level II SKU"]).value, "SUB-1")
            self.assertAlmostEqual(components.cell(part_1, component_headers["Total Qty in Top BOM"]).value, 6)
            self.assertAlmostEqual(components.cell(part_1, component_headers["Purchase Unit Price"]).value, 2)
            self.assertAlmostEqual(components.cell(part_1, component_headers["Component Cost"]).value, 12)
            direct = component_rows["DIRECT-1"]
            self.assertAlmostEqual(components.cell(direct, component_headers["Component Cost"]).value, 28)

    def test_application_config_replaces_legacy_workbook_at_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy = base / "legacy.xlsx"
            bom_input = base / "Reform_BOM_Input.xlsx"
            config = base / "so_pricing_rules.json"
            prices = base / "prices.xlsx"
            output = base / "result.xlsx"

            wb = Workbook()
            ws = wb.active; ws.title = "bomai"
            ws.append([]); ws.append([]); ws.append([None, "TOP", "CABINET", "SUB", None, 2, "PART", 3])
            ws = wb.create_sheet("Kainodaros kategorijos")
            ws.append(["SKU", "ID", "Name", "Odoo", "Assembly", "Storage", "Packaging", "Pallet", "Other", "Markup"])
            ws.append(["SUB", "2", "Pack", "", 1, 0, 0, 0, 0, 0])
            ws.append(["TOP", "1", "Cabinet", "", 10, 0, 0, 0, 0, 0])
            ws = wb.create_sheet("Ne BOM pozicijos")
            ws.append(["SKU", "Name", "Group", "Category", "", "", "Preparation", "Storage", "Bag", "Sticker"])
            wb.save(legacy)
            migrated = migrate_legacy_workbook(legacy)
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(len(migrated["bom_categories"]), 2)
            self.assertEqual(len(migrated["bom_skus"]), 2)
            self.assertEqual(migrated["bom_skus"][0]["category_id"], "BOM-001")
            save_config(config, migrated)
            self.assertEqual(load_config(config)["schema_version"], 2)
            legacy.unlink()

            wb = Workbook(); ws = wb.active; ws.title = "BOM - Input"
            ws.append(["BOM SKU Code", "Part 1 Code", "Part 1 Qty"])
            ws.append(["TOP", "SUB", 2]); ws.append(["SUB", "PART", 3]); wb.save(bom_input)
            wb = Workbook(); ws = wb.active; ws.title = "REFORM PRICE LIST"
            ws.append(["Internal Reference", "Name", "Adjusted Furnibox Purchase Price", "Reform Markup Factor", "Reform Purchase Price"])
            ws.append(["PART", "Part", 5, 1, 5]); wb.save(prices)

            self.assertEqual(build_from_application_config(bom_input, prices, config, output), (1, 0, 0))
            result = load_workbook(output, data_only=True)["SO LINE PRICES"]
            headers = {cell.value: cell.column for cell in result[1]}
            self.assertAlmostEqual(result.cell(2, headers["Final Reform SO Unit Price"]).value, 41.16)


if __name__ == "__main__":
    unittest.main()
