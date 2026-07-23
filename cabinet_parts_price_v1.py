"""Paruošia naujų Cabinet Parts kainų skaičiavimo failą.

Šaltinis – 6 veiksmo MAP_Comparison.xlsx:
* NEW PRODUCTS nustato, kurios produktų kortelės yra naujos;
* NEW BOM LINES pateikia FPACK, detalės SKU ir kiekį.

Scenarijus tik sukuria Excel failą. Odoo duomenų nekeičia.
"""

from __future__ import annotations

from collections import defaultdict
import os
from pathlib import Path
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from output_paths import environment_output_dir


BASE_DIR = Path(__file__).resolve().parent
SOURCE_NAME = "MAP_Comparison.xlsx"
OUTPUT_NAME = "New_Cabinet_Parts_Prices.xlsx"
DIMENSION_RE = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)(?!\d)"
)


def canon(value: object) -> str:
    return str(value or "").strip().upper()


def parse_number(value: str) -> int | float:
    number = float(value.replace(",", "."))
    return int(number) if number.is_integer() else number


def parse_dimensions(sku: str) -> tuple[int | float, int | float] | None:
    match = DIMENSION_RE.search(sku)
    if not match:
        return None
    return parse_number(match.group(1)), parse_number(match.group(2))


def header_map(ws) -> dict[str, int]:
    result: dict[str, int] = {}
    for cell in ws[1]:
        name = str(cell.value or "").strip()
        if name:
            result[name] = cell.column
    return result


def required_column(headers: dict[str, int], name: str, sheet_name: str) -> int:
    if name not in headers:
        raise ValueError(f"Lape '{sheet_name}' nerastas privalomas stulpelis: {name}")
    return headers[name]


def load_new_products(ws) -> tuple[dict[str, str], dict[str, tuple[int | float, int | float]]]:
    headers = header_map(ws)
    sku_col = required_column(headers, "SKU", ws.title)
    action_col = required_column(headers, "Required Action", ws.title)

    display_skus: dict[str, str] = {}
    dimensions: dict[str, tuple[int | float, int | float]] = {}
    for row in range(2, ws.max_row + 1):
        sku = str(ws.cell(row, sku_col).value or "").strip()
        action = canon(ws.cell(row, action_col).value)
        parsed = parse_dimensions(sku)
        if sku and action == "CREATE PRODUCT" and parsed:
            key = canon(sku)
            display_skus[key] = sku
            dimensions[key] = parsed
    return display_skus, dimensions


def load_fpack_lines(
    ws,
    new_skus: dict[str, str],
) -> tuple[list[tuple[str, str, float]], list[str]]:
    headers = header_map(ws)
    parent_col = required_column(headers, "Parent SKU", ws.title)
    component_col = required_column(headers, "Component SKU", ws.title)
    quantity_col = required_column(headers, "Quantity", ws.title)

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    invalid_quantities: list[str] = []
    for row in range(2, ws.max_row + 1):
        parent = str(ws.cell(row, parent_col).value or "").strip()
        component = str(ws.cell(row, component_col).value or "").strip()
        parent_key = canon(parent)
        component_key = canon(component)
        if not parent_key.startswith("FPACK-") or component_key not in new_skus:
            continue
        raw_quantity = ws.cell(row, quantity_col).value
        try:
            quantity = float(str(raw_quantity).replace(",", "."))
        except (TypeError, ValueError):
            invalid_quantities.append(
                f"{parent} / {component}: netinkamas kiekis '{raw_quantity}'"
            )
            continue
        key = (parent_key, component_key)
        if key not in grouped:
            grouped[key] = {
                "parent": parent,
                "component": new_skus[component_key],
                "quantity": 0.0,
            }
        grouped[key]["quantity"] = float(grouped[key]["quantity"]) + quantity

    rows = [
        (
            str(value["parent"]),
            str(value["component"]),
            float(value["quantity"]),
        )
        for value in grouped.values()
    ]
    rows.sort(key=lambda item: (canon(item[0]), canon(item[1])))
    return rows, invalid_quantities


def style_output(ws, last_row: int) -> None:
    dark_fill = PatternFill("solid", fgColor="1F4E78")
    light_fill = PatternFill("solid", fgColor="D9EAF7")
    group_fill = PatternFill("solid", fgColor="E9ECEF")
    white_font = Font(color="FFFFFF", bold=True)
    thin_gray = Side(style="thin", color="D9E2F3")
    medium_blue = Side(style="medium", color="5B9BD5")

    for cell in ws[1]:
        cell.fill = dark_fill
        cell.font = white_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{last_row}"
    ws.sheet_view.showGridLines = False

    widths = {
        "A": 30, "B": 30, "C": 42, "D": 15,
        "E": 3, "F": 3, "G": 3, "H": 3,
        "I": 18, "J": 13, "K": 13, "L": 17,
    }
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    for row in range(2, last_row + 1):
        ws.cell(row, 4).number_format = "General"
        ws.cell(row, 9).number_format = '#,##0.00 [$€-x-euro2]'
        ws.cell(row, 10).number_format = "General"
        ws.cell(row, 11).number_format = "General"
        ws.cell(row, 12).number_format = "0.0000"
        for col in range(1, 13):
            ws.cell(row, col).alignment = Alignment(vertical="center")
            ws.cell(row, col).border = Border(bottom=thin_gray)
        if ws.cell(row, 1).value:
            for col in range(1, 13):
                ws.cell(row, col).fill = group_fill
                ws.cell(row, col).border = Border(top=medium_blue, bottom=thin_gray)
            ws.cell(row, 1).font = Font(bold=True)
        ws.cell(row, 9).fill = light_fill


def build_workbook(
    source_path: Path,
    output_path: Path,
) -> tuple[int, int, int, int]:
    source_wb = load_workbook(source_path, read_only=False, data_only=False)
    required_sheets = {"NEW PRODUCTS", "NEW BOM LINES"}
    missing_sheets = sorted(required_sheets - set(source_wb.sheetnames))
    if missing_sheets:
        raise ValueError("Trūksta lapų: " + ", ".join(missing_sheets))

    new_skus, dimensions = load_new_products(source_wb["NEW PRODUCTS"])
    lines, invalid_quantities = load_fpack_lines(
        source_wb["NEW BOM LINES"],
        new_skus,
    )

    used_new_skus = {canon(component) for _, component, _ in lines}
    unused_new_skus = sorted(set(new_skus) - used_new_skus)

    wb = Workbook()
    ws = wb.active
    ws.title = "Cabinet part kainso"
    headers = [
        "Product/Internal Reference",
        "FPACK SKU",
        "BoM Lines/Component/Internal Reference",
        "BoM Lines/Quantity",
        None, None, None, None,
        "detaliu kaina",
        "matmuo 1, mm",
        "matmuo 2, mm",
        "detalės plotas, m²",
    ]
    ws.append(headers)

    previous_parent = None
    for excel_row, (parent, component, quantity) in enumerate(lines, start=2):
        component_key = canon(component)
        width, height = dimensions[component_key]
        quantity_value: int | float = (
            int(quantity) if quantity.is_integer() else quantity
        )
        first_in_group = canon(parent) != canon(previous_parent)
        ws.append([
            parent if first_in_group else None,
            parent,
            component,
            quantity_value,
            None, None, None, None,
            None,
            width,
            height,
            f"=J{excel_row}*K{excel_row}*D{excel_row}/1000000",
        ])
        previous_parent = parent

    last_row = max(ws.max_row, 1)
    style_output(ws, last_row)

    diagnostics = wb.create_sheet("DIAGNOSTICS")
    diagnostics.append(["Type", "SKU / ryšys", "Message"])
    for sku in unused_new_skus:
        diagnostics.append([
            "NEW DIMENSIONAL PRODUCT NOT IN FPACK",
            new_skus[sku],
            "Nauja kortelė su matmenimis nerasta nė vienoje FPACK BOM eilutėje.",
        ])
    for message in invalid_quantities:
        diagnostics.append(["INVALID QUANTITY", message.split(":", 1)[0], message])
    for cell in diagnostics[1]:
        cell.fill = PatternFill("solid", fgColor="C00000")
        cell.font = Font(color="FFFFFF", bold=True)
    diagnostics.freeze_panes = "A2"
    diagnostics.auto_filter.ref = f"A1:C{max(diagnostics.max_row, 1)}"
    diagnostics.column_dimensions["A"].width = 42
    diagnostics.column_dimensions["B"].width = 45
    diagnostics.column_dimensions["C"].width = 75
    diagnostics.sheet_view.showGridLines = False

    info = wb.create_sheet("INFO")
    info.append(["Parameter", "Value"])
    info.append(["Source", str(source_path)])
    info.append(["New products with dimensions", len(new_skus)])
    info.append(["Rows prepared", len(lines)])
    info.append(["Unique new Cabinet Parts in FPACK", len(used_new_skus)])
    info.append(["FPACK count", len({canon(parent) for parent, _, _ in lines})])
    info.append(["Unused dimensional new products", len(unused_new_skus)])
    info.append(["Invalid quantities", len(invalid_quantities)])
    for cell in info[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(color="FFFFFF", bold=True)
    info.column_dimensions["A"].width = 40
    info.column_dimensions["B"].width = 90
    info.sheet_view.showGridLines = False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return (
        len(lines),
        len(used_new_skus),
        len({canon(parent) for parent, _, _ in lines}),
        len(unused_new_skus),
    )


def main() -> None:
    output_dir = environment_output_dir(BASE_DIR)
    source_path = output_dir / SOURCE_NAME
    if not source_path.exists():
        raise FileNotFoundError(
            f"Nerastas 6 veiksmo rezultatas:\n{source_path}\n"
            "Pirmiausia paleiskite 6 veiksmą „Palyginti MAP“."
        )

    output_path = output_dir / OUTPUT_NAME
    rows, unique_parts, fpack_count, diagnostics = build_workbook(
        source_path,
        output_path,
    )

    print("NAUJŲ CABINET PARTS KAINŲ FAILAS PARUOŠTAS")
    print(f"Aplinka: {os.environ.get('FURNIBOX_ENVIRONMENT', 'NEŽINOMA')}")
    print(f"Eilučių: {rows}")
    print(f"Unikalių naujų Cabinet Parts: {unique_parts}")
    print(f"FPACK: {fpack_count}")
    print(f"Diagnostikoje: {diagnostics}")
    print(f"Rezultatas: {output_path}")
    print("I stulpelis paliktas tuščias kainai įvesti.")


if __name__ == "__main__":
    main()
