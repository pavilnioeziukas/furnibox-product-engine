"""Read-only component reservation audit scoped to one sales order."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from odoo_supply_chain_audit import read_records, relation_id, relation_name


FINAL_STATES = {"done", "cancel"}


@dataclass(frozen=True)
class ReservationRow:
    mo: str
    mo_state: str
    finished_product: str
    component: str
    demand: float
    reserved: float
    missing: float
    move_state: str
    status: str


def reservation_status(mo_state: str, demand: float, reserved: float) -> str:
    if mo_state in FINAL_STATES:
        return "MO_CLOSED"
    missing = max(demand - reserved, 0.0)
    if missing <= 1e-6:
        return "RESERVED"
    if reserved > 1e-6:
        return "PARTIALLY_RESERVED"
    return "NOT_RESERVED"


def audit_so_reservations(client: Any, so_number: str) -> dict[str, Any]:
    normalized = str(so_number or "").strip().upper()
    orders = client.search_read_all(
        "sale.order",
        [["name", "=", normalized]],
        ["name", "state"],
    )
    if not orders:
        raise ValueError(f"SO nerastas: {normalized}")

    order = orders[0]
    productions = client.search_read_all(
        "mrp.production",
        [["sale_primary_id", "=", int(order["id"])]],
        [
            "name",
            "state",
            "product_id",
            "product_qty",
            "qty_produced",
            "move_raw_ids",
        ],
        order="name asc",
    )
    moves = read_records(
        client,
        "stock.move",
        [move_id for mo in productions for move_id in mo.get("move_raw_ids", [])],
        [
            "product_id",
            "raw_material_production_id",
            "product_uom_qty",
            "quantity",
            "state",
        ],
    )
    production_by_id = {int(row["id"]): row for row in productions}
    rows: list[ReservationRow] = []
    for move in moves:
        production = production_by_id.get(
            relation_id(move.get("raw_material_production_id")) or -1
        )
        if not production or move.get("state") == "cancel":
            continue
        demand = float(move.get("product_uom_qty") or 0.0)
        reserved = float(move.get("quantity") or 0.0)
        mo_state = str(production.get("state") or "")
        rows.append(
            ReservationRow(
                mo=str(production.get("name") or ""),
                mo_state=mo_state,
                finished_product=relation_name(production.get("product_id")),
                component=relation_name(move.get("product_id")),
                demand=demand,
                reserved=reserved,
                missing=max(demand - reserved, 0.0),
                move_state=str(move.get("state") or ""),
                status=reservation_status(mo_state, demand, reserved),
            )
        )

    active_rows = [row for row in rows if row.mo_state not in FINAL_STATES]
    return {
        "so_number": normalized,
        "so_state": str(order.get("state") or ""),
        "mo_count": len(productions),
        "active_mo_count": sum(
            str(mo.get("state") or "") not in FINAL_STATES for mo in productions
        ),
        "component_move_count": len(rows),
        "not_reserved_count": sum(row.status == "NOT_RESERVED" for row in active_rows),
        "partially_reserved_count": sum(
            row.status == "PARTIALLY_RESERVED" for row in active_rows
        ),
        "missing_qty_total": sum(row.missing for row in active_rows),
        "rows": [asdict(row) for row in rows],
    }


def write_reservation_report(report: dict[str, Any], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"SO_Reservation_Audit_{report['so_number']}"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = list(ReservationRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["rows"])
    return [json_path, csv_path]
