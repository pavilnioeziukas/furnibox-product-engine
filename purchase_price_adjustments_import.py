from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


SOURCE_SKU_COLUMN = "Invoice lines/Product/Internal Reference"
SOURCE_REAL_PRICE_COLUMN = "Reali pirkimo kaina"
SOURCE_ADJUSTED_PRICE_COLUMN = "Adjustint kaina"


@dataclass(frozen=True)
class PurchasePriceAdjustmentCandidate:
    sku: str
    excel_real_price: float | None
    current_adjustment: float | None
    new_adjustment: float
    status: str


def _headers(sheet) -> dict[str, int]:
    return {
        str(cell.value).strip(): cell.column
        for cell in sheet[1]
        if cell.value not in (None, "")
    }


def _to_float(
    value: Any,
    *,
    field_name: str,
    sku: str,
    allow_empty: bool = False,
) -> float | None:
    if value in (None, ""):
        if allow_empty:
            return None
        raise ValueError(
            f"SKU {sku}: laukas '{field_name}' negali būti tuščias."
        )

    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"SKU {sku}: laukas '{field_name}' nėra skaičius: {value!r}"
        ) from exc


def load_purchase_price_excel_adjustments(
    path: Path,
) -> dict[str, dict[str, float | None]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Nerastas Pirkimo kain? Excel failas: {path}"
        )

    workbook = load_workbook(
        path,
        data_only=True,
        read_only=True,
    )

    sheet = workbook.active
    columns = _headers(sheet)

    required_columns = (
        SOURCE_SKU_COLUMN,
        SOURCE_REAL_PRICE_COLUMN,
        SOURCE_ADJUSTED_PRICE_COLUMN,
    )

    for required in required_columns:
        if required not in columns:
            workbook.close()
            raise ValueError(
                f"Pirkimo kain? Excel faile nerastas stulpelis: {required}"
            )

    result: dict[str, dict[str, float | None]] = {}
    duplicates: set[str] = set()

    for row_number in range(2, sheet.max_row + 1):
        raw_sku = sheet.cell(
            row_number,
            columns[SOURCE_SKU_COLUMN],
        ).value

        if raw_sku in (None, ""):
            continue

        sku = str(raw_sku).strip()

        raw_adjusted_price = sheet.cell(
            row_number,
            columns[SOURCE_ADJUSTED_PRICE_COLUMN],
        ).value

        if raw_adjusted_price in (None, ""):
            continue

        if sku in result:
            duplicates.add(sku)
            continue

        excel_real_price = _to_float(
            sheet.cell(
                row_number,
                columns[SOURCE_REAL_PRICE_COLUMN],
            ).value,
            field_name=SOURCE_REAL_PRICE_COLUMN,
            sku=sku,
            allow_empty=True,
        )

        adjusted_price = _to_float(
            raw_adjusted_price,
            field_name=SOURCE_ADJUSTED_PRICE_COLUMN,
            sku=sku,
        )

        assert adjusted_price is not None

        result[sku] = {
            "excel_real_price": excel_real_price,
            "new_adjustment": adjusted_price,
        }

    workbook.close()

    if duplicates:
        preview = ", ".join(sorted(duplicates)[:20])
        raise ValueError(
            "Pirkimo kain? Excel faile kartojasi SKU: "
            f"{preview}"
        )

    return result


def build_adjustment_preview(
    excel_adjustments: dict[str, dict[str, float | None]],
    current_adjustments: dict[str, dict[str, Any]],
) -> list[PurchasePriceAdjustmentCandidate]:
    rows: list[PurchasePriceAdjustmentCandidate] = []

    for sku in sorted(
        excel_adjustments,
        key=str.casefold,
    ):
        excel_row = excel_adjustments[sku]

        current_document = current_adjustments.get(sku)
        current_adjustment = None

        if current_document is not None:
            current_adjustment = float(
                current_document["adjusted_purchase_price"]
            )

        new_adjustment = float(
            excel_row["new_adjustment"]
        )

        if current_adjustment is None:
            status = "NEW"
        elif current_adjustment == new_adjustment:
            status = "SAME"
        else:
            status = "CHANGED"

        rows.append(
            PurchasePriceAdjustmentCandidate(
                sku=sku,
                excel_real_price=excel_row["excel_real_price"],
                current_adjustment=current_adjustment,
                new_adjustment=new_adjustment,
                status=status,
            )
        )

    return rows


def summarize_preview(
    rows: list[PurchasePriceAdjustmentCandidate],
) -> dict[str, int]:
    summary = {
        "TOTAL": len(rows),
        "NEW": 0,
        "CHANGED": 0,
        "SAME": 0,
    }

    for row in rows:
        summary[row.status] += 1

    return summary