"""Read-only production configuration audit for four single-component BOM cases."""
import json
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

CASES = {
    "UNI-P-ACC01-MIS102": ("BHT375M", 2),
    "SLF-PINS-HRD-4": ("459229-94", 4),
    "SLF-PINS-HRD-6": ("459229-94", 6),
    "UNI-P-ACC03-MIS009": ("MED4.0*30/100", 12),
}


def inspect_production():
    from config import load_settings
    from odoo_client import OdooClient
    settings = load_settings()
    if urlsplit(settings.url).hostname != "odoo.furnibox.lt":
        raise ValueError("Production host required")
    client = OdooClient(settings)
    def read(model, domain, fields):
        schema = client.execute(model, "fields_get", [], {"attributes": ["type"]})
        return client.search_read_all(model, domain, [f for f in fields if f in schema],
                                      context={"active_test": False})
    products = read("product.product", [("default_code", "in", list(CASES))],
        ["id","default_code","name","active","product_tmpl_id","purchase_ok","sale_ok",
         "uom_id","uom_po_id","route_ids","type","is_storable","company_id","write_date"])
    template_ids = sorted({p["product_tmpl_id"][0] for p in products if p.get("product_tmpl_id")})
    boms = read("mrp.bom", [("product_tmpl_id", "in", template_ids)],
        ["id","product_tmpl_id","product_id","active","code","sequence","type","product_qty",
         "product_uom_id","company_id","operation_ids","write_date"])
    lines = read("mrp.bom.line", [("bom_id", "in", [b["id"] for b in boms])],
        ["id","bom_id","product_id","product_qty","product_uom_id"])
    components = read("product.product", [("id", "in", sorted({l["product_id"][0] for l in lines}))],
        ["id","default_code","name","active","purchase_ok","sale_ok","uom_id","uom_po_id"])
    routes = read("stock.route", [("id", "in", sorted({r for p in products for r in p.get("route_ids", [])}))],
                  ["id","name","active"])
    route_names = {r["id"]: r["name"] for r in routes}
    suppliers = read("product.supplierinfo", [("product_tmpl_id", "in", template_ids)],
        ["id","product_tmpl_id","product_id","partner_id","product_code","product_uom_id","min_qty"])
    rows = []
    for code, expected in CASES.items():
        matches = [p for p in products if p.get("default_code") == code]
        for p in matches:
            company = p.get("company_id")
            candidates = [b for b in boms if b["product_tmpl_id"][0] == p["product_tmpl_id"][0]
                and (not b.get("product_id") or b["product_id"][0] == p["id"])
                and (not company or not b.get("company_id") or b["company_id"][0] == company[0])]
            active = [b for b in candidates if b.get("active")]
            lowest = min((b["sequence"] for b in active), default=None)
            selected = [b for b in active if b["sequence"] == lowest]
            contexts = {(str(b.get("company_id")),b.get("type")) for b in selected}
            chosen = selected[0] if len(selected) == 1 and len(contexts) == 1 and p.get("active") else None
            chosen_lines = [l for l in lines if chosen and l["bom_id"][0] == chosen["id"]]
            rows.append(dict(reform_product=code, reform_component=expected[0], reform_quantity=expected[1],
                product=p, routes=[route_names.get(r, str(r)) for r in p.get("route_ids", [])],
                bom_candidates=candidates, selected_bom=chosen, selected_lines=chosen_lines,
                components=[c for c in components if c["id"] in {l["product_id"][0] for l in chosen_lines}],
                suppliers=[s for s in suppliers if s["product_tmpl_id"][0] == p["product_tmpl_id"][0]]))
        if not matches:
            rows.append(dict(reform_product=code, error="Production product not found"))
    return dict(captured_at=datetime.now(timezone.utc).isoformat(), host="odoo.furnibox.lt", rows=rows)


def register(app):
    from flask import abort, jsonify, session
    @app.get("/reform-review/single-component-production-audit")
    def audit():
        if not session.get("authenticated"):
            abort(403)
        return jsonify(inspect_production())
    def probe():
        try:
            print("REFORM_SINGLE_COMPONENT_PRODUCTION " + json.dumps(inspect_production(), ensure_ascii=False), flush=True)
        except Exception as exc:
            print("REFORM_SINGLE_COMPONENT_PRODUCTION_FAILED " + type(exc).__name__, flush=True)
    threading.Thread(target=probe, daemon=True).start()
