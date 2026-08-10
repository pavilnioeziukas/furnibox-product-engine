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
        "received_qty": row.received_qty,
        "input_custom_qty": row.input_custom_qty,
        "sorted_qty": row.sorted_qty,
        "mo_demand_qty": row.mo_demand_qty,
        "mo_reserved_qty": row.mo_reserved_qty,
        "supply_status": row.supply_status,
        "supply_note": row.supply_error,
        "data_status": row.data_status,
        "data_note": row.data_error,
        "receipt_numbers": row.receipt_names,
        "sorting_numbers": row.sorting_names,
        "mo_numbers": row.mo_names,
    }


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
    report = {
        "so_number": result.so_number,
        "supply_readiness": "PARUOŠTA GAMYBAI" if result.mo_supply_ready else "DAR NEPARUOŠTA GAMYBAI",
        "mo_reserved_qty": result.mo_reserved_total,
        "mo_demand_qty": result.mo_demand_total,
        "po_number": result.po_number,
        "po_state": result.po_state,
        "data_quality_status": result.status,
        "error": result.error,
        "warnings": result.warnings,
        "summary": {
            "reserved_for_mo": result.supply_status_count("REZERVUOTA MO"),
            "waiting_for_receipt": result.supply_status_count("LAUKIAMA GAVIMO"),
            "waiting_for_sorting": result.supply_status_count("LAUKIAMA RŪŠIAVIMO"),
            "requires_investigation": result.supply_issue_count,
            "data_mismatches": sum(bool(row.data_status) for row in result.rows),
        },
        "rows": rows,
    }
    report_path = output_dir / f"SO_Tiekimo_Bukle_{so_number}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SO: {result.so_number}")
    print(f"TIEKIMO BŪKLĖ: {report['supply_readiness']}")
    print(f"MO rezervuota: {result.mo_reserved_total:g} / {result.mo_demand_total:g}")
    print(f"PO: {result.po_number or '-'} ({result.po_state or '-'})")
    print(f"Duomenų kokybė: {result.status}")
    if result.error:
        print(f"Pastaba: {result.error}")
    for key, value in report["summary"].items():
        print(f"{key}: {value}")
    print(f"Ataskaita: {report_path}")


if __name__ == "__main__":
    main()
