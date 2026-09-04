"""Safely archive BoMs that are blocked by untouched sales-order lines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from bom_archive_blockers import EPSILON, run_check


@dataclass(frozen=True)
class QuantitySnapshot:
    sale_line_id: int
    so_number: str
    quantity: float


class BomArchiveResolutionError(RuntimeError):
    pass


def parse_queries(value: str) -> list[str]:
    normalized = value.replace(";", " ").replace(",", " ").replace("\n", " ")
    queries = list(dict.fromkeys(part.strip().upper() for part in normalized.split() if part.strip()))
    if not queries:
        raise ValueError("Įveskite bent vieną produkto kodą arba BOM ID.")
    return queries


def resolve(client: Any, queries: list[str]) -> dict[str, Any]:
    assessments = [run_check(client, query) for query in queries]
    active_boms: dict[int, dict[str, Any]] = {}
    blockers: dict[int, QuantitySnapshot] = {}
    unsafe: list[dict[str, Any]] = []

    for assessment in assessments:
        for bom in assessment["boms"]:
            if bom.get("active"):
                active_boms[int(bom["id"])] = bom
        for row in assessment["rows"]:
            if not row["blocks_archive"]:
                continue
            if row["delivered_qty"] > EPSILON or row["invoiced_qty"] > EPSILON:
                unsafe.append(row)
                continue
            blockers[int(row["sale_line_id"])] = QuantitySnapshot(
                sale_line_id=int(row["sale_line_id"]),
                so_number=str(row["so_number"]),
                quantity=float(row["ordered_qty"]),
            )

    if unsafe:
        details = ", ".join(f"{row['so_number']} / {row['sale_line_id']}" for row in unsafe)
        raise BomArchiveResolutionError(
            "Operacija sustabdyta: dalinai pristatytos arba išrašytos eilutės: " + details
        )
    if not active_boms:
        return {
            "status": "NO_CHANGES",
            "queries": queries,
            "archived_bom_ids": [],
            "restored_lines": [],
            "message": "Visi rasti BOM jau buvo archyvuoti.",
        }

    snapshots = list(blockers.values())
    archived_ids: list[int] = []
    restore_errors: list[str] = []
    try:
        for snapshot in snapshots:
            client.execute(
                "sale.order.line", "write", [[snapshot.sale_line_id], {"product_uom_qty": 0.0}]
            )
        for bom_id in sorted(active_boms):
            client.execute("mrp.bom", "write", [[bom_id], {"active": False}])
            archived_ids.append(bom_id)
    finally:
        for snapshot in snapshots:
            try:
                client.execute(
                    "sale.order.line",
                    "write",
                    [[snapshot.sale_line_id], {"product_uom_qty": snapshot.quantity}],
                )
            except Exception as exc:  # restoration must continue for every line
                restore_errors.append(f"{snapshot.sale_line_id}: {exc}")

    if restore_errors:
        raise BomArchiveResolutionError(
            "KRITINĖ KLAIDA: nepavyko atkurti dalies kiekių: " + "; ".join(restore_errors)
        )

    verification = client.search_read_all(
        "mrp.bom",
        [["id", "in", sorted(active_boms)]],
        ["id", "active"],
        context={"active_test": False},
    )
    still_active = [int(row["id"]) for row in verification if row.get("active")]
    if still_active:
        raise BomArchiveResolutionError(
            "BOM archyvavimo patikra nepavyko, aktyvūs liko ID: "
            + ", ".join(map(str, still_active))
        )

    restored = client.search_read_all(
        "sale.order.line",
        [["id", "in", [item.sale_line_id for item in snapshots]]],
        ["id", "product_uom_qty"],
        context={"active_test": False},
    ) if snapshots else []
    restored_by_id = {int(row["id"]): float(row.get("product_uom_qty") or 0) for row in restored}
    mismatches = [
        item.sale_line_id for item in snapshots
        if item.sale_line_id not in restored_by_id
        or abs(restored_by_id[item.sale_line_id] - item.quantity) > EPSILON
    ]
    if mismatches:
        raise BomArchiveResolutionError(
            "Atkurtų kiekių patikra nepavyko, eilučių ID: " + ", ".join(map(str, mismatches))
        )

    return {
        "status": "COMPLETED",
        "queries": queries,
        "archived_bom_ids": archived_ids,
        "restored_lines": [asdict(item) for item in snapshots],
        "message": "BOM suarchyvuoti, visi laikini kiekių pakeitimai atkurti.",
    }
