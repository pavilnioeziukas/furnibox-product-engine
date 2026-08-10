"""Eksportuoja paskutinę patvirtintą kiekvieno produkto pirkimo kainą iš Odoo."""

from __future__ import annotations

import logging
from copy import copy
from datetime import datetime

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from config import load_settings
from excel_writer import HEADER_FILL, HEADER_FONT
from odoo_client import OdooClient

EXPORT_COLUMNS = [
    "Internal Reference",
    "Name",
    "Product Category/Name",
    "Purchase Order",
    "Vendor",
    "Ordered Quantity",
    "Last Purchase Price",
    "Order Date",
]

CALCULATOR_COLUMNS = [
    "Adjusted Purchase Price",
    "Markup Factor",
    "Reform Price",
]

OUTPUT_COLUMNS = [
    "Real Purchase Price" if column == "Last Purchase Price" else column
    for column in EXPORT_COLUMNS
] + CALCULATOR_COLUMNS


def relation_id(value):
    return value[0] if isinstance(value, list) and value else None


def relation_name(value):
    return value[1] if isinstance(value, list) and len(value) >= 2 else ""


def build_last_purchase_prices(purchase_lines, products):
    """Sujungia naujausią PO eilutę su tikrais product.product laukais."""
    products_by_id = {row["id"]: row for row in products}
    latest_lines = {}

    for line in purchase_lines:
        product_id = relation_id(line.get("product_id"))
        if product_id is None:
            continue

        candidate_key = (line.get("date_order") or "", line.get("id") or 0)
        current = latest_lines.get(product_id)
        if current is not None:
            current_key = (current.get("date_order") or "", current.get("id") or 0)
            if candidate_key <= current_key:
                continue
        latest_lines[product_id] = line

    missing_product_ids = sorted(set(latest_lines) - set(products_by_id))
    if missing_product_ids:
        preview = ", ".join(map(str, missing_product_ids[:10]))
        suffix = "..." if len(missing_product_ids) > 10 else ""
        raise RuntimeError(
            "Odoo negrąžino product.product įrašų šiems ID: "
            f"{preview}{suffix}"
        )

    rows = []
    for product_id in sorted(latest_lines):
        line = latest_lines[product_id]
        product = products_by_id[product_id]
        rows.append({
            "Internal Reference": product.get("default_code") or "",
            "Name": product.get("name") or "",
            "Product Category/Name": relation_name(product.get("categ_id")),
            "Purchase Order": relation_name(line.get("order_id")),
            "Vendor": relation_name(line.get("partner_id")),
            "Ordered Quantity": line.get("product_qty"),
            "Last Purchase Price": line.get("price_unit"),
            "Order Date": line.get("date_order") or "",
        })

    return rows


def load_last_purchase_prices(client):
    """Nuskaito PO eilutes ir atskirus produktų laukus iš Odoo."""
    purchase_lines = client.purchase_order_lines()
    product_ids = {
        relation_id(line.get("product_id"))
        for line in purchase_lines
        if relation_id(line.get("product_id")) is not None
    }
    products = client.search_read_all(
        "product.product",
        [["id", "in", sorted(product_ids)]],
        ["id", "default_code", "name", "categ_id"],
        context={"active_test": False},
    ) if product_ids else []
    return build_last_purchase_prices(purchase_lines, products)


def write_purchase_prices(path, purchase_prices, metadata):
    """Sukuria komponentų pirkimo ir Reform kainų skaičiuoklę."""
    workbook = Workbook()

    info = workbook.active
    info.title = "INFO"
    for row in [
        ("Generated", datetime.now().isoformat(sep=" ", timespec="seconds")),
        ("Odoo URL", metadata["url"]),
        ("Database", metadata["db"]),
        ("User", metadata["login"]),
        ("Odoo UID", metadata["uid"]),
        ("Products with Last Purchase Price", len(purchase_prices)),
    ]:
        info.append(row)
    info.column_dimensions["A"].width = 36
    info.column_dimensions["B"].width = 45

    prices = workbook.create_sheet("LAST PURCHASE PRICES")
    invalid_columns = [
        key
        for row in purchase_prices
        for key in row
        if key not in EXPORT_COLUMNS
    ]
    if invalid_columns:
        raise RuntimeError(
            "Eksporte aptikti neleistini stulpeliai: "
            + ", ".join(sorted(set(invalid_columns)))
        )

    prices.title = "COMPONENT PRICES"
    prices.append(OUTPUT_COLUMNS)
    for row in purchase_prices:
        prices.append(
            [row.get(column, "") for column in EXPORT_COLUMNS]
            + [row.get("Last Purchase Price"), 1.0, None]
        )

    for row_number in range(2, prices.max_row + 1):
        prices.cell(row_number, 11).value = (
            f'=IF(I{row_number}="",G{row_number},I{row_number})*J{row_number}'
        )

    for cell in prices[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        alignment = copy(cell.alignment)
        alignment.horizontal = "center"
        alignment.vertical = "center"
        alignment.wrap_text = True
        cell.alignment = alignment

    prices.freeze_panes = "A2"
    prices.auto_filter.ref = prices.dimensions

    column_widths = [22, 45, 38, 20, 35, 18, 19, 21, 25, 16, 18]
    for index, width in enumerate(column_widths, start=1):
        column_letter = prices.cell(row=1, column=index).column_letter
        prices.column_dimensions[column_letter].width = width

    input_fill = PatternFill("solid", fgColor="FFF2CC")
    formula_fill = PatternFill("solid", fgColor="E2F0D9")
    for row_number in range(2, prices.max_row + 1):
        prices.cell(row_number, 7).number_format = '0.0000 [$€-x-euro2]'
        prices.cell(row_number, 9).number_format = '0.0000 [$€-x-euro2]'
        prices.cell(row_number, 10).number_format = "0.00"
        prices.cell(row_number, 11).number_format = '0.0000 [$€-x-euro2]'
        prices.cell(row_number, 9).fill = input_fill
        prices.cell(row_number, 10).fill = input_fill
        prices.cell(row_number, 11).fill = formula_fill

    markup_validation = DataValidation(
        type="decimal",
        operator="between",
        formula1="1",
        formula2="5",
        allow_blank=False,
    )
    markup_validation.error = "Įrašykite koeficientą nuo 1,00 iki 5,00."
    markup_validation.errorTitle = "Netinkamas antkainio koeficientas"
    markup_validation.prompt = "1,00 – be antkainio; 1,05 – 5 % antkainis."
    markup_validation.promptTitle = "Markup Factor"
    markup_validation.showErrorMessage = True
    markup_validation.showInputMessage = True
    prices.add_data_validation(markup_validation)
    markup_validation.add(f"J2:J{prices.max_row}")

    prices.conditional_formatting.add(
        f"J2:J{prices.max_row}",
        FormulaRule(
            formula=["J2<>1"],
            fill=PatternFill("solid", fgColor="FCE4D6"),
        ),
    )

    note = workbook.create_sheet("PRICING RULES", 1)
    note.append(["Field", "Rule"])
    note.append(["Real Purchase Price", "Last confirmed purchase price from Odoo."])
    note.append(["Adjusted Purchase Price", "Editable input; initially equals Real Purchase Price."])
    note.append(["Markup Factor", "Editable input; 1.00 = no markup, 1.05 = 5% markup."])
    note.append(["Reform Price", "Adjusted Purchase Price × Markup Factor; use as Reform Sales Price."])
    for cell in note[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    note.column_dimensions["A"].width = 28
    note.column_dimensions["B"].width = 78
    note.freeze_panes = "A2"

    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"

    workbook.save(path)


def main():
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(
                settings.log_dir / "last_purchase_prices.log",
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    client = OdooClient(settings)

    logging.info("Jungiamasi prie Odoo...")
    uid = client.authenticate()
    logging.info("Prisijungta. UID=%s", uid)

    logging.info("Nuskaitomos patvirtintų ir užbaigtų pirkimų eilutės...")
    purchase_prices = load_last_purchase_prices(client)
    logging.info("Produktų su paskutine pirkimo kaina: %s", len(purchase_prices))

    output_path = settings.output_dir / "Last_Purchase_Prices.xlsx"
    write_purchase_prices(
        output_path,
        purchase_prices,
        {
            "url": settings.url,
            "db": settings.db,
            "login": settings.login,
            "uid": uid,
        },
    )

    print()
    print("KOMPONENTŲ PIRKIMO IR REFORM KAINŲ FAILAS SUKURTAS")
    print("Failas:", output_path)
    print("Produktai su kaina:", len(purchase_prices))


if __name__ == "__main__":
    main()
