"""Generate a read-only SO supply-status report for the web application."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.bom_engine import BomEngine
from core.bom_repository import BomRepository
from core.bom_selector import BomSelector
from core.config import OdooConfig
from core.dataset_execution_engine import DatasetExecutionEngine
from core.odoo_client import OdooClient
from validators.furnix_po_validator import FurnixPoValidator


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Furnix SO supply-status report")
    result.add_argument("--so-number", required=True)
    result.add_argument("--output-dir", required=True)
    return result


def row_payload(row: Any) -> dict[str, Any]:
    return {
        "sku": row.sku,
        "product_name": row.product_name,
        "required_qty": row.required_qty,
        "po_qty": row.po_qty,
        "difference": row.difference,
        "status": row.status,
        "origins": row.origins,
        "component_sticker_info": row.component_sticker_info,
        "sticker_status": row.sticker_status,
        "sticker_note": row.sticker_error,
        "received_qty": row.received_qty,
        "input_custom_qty": row.input_custom_qty,
        "sorted_qty": row.sorted_qty,
        "sorting_pending_qty": row.sorting_pending_qty,
        "mo_demand_qty": row.mo_demand_qty,
        "mo_reserved_qty": row.mo_reserved_qty,
        "cross_so_reserved_qty": row.cross_so_reserved_qty,
        "cross_so_reservations": row.cross_so_reservations,
        "supply_status": row.supply_status,
        "supply_note": row.supply_error,
        "receipt_numbers": row.receipt_names,
        "sorting_numbers": row.sorting_names,
        "mo_numbers": row.mo_names,
    }


def count_supply_status(rows: list[Any], status: str) -> int:
    return sum(row.supply_status == status for row in rows)


def total(rows: list[Any], field_name: str) -> float:
    return sum(float(getattr(row, field_name, 0.0) or 0.0) for row in rows)

def mo_missing_qty(row: Any) -> float:
    return max(
        float(row.mo_demand_qty or 0.0)
        - float(row.mo_reserved_qty or 0.0),
        0.0,
    )

def main() -> None:
    args = parser().parse_args()
    so_number = args.so_number.strip().upper()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OdooClient(OdooConfig.from_env())
    client.connect()

    repository = BomRepository(client)
    selector = BomSelector(repository)
    execution_engine = DatasetExecutionEngine(
        client,
        BomEngine(repository, selector),
        environment="production",
    )
    result = FurnixPoValidator(client, execution_engine).validate(so_number)

    rows = [row_payload(row) for row in result.rows]
    supply_readiness = (
        "PARUOŠTA GAMYBAI"
        if result.status == "PASS"
        and bool(result.rows)
        and all(row.supply_status == "AVAILABLE / RESERVED" for row in result.rows)
        else "DAR NEPARUOŠTA GAMYBAI"
    )

    report = {
        "so_number": result.so_number,
        "po_number": result.po_number,
        "po_state": result.po_state,
        "vendor_name": result.vendor_name,
        "furnix_po_count": result.furnix_po_count,
        "data_quality_status": result.status,
        "supply_readiness": supply_readiness,
        "mo_reserved_qty": total(result.rows, "mo_reserved_qty"),
        "mo_demand_qty": total(result.rows, "mo_demand_qty"),
        "error": result.error,
        "warnings": result.warnings,
        "dataset_id": result.dataset_id,
        "batch_reference": result.batch_reference,
        "fallback_count": result.fallback_count,
        "fallbacks": result.fallbacks,
        "summary": {
            "total_rows": len(result.rows),
            "bom_po_mismatches": sum(row.status != "PASS" for row in result.rows),
            "mo_missing_sku_count": sum(
                mo_missing_qty(row) > 0.0
                for row in result.rows
            ),
            "mo_missing_qty_total": sum(
                mo_missing_qty(row)
                for row in result.rows
            ),
            "sticker_issues": result.sticker_error_count,
            "reserved_for_mo": count_supply_status(
                result.rows, "AVAILABLE / RESERVED"
            ),
            "waiting_for_receipt": count_supply_status(
                result.rows, "NOT RECEIVED"
            ),
            "waiting_for_sorting": (
                count_supply_status(result.rows, "SORTING NOT DONE")
                + count_supply_status(result.rows, "SORTING PARTIAL")
            ),
            "mo_not_reserved": count_supply_status(
                result.rows, "MO NOT RESERVED"
            ),
            "requires_investigation": result.supply_issue_count,
        },
        "rows": rows,
    }

    report_path = output_dir / f"SO_Tiekimo_Bukle_{so_number}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"SO: {result.so_number}")
    print(f"TIEKIMO BŪKLĖ: {report['supply_readiness']}")
    print(
        f"MO rezervuota: {report['mo_reserved_qty']:g} / "
        f"{report['mo_demand_qty']:g}"
    )
    print(f"PO: {result.po_number or '-'} ({result.po_state or '-'})")
    print(f"Duomenų kokybė: {result.status}")
    if result.error:
        print(f"Pastaba: {result.error}")
    for key, value in report["summary"].items():
        print(f"{key}: {value}")
    print(f"Ataskaita: {report_path}")


if __name__ == "__main__":
    main()
