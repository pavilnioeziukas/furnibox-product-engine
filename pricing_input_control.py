from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


DEFAULT_EXPECTATION_PATH = (
    Path(__file__).resolve().parent
    / "manifest"
    / "pricing_input_snapshot.json"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _price(value: Any) -> str:
    if value in (None, ""):
        return ""
    decimal = Decimal(str(value))
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _columns(sheet) -> dict[str, int]:
    return {
        _text(cell.value): cell.column
        for cell in sheet[1]
        if _text(cell.value)
    }


def build_pricing_input_snapshot(workbook_path: Path) -> dict[str, Any]:
    """Build a stable R001/R007 input snapshot from a completed pricing run."""
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        records: dict[tuple[str, str], dict[str, str]] = {}

        component_sheet = workbook["BOM COMPONENT COSTS"]
        component_columns = _columns(component_sheet)
        for row in component_sheet.iter_rows(min_row=2, values_only=True):
            sku = _text(row[component_columns["Purchased Component SKU"] - 1])
            if not sku:
                continue
            record = {
                "rule": "R001",
                "sku": sku,
                "price": _price(row[component_columns["Purchase Unit Price"] - 1]),
                "source": _text(row[component_columns["Cost Source"] - 1]),
            }
            key = (record["rule"], sku.casefold())
            existing = records.get(key)
            if existing is not None and existing != record:
                raise ValueError(
                    f"R001 snapshot contains conflicting prices for {sku}: "
                    f"{existing['price']} and {record['price']}"
                )
            records[key] = record

        non_bom_sheet = workbook["NON-BOM RULES"]
        non_bom_columns = _columns(non_bom_sheet)
        for row in non_bom_sheet.iter_rows(min_row=2, values_only=True):
            sku = _text(row[non_bom_columns["SKU"] - 1])
            if not sku:
                continue
            record = {
                "rule": "R007",
                "sku": sku,
                "price": _price(row[non_bom_columns["Purchase Price"] - 1]),
                "source": "NON-BOM PURCHASE PRICE",
            }
            key = (record["rule"], sku.casefold())
            existing = records.get(key)
            if existing is not None and existing != record:
                raise ValueError(f"R007 snapshot contains conflicting prices for {sku}")
            records[key] = record

        ordered = sorted(
            records.values(),
            key=lambda record: (record["rule"], record["sku"].casefold()),
        )
        canonical_prices = [
            {
                "rule": record["rule"],
                "sku": record["sku"],
                "price": record["price"],
            }
            for record in ordered
        ]
        canonical = json.dumps(
            canonical_prices,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "schema_version": 2,
            "record_count": len(ordered),
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "records": ordered,
        }
    finally:
        workbook.close()


def validate_pricing_input_snapshot(
    workbook_path: Path,
    output_path: Path,
    expectation_path: Path = DEFAULT_EXPECTATION_PATH,
) -> dict[str, Any]:
    expectation = json.loads(expectation_path.read_text(encoding="utf-8"))
    snapshot = build_pricing_input_snapshot(workbook_path)
    expected_hash = _text(expectation.get("expected_sha256"))
    expected_count = expectation.get("expected_record_count")
    matches = (
        snapshot["sha256"] == expected_hash
        and snapshot["record_count"] == expected_count
    )
    result = {
        **snapshot,
        "status": "PASS" if matches else "BLOCKED",
        "expected_sha256": expected_hash,
        "expected_record_count": expected_count,
        "reference": expectation.get("reference"),
        "approved_overlays": expectation.get("approved_overlays", []),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not matches:
        raise ValueError(
            "R001/R007 kainų įvesties snapshotas nesutampa su patvirtintu "
            "2026-09-17 etalonu ir penkiomis patvirtintomis korekcijomis. "
            f"Faktinis SHA-256: {snapshot['sha256']}; laukiamas: {expected_hash}. "
            f"Žr. {output_path.name}."
        )
    return result
