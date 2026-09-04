"""Read-only Odoo BoM archive blocker diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

EPSILON = 1e-9


def relation_id(value: Any) -> int | None:
    return int(value[0]) if isinstance(value, (list, tuple)) and value else None


def relation_name(value: Any) -> str:
    return str(value[1]) if isinstance(value, (list, tuple)) and len(value) > 1 else ""


@dataclass(frozen=True)
class BlockerRow:
    sale_line_id: int
    so_number: str
    so_state: str
    product_id: int
    product: str
    ordered_qty: float
    delivered_qty: float
    invoiced_qty: float
    blocks_archive: bool
    zero_residual_line: bool
    recommended_action: str


def assess_line(line: dict[str, Any], order: dict[str, Any]) -> BlockerRow:
    ordered = float(line.get("product_uom_qty") or 0)
    delivered = float(line.get("qty_delivered") or 0)
    invoiced = float(line.get("qty_invoiced") or 0)
    zero = all(abs(qty) <= EPSILON for qty in (ordered, delivered, invoiced))
    state = str(order.get("state") or "")
    blocks = state != "cancel" and (
        delivered + EPSILON < ordered or invoiced + EPSILON < ordered
    )
    if blocks and delivered <= EPSILON and invoiced <= EPSILON:
        action = "Laikinai pašalinti ir po BOM archyvavimo tiksliai atkurti eilutę."
    elif blocks:
        action = "Netrinti: dalinai įvykdyta eilutė, pirmiausia ištirti pristatymą ir sąskaitą."
    elif zero:
        action = "Nulinė likutinė eilutė; šalinti tik jei po realių blokatorių pašalinimo BOM vis dar blokuojamas."
    else:
        action = "Veiksmų nereikia."
    product_id = relation_id(line.get("product_id"))
    order_id = relation_id(line.get("order_id"))
    if product_id is None or order_id is None:
        raise ValueError(f"Nepilni sale.order.line duomenys: {line.get('id')}")
    return BlockerRow(
        sale_line_id=int(line["id"]),
        so_number=str(order.get("name") or relation_name(line.get("order_id"))),
        so_state=state,
        product_id=product_id,
        product=relation_name(line.get("product_id")),
        ordered_qty=ordered,
        delivered_qty=delivered,
        invoiced_qty=invoiced,
        blocks_archive=blocks,
        zero_residual_line=zero,
        recommended_action=action,
    )


def run_check(client: Any, query: str) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("Įveskite BOM ID, BOM nuorodą arba pagrindinio produkto kodą.")
    bom_fields = ["id", "code", "active", "type", "product_id", "product_tmpl_id"]
    boms = client.search_read_all("mrp.bom", [["id", "=", int(query)]], bom_fields) if query.isdigit() else []
    if not boms:
        boms = client.search_read_all("mrp.bom", [["code", "=", query]], bom_fields)
    if not boms:
        products = client.search_read_all(
            "product.product", [["default_code", "=", query]],
            ["id", "default_code", "product_tmpl_id"], context={"active_test": False},
        )
        template_ids = sorted({tid for row in products if (tid := relation_id(row.get("product_tmpl_id"))) is not None})
        if template_ids:
            boms = client.search_read_all(
                "mrp.bom", [["product_tmpl_id", "in", template_ids]], bom_fields,
                context={"active_test": False},
            )
    if not boms:
        raise ValueError(f"BOM nerastas pagal „{query}“.")
    template_ids = sorted({tid for bom in boms if (tid := relation_id(bom.get("product_tmpl_id"))) is not None})
    variants = client.search_read_all(
        "product.product", [["product_tmpl_id", "in", template_ids]],
        ["id", "default_code", "display_name", "product_tmpl_id"], context={"active_test": False},
    )
    product_ids = [int(row["id"]) for row in variants]
    lines = client.search_read_all(
        "sale.order.line", [["product_id", "in", product_ids], ["display_type", "=", False]],
        ["id", "order_id", "product_id", "product_uom_qty", "qty_delivered", "qty_invoiced", "display_type"],
        context={"active_test": False},
    ) if product_ids else []
    order_ids = sorted({oid for line in lines if (oid := relation_id(line.get("order_id"))) is not None})
    orders = client.search_read_all("sale.order", [["id", "in", order_ids]], ["id", "name", "state"]) if order_ids else []
    orders_by_id = {int(order["id"]): order for order in orders}
    rows = [assess_line(line, orders_by_id.get(relation_id(line.get("order_id")), {})) for line in lines]
    rows.sort(key=lambda row: (row.so_number, row.sale_line_id))
    return {
        "query": query,
        "boms": boms,
        "summary": {
            "sale_line_count": len(rows),
            "blocking_line_count": sum(row.blocks_archive for row in rows),
            "zero_residual_line_count": sum(row.zero_residual_line for row in rows),
        },
        "rows": [asdict(row) for row in rows],
        "note": "Komponentų savarankiški pardavimai neįtraukti; analizuojamas tik BOM pagrindinis produktas.",
    }
