"""Read-only Odoo preflight for the first outstanding Furnibox #43 BOM."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from config import load_settings
from odoo_client import OdooClient

BOM_ID = 49502
OPERATION_ID = 14966
SKU = "APACK-EU-C-CAB01-BAS009-A"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    try:
        package = json.loads(args.package.read_text(encoding="utf-8-sig"))
        rows = [row for row in package["records"] if row["source_bom_id"] == BOM_ID]
        valid = (
            package["ticket"] == 43 and package["mode"] == "create_inactive_revisions"
            and len(rows) == 1 and rows[0]["sku"] == SKU and len(rows[0]["changes"]) == 1
        )
        change = rows[0]["changes"][0] if valid else {}
        valid = valid and (
            change["field"] == "operation_duration_minutes"
            and change["source_operation_id"] == OPERATION_ID
            and change["expected"] == 50 and change["desired"] == 35
        )
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        print("JSON pakete nerastas patvirtintas BOM 49502 pakeitimas.")
        return 1

    settings = load_settings()
    if urlsplit(settings.url).hostname != "odoo.furnibox.lt":
        print("Patikra skirta produkcinei odoo.furnibox.lt aplinkai.")
        return 1
    client = OdooClient(settings)
    sources = client.search_read_all(
        "mrp.bom", [["id", "=", BOM_ID]],
        ["product_tmpl_id", "product_id", "operation_ids", "code"],
    )
    if len(sources) != 1:
        print(f"Aktyvus BOM {BOM_ID} nerastas.")
        return 1
    bom = sources[0]
    product = bom["product_id"] or bom["product_tmpl_id"]
    products = client.search_read_all(
        "product.product" if bom["product_id"] else "product.template",
        [["id", "=", product[0]]], ["default_code"],
    )
    operations = client.search_read_all(
        "mrp.routing.workcenter", [["id", "=", OPERATION_ID], ["bom_id", "=", BOM_ID]],
        ["name", "time_cycle_manual"],
    )
    ecos = client.search_read_all("mrp.eco", [["bom_id", "=", BOM_ID]], ["id"])
    if (
        len(products) != 1 or products[0]["default_code"] != SKU
        or not (bom["code"] or "").startswith("BOM_for Furnibox_v10")
        or OPERATION_ID not in bom["operation_ids"] or len(operations) != 1
    ):
        print("BOM arba operacija neatitinka patvirtinto paketo.")
        return 1
    operation = operations[0]
    duration = operation["time_cycle_manual"]
    print(f"BOM {BOM_ID}, {SKU}, operacija {OPERATION_ID} ({operation['name']}).")
    print(f"Esama trukmė {duration:g} min., patvirtinta 35 min. Rasti ECO: {len(ecos)}.")
    return int(bool(ecos) or duration != 50)


if __name__ == "__main__":
    raise SystemExit(main())
