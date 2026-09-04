from pathlib import Path

from openpyxl import Workbook

from purchase_price_adjustments_import import (
    load_purchase_price_excel_adjustments,
)


def test_imports_main_tamara_adjustments_sheet(tmp_path: Path):
    path = tmp_path / "Tamara_Adjusted_Component_Prices.xlsx"
    workbook = Workbook()
    workbook.active.title = "INFO"
    sheet = workbook.create_sheet("TAMARA ADJUSTMENTS")
    sheet.append([
        "Internal Reference",
        "Adjusted Purchase Price",
        "Real Purchase Price (reference)",
        "Comment",
    ])
    sheet.append(["7001730", 1.48, 0, "Tamara"])
    sheet.append(["3284903", 0.04, 0, "Tamara"])
    sheet.append(["3503786", 0, 0, "Missing"])
    workbook.save(path)

    result = load_purchase_price_excel_adjustments(path)

    assert result == {
        "7001730": {"excel_real_price": 0.0, "new_adjustment": 1.48},
        "3284903": {"excel_real_price": 0.0, "new_adjustment": 0.04},
    }
