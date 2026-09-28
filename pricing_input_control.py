from __future__ import annotations

import hashlib
import csv
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
    *,
    report_changes: bool = False,
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
        "status": "PASS" if matches else ("CHANGED" if report_changes else "BLOCKED"),
        "policy": "REPORT_CHANGES" if report_changes else "STRICT_BASELINE",
        "expected_sha256": expected_hash,
        "expected_record_count": expected_count,
        "reference": expectation.get("reference"),
        "approved_overlays": expectation.get("approved_overlays", []),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if report_changes:
        # Run directories are siblings under web_state/runs. Compare effective
        # inputs with the previous calculation, including an unpublished run.
        # Never label that calculation as an approved or released price list.
        previous = None
        for path in sorted(
            output_path.parent.parent.parent.glob("*/files/Pricing_Input_Snapshot.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            if path.resolve() == output_path.resolve():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                records = value["records"]
                if value.get("schema_version") != 2 or not isinstance(records, list):
                    continue
                if not all(isinstance(row, dict) and all(k in row for k in ("rule", "sku", "price")) for row in records):
                    continue
                previous = (path, records)
                break
            except (OSError, ValueError, KeyError, TypeError):
                continue
        changes = []
        if previous is not None:
            before = {(r["rule"], r["sku"].casefold()): r for r in previous[1]}
            after = {(r["rule"], r["sku"].casefold()): r for r in snapshot["records"]}
            for key in sorted(before.keys() | after.keys()):
                old, new = before.get(key), after.get(key)
                if old is not None and new is not None and old["price"] == new["price"]:
                    continue
                row = new if new is not None else old
                changes.append({
                    "rule": row["rule"], "sku": row["sku"],
                    "change": "ADDED" if old is None else ("REMOVED" if new is None else "PRICE_CHANGED"),
                    "old_price": old["price"] if old else None,
                    "new_price": new["price"] if new else None,
                    "source": (new or old).get("source", ""),
                })
        result.update(
            comparison_status="COMPARED" if previous else "NO_PREVIOUS_SNAPSHOT",
            comparison_run=previous[0].parent.parent.name if previous else None,
            comparison_basis="Previous calculated inputs, not necessarily released prices",
            change_count=len(changes) if previous else None,
            changes=changes,
        )
        report = output_path.with_name("Pirkimo_kainu_pokyciai.csv")
        with report.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Palyginimas su ankstesniu skaičiavimu (nebūtinai paskelbtu)", result["comparison_run"] or "Ankstesnių duomenų nėra – palyginimo pradžia"])
            writer.writerow(["Pokyčių skaičius", result["change_count"] if previous else "Nežinomas"])
            writer.writerow(["Taisyklė", "SKU", "Pokytis", "Ankstesnė kaina", "Nauja kaina", "Kainos šaltinis"])
            for row in changes:
                # Prevent spreadsheet formulas in externally supplied identifiers.
                writer.writerow([("'" + str(v)) if str(v).startswith(("=", "+", "-", "@")) else v for v in row.values()])
        print(f"Pirkimo kainų pokyčiai: {result['change_count'] if previous else 'pirmasis palyginimas'}. Žr. {report.name}.")
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not matches and not report_changes:
        raise ValueError(
            "R001/R007 kainų įvesties snapshotas nesutampa su patvirtintu "
            "2026-09-17 etalonu ir penkiomis patvirtintomis korekcijomis. "
            f"Faktinis SHA-256: {snapshot['sha256']}; laukiamas: {expected_hash}. "
            f"Žr. {output_path.name}."
        )
    return result
