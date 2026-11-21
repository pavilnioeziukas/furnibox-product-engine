"""Create inactive Furnibox #43 PLM revisions. Dry run unless --write."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from xmlrpc.client import Fault, ServerProxy

from config import load_settings

FIELDS = {
    "bom_operation_type": "picking_type_id",
    "manufacturing_lead_days": "produce_delay",
    "prepare_manufacturing_days": "days_to_prepare_mo",
    "operation_duration_minutes": "time_cycle_manual",
    "operation_name": "name",
}
COMPLETED = {49496, 49497, 49498, 49499, 49500, 49501}
BOM = "mrp.bom"
OP = "mrp.routing.workcenter"
ECO = "mrp.eco"


def demand(condition, message):
    if not condition:
        raise ValueError(message)


def equals(actual, expected):
    if expected is None:
        return actual is False or actual is None
    if type(expected) in (float, int):
        return type(actual) in (int, float) and math.isclose(actual, expected, abs_tol=0.001)
    return actual == expected


def pair(value):
    return value[0] if value else False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--validate-package", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-method", default="action_new_revision")
    args = parser.parse_args()
    raw = args.package.read_bytes()
    demand(hashlib.sha256(raw).hexdigest() == "d6bbca858460583f765cc76c12711b88461462f249204c3702352092d56458e9", "File differs from the approved package")
    package = json.loads(raw)
    demand(package["ticket"] == 43 and package["mode"] == "create_inactive_revisions", "Unexpected package")
    records = [row for row in package["records"] if row["source_bom_id"] not in COMPLETED]
    demand(len({row["source_bom_id"] for row in records}) == len(records), "Duplicate source BOM")
    for row in records:
        keys = [(c["source_operation_id"], FIELDS[c["field"]]) for c in row["changes"]]
        demand(len(keys) == len(set(keys)), "Duplicate field change")
    print(json.dumps({"pending_boms": len(records), "pending_fields": sum(len(r["changes"]) for r in records)}))
    if args.validate_package:
        return
    if args.limit is not None:
        demand(args.limit > 0, "Limit must be positive")
        records = records[:args.limit]

    url = "https://odoo.furnibox.lt"
    settings = load_settings()
    demand(settings.url == url, "Configured Odoo is not Furnibox production")
    db, login, key = settings.db, settings.login, settings.api_key
    uid = ServerProxy(url + "/xmlrpc/2/common").authenticate(db, login, key, {})
    demand(uid, "Authentication failed")
    models = ServerProxy(url + "/xmlrpc/2/object")

    def call(model, method, *values, **options):
        return models.execute_kw(db, uid, key, model, method, values, options)

    def read(model, ids, fields):
        return call(model, "read", ids, fields=fields, context={"active_test": False})

    def one(model, ids, fields):
        result = read(model, ids, fields)
        demand(len(result) == 1, f"Expected one {model} record")
        return result[0]

    def find(model, domain, fields):
        return call(model, "search_read", domain, fields=fields, limit=2)

    type_id = find("mrp.eco.type", [["name", "=", "BOM Updates"]], ["id"])
    demand(len(type_id) == 1, "BOM Updates ECO type is ambiguous")
    bf = ["active", "product_id", "product_tmpl_id", "code", "operation_ids",
          "picking_type_id", "produce_delay", "days_to_prepare_mo", "write_date"]
    of = ["bom_id", "name", "sequence", "workcenter_id", "time_cycle_manual", "write_date"]
    ef = ["bom_id", "new_bom_id"]
    demand(set(ef) <= set(call(ECO, "fields_get", attributes=["type"])), "Unexpected ECO schema")
    routing_ids = {}

    def route(name):
        if name not in routing_ids:
            domain = [["name", "=", name]]
            matches = find("stock.picking.type", domain, ["warehouse_id", "display_name"])
            if not matches and ": " in name:
                warehouse, operation = name.split(": ", 1)
                matches = find("stock.picking.type", [["name", "=", operation], ["warehouse_id.name", "=", warehouse]], ["id"])
            demand(len(matches) == 1, f"Ambiguous routing: {name}")
            routing_ids[name] = matches[0]["id"]
        return routing_ids[name]

    def plan(row):
        bid = row["source_bom_id"]
        bom = one(BOM, [bid], bf)
        demand(bom["active"] and (bom["code"] or "").startswith("BOM_for Furnibox_v10"), "Source BOM unavailable")
        product_model = "product.product" if bom["product_id"] else "product.template"
        product_id = pair(bom["product_id"] or bom["product_tmpl_id"])
        demand(one(product_model, [product_id], ["default_code"])["default_code"] == row["sku"], "Product code differs")
        operations = {op["id"]: op for op in read(OP, bom["operation_ids"], of)}
        title = f"Furnibox #43 batch BOM {bid}"
        ecos = find(ECO, [["name", "ilike", title], ["bom_id", "=", bid]], ef)
        demand(len(ecos) <= 1, "Duplicate batch ECO")
        if not ecos:
            demand(not find(ECO, [["bom_id", "=", bid]], ["id"]), "Existing ECO requires review")
        targets = {}
        for change in row["changes"]:
            field = FIELDS[change["field"]]
            oid = change["source_operation_id"]
            source = operations[oid] if oid else bom
            current = source[field]
            expected, desired = change["expected"], change["desired"]
            if field == "picking_type_id":
                current = pair(current)
                expected = route(expected) if expected else False
                desired = route(desired)
                valid = current == expected
            else:
                valid = equals(current, expected)
            demand(valid, f"Current value differs: {field}, operation {oid}")
            targets.setdefault(oid, {})[field] = desired
        return bom, operations, title, ecos, targets

    def signature(op):
        return op["sequence"], pair(op["workcenter_id"])

    def execute(row, bom, operations, title, ecos, targets):
        bid = row["source_bom_id"]
        demand(one(BOM, [bid], bf) == bom, "BOM changed after validation")
        demand({op["id"]: op for op in read(OP, bom["operation_ids"], of)} == operations, "Operations changed after validation")
        eco = ecos[0] if ecos else None
        eid = eco["id"] if eco else call(ECO, "create", {
            "name": title, "type_id": type_id[0]["id"], "type": "bom",
            "product_tmpl_id": pair(bom["product_tmpl_id"]), "bom_id": bid,
        })
        if not eco or not eco["new_bom_id"]:
            try:
                call(ECO, args.start_method, [eid])
            except Fault as error:
                if not error.faultString.rstrip().endswith("TypeError: cannot marshal None unless allow_none is enabled"):
                    raise
        rid = pair(one(ECO, [eid], ef)["new_bom_id"])
        demand(rid and rid != bid, "PLM did not return a new revision")
        rev = one(BOM, [rid], bf)
        demand(not rev["active"] and rev["product_tmpl_id"] == bom["product_tmpl_id"], "Unexpected revision state")
        copies = read(OP, rev["operation_ids"], of)
        writes = []
        for oid, fields in targets.items():
            if oid:
                source = operations[oid]
                candidates = [op for op in copies if signature(op) == signature(source)
                              and all(equals(op[k], v) or equals(op[k], source[k])
                                      for k, v in {"name": source["name"], "time_cycle_manual": source["time_cycle_manual"], **fields}.items())]
                demand(len(candidates) == 1, f"Cannot match copied operation {oid}")
                record = candidates[0]
                demand(pair(record["bom_id"]) == rid, "Operation belongs to a different BOM")
                writes.append((OP, record, source, fields))
            else:
                writes.append((BOM, rev, bom, fields))
        for model, record, old, fields in writes:
            for field, target in fields.items():
                get = pair if field == "picking_type_id" else lambda v: v
                demand(equals(get(record[field]), get(old[field])) or equals(get(record[field]), target), f"Revision has another edit: {field}")
        for model, record, old, fields in writes:
            if not all(equals(pair(record[k]) if k == "picking_type_id" else record[k], v) for k, v in fields.items()):
                demand(not one(BOM, [rid], ["active"])["active"], "Revision was activated during execution")
                call(model, "write", [record["id"]], fields)
            check = one(model, [record["id"]], list(fields))
            demand(all(equals(pair(check[k]) if k == "picking_type_id" else check[k], v) for k, v in fields.items()), "Verification failed")
        demand(not one(BOM, [rid], ["active"])["active"], "Revision is active")
        return eid, rid

    failures = 0
    for row in records:
        result = {"bom": row["source_bom_id"], "sku": row["sku"]}
        try:
            prepared = plan(row)
            if args.write:
                result["eco"], result["revision"] = execute(row, *prepared)
            result["status"] = "verified" if args.write else "ready"
        except (ValueError, KeyError, OSError, RuntimeError, Fault) as exc:
            failures += 1
            result.update(status="blocked", reason=str(exc))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
