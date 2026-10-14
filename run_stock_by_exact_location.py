from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Font

from core.config import OdooConfig
from core.odoo_client import OdooClient
from run_stock_by_location import StockByLocationReport


class StockByExactLocationReport(StockByLocationReport):
    """Read-only stock quantities grouped by product and exact internal location."""

    LOCATION_COLUMNS = ["Location ID", "Location", "On Hand", "Reserved", "Available"]

    def load_exact_balances(self, product_ids: set[int]):
        quant_ids = self.client.search(
            "stock.quant",
            [("location_id.usage", "=", "internal"),
             "|", ("quantity", "!=", 0), ("reserved_quantity", "!=", 0)],
        )
        quants = self.read_in_batches(
            model="stock.quant", record_ids=quant_ids,
            fields=["product_id", "location_id", "quantity", "reserved_quantity"],
        )
        balances = defaultdict(lambda: {"on_hand": 0.0, "reserved": 0.0})
        for quant in quants:
            product_id = self.many2one_id(quant.get("product_id"))
            location_id = self.many2one_id(quant.get("location_id"))
            if product_id not in product_ids or location_id is None:
                continue
            balance = balances[(product_id, location_id)]
            balance["on_hand"] += float(quant.get("quantity") or 0)
            balance["reserved"] += float(quant.get("reserved_quantity") or 0)
        locations = self.read_map(
            model="stock.location",
            record_ids={location_id for _, location_id in balances},
            fields=["complete_name"],
        )
        return dict(balances), locations

    def build_exact_rows(self, products, buy_product_ids, last_purchases, balances, locations):
        # Reuse existing product/purchase metadata without WH/C aggregate columns.
        metadata_rows = self.build_rows(
            products=products, buy_product_ids=buy_product_ids,
            wh_balances={}, c_balances={}, last_purchases=last_purchases,
        )
        # Match by product ID rather than SKU: duplicate codes must not merge products.
        sorted_products = sorted(products, key=lambda product: str(product.get("default_code") or "").lower())
        metadata = {
            int(product["id"]): {key: value for key, value in row.items()
                                 if not key.startswith(("WH ", "C "))}
            for product, row in zip(sorted_products, metadata_rows)
        }
        rows = []
        for (product_id, location_id), balance in balances.items():
            on_hand, reserved = balance["on_hand"], balance["reserved"]
            if on_hand == 0 and reserved == 0:
                continue
            location = locations.get(location_id, {}).get("complete_name")
            if not location:
                raise ValueError(f"Nepavyko nuskaityti lokacijos {location_id} pilno kelio.")
            rows.append({**metadata[product_id], "Location ID": location_id,
                         "Location": location, "On Hand": on_hand,
                         "Reserved": reserved, "Available": on_hand - reserved})
        return sorted(rows, key=lambda row: (str(row["SKU"]).lower(), str(row["Location"]), row["Location ID"]))

    def run(self, output_dir: str = "output") -> Path:
        products = self.load_products()
        print(f"Rasta produktų: {len(products)}")
        categories = self.load_categories(products)
        buy_product_ids = self.find_buy_product_ids(products=products, categories=categories)
        balances, locations = self.load_exact_balances({int(p["id"]) for p in products})
        last_purchases = self.load_last_purchases(buy_product_ids)
        rows = self.build_exact_rows(products, buy_product_ids, last_purchases, balances, locations)
        incoming_po = self.load_active_po_remaining(products)
        # Incoming PO is a global SKU quantity, not a physical location balance.
        totals: dict[str, dict[str, Any]] = {}
        for product in products:
            sku = str(product.get("default_code") or "")
            totals.setdefault(sku, {"SKU": sku, "On Hand": 0.0, "Reserved": 0.0,
                                    "Available": 0.0, self.INCOMING_PO_COLUMN: incoming_po.get(sku, 0.0)})
        for row in rows:
            for column in ("On Hand", "Reserved", "Available"):
                totals[str(row["SKU"])][column] += row[column]
        summary = sorted(totals.values(), key=lambda row: row["SKU"].lower())
        path = self.export_exact_excel(rows, summary, output_dir)
        print(f"Lokacijų: {len(locations)}; SKU/lokacijos eilučių: {len(rows)}")
        print(f"Ataskaita sukurta: {path}")
        return path

    @classmethod
    def export_exact_excel(cls, rows, summary, output_dir: str) -> Path:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"SKU_Stock_By_Location_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx"
        columns = ["SKU", "Product", "Product Category Name", "UoM", "Buy", "Last Supplier",
                   "Last Purchase Price", "Purchase Currency", *cls.LOCATION_COLUMNS]
        summary_columns = ["SKU", "On Hand", "Reserved", "Available", cls.INCOMING_PO_COLUMN]
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(rows, columns=columns).to_excel(writer, index=False, sheet_name="Stock by Location")
            pd.DataFrame(summary, columns=summary_columns).to_excel(writer, index=False, sheet_name="SKU Summary")
            for worksheet in writer.book.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions
                for cell in worksheet[1]:
                    cell.font = Font(bold=True)
                for cells in worksheet.columns:
                    worksheet.column_dimensions[cells[0].column_letter].width = min(
                        max(max(len(str(cell.value or "")) for cell in cells) + 2, 12), 60)
                    if cells[0].value in ("On Hand", "Reserved", "Available", cls.INCOMING_PO_COLUMN, "Last Purchase Price"):
                        for cell in cells[1:]:
                            cell.number_format = "#,##0.0000"
        return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="SKU likučiai kiekvienoje konkrečioje vidinėje lokacijoje")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    try:
        StockByExactLocationReport(OdooClient(OdooConfig.from_env())).run(args.output_dir)
        return 0
    except Exception as exc:
        print(f"Ataskaitos generavimo klaida: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
