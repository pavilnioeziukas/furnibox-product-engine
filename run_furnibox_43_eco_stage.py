"""Prepare one inactive Furnibox #43 revision in Odoo Stage."""
from pathlib import Path
import sys
from urllib.parse import urlsplit

from config import load_settings
from odoo_client import OdooClient
import json

BOM_ID = 49502
OPERATION_ID = 14966
SKU = "APACK-EU-C-CAB01-BAS009-A"

TITLE = "Furnibox #43 Stage pilot BOM 49502"
OPERATION = "Spintelės surinkimas"
INACTIVE_CONTEXT = {"active_test": False}


def require_one(records, description):
    if len(records) != 1:
        raise ValueError(f"{description}: tikėtasi vieno įrašo, rasta {len(records)}.")
    return records[0]


def run(package_path):
    package = json.loads(Path(package_path).read_text(encoding="utf-8-sig"))
    row = require_one(
        [row for row in package["records"] if row["source_bom_id"] == BOM_ID], "JSON BOM"
    )
    change = require_one(row["changes"], "JSON pakeitimas")
    if (
        package["ticket"] != 43 or package["mode"] != "create_inactive_revisions"
        or row["sku"] != SKU or change["source_operation_id"] != OPERATION_ID
        or change["field"] != "operation_duration_minutes"
        or change["expected"] != 50 or change["desired"] != 35
    ):
        raise ValueError("JSON neatitinka patvirtinto bandomojo pakeitimo.")

    settings = load_settings()
    url = urlsplit(settings.url)
    if url.scheme != "https" or url.hostname != "stageodoo.furnibox.lt":
        raise ValueError("Bandymui reikalinga Furnibox Stage Odoo jungtis.")
    client = OdooClient(settings)
    client.authenticate()

    def execute(model, method, *args):
        return client.models.execute_kw(
            settings.db, client.uid, settings.api_key, model, method, list(args)
        )

    search = client.search_read_all
    product = require_one(
        search("product.template", [["default_code", "=", SKU]], ["id"]), SKU
    )
    source = require_one(search(
        "mrp.bom",
        [["product_tmpl_id", "=", product["id"]], ["code", "=", "BOM_for Furnibox_v10"],
         ["type", "=", "normal"], ["active", "=", True]],
        ["id", "active"],
    ), "Aktyvus Stage V10 BOM")
    bid = source["id"]

    def operation(bom_id):
        return require_one(search(
            "mrp.routing.workcenter", [["bom_id", "=", bom_id], ["name", "=", OPERATION]],
            ["id", "time_cycle_manual"], context=INACTIVE_CONTEXT,
        ), OPERATION)

    if operation(bid)["time_cycle_manual"] != 50:
        raise ValueError("Aktyvaus BOM trukmė skiriasi nuo 50 min.")
    existing = search(
        "mrp.eco", [["bom_id", "=", bid]], ["name", "new_bom_id"],
        context=INACTIVE_CONTEXT,
    )
    if existing:
        eco = require_one(existing, "Esami ECO")
        if not eco["name"].endswith(TITLE):
            raise ValueError("Stage BOM jau turi kitą ECO.")
        eid = eco["id"]
    else:
        eco_type = require_one(search("mrp.eco.type", [["name", "=", "BOM Updates"]], ["id"]), "BOM Updates")
        eid = execute("mrp.eco", "create", {
            "name": TITLE, "type_id": eco_type["id"], "type": "bom",
            "product_tmpl_id": product["id"], "bom_id": bid,
        })
        eco = {"new_bom_id": False}

    if not eco["new_bom_id"]:
        execute("mrp.eco", "action_new_revision", [eid])
    eco = require_one(search(
        "mrp.eco", [["id", "=", eid]], ["new_bom_id"], context=INACTIVE_CONTEXT
    ), "ECO")
    if not eco["new_bom_id"]:
        raise ValueError("Start Revision nesukūrė revizijos.")
    rid = eco["new_bom_id"][0]
    revision = require_one(search(
        "mrp.bom", [["id", "=", rid]], ["active", "product_tmpl_id"], context=INACTIVE_CONTEXT
    ), "Revizija")
    if rid == bid or revision["active"] or revision["product_tmpl_id"][0] != product["id"]:
        raise ValueError("Odoo grąžino netinkamą reviziją.")
    target = operation(rid)
    if target["time_cycle_manual"] == 50:
        execute("mrp.routing.workcenter", "write", [target["id"]], {"time_cycle_manual": 35})
    if operation(rid)["time_cycle_manual"] != 35 or operation(bid)["time_cycle_manual"] != 50:
        raise ValueError("Patikra nepraėjo: revizijoje turi būti 35 min., aktyviame BOM – 50 min.")
    print(f"Stage ECO {eid}, neaktyvi revizija {rid}: 35 min. Aktyvus BOM {bid}: 50 min.")


if __name__ == "__main__":
    run(sys.argv[1])
