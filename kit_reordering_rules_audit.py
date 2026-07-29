"""Read-only audit of Reordering Rules for products in the generated KIT BOM file."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from config import load_settings
from odoo_client import OdooClient


KIT_FILE_NAME = "BOM_Import_KIT_lv1.xlsx"
REPORT_FILE_NAME = "KIT_Reordering_Rules_Audit.xlsx"
SKU_COLUMN = "Product/Internal Reference"


def find_kit_file(settings) -> Path:
    candidates = [
        settings.output_dir / KIT_FILE_NAME,
        Path(__file__).resolve().parent / "output" / "production" / KIT_FILE_NAME,
        Path(__file__).resolve().parent / "output" / KIT_FILE_NAME,
    ]
    for path in candidates:
        if path.exists():
            return path
    checked = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        f"Nerastas {KIT_FILE_NAME}. Patikrintos vietos:\n{checked}"
    )


def read_kit_skus(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows())]
    try:
        sku_index = headers.index(SKU_COLUMN)
    except ValueError as exc:
        raise ValueError(
            f"Faile nėra stulpelio „{SKU_COLUMN}“. Rasti stulpeliai: {headers}"
        ) from exc

    skus: list[str] = []
    seen: set[str] = set()
    for row in sheet.iter_rows(values_only=True):
        raw = row[sku_index]
        sku = str(raw).strip() if raw is not None else ""
        if sku and sku not in seen:
            seen.add(sku)
            skus.append(sku)
    return skus


def chunks(values: list, size: int = 500):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def relation_name(value) -> str:
    return str(value[1]) if isinstance(value, (list, tuple)) and len(value) > 1 else ""


def relation_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else None


def fetch_products(client: OdooClient, skus: list[str]) -> list[dict]:
    rows: list[dict] = []
    for sku_batch in chunks(skus):
        rows.extend(
            client.search_read_all(
                "product.product",
                [["default_code", "in", sku_batch]],
                [
                    "id",
                    "default_code",
                    "name",
                    "active",
                    "product_tmpl_id",
                    "categ_id",
                ],
                context={"active_test": False},
            )
        )
    return rows


def fetch_orderpoints(client: OdooClient, product_ids: list[int]) -> list[dict]:
    rows: list[dict] = []
    fields = [
        "id",
        "active",
        "product_id",
        "warehouse_id",
        "location_id",
        "company_id",
        "product_min_qty",
        "product_max_qty",
        "qty_multiple",
        "trigger",
        "route_id",
    ]
    for id_batch in chunks(product_ids):
        rows.extend(
            client.search_read_all(
                "stock.warehouse.orderpoint",
                [["product_id", "in", id_batch]],
                fields,
                context={"active_test": False},
            )
        )
    return rows


def style_sheet(sheet) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 50)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = width


def build_report(
    report_path: Path,
    source_path: Path,
    skus: list[str],
    products: list[dict],
    orderpoints: list[dict],
) -> dict:
    products_by_sku: dict[str, list[dict]] = {}
    products_by_id: dict[int, dict] = {}
    for product in products:
        products_by_sku.setdefault(product["default_code"], []).append(product)
        products_by_id[product["id"]] = product

    rule_counts = Counter(relation_id(rule["product_id"]) for rule in orderpoints)
    missing_skus = [sku for sku in skus if sku not in products_by_sku]
    duplicate_skus = {
        sku: rows for sku, rows in products_by_sku.items() if len(rows) > 1
    }
    skus_with_rules = {
        product["default_code"]
        for product in products
        if rule_counts.get(product["id"], 0) > 0
    }

    workbook = Workbook()
    summary = workbook.active
    summary.title = "SUMMARY"
    summary.append(["Rodiklis", "Reikšmė"])
    summary_rows = [
        ("Patikros laikas", datetime.now().isoformat(timespec="seconds")),
        ("Šaltinio failas", str(source_path)),
        ("Unikalūs KIT SKU", len(skus)),
        ("Odoo rasti produktų variantai", len(products)),
        ("KIT SKU su bent viena Reordering Rule", len(skus_with_rules)),
        ("Rastos Reordering Rules", len(orderpoints)),
        ("KIT SKU be Reordering Rules", len(skus) - len(skus_with_rules)),
        ("Odoo nerasti KIT SKU", len(missing_skus)),
        ("Dubliuoti SKU Odoo", len(duplicate_skus)),
        ("Pastaba", "Ataskaita tik skaitanti. Odoo duomenys nekeisti."),
    ]
    for row in summary_rows:
        summary.append(row)

    rules_sheet = workbook.create_sheet("REORDERING RULES")
    rules_sheet.append(
        [
            "SKU",
            "Produkto pavadinimas",
            "Produkto ID",
            "Produkto aktyvumas",
            "Kategorija",
            "Rule ID",
            "Rule aktyvumas",
            "Sandėlis",
            "Lokacija",
            "Min",
            "Max",
            "Multiple",
            "Trigger",
            "Route",
            "Įmonė",
        ]
    )
    for rule in sorted(orderpoints, key=lambda row: (relation_name(row["product_id"]), row["id"])):
        product_id = relation_id(rule["product_id"])
        product = products_by_id.get(product_id, {})
        rules_sheet.append(
            [
                product.get("default_code", ""),
                product.get("name", relation_name(rule["product_id"])),
                product_id,
                product.get("active", ""),
                relation_name(product.get("categ_id")),
                rule["id"],
                rule.get("active", ""),
                relation_name(rule.get("warehouse_id")),
                relation_name(rule.get("location_id")),
                rule.get("product_min_qty"),
                rule.get("product_max_qty"),
                rule.get("qty_multiple"),
                rule.get("trigger"),
                relation_name(rule.get("route_id")),
                relation_name(rule.get("company_id")),
            ]
        )

    no_rules_sheet = workbook.create_sheet("KIT WITHOUT RULES")
    no_rules_sheet.append(["SKU", "Produkto ID", "Produkto pavadinimas", "Aktyvus"])
    for sku in skus:
        rows = products_by_sku.get(sku, [])
        if not rows:
            no_rules_sheet.append([sku, "", "NERASTAS ODOO", ""])
        elif not any(rule_counts.get(product["id"], 0) for product in rows):
            for product in rows:
                no_rules_sheet.append(
                    [sku, product["id"], product["name"], product["active"]]
                )

    duplicates_sheet = workbook.create_sheet("DUPLICATE SKU")
    duplicates_sheet.append(["SKU", "Produkto ID", "Pavadinimas", "Aktyvus", "Template ID"])
    for sku, rows in sorted(duplicate_skus.items()):
        for product in rows:
            duplicates_sheet.append(
                [
                    sku,
                    product["id"],
                    product["name"],
                    product["active"],
                    relation_id(product["product_tmpl_id"]),
                ]
            )

    for sheet in workbook.worksheets:
        style_sheet(sheet)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(report_path)

    return {
        "kit_skus": len(skus),
        "products": len(products),
        "skus_with_rules": len(skus_with_rules),
        "rules": len(orderpoints),
        "missing_skus": len(missing_skus),
        "duplicate_skus": len(duplicate_skus),
    }


def main() -> int:
    try:
        settings = load_settings()
        kit_path = find_kit_file(settings)
        print(f"KIT failas: {kit_path}")
        skus = read_kit_skus(kit_path)
        print(f"Unikalūs KIT SKU: {len(skus)}")

        client = OdooClient(settings)
        client.authenticate()
        print(f"Prisijungta tik skaitymui: {settings.url}")

        products = fetch_products(client, skus)
        orderpoints = fetch_orderpoints(client, [row["id"] for row in products])
        report_path = settings.output_dir / REPORT_FILE_NAME
        result = build_report(report_path, kit_path, skus, products, orderpoints)

        print("\nPATIKROS SUVESTINĖ")
        print(f"KIT SKU: {result['kit_skus']}")
        print(f"Odoo rasti produktų variantai: {result['products']}")
        print(f"KIT SKU su Reordering Rules: {result['skus_with_rules']}")
        print(f"Reordering Rules iš viso: {result['rules']}")
        print(f"Odoo nerasti KIT SKU: {result['missing_skus']}")
        print(f"Dubliuoti SKU: {result['duplicate_skus']}")
        print(f"Ataskaita: {report_path}")
        print("Odoo duomenys nepakeisti.")
        return 0
    except Exception as exc:
        print(f"\nKLAIDA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
