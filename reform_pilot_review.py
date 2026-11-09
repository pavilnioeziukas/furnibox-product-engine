"""Pure read-only interpretation for three explicitly sourced Reform pilot cases."""
SOURCE = {
    "file": "Reform-Pivot-Changes (4).xlsx",
    "sha256": "b6beb112a4a733118304d11aca96f05f6cc7048d2cd68df9a77cc62870bc2b46",
    "submitted_at": "2026-11-06 11:24 UTC",
    "submitted_by": "pallingham@reformcph.com",
}
NON_BOM = {"code": "1632305B/0381", "name": "Linear light with sensor - W15 (Aluminium)",
           "category": "LED HARDWARE", "uom": "Units", "vendor_code": "1632305B/0381", "row": 44}
LED = {"reform_sku": "EUB-PACK-CAB03-SLF901-PP", "target": "EUB-C-CAB03-SLF901",
       "old": "EUB-LED-LAB01-1163-MB", "new": "EUB-LED-LAB01-1163-MS", "qty": 1,
       "removed_export_row": 3, "added_export_row": 4, "source_row": 4398}
NEW_BOM = {"sku": "EUB-P-ACC02-MIS012", "component": "2346417500", "qty": 1,
           "export_row": 2, "source_row": 4404}
PILOT_CODES = [
    "UNI-P-ACC02-MIS017", LED["reform_sku"], LED["target"], LED["old"], LED["new"],
    NON_BOM["code"], NEW_BOM["sku"], NEW_BOM["component"],
]


def relation_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else None


def label(value):
    if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int):
        return str(value[1])
    if value is True:
        return "Taip"
    if value is False or value is None or value == "":
        return "Nenustatyta"
    return str(value)



def select_bom(products, boms, *, scan_complete=False):
    """R16: choose a unique lowest sequence in a resolved active BOM context."""
    result = dict(status="review", label="Reikia peržiūros", reason="",
                  bom_ids=[], selected=None, ready_to_write=False)
    if not scan_complete:
        result["reason"] = "BOM nuskaitymas nepilnas; negalima nustatyti aktualaus BOM."
        return result
    if len(products) != 1 or not products[0].get("active"):
        result["reason"] = "Produkto atitikmuo nėra vienareikšmis ir aktyvus."
        return result
    product = products[0]
    template = relation_id(product.get("product_tmpl_id"))
    if not template:
        result["reason"] = "Trūksta produkto šablono tapatybės."
        return result
    company = relation_id(product.get("company_id"))
    matches = list({b["id"]: b for b in boms
                    if relation_id(b.get("product_tmpl_id")) == template
                    and (not b.get("product_id") or relation_id(b["product_id"]) == product["id"])
                    and (not company or not b.get("company_id")
                         or relation_id(b["company_id"]) == company)}.values())
    result["bom_ids"] = [b["id"] for b in matches]
    active = [b for b in matches if b.get("active")]
    if not matches:
        result.update(status="new_candidate", label="Kandidatas naujam BOM",
            reason="Stage nerasta nei aktyvaus, nei archyvuoto tinkamo BOM. Prieš kūrimą reikia produkcinės patikros, visos struktūros ir patvirtinimų.")
        return result
    if not active:
        result["reason"] = "Rasti tik archyvuoti BOM. Naujo BOM automatiškai nekurti."
        return result
    contexts = {(relation_id(b.get("company_id")), b.get("type")) for b in active}
    if len(contexts) != 1 or any(not b.get("type") for b in active):
        result["reason"] = "BOM tipas arba įmonės kontekstas nevienareikšmis; pirmiausia nustatyti tinkamą paskirtį."
        return result
    if any(type(b.get("sequence")) is not int for b in active):
        result["reason"] = "Trūksta patikimos sequence reikšmės; automatinė atranka blokuojama."
        return result
    minimum = min(b["sequence"] for b in active)
    lowest = [b for b in active if b["sequence"] == minimum]
    result["minimum_sequence"] = minimum
    if len(lowest) != 1:
        result["reason"] = "Keli aktyvūs BOM turi vienodą mažiausią sequence (" + str(minimum) + "). Reikia peržiūros."
        return result
    selected = lowest[0]
    result.update(status="plm_update", label="Esamo BOM korekcija per PLM",
        selected=selected, proposed_bom_id=selected["id"],
        reason="Pasirinktas BOM #" + str(selected["id"]) + ": vienintelis mažiausias sequence = "
               + str(minimum) + ". Pavadinimas ir versijos žyma atrankai nenaudojami. Keitimo apimčiai dar reikia patvirtinimų.")
    return result


def classify_bom(products, boms, *, scan_complete=False):
    result = select_bom(products, boms, scan_complete=scan_complete)
    return {key: value for key, value in result.items() if key != "selected"}


def pilot_version_evidence(products, boms, *, scan_complete=False):
    """Show the same sequence selection used by classification; never authorize writes."""
    selection = select_bom(products, boms, scan_complete=scan_complete)
    candidates = []
    for b in boms:
        if b["id"] not in selection["bom_ids"]:
            continue
        candidates.append(dict(id=b["id"], reference=b.get("code") or "Be nuorodos",
            sequence=b.get("sequence"), type=b.get("type"), active=b.get("active", False),
            company=label(b.get("company_id")), version=b.get("version"),
            write_date=b.get("write_date") or ""))
    selected = selection.get("selected")
    suggestion = next((b for b in candidates if selected and b["id"] == selected["id"]), None)
    return dict(candidates=candidates, suggestion=suggestion, reason=selection["reason"],
                ready_to_write=False)


def build_review(data):
    products = data["products"]
    by_id = {p["id"]: p for p in products}
    def exact(code):
        return [p for p in products if p.get("default_code") == code]
    def boms_for(product):
        template = relation_id(product.get("product_tmpl_id"))
        return [b for b in data["boms"] if relation_id(b.get("product_tmpl_id")) == template
                and (not b.get("product_id") or relation_id(b["product_id"]) == product["id"])]
    def display_product(p):
        return dict(code=p.get("default_code") or "Be vidinio kodo", name=p.get("name", ""),
                    active=p.get("active", False), id=p["id"])
    matches = {p["id"]: dict(display_product(p), basis="Vidinis kodas")
               for p in exact(NON_BOM["code"])}
    for vendor in data.get("suppliers", []):
        if vendor.get("product_code") != NON_BOM["vendor_code"]:
            continue
        variant = relation_id(vendor.get("product_id"))
        template = relation_id(vendor.get("product_tmpl_id"))
        for p in products:
            if (variant and variant == p["id"]) or (
                    not variant and relation_id(p.get("product_tmpl_id")) == template):
                item = dict(display_product(p), basis="Reform tiekėjo kodas")
                if p["id"] in matches:
                    item["basis"] += " ir vidinis kodas"
                matches[p["id"]] = item
    active_vendor_matches = [p for p in matches.values() if p["active"] and "tiekėjo" in p["basis"]]
    if not data.get("supplier_scope_complete", True):
        card_status = "Tiekėjo patikra nepilna — naujos kortelės nesiūlyti"
    elif len(matches) == 1 and len(active_vendor_matches) == 1:
        card_status = "Esama prekė — naujos kortelės nesiūlyti"
    elif matches:
        card_status = "Rasti atitikmenys — reikia susiejimo sprendimo"
    else:
        card_status = "Stage atitikmens nerasta — kandidatė naujai kortelei"
    rows = []
    for code, role in [(LED["target"], "Siūlomas Odoo tikslas"), (LED["reform_sku"], "Reform pateiktas kodas")]:
        for p in exact(code):
            for b in boms_for(p):
                matching = [line for line in data["lines"]
                            if relation_id(line.get("bom_id")) == b["id"]
                            and relation_id(line.get("product_id")) in
                            {x["id"] for x in exact(LED["old"])}]
                if matching:
                    rows.append(dict(id=b["id"], code=code, role=role, active=b.get("active", False),
                        reference=b.get("code") or "Be nuorodos", type=b.get("type") or "Nežinoma",
                        write_date=b.get("write_date") or "", quantity=b.get("product_qty"),
                        lines=[dict(id=line["id"], qty=line.get("product_qty"),
                                    uom=label(line.get("product_uom_id"))) for line in matching]))
    new_components = [p for p in exact(LED["new"]) if p.get("active")]
    selection = classify_bom(exact(LED["target"]), data["boms"],
                             scan_complete=data.get("bom_scan_complete", False))
    selected_id = selection.get("proposed_bom_id")
    led_blockers = ["Patikrinti pakeitimo poveikį kitiems gaminiams ir gauti turinio patvirtinimus."]
    if not selected_id:
        led_blockers.insert(0, selection["reason"])
    elif not any(b["id"] == selected_id for b in rows):
        led_blockers.insert(0, "Pagal sequence pasirinktame BOM seno komponento nėra. Aukštesnio sequence BOM vietoje jo automatiškai nepasirenkame.")
    if len(new_components) != 1:
        led_blockers.insert(0, "Naujo komponento aktyvus atitikmuo nėra vienareikšmis.")
    routes = {r["id"]: r.get("name", "") for r in data.get("routes", [])}
    configs = []
    for p in products:
        if p.get("default_code") not in ("UNI-P-ACC02-MIS017", LED["target"], LED["reform_sku"]):
            continue
        configs.append(dict(product=display_product(p), fields=[
            ("Kategorija", label(p.get("categ_id"))),
            ("Tipas", label(p.get("type"))), ("Atsargų apskaita", label(p.get("is_storable"))),
            ("Perkama", label(p.get("purchase_ok"))), ("Parduodama", label(p.get("sale_ok"))),
            ("Matavimo vienetas", label(p.get("uom_id"))),
            ("Pirkimo matavimo vienetas", label(p.get("uom_po_id"))),
            ("Maršrutai", ", ".join(routes.get(r, str(r)) for r in p.get("route_ids", [])) or "Nenustatyta"),
            ("Sekimas", label(p.get("tracking"))),
            ("Tiekėjo sąskaitos kontrolė", label(p.get("purchase_method"))),
        ]))
    return dict(source=SOURCE, non_bom=NON_BOM, card_status=card_status,
                matches=list(matches.values()), led=LED, led_boms=rows, led_blockers=led_blockers,
                new_components=[display_product(p) for p in new_components],
                new_bom=NEW_BOM, new_bom_products=[display_product(p) for p in exact(NEW_BOM["sku"])],
                led_classification=classify_bom(exact(LED["target"]), data["boms"],
                    scan_complete=data.get("bom_scan_complete", False)),
                new_bom_classification=classify_bom(exact(NEW_BOM["sku"]), data["boms"],
                    scan_complete=data.get("bom_scan_complete", False)),
                led_versions=pilot_version_evidence(exact(LED["target"]), data["boms"],
                    scan_complete=data.get("bom_scan_complete", False)),
                bom_versions=pilot_version_evidence(exact(NEW_BOM["sku"]), data["boms"],
                    scan_complete=data.get("bom_scan_complete", False)),
                configs=configs, ready_to_write=False)
