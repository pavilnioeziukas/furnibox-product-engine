from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

from reform_so_line_prices import build_reform_so_line_prices


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
                "SO LINE PRICES", "BOM CATEGORY BREAKDOWN", "CATEGORY RULES",
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


if __name__ == "__main__":
    unittest.main()
