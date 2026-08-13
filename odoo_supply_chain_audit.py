"""Read-only Odoo audit for Furnix receipt, sorting and MO chains."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


FINAL_STATES = {"done", "cancel"}


def relation_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    return None


def relation_name(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return str(value[1])
    return ""


def batches(values: Iterable[int], size: int = 500):
    values = sorted({int(value) for value in values if value})
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def read_records(client, model: str, ids: Iterable[int], fields: list[str]):
    rows = []
    for batch in batches(ids):
        rows.extend(
            client.search_read_all(
                model,
                [["id", "in", batch]],
                fields,
            )
        )
    return rows


@dataclass(frozen=True)
class SortingAuditRow:
    classification: str
    sorting: str
    sorting_state: str
    primary_so: str
    source: str
    demand: float
    reserved: float
    receipts: str
    receipt_states: str


def classify_receipts(receipts: list[dict[str, Any]]) -> str:
    if not receipts:
        return "NO_WH_INPC_LINK"
    if any(row.get("state") not in FINAL_STATES for row in receipts):
        return "WH_INPC_NOT_DONE"
    if any(row.get("state") == "done" for row in receipts):
        return "WH_INPC_DONE"
    return "WH_INPC_CANCELLED"


def audit_open_sorting(client) -> list[SortingAuditRow]:
    pickings = client.search_read_all(
        "stock.picking",
        [["picking_type_id", "=", 5], ["state", "not in", sorted(FINAL_STATES)]],
        ["name", "state", "origin", "sale_primary_id", "move_ids"],
    )
    moves = read_records(
        client,
        "stock.move",
        [move_id for picking in pickings for move_id in picking.get("move_ids", [])],
        ["state", "product_uom_qty", "quantity", "picking_id", "move_orig_ids"],
    )
    origin_moves = read_records(
        client,
        "stock.move",
        [origin_id for move in moves for origin_id in move.get("move_orig_ids", [])],
        ["picking_id"],
    )
    receipt_pickings = read_records(
        client,
        "stock.picking",
        [relation_id(move.get("picking_id")) for move in origin_moves],
        ["name", "state"],
    )
    moves_by_picking: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for move in moves:
        moves_by_picking[relation_id(move.get("picking_id")) or -1].append(move)
    origins_by_id = {int(row["id"]): row for row in origin_moves}
    receipts_by_id = {int(row["id"]): row for row in receipt_pickings}

    result = []
    for picking in pickings:
        picking_moves = moves_by_picking[int(picking["id"])]
        receipts: dict[int, dict[str, Any]] = {}
        for move in picking_moves:
            for origin_id in move.get("move_orig_ids", []):
                origin = origins_by_id.get(int(origin_id), {})
                receipt_id = relation_id(origin.get("picking_id"))
                receipt = receipts_by_id.get(receipt_id or -1)
                if receipt and str(receipt.get("name", "")).startswith("WH/INPC/"):
                    receipts[int(receipt["id"])] = receipt
        receipt_rows = list(receipts.values())
        states = Counter(str(row.get("state")) for row in receipt_rows)
        result.append(
            SortingAuditRow(
                classification=classify_receipts(receipt_rows),
                sorting=str(picking.get("name", "")),
                sorting_state=str(picking.get("state", "")),
                primary_so=relation_name(picking.get("sale_primary_id")),
                source=str(picking.get("origin") or ""),
                demand=sum(float(row.get("product_uom_qty") or 0) for row in picking_moves if row.get("state") != "cancel"),
                reserved=sum(float(row.get("quantity") or 0) for row in picking_moves if row.get("state") != "cancel"),
                receipts=", ".join(sorted(str(row.get("name")) for row in receipt_rows)),
                receipt_states=", ".join(f"{key}: {value}" for key, value in sorted(states.items())),
            )
        )
    return result


def audit_invoiced_active_mos(client) -> list[dict[str, Any]]:
    orders = client.search_read_all(
        "sale.order",
        [["invoice_status", "=", "invoiced"]],
        ["name", "state", "invoice_status", "delivery_status"],
    )
    order_by_id = {int(row["id"]): row for row in orders}
    if not order_by_id:
        return []
    productions = client.search_read_all(
        "mrp.production",
        [["sale_primary_id", "in", sorted(order_by_id)], ["state", "not in", sorted(FINAL_STATES)]],
        ["name", "state", "product_id", "product_qty", "qty_produced", "sale_primary_id", "write_date"],
    )
    result = []
    for production in productions:
        order = order_by_id.get(relation_id(production.get("sale_primary_id")) or -1, {})
        result.append(
            {
                "primary_so": order.get("name", relation_name(production.get("sale_primary_id"))),
                "so_state": order.get("state", ""),
                "delivery_status": order.get("delivery_status", ""),
                "mo": production.get("name", ""),
                "mo_state": production.get("state", ""),
                "product": relation_name(production.get("product_id")),
                "product_qty": float(production.get("product_qty") or 0),
                "qty_produced": float(production.get("qty_produced") or 0),
                "write_date": production.get("write_date", ""),
            }
        )
    return result


def audit_input_custom(client) -> list[dict[str, Any]]:
    locations = client.search_read_all(
        "stock.location",
        [["complete_name", "=", "WH/Input-Custom"]],
        ["complete_name"],
    )
    if not locations:
        return []
    return client.search_read_all(
        "stock.quant",
        [["location_id", "=", int(locations[0]["id"])], ["quantity", "!=", 0]],
        ["product_id", "quantity", "reserved_quantity", "write_date"],
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_audit(client, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sorting = [asdict(row) for row in audit_open_sorting(client)]
    active_mos = audit_invoiced_active_mos(client)
    quants = audit_input_custom(client)
    sorting_counts = Counter(row["classification"] for row in sorting)
    quant_rows = [
        {
            "product": relation_name(row.get("product_id")),
            "on_hand": float(row.get("quantity") or 0),
            "reserved": float(row.get("reserved_quantity") or 0),
            "available": float(row.get("quantity") or 0) - float(row.get("reserved_quantity") or 0),
            "write_date": row.get("write_date", ""),
        }
        for row in quants
    ]
    summary = {
        "open_sorting": len(sorting),
        "sorting_by_receipt_state": dict(sorting_counts),
        "active_mo_with_invoiced_so": len(active_mos),
        "input_custom_products": len(quant_rows),
        "input_custom_on_hand": sum(row["on_hand"] for row in quant_rows),
        "input_custom_reserved": sum(row["reserved"] for row in quant_rows),
    }
    (output_dir / "supply_chain_audit.json").write_text(
        json.dumps({"summary": summary, "sorting": sorting, "active_mos": active_mos, "input_custom": quant_rows}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    write_csv(output_dir / "sorting_by_receipt.csv", sorting)
    write_csv(output_dir / "invoiced_active_mos.csv", active_mos)
    write_csv(output_dir / "input_custom.csv", quant_rows)
    report = [
        "# Odoo tiekimo grandinių auditas",
        "",
        "Ši ataskaita yra tik skaitoma. Ji nekeičia Odoo duomenų.",
        "",
        f"- Atviri WH/INT: {summary['open_sorting']}",
        f"- WH/INPC dar nepatvirtintas: {sorting_counts.get('WH_INPC_NOT_DONE', 0)}",
        f"- WH/INPC jau patvirtintas: {sorting_counts.get('WH_INPC_DONE', 0)}",
        f"- Nutrūkęs WH/INPC ryšys: {sorting_counts.get('NO_WH_INPC_LINK', 0)}",
        f"- Aktyvūs MO su Invoiced SO: {summary['active_mo_with_invoiced_so']}",
        f"- WH/Input-Custom bendras likutis: {summary['input_custom_on_hand']:g}",
        f"- WH/Input-Custom rezervuota: {summary['input_custom_reserved']:g}",
    ]
    (output_dir / "supply_chain_audit.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary
