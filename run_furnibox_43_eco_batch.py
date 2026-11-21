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
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--retry-connection-refused", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-method", default="action_new_revision")
    args = parser.parse_args()
    raw = args.package.read_bytes()
    demand(hashlib.sha256(raw).hexdigest() == "d6bbca858460583f765cc76c12711b88461462f249204c3702352092d56458e9", "File differs from the approved package")
    package = json.loads(raw)
    demand(package["ticket"] == 43 and package["mode"] == "create_inactive_revisions", "Unexpected package")
    records = [row for row in package["records"] if row["source_bom_id"] not in COMPLETED]
    if args.retry_connection_refused:
        log_path = args.package.parent.parent / "717189f3e67b" / "run.log"
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
                   if line.startswith('{"bom":')]
        expected_ids = {row["source_bom_id"] for row in records}
        demand(len(entries) == len(expected_ids) and {entry["bom"] for entry in entries} == expected_ids,
               "Prior run log does not cover the approved package")
        blocked = [entry for entry in entries if entry["status"] == "blocked"]
        demand(len(blocked) == 74 and all(entry["reason"] == "[Errno 111] Connection refused" for entry in blocked),
               "Prior run does not contain the expected 74 connection failures")
        retry_ids = {entry["bom"] for entry in blocked}
        records = [row for row in records if row["source_bom_id"] in retry_ids]
    activation = {}
    if args.activate:
        demand(not args.write and not args.retry_connection_refused, "Conflicting execution modes")
        run_dir = args.package.parent.parent
        for run_id, count in (("717189f3e67b", 1721), ("c292f9b65dee", 74)):
            log = (run_dir / run_id / "run.log").read_text(encoding="utf-8")
            entries = [json.loads(line) for line in log.splitlines() if line.startswith('{"bom":')]
            verified = [entry for entry in entries if entry["status"] == "verified"]
            demand(len(verified) == count, "Activation audit is incomplete")
            for entry in verified:
                bid = entry["bom"]
                demand(bid not in activation, "Duplicate verified BOM")
                activation[bid] = (entry["eco"], entry["revision"])
        demand(set(activation) == {r["source_bom_id"] for r in records}, "Verified BOMs differ from approved package")
        activation.update({bid: (eid, None) for bid, eid in zip(sorted(COMPLETED), range(372, 378))})
        demand(len({value[0] for value in activation.values()}) == 1801, "Duplicate ECO")
        records = package["records"]
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

    if args.activate:
        seed = one(ECO, [380], ["stage_id", "type_id"])
        if seed["stage_id"] and "validated" in seed["stage_id"][1].casefold() and pair(seed["type_id"]) == type_id[0]["id"]:
            stage = pair(seed["stage_id"])
        else:
            stages = find("mrp.eco.stage", [["name", "in", ["Validated", "Validated (BOM)"]]], ["id"])
            demand(len(stages) == 1, "Validated BOM stage could not be identified")
            stage = stages[0]["id"]
        progress_seed = one(ECO, [381], ["stage_id", "type_id", "state", "bom_id"])
        if progress_seed["stage_id"] and pair(progress_seed["type_id"]) == type_id[0]["id"] and progress_seed["state"] != "done" and pair(progress_seed["stage_id"]) != stage:
            progress_stage = pair(progress_seed["stage_id"])
        else:
            stages = find("mrp.eco.stage", [["name", "ilike", "In Progress"]], ["id"])
            demand(len(stages) == 1 and stages[0]["id"] != stage, "In Progress BOM stage could not be identified")
            progress_stage = stages[0]["id"]

    def activate(row):
        bid = row["source_bom_id"]
        eid, audited_revision = activation[bid]
        eco = one(ECO, [eid], ["bom_id", "new_bom_id", "type_id", "stage_id", "state", "allow_apply_change", "name"])
        rid = pair(eco["new_bom_id"])
        demand(pair(eco["bom_id"]) == bid and rid and rid != bid and pair(eco["type_id"]) == type_id[0]["id"],
               "ECO does not match approved BOM")
        demand(rid == audited_revision if audited_revision else "Furnibox #43" in eco["name"],
               "ECO revision does not match audit")
        source = one(BOM, [bid], bf)
        target = one(BOM, [rid], bf)
        demand(source["product_tmpl_id"] == target["product_tmpl_id"] and source["product_id"] == target["product_id"],
               "Revision belongs to a different product")
        op_ids = [change["source_operation_id"] for change in row["changes"] if change["source_operation_id"]]
        old_ops = {op["id"]: op for op in read(OP, sorted(set(op_ids)), of)} if op_ids else {}
        new_ops = read(OP, target["operation_ids"], of) if op_ids else []
        for change in row["changes"]:
            field = FIELDS[change["field"]]
            oid = change["source_operation_id"]
            old = old_ops[oid] if oid else source
            expected, desired = change["expected"], change["desired"]
            if oid:
                demand(pair(old["bom_id"]) == bid, "Source operation belongs to another BOM")
                matches = [op for op in new_ops if signature(op) == signature(old) and equals(op[field], desired)]
                demand(len(matches) == 1 and pair(matches[0]["bom_id"]) == rid, f"Revision operation differs: {oid}, {field}")
                new = matches[0]
            else:
                new = target
            if field == "picking_type_id":
                demand(pair(old[field]) == (route(expected) if expected else False) and pair(new[field]) == route(desired),
                       "Routing differs from approved change")
            else:
                demand(equals(old[field], expected) and equals(new[field], desired), f"Value differs: {field}")
        if eco["state"] != "done":
            demand(source["active"] and not target["active"], "Unexpected BOM activation state")
            if pair(eco["stage_id"]) != stage:
                demand(pair(eco["stage_id"]) == progress_stage, "Unexpected ECO stage")
                call(ECO, "write", [eid], {"stage_id": stage})
            current = one(ECO, [eid], ["stage_id", "state", "allow_apply_change"])
            demand(pair(current["stage_id"]) == stage and current["state"] != "done" and current["allow_apply_change"],
                   "Odoo does not allow Apply Changes")
            try:
                call(ECO, "action_apply", [eid])
            except Fault as error:
                if not error.faultString.rstrip().endswith("TypeError: cannot marshal None unless allow_none is enabled"):
                    raise
        flags = {row["id"]: row["active"] for row in read(BOM, [bid, rid], ["active"])}
        demand(flags == {bid: False, rid: True} and one(ECO, [eid], ["state"])["state"] == "done",
               "Activation could not be verified")
        return eid, rid

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
            if args.activate:
                result["eco"], result["revision"] = activate(row)
                result["status"] = "effective"
            else:
                prepared = plan(row)
                if args.write:
                    result["eco"], result["revision"] = execute(row, *prepared)
                result["status"] = "verified" if args.write else "ready"
        except (ValueError, KeyError, OSError, RuntimeError, Fault) as exc:
            failures += 1
            result.update(status="blocked", reason=str(exc))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    print(json.dumps({"checked": len(records), "verified" if args.write else "ready": len(records) - failures, "blocked": failures}), flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
