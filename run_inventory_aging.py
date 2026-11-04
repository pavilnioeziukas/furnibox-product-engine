"""Read-only company-wide Odoo inventory aging export."""
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font

from core.config import OdooConfig
from core.odoo_client import OdooClient
from run_stock_by_location import StockByLocationReport


BUCKETS = ("0–30 d.", "31–90 d.", "91–180 d.", "181–365 d.", ">365 d.")


class InventoryAgingReport(StockByLocationReport):
    def read_matching(self, model, domain, fields):
        return self.read_in_batches(
            model=model, record_ids=self.client.search(model, domain), fields=fields,
        )

    def run(self, output_dir):
        extracted = datetime.now(ZoneInfo("Europe/Vilnius"))
        company = self.read_matching("res.company", [], ["name", "currency_id"])
        if len(company) != 1:
            raise ValueError("Ataskaitai reikalinga prieiga prie vienos Odoo įmonės.")
        company_filter = [("company_id", "=", company[0]["id"])]
        balances = defaultdict(lambda: [0.0, 0.0, False])
        for quant in self.read_matching(
            "stock.quant",
            company_filter + [("location_id.usage", "=", "internal"),
                              ("owner_id", "=", False),
                              "|", ("quantity", "!=", 0), ("reserved_quantity", "!=", 0)],
            ["product_id", "quantity", "reserved_quantity"],
        ):
            balance = balances[quant["product_id"][0]]
            balance[0] += quant["quantity"]
            balance[1] += quant["reserved_quantity"]
            balance[2] |= quant["quantity"] < 0

        aging = defaultdict(lambda: [0.0] * 8)
        for layer in self.read_matching(
            "stock.valuation.layer",
            company_filter + [("quantity", ">", 0), ("remaining_qty", ">", 0)],
            ["product_id", "create_date", "remaining_qty", "remaining_value"],
        ):
            values = aging[layer["product_id"][0]]
            if layer["create_date"]:
                date = datetime.fromisoformat(layer["create_date"]).replace(
                    tzinfo=ZoneInfo("UTC")
                ).astimezone(extracted.tzinfo).date()
                days = (extracted.date() - date).days
                bucket = sum(days > limit for limit in (30, 90, 180, 365)) if days >= 0 else 5
            else:
                bucket = 5
            values[bucket] += layer["remaining_qty"]
            values[6] += layer["remaining_value"]
            if bucket == 4:
                values[7] += layer["remaining_value"]

        products = self.read_map(
            model="product.product", record_ids=set(balances) | set(aging),
            fields=["default_code", "name", "categ_id", "uom_id"],
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Atsargų senėjimas"
        sheet.append(["SKU", "Produktas", "Kategorija", "Mato vnt.", "On Hand",
                      "Rezervuota", *BUCKETS, "Amžius nežinomas", "Sluoksnių vertė",
                      ">365 d. vertė", "Sluoksnių ir On Hand skirtumas", "Išimtis"])
        for product_id in sorted(products, key=lambda key: (
            -aging[key][7], str(products[key]["default_code"] or ""), key
        )):
            product = products[product_id]
            on_hand, reserved, negative_quant = balances[product_id]
            quantities = aging[product_id]
            difference = round(sum(quantities[:6]) - on_hand, 8)
            issues = []
            if difference:
                issues.append("Sluoksnių kiekis nesutampa su On Hand")
            if negative_quant:
                issues.append("Yra neigiamas likutis")
            sheet.append([
                str(product["default_code"] or ""), product["name"],
                (product["categ_id"] or [None, ""])[1],
                (product["uom_id"] or [None, ""])[1], on_hand, reserved,
                *quantities, difference, ", ".join(issues),
            ])
            for cell in sheet[sheet.max_row][:4]:
                cell.data_type = "s"

        sheet.freeze_panes = "E2"
        sheet.auto_filter.ref = sheet.dimensions
        for cells in sheet.columns:
            cells[0].font = Font(bold=True)
            sheet.column_dimensions[cells[0].column_letter].width = min(
                60, max(12, max(len(str(cell.value or "")) for cell in cells) + 2)
            )
        info = workbook.create_sheet("Informacija")
        info.append(["Ištraukta", extracted.isoformat(timespec="seconds")])
        info.append(["Įmonė", company[0]["name"]])
        info.append(["Valiuta", company[0]["currency_id"][1]])
        info.append(["Apimtis", "Visos įmonės vidinės vietos, įmonės atsargos"])
        info.append(["Šaltinis", "Odoo Inventory Aging, Remaining Qty ir Remaining Value"])
        info.append(["Amžius", "Pagal Odoo vertinimo sluoksnio datą"])
        info.column_dimensions["A"].width = 18
        info.column_dimensions["B"].width = 68
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"Inventory_Aging_{extracted:%Y%m%d_%H%M%S_%f}.xlsx"
        workbook.save(path)
        print(f"Ataskaita sukurta: {path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    InventoryAgingReport(OdooClient(OdooConfig.from_env())).run(args.output_dir)


if __name__ == "__main__":
    main()
