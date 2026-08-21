"""Read-only Production Odoo validation for the TOC decision-support contract.

The script intentionally permits only non-mutating XML-RPC methods and emits
aggregate metadata. It does not export business records or credentials.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
import xmlrpc.client

ALLOWED_METHODS = frozenset({"fields_get", "search_count", "search_read", "read"})
MODEL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "crm.tag": ("name",),
    "sale.order": (
        "name", "partner_id", "commitment_date", "expected_date", "date_order",
        "tag_ids", "order_line", "picking_ids", "delivery_status", "state",
    ),
    "sale.order.line": (
        "order_id", "product_id", "product_uom_qty", "qty_delivered",
        "price_subtotal", "price_total", "purchase_price", "margin",
        "move_ids", "production_ids", "mrp_production_ids",
    ),
    "mrp.production": (
        "name", "origin", "product_id", "product_qty", "bom_id", "state",
        "date_start", "date_finished", "workorder_ids", "move_dest_ids",
        "procurement_group_id", "sale_line_id",
    ),
    "mrp.workorder": (
        "name", "production_id", "workcenter_id", "state", "working_state",
        "date_start", "date_finished", "duration_expected", "duration",
        "time_ids", "employee_ids", "user_id", "blocked_by_workorder_ids",
    ),
    "mrp.workcenter.productivity": (
        "workorder_id", "user_id", "employee_id", "date_start", "date_end",
        "duration", "loss_id", "loss_type", "description",
    ),
    "mrp.workcenter.productivity.loss": (
        "name", "loss_type", "manual", "sequence",
    ),
    "mrp.workcenter": ("name", "code", "active"),
    "mrp.routing.workcenter": (
        "name", "bom_id", "workcenter_id", "time_cycle", "sequence",
    ),
    "mrp.bom": (
        "product_tmpl_id", "product_id", "product_qty", "operation_ids",
        "bom_line_ids", "active", "type",
    ),
    "stock.picking": (
        "name", "origin", "sale_id", "state", "picking_type_id",
        "picking_type_code", "scheduled_date", "date_done", "move_ids",
    ),
    "stock.move": (
        "picking_id", "sale_line_id", "production_id",
        "raw_material_production_id", "workorder_id", "group_id",
        "product_id", "product_uom_qty", "quantity", "date", "state",
    ),
}


class ReadOnlyOdoo:
    def __init__(self, values: dict[str, str]):
        self.db = values["ODOO_DB"]
        self.login = values["ODOO_LOGIN"]
        self.api_key = values["ODOO_API_KEY"]
        url = values["ODOO_URL"].rstrip("/")
        self.common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self.uid: int | None = None

    def authenticate(self) -> int:
        uid = self.common.authenticate(self.db, self.login, self.api_key, {})
        if not uid:
            raise PermissionError("Odoo authentication failed")
        self.uid = int(uid)
        return self.uid

    def call(self, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None):
        if method not in ALLOWED_METHODS:
            raise PermissionError(f"Mutating or unapproved Odoo method denied: {method}")
        if self.uid is None:
            self.authenticate()
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.api_key,
            model,
            method,
            args,
            kwargs or {},
        )

    def fields(self, model: str) -> dict[str, dict[str, Any]]:
        return self.call(
            model,
            "fields_get",
            [],
            {"attributes": ["string", "type", "relation", "required", "readonly"]},
        )

    def count(self, model: str, domain: list[Any]) -> int:
        return int(self.call(model, "search_count", [domain]))

    def sample(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        *,
        limit: int,
        order: str = "id desc",
    ) -> list[dict[str, Any]]:
        return self.call(
            model,
            "search_read",
            [domain],
            {"fields": fields, "limit": limit, "order": order},
        )


def load_credentials(path: Path) -> dict[str, str]:
    file_values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        file_values[key.strip()] = value.strip().strip('"').strip("'")
    values = {
        name: (os.getenv(name) or file_values.get(name) or "").strip()
        for name in ("ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_API_KEY")
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("Missing Odoo settings: " + ", ".join(missing))
    return values


def is_populated(value: Any) -> bool:
    return value is not False and value is not None and value != "" and value != []


def ratio(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    populated = sum(1 for row in rows if is_populated(row.get(field)))
    total = len(rows)
    return {
        "sample_count": total,
        "populated_count": populated,
        "populated_ratio": round(populated / total, 4) if total else None,
    }


def numeric_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [float(row[field]) for row in rows if is_populated(row.get(field))]
    if not values:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": median(values),
        "max": max(values),
    }


def safe_field_summary(fields: dict[str, dict[str, Any]], names: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        definition = fields.get(name)
        if not definition:
            result[name] = {"exists": False}
            continue
        result[name] = {
            "exists": True,
            "type": definition.get("type"),
            "relation": definition.get("relation") or None,
            "required": bool(definition.get("required")),
            "readonly": bool(definition.get("readonly")),
        }
    return result


def validate(client: ReadOnlyOdoo, sample_limit: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only_methods": sorted(ALLOWED_METHODS),
        "sample_limit_per_model": sample_limit,
        "models": {},
        "relations": {},
        "findings": [],
    }
    all_fields: dict[str, dict[str, dict[str, Any]]] = {}

    for model, candidates in MODEL_CANDIDATES.items():
        try:
            fields = client.fields(model)
        except xmlrpc.client.Fault as exc:
            report["models"][model] = {"available": False, "fault_code": exc.faultCode}
            continue
        all_fields[model] = fields
        present = [name for name in candidates if name in fields]
        sample_fields = ["id", *present]
        rows = client.sample(model, [], sample_fields, limit=sample_limit)
        report["models"][model] = {
            "available": True,
            "record_count": client.count(model, []),
            "fields": safe_field_summary(fields, candidates),
            "population": {name: ratio(rows, name) for name in present},
        }

    so_fields = all_fields.get("sale.order", {})
    so_line_fields = all_fields.get("sale.order.line", {})
    production_fields = all_fields.get("mrp.production", {})
    workorder_fields = all_fields.get("mrp.workorder", {})
    productivity_fields = all_fields.get("mrp.workcenter.productivity", {})
    picking_fields = all_fields.get("stock.picking", {})

    so_read_fields = [name for name in ("name", "commitment_date", "tag_ids", "order_line") if name in so_fields]
    sales = client.sample("sale.order", [["state", "in", ["sale", "done"]]], so_read_fields, limit=sample_limit)
    so_names = [row.get("name") for row in sales if row.get("name")]
    so_ids = [row["id"] for row in sales]

    lines: list[dict[str, Any]] = []
    if so_ids:
        line_read_fields = [name for name in ("order_id", "product_id", "price_subtotal", "purchase_price", "move_ids", "production_ids", "mrp_production_ids") if name in so_line_fields]
        lines = client.sample("sale.order.line", [["order_id", "in", so_ids]], line_read_fields, limit=max(sample_limit * 10, 500))

    productions: list[dict[str, Any]] = []
    if so_names:
        production_read_fields = [name for name in ("origin", "product_id", "bom_id", "workorder_ids", "procurement_group_id", "sale_line_id") if name in production_fields]
        productions = client.sample("mrp.production", [["origin", "in", so_names]], production_read_fields, limit=max(sample_limit * 10, 500))

    production_ids = [row["id"] for row in productions]
    workorders: list[dict[str, Any]] = []
    if production_ids:
        wo_read_fields = [name for name in ("production_id", "state", "working_state", "date_start", "date_finished", "duration_expected", "duration", "time_ids", "employee_ids", "user_id") if name in workorder_fields]
        workorders = client.sample("mrp.workorder", [["production_id", "in", production_ids]], wo_read_fields, limit=max(sample_limit * 20, 1000))

    workorder_ids = [row["id"] for row in workorders]
    productivity: list[dict[str, Any]] = []
    if workorder_ids and productivity_fields:
        prod_read_fields = [name for name in ("workorder_id", "user_id", "employee_id", "date_start", "date_end", "duration", "loss_id") if name in productivity_fields]
        productivity = client.sample("mrp.workcenter.productivity", [["workorder_id", "in", workorder_ids]], prod_read_fields, limit=max(sample_limit * 40, 2000))

    pickings: list[dict[str, Any]] = []
    if so_ids:
        picking_read_fields = [name for name in ("origin", "sale_id", "state", "picking_type_code", "date_done", "move_ids") if name in picking_fields]
        picking_domain: list[Any] = [["sale_id", "in", so_ids]] if "sale_id" in picking_fields else [["origin", "in", so_names]]
        pickings = client.sample("stock.picking", picking_domain, picking_read_fields, limit=max(sample_limit * 10, 500))

    move_fields = all_fields.get("stock.move", {})
    sale_line_ids = [row["id"] for row in lines]
    linked_moves: list[dict[str, Any]] = []
    if sale_line_ids:
        move_read_fields = [name for name in ("sale_line_id", "production_id", "raw_material_production_id", "group_id", "product_id", "state") if name in move_fields]
        linked_moves = client.sample(
            "stock.move",
            [["sale_line_id", "in", sale_line_ids]],
            move_read_fields,
            limit=max(sample_limit * 50, 5000),
        )

    direct_pairs: set[tuple[int, int]] = set()
    raw_pairs: set[tuple[int, int]] = set()
    sale_line_groups: dict[int, set[int]] = {}
    for move in linked_moves:
        sale_line = move.get("sale_line_id")
        if not sale_line:
            continue
        sale_line_id = int(sale_line[0])
        production = move.get("production_id")
        raw_production = move.get("raw_material_production_id")
        group = move.get("group_id")
        if production:
            direct_pairs.add((sale_line_id, int(production[0])))
        if raw_production:
            raw_pairs.add((sale_line_id, int(raw_production[0])))
        if group:
            sale_line_groups.setdefault(sale_line_id, set()).add(int(group[0]))

    production_groups: dict[int, set[int]] = {}
    for production in productions:
        group = production.get("procurement_group_id")
        if group:
            production_groups.setdefault(int(group[0]), set()).add(int(production["id"]))
    group_pairs: set[tuple[int, int]] = set()
    for sale_line_id, groups in sale_line_groups.items():
        for group in groups:
            for production_id in production_groups.get(group, set()):
                group_pairs.add((sale_line_id, production_id))

    sale_order_names = {int(row["id"]): row.get("name") for row in sales}
    origin_product_to_productions: dict[tuple[str, int], set[int]] = {}
    for production in productions:
        product = production.get("product_id")
        origin = production.get("origin")
        if origin and product:
            origin_product_to_productions.setdefault((str(origin), int(product[0])), set()).add(int(production["id"]))
    origin_product_candidate_counts: list[int] = []
    for line in lines:
        order = line.get("order_id")
        product = line.get("product_id")
        if not order or not product:
            continue
        order_name = sale_order_names.get(int(order[0]))
        if not order_name:
            continue
        origin_product_candidate_counts.append(
            len(origin_product_to_productions.get((str(order_name), int(product[0])), set()))
        )

    urgent_tags: list[dict[str, Any]] = []
    if "crm.tag" in all_fields:
        urgent_tags = client.sample("crm.tag", [["name", "=ilike", "SKUBUS"]], ["name"], limit=20)
    urgent_tag_ids = [int(row["id"]) for row in urgent_tags]
    urgent_tag_count = len(urgent_tag_ids)
    urgent_sales_order_count = client.count("sale.order", [["tag_ids", "in", urgent_tag_ids]]) if urgent_tag_ids and "tag_ids" in so_fields else 0
    urgent_sampled_sales_order_count = sum(
        1 for row in sales
        if any(int(tag_id) in urgent_tag_ids for tag_id in (row.get("tag_ids") or []))
    )
    assembly_workcenter_count = 0
    assembly_workcenter_ids: list[int] = []
    if "mrp.workcenter" in all_fields:
        assembly_workcenters = client.sample(
            "mrp.workcenter",
            ["|", ["name", "ilike", "Assembly"], ["name", "ilike", "Surink"]],
            ["name"],
            limit=20,
        )
        assembly_workcenter_ids = [int(row["id"]) for row in assembly_workcenters]
        assembly_workcenter_count = len(assembly_workcenter_ids)
    loss_config: list[dict[str, Any]] = []
    if "mrp.workcenter.productivity.loss" in all_fields:
        loss_config = client.sample(
            "mrp.workcenter.productivity.loss",
            [],
            [name for name in ("name", "loss_type", "manual") if name in all_fields["mrp.workcenter.productivity.loss"]],
            limit=100,
            order="sequence asc, id asc",
        )
    loss_names = {int(row["id"]): str(row.get("name") or "") for row in loss_config}

    assembly_workorders: list[dict[str, Any]] = []
    if assembly_workcenter_ids:
        assembly_wo_fields = [name for name in ("production_id", "state", "working_state", "date_start", "date_finished", "duration_expected", "duration", "time_ids", "employee_ids", "user_id") if name in workorder_fields]
        assembly_workorders = client.sample(
            "mrp.workorder",
            [["workcenter_id", "in", assembly_workcenter_ids]],
            assembly_wo_fields,
            limit=max(sample_limit * 10, 2000),
        )
    assembly_wo_ids = [int(row["id"]) for row in assembly_workorders]
    assembly_productivity: list[dict[str, Any]] = []
    if assembly_wo_ids and productivity_fields:
        assembly_prod_fields = [name for name in ("workorder_id", "user_id", "employee_id", "date_start", "date_end", "duration", "loss_id") if name in productivity_fields]
        assembly_productivity = client.sample(
            "mrp.workcenter.productivity",
            [["workorder_id", "in", assembly_wo_ids]],
            assembly_prod_fields,
            limit=max(sample_limit * 20, 4000),
        )
    assembly_loss_counts: Counter[str] = Counter()
    for row in assembly_productivity:
        loss = row.get("loss_id")
        if loss:
            loss_id = int(loss[0])
            assembly_loss_counts[loss_names.get(loss_id, f"loss_id:{loss_id}")] += 1

    matched_origin_names = {str(row.get("origin")) for row in productions if row.get("origin")}
    non_exact_origin_match_count = 0
    missing_origin_names = [str(name) for name in so_names if str(name) not in matched_origin_names]
    for name in missing_origin_names:
        if client.count("mrp.production", [["origin", "ilike", name]]) > 0:
            non_exact_origin_match_count += 1

    outgoing_done_pickings = [
        row for row in pickings
        if row.get("state") == "done" and row.get("picking_type_code") == "outgoing"
    ]
    outgoing_picking_ids = [int(row["id"]) for row in outgoing_done_pickings]
    outgoing_moves: list[dict[str, Any]] = []
    if outgoing_picking_ids:
        outgoing_moves = client.sample(
            "stock.move",
            [["picking_id", "in", outgoing_picking_ids], ["state", "=", "done"]],
            [name for name in ("picking_id", "sale_line_id", "product_id", "quantity", "product_uom_qty") if name in move_fields],
            limit=max(sample_limit * 50, 5000),
        )
    shipment_dates_by_so: dict[int, set[str]] = {}
    for picking in outgoing_done_pickings:
        sale = picking.get("sale_id")
        date_done = picking.get("date_done")
        if sale and date_done:
            shipment_dates_by_so.setdefault(int(sale[0]), set()).add(str(date_done))

    line_direct_relations = [name for name in ("production_ids", "mrp_production_ids") if name in so_line_fields]
    report["relations"] = {
        "sampled_confirmed_sales_orders": len(sales),
        "sales_order_delivery_date": ratio(sales, "commitment_date") if "commitment_date" in so_fields else {"field_missing": True},
        "sales_order_tags": ratio(sales, "tag_ids") if "tag_ids" in so_fields else {"field_missing": True},
        "sampled_sales_order_lines": len(lines),
        "sale_line_direct_production_fields": line_direct_relations,
        "sale_line_material_cost": ratio(lines, "purchase_price") if "purchase_price" in so_line_fields else {"field_missing": True},
        "production_matches_by_exact_origin": len(productions),
        "production_sale_line_field": "sale_line_id" in production_fields,
        "sampled_workorders_for_matched_productions": len(workorders),
        "workorder_expected_duration": ratio(workorders, "duration_expected") if "duration_expected" in workorder_fields else {"field_missing": True},
        "workorder_start": ratio(workorders, "date_start") if "date_start" in workorder_fields else {"field_missing": True},
        "workorder_finish": ratio(workorders, "date_finished") if "date_finished" in workorder_fields else {"field_missing": True},
        "sampled_productivity_rows": len(productivity),
        "productivity_employee": ratio(productivity, "employee_id") if "employee_id" in productivity_fields else {"field_missing": True},
        "productivity_user": ratio(productivity, "user_id") if "user_id" in productivity_fields else {"field_missing": True},
        "productivity_loss": ratio(productivity, "loss_id") if "loss_id" in productivity_fields else {"field_missing": True},
        "sampled_pickings_by_origin": len(pickings),
        "done_picking_date": ratio([row for row in pickings if row.get("state") == "done"], "date_done") if "date_done" in picking_fields else {"field_missing": True},
        "workorder_states": dict(Counter(str(row.get("state")) for row in workorders)),
        "workorder_working_states": dict(Counter(str(row.get("working_state")) for row in workorders)) if "working_state" in workorder_fields else {},
        "urgent_tag_exact_match_count": urgent_tag_count,
        "urgent_sales_order_total_count": urgent_sales_order_count,
        "urgent_sales_order_in_sample_count": urgent_sampled_sales_order_count,
        "assembly_named_workcenter_count": assembly_workcenter_count,
        "productivity_loss_configuration": loss_config,
        "sampled_stock_moves_for_sale_lines": len(linked_moves),
        "sale_line_to_finished_production_pairs": len(direct_pairs),
        "sale_line_to_raw_production_pairs": len(raw_pairs),
        "sale_line_to_production_group_pairs": len(group_pairs),
        "origin_product_unique_line_count": sum(1 for count in origin_product_candidate_counts if count == 1),
        "origin_product_ambiguous_line_count": sum(1 for count in origin_product_candidate_counts if count > 1),
        "origin_product_unmatched_line_count": sum(1 for count in origin_product_candidate_counts if count == 0),
        "sales_orders_with_exact_origin_mo": sum(1 for name in so_names if str(name) in matched_origin_names),
        "sales_orders_without_exact_origin_mo": sum(1 for name in so_names if str(name) not in matched_origin_names),
        "sales_orders_with_non_exact_origin_mo": non_exact_origin_match_count,
        "sampled_assembly_workorders": len(assembly_workorders),
        "assembly_workorder_expected_duration_raw": numeric_summary(assembly_workorders, "duration_expected"),
        "assembly_workorder_actual_duration_raw": numeric_summary(assembly_workorders, "duration"),
        "assembly_workorder_start": ratio(assembly_workorders, "date_start"),
        "assembly_workorder_finish": ratio(assembly_workorders, "date_finished"),
        "assembly_workorder_employee_ids": ratio(assembly_workorders, "employee_ids") if "employee_ids" in workorder_fields else {"field_missing": True},
        "sampled_assembly_productivity_rows": len(assembly_productivity),
        "assembly_productivity_employee": ratio(assembly_productivity, "employee_id") if "employee_id" in productivity_fields else {"field_missing": True},
        "assembly_productivity_loss": ratio(assembly_productivity, "loss_id") if "loss_id" in productivity_fields else {"field_missing": True},
        "assembly_productivity_duration_raw": numeric_summary(assembly_productivity, "duration"),
        "assembly_productivity_loss_counts": dict(assembly_loss_counts),
        "assembly_workorder_states": dict(Counter(str(row.get("state")) for row in assembly_workorders)),
        "assembly_workorder_working_states": dict(Counter(str(row.get("working_state")) for row in assembly_workorders)) if "working_state" in workorder_fields else {},
        "done_outgoing_pickings": len(outgoing_done_pickings),
        "done_outgoing_moves": len(outgoing_moves),
        "done_outgoing_moves_with_sale_line": sum(1 for row in outgoing_moves if row.get("sale_line_id")),
        "sales_orders_with_multiple_actual_shipment_dates": sum(1 for dates in shipment_dates_by_so.values() if len(dates) > 1),
    }

    findings = report["findings"]
    if "commitment_date" not in so_fields:
        findings.append({"severity": "BLOCKED", "code": "SO_DELIVERY_DATE_FIELD_MISSING"})
    if "tag_ids" not in so_fields:
        findings.append({"severity": "BLOCKED", "code": "SO_TAG_FIELD_MISSING"})
    if not line_direct_relations and "sale_line_id" not in production_fields:
        findings.append({"severity": "NEEDS_DESIGN", "code": "NO_DIRECT_SO_LINE_MO_RELATION"})
    if productions and not workorders:
        findings.append({"severity": "BLOCKED", "code": "MATCHED_PRODUCTIONS_HAVE_NO_WORKORDERS"})
    if "employee_id" not in productivity_fields and "user_id" not in productivity_fields:
        findings.append({"severity": "BLOCKED", "code": "WORK_LOG_ACTOR_FIELD_MISSING"})
    if "loss_id" not in productivity_fields:
        findings.append({"severity": "NEEDS_DESIGN", "code": "WORK_LOG_LOSS_FIELD_MISSING"})
    if "date_done" not in picking_fields:
        findings.append({"severity": "BLOCKED", "code": "SHIPMENT_TIMESTAMP_FIELD_MISSING"})
    if "purchase_price" not in so_line_fields:
        findings.append({"severity": "NEEDS_DESIGN", "code": "SO_LINE_MATERIAL_COST_FIELD_MISSING"})
    if not direct_pairs and not group_pairs:
        findings.append({"severity": "NEEDS_DESIGN", "code": "NO_STOCK_MOVE_OR_GROUP_SO_LINE_MO_BRIDGE"})
    if urgent_tag_count == 0:
        findings.append({"severity": "BLOCKED", "code": "URGENT_TAG_NOT_FOUND"})
    if assembly_workcenter_count == 0:
        findings.append({"severity": "NEEDS_DESIGN", "code": "ASSEMBLY_WORKCENTER_NOT_IDENTIFIED_BY_NAME"})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-limit", type=int, default=200)
    args = parser.parse_args()

    client = ReadOnlyOdoo(load_credentials(args.env_file))
    client.authenticate()
    report = validate(client, max(1, args.sample_limit))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at_utc": report["generated_at_utc"],
        "models_checked": len(report["models"]),
        "findings": report["findings"],
        "output": str(args.output.resolve()),
        "read_only_methods": report["read_only_methods"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
