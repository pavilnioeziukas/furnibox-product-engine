from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.config import OdooConfig
from core.odoo_client import OdooClient, OdooConnectionError
from reports.stock_by_location import StockByLocationReport as BaseStockByLocationReport


class StockByLocationReport(BaseStockByLocationReport):
    """Stock report extended with quantities still due on confirmed POs."""

    PURCHASE_ORDER_LINE_FIELDS = [
        "product_id",
        "product_qty",
        "qty_received",
        "product_uom",
    ]
    UOM_FIELDS = ["category_id", "factor", "factor_inv", "rounding"]
    ACTIVE_PO_STATES = ["purchase", "done"]
    INCOMING_PO_COLUMN = "Aktyviuose PO dar negauta"

    def run(self) -> None:
        print("\n====================================")
        print("SKU LIKUČIAI PAGAL LOKACIJĄ")
        print("====================================")
        print("\nNuskaitomi aktyvūs stockable produktai...")

        products = self.load_products()
        print(f"Rasta produktų: {len(products)}")
        categories = self.load_categories(products)
        buy_product_ids = self.find_buy_product_ids(
            products=products,
            categories=categories,
        )
        print(f"Rasta perkamų produktų: {len(buy_product_ids)}")

        print("Nuskaitomi WH/STOCK likučiai...")
        wh_balances = self.load_location_balances(self.LOCATION_IDS["WH"])
        print("Nuskaitomi C/Stock likučiai...")
        c_balances = self.load_location_balances(self.LOCATION_IDS["C"])

        print("Nuskaitomi paskutiniai faktiniai pirkimų gavimai...")
        last_purchases = self.load_last_purchases(buy_product_ids)
        print(
            "Rasta perkamų produktų su faktiniu gavimu: "
            f"{len(last_purchases)}"
        )

        print("Skaičiuojami dar negauti aktyvių PO kiekiai...")
        incoming_po = self.load_active_po_remaining(products)

        rows = self.build_rows(
            products=products,
            buy_product_ids=buy_product_ids,
            wh_balances=wh_balances,
            c_balances=c_balances,
            last_purchases=last_purchases,
        )
        for row in rows:
            row[self.INCOMING_PO_COLUMN] = incoming_po.get(
                str(row.get("SKU") or ""), 0.0
            )

        output_path = self.export_to_excel(rows)
        print("\nAtaskaita sukurta:")
        print(output_path)

    def load_active_po_remaining(
        self,
        products: list[dict[str, Any]],
    ) -> dict[str, float]:
        product_by_id = {int(product["id"]): product for product in products}
        if not product_by_id:
            return {}

        line_ids = self.client.search(
            "purchase.order.line",
            [
                ("state", "in", self.ACTIVE_PO_STATES),
            ],
        )
        lines = self.read_in_batches(
            model="purchase.order.line",
            record_ids=line_ids,
            fields=self.PURCHASE_ORDER_LINE_FIELDS,
        )

        uom_ids = {
            uom_id
            for record in [*products, *lines]
            if (uom_id := self.many2one_id(
                record.get("uom_id") or record.get("product_uom")
            )) is not None
        }
        uoms = self.read_map(
            model="uom.uom",
            record_ids=uom_ids,
            fields=self.UOM_FIELDS,
        )

        remaining_by_sku: dict[str, float] = defaultdict(float)
        for line in lines:
            product_id = self.many2one_id(line.get("product_id"))
            product = product_by_id.get(product_id or 0)
            if product is None:
                continue

            ordered = float(line.get("product_qty") or 0.0)
            received = float(line.get("qty_received") or 0.0)
            remaining = ordered - received
            source_uom_id = self.many2one_id(line.get("product_uom"))
            target_uom_id = self.many2one_id(product.get("uom_id"))
            source_uom = uoms.get(source_uom_id or 0, {})
            target_uom = uoms.get(target_uom_id or 0, {})
            tolerance = float(source_uom.get("rounding") or 0.0) / 2
            if remaining <= tolerance:
                continue

            converted = self.convert_uom_quantity(
                remaining,
                source_uom=source_uom,
                target_uom=target_uom,
            )
            sku = str(product.get("default_code") or "")
            remaining_by_sku[sku] += converted

        return dict(remaining_by_sku)

    @classmethod
    def convert_uom_quantity(
        cls,
        quantity: float,
        *,
        source_uom: dict[str, Any],
        target_uom: dict[str, Any],
    ) -> float:
        if not source_uom or not target_uom:
            raise ValueError("Nepavyko nuskaityti PO arba produkto matavimo vieneto.")

        source_category = cls.many2one_id(source_uom.get("category_id"))
        target_category = cls.many2one_id(target_uom.get("category_id"))
        if source_category != target_category:
            raise ValueError("PO ir produkto matavimo vienetų kategorijos nesutampa.")

        source_factor = float(source_uom.get("factor") or 0.0)
        target_factor = float(target_uom.get("factor") or 0.0)
        if source_factor <= 0 or target_factor <= 0:
            raise ValueError("Odoo grąžino netinkamą matavimo vieneto koeficientą.")

        return quantity / source_factor * target_factor


def main() -> int:
    try:
        report = StockByLocationReport(OdooClient(OdooConfig.from_env()))
        report.run()
        return 0
    except ValueError as exc:
        print(f"Konfigūracijos klaida: {exc}")
        return 1
    except OdooConnectionError as exc:
        print(f"Odoo klaida: {exc}")
        return 1
    except Exception as exc:
        print(f"Ataskaitos generavimo klaida: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
