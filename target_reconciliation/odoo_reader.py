from __future__ import annotations

from collections import defaultdict
from typing import Any

from bom_release.analyzer import many2one_id
from odoo_client import OdooClient


def _xmlids(client: OdooClient, model: str) -> dict[int, str]:
    rows = client.search_read_all(
        "ir.model.data", [["model", "=", model]], ["module", "name", "res_id"]
    )
    return {
        int(row["res_id"]): f"{row['module']}.{row['name']}"
        for row in rows if row.get("res_id") and row.get("module") and row.get("name")
    }


def read_production_snapshot(client: OdooClient) -> dict[str, Any]:
    """Only ``search_read`` calls are used; this function cannot mutate Odoo."""
    variants = client.search_read_all(
        "product.product", [],
        ["id", "default_code", "active", "product_tmpl_id"],
        context={"active_test": False},
    )
    templates = client.search_read_all(
        "product.template", [],
        ["id", "name", "categ_id", "route_ids", "type", "invoice_policy", "seller_ids"],
        context={"active_test": False},
    )
    template_by_id = {int(row["id"]): row for row in templates}
    category_xmlids = _xmlids(client, "product.category")
    route_xmlids = _xmlids(client, "stock.route")
    template_xmlids = _xmlids(client, "product.template")
    partner_xmlids = _xmlids(client, "res.partner")
    sellers = client.search_read_all(
        "product.supplierinfo", [], ["id", "partner_id", "sequence"]
    )
    seller_by_id = {int(row["id"]): row for row in sellers}

    products = []
    variant_by_id = {}
    variants_by_template: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for variant in variants:
        variant_by_id[int(variant["id"])] = variant
        template_id = many2one_id(variant.get("product_tmpl_id"))
        if template_id:
            variants_by_template[template_id].append(variant)
        template = template_by_id.get(template_id or 0, {})
        category_id = many2one_id(template.get("categ_id"))
        routes = tuple(sorted(
            route_xmlids.get(int(route_id), "") for route_id in template.get("route_ids") or []
        ))
        seller_rows = [seller_by_id[x] for x in template.get("seller_ids") or [] if x in seller_by_id]
        seller_rows.sort(key=lambda row: (int(row.get("sequence") or 0), int(row["id"])))
        partner_id = many2one_id(seller_rows[0].get("partner_id")) if seller_rows else None
        products.append({
            "id": int(variant["id"]),
            "sku": variant.get("default_code") or "",
            "active": bool(variant.get("active", True)),
            "template_id": template_id,
            "external_id": template_xmlids.get(template_id or 0, ""),
            "name": template.get("name") or "",
            "category_external_id": category_xmlids.get(category_id or 0, ""),
            "route_external_ids": routes,
            "product_type_field": template.get("type") or "",
            "invoice_policy": template.get("invoice_policy") or "",
            "vendor_external_id": partner_xmlids.get(partner_id or 0, ""),
        })

    raw_boms = client.search_read_all(
        "mrp.bom", [],
        ["id", "active", "sequence", "type", "product_id", "product_tmpl_id"],
        context={"active_test": False},
    )
    bom_ids = [int(row["id"]) for row in raw_boms]
    raw_lines = client.search_read_all(
        "mrp.bom.line", [["bom_id", "in", bom_ids]],
        ["bom_id", "product_id", "product_qty"],
    ) if bom_ids else []
    raw_operations = client.search_read_all(
        "mrp.routing.workcenter", [["bom_id", "in", bom_ids]],
        ["bom_id", "name", "sequence", "workcenter_id", "time_mode", "time_cycle_manual", "time_cycle"],
        order="bom_id asc, sequence asc, id asc",
    ) if bom_ids else []
    lines_by_bom: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in raw_lines:
        product = variant_by_id.get(many2one_id(line.get("product_id")) or 0, {})
        lines_by_bom[many2one_id(line.get("bom_id")) or 0].append({
            "component_sku": product.get("default_code") or "",
            "quantity": line.get("product_qty"),
        })
    operations_by_bom: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for operation in raw_operations:
        manual = operation.get("time_cycle_manual")
        operations_by_bom[many2one_id(operation.get("bom_id")) or 0].append({
            "name": operation.get("name") or "",
            "sequence": operation.get("sequence") or 0,
            "workcenter": (operation.get("workcenter_id") or [0, ""])[1],
            "time_mode": operation.get("time_mode") or "",
            "time_minutes": manual if isinstance(manual, (int, float)) else operation.get("time_cycle") or 0,
        })
    boms = []
    for bom in raw_boms:
        product_id = many2one_id(bom.get("product_id"))
        template_id = many2one_id(bom.get("product_tmpl_id"))
        candidates = [variant_by_id[product_id]] if product_id in variant_by_id else variants_by_template.get(template_id or 0, [])
        candidates = [row for row in candidates if row.get("default_code")]
        sku = candidates[0].get("default_code") if len(candidates) == 1 else ""
        bom_id = int(bom["id"])
        boms.append({
            "id": bom_id, "sku": sku, "active": bool(bom.get("active", True)),
            "sequence": int(bom.get("sequence") or 0), "bom_type": bom.get("type") or "",
            "components": lines_by_bom[bom_id], "operations": operations_by_bom[bom_id],
        })
    return {"environment": "production", "products": products, "boms": boms}
