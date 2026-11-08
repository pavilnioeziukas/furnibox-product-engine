"""Authenticated read-only ticket #28 review screen; no PLM write endpoint."""
import hashlib
import hmac
from io import BytesIO
import os
from pathlib import Path
import secrets
import socket
import threading
import xmlrpc.client

from flask import Blueprint, abort, jsonify, render_template_string, request, session

from bom_excel_review import read_rows, require_stage, review_rows
from reform_pilot_review import PILOT_CODES, NON_BOM, build_review

PAGE = '''<!doctype html><html lang="lt"><meta charset="utf-8">
<title>BOM Excel → PLM · Peržiūra</title>
<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#f5f6f8;color:#17212b}section{background:white;border-radius:12px;padding:24px;margin:18px 0}button{background:#684863;color:white;padding:12px 20px;border:0;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.error{color:#a12424}input{margin:12px}</style>
<h1>BOM Excel → PLM</h1><p><a href="/bom-excel/reform-pilot/">Reform Stage piloto patikra</a></p><p>1. Failo patikra → 2. Stage susiejimas → 3. Patvirtinimas → 4. ECO revizijos</p>
<section><h2>Stage ryšys</h2><p>{{ connection }}</p>
<p>Ši versija tik skaito. ECO kūrimas dar neįjungtas.</p></section>
<section><h2>Tamaros korekcijų peržiūra</h2>
<p>Palyginimui naudojama serveryje saugoma patikima bazinė versija. Grąžinto failo paslėptas lapas nelaikomas etalonu.</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{{ csrf }}">
<input type="file" name="workbook" accept=".xlsx" required><button>Tikrinti Excel</button></form></section>
{% if result %}<section><h2>Rezultatas</h2><p>{{ result.changes|length }} pakeitimų; {{ result.errors|length }} klaidų; {{ result.human_review|length }} pastabų žmogaus peržiūrai.</p>
<p>Numatoma iki {{ result.proposed_eco_count }} ECO — po vieną kiekvienam keičiamam BOM.</p>
<pre>{{ result|tojson(indent=2) }}</pre><p>Rašymas į Odoo blokuojamas, kol nebaigta Stage susiejimo ir ECO vykdymo dalis.</p></section>{% endif %}
</html>'''


def stage_status():
    url = os.getenv('ODOO_URL', '').strip().rstrip('/')
    try:
        require_stage(url)
    except ValueError:
        return 'Blokuota: integracijos ODOO_URL nėra patvirtintas Furnibox Stage adresas.'
    if not all(os.getenv(k, '').strip() for k in ('ODOO_DB', 'ODOO_LOGIN', 'ODOO_API_KEY')):
        return 'Blokuota: trūksta Stage API konfigūracijos.'
    try:
        # Each proxy uses a bounded transport without changing global sockets.
        class Transport(xmlrpc.client.SafeTransport):
            def make_connection(self, host):
                connection = super().make_connection(host)
                connection.timeout = 20
                return connection
        db, key = os.environ['ODOO_DB'], os.environ['ODOO_API_KEY']
        uid = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', transport=Transport()).authenticate(
            db, os.environ['ODOO_LOGIN'], key, {})
        if not uid:
            return 'Stage API autentifikacija nepavyko.'
        proxy = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/object', transport=Transport())
        fields = proxy.execute_kw(db, uid, key, 'mrp.eco', 'fields_get', [],
                                  {'attributes': ['type', 'relation']})
        needed = {'bom_id', 'new_bom_id', 'product_tmpl_id', 'type_id'}
        if not needed <= fields.keys():
            return 'Stage API veikia, tačiau PLM laukų sutartis neatitinka laukiamų laukų.'
        return 'Stage API autentifikacija ir ECO laukų skaitymas patvirtinti.'
    except Exception as exc:
        return 'Stage API patikra nepavyko (' + type(exc).__name__ + ').'


def trusted_baseline():
    path = os.getenv('BOM_EXCEL_BASELINE_PATH', '')
    expected = os.getenv('BOM_EXCEL_BASELINE_SHA256', '')
    if not path or len(expected) != 64:
        raise ValueError('Neįdiegta patikima bazinio Excel kopija ir jos SHA-256 kontrolinė suma.')
    data = Path(path).read_bytes()
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected.lower()):
        raise ValueError('Bazinės Excel kopijos kontrolinė suma nesutampa.')
    return read_rows(BytesIO(data))



def pilot_inventory():
    """Read Stage configuration only; never infer approval from a matching card."""
    url = os.getenv('ODOO_URL', '').strip().rstrip('/')
    require_stage(url)
    db, login, key = [os.environ[k] for k in ('ODOO_DB', 'ODOO_LOGIN', 'ODOO_API_KEY')]
    class Transport(xmlrpc.client.SafeTransport):
        def make_connection(self, host):
            connection = super().make_connection(host)
            connection.timeout = 20
            return connection
    uid = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', transport=Transport()).authenticate(db, login, key, {})
    if not uid:
        raise ValueError('Stage autentifikacija nepavyko.')
    proxy = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/object', transport=Transport())
    def read(model, domain, wanted):
        available = proxy.execute_kw(db, uid, key, model, 'fields_get', [], {'attributes': ['type']})
        fields = [f for f in wanted if f in available]
        rows, offset = [], 0
        while True:
            batch = proxy.execute_kw(db, uid, key, model, 'search_read', [domain],
                {'fields': fields, 'context': {'active_test': False}, 'limit': 200, 'offset': offset, 'order': 'id'})
            rows.extend(batch)
            if len(batch) < 200:
                return rows
            offset += 200
    codes = PILOT_CODES
    products = read('product.product', [('default_code', 'in', codes)],
        ['id','default_code','name','active','product_tmpl_id','type','is_storable','categ_id','uom_id','uom_po_id','route_ids','purchase_ok','sale_ok','invoice_policy','purchase_method','taxes_id','supplier_taxes_id','tracking','company_id','write_date'])
    partners = read('res.partner', [('name', '=', 'Reform Supply & Logistics, UAB')], ['id', 'name'])
    suppliers = read('product.supplierinfo',
        [('partner_id', 'in', [p['id'] for p in partners]), ('product_code', '=', NON_BOM['vendor_code'])],
        ['id', 'partner_id', 'product_code', 'product_id', 'product_tmpl_id', 'company_id'])
    vendor_templates = sorted({v['product_tmpl_id'][0] for v in suppliers if v.get('product_tmpl_id')})
    if vendor_templates:
        linked = read('product.product', [('product_tmpl_id', 'in', vendor_templates)],
            ['id','default_code','name','active','product_tmpl_id','type','is_storable','categ_id','uom_id','uom_po_id','route_ids','purchase_ok','sale_ok','invoice_policy','purchase_method','taxes_id','supplier_taxes_id','tracking','company_id','write_date'])
        products = list({p['id']: p for p in products + linked}.values())
    templates = sorted({p['product_tmpl_id'][0] for p in products if p.get('product_tmpl_id')})
    boms = read('mrp.bom', [('product_tmpl_id', 'in', templates)],
        ['id','product_tmpl_id','product_id','active','type','code','sequence','product_qty','product_uom_id','write_date','company_id','version'])
    lines = read('mrp.bom.line', [('bom_id', 'in', [b['id'] for b in boms])],
        ['id','bom_id','product_id','product_qty','product_uom_id'])
    routes = sorted({r for p in products for r in p.get('route_ids', [])})
    return dict(products=products, boms=boms, lines=lines, suppliers=suppliers, supplier_scope_complete=len(partners) == 1,
        routes=read('stock.route', [('id','in',routes)], ['id','name','active']),
        eco_types=read('mrp.eco.type', [], ['id','name']),
        eco_stages=read('mrp.eco.stage', [], ['id','name','type_ids','allow_apply_change','final_stage','approval_ids']),
        bom_scan_complete=True, ready_to_write=False)

PILOT_PAGE = '''<!doctype html><html lang="lt"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reform · Pakeitimų peržiūra</title>
<style>
:root{font-family:system-ui;color:#17332e;background:#f3f6f5}*{box-sizing:border-box}body{max-width:1160px;margin:32px auto;padding:0 20px 50px}a{color:#126451}h1{font-size:32px;margin:16px 0 8px}h2{font-size:23px}h3{font-size:17px}p{line-height:1.55}.muted{color:#5b6e68}.badge{display:inline-block;background:#e3eee9;border-radius:20px;padding:6px 12px;font-size:13px}.pending{background:#fff1d7;color:#79530c}.error{color:#9f2b25;background:#fff0ed;padding:20px;border-radius:12px}section{background:white;border:1px solid #dce5e0;border-radius:14px;padding:26px;margin:20px 0;scroll-margin-top:20px}nav{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}nav a{padding:10px 14px;background:#fff;border:1px solid #dce5e0;border-radius:8px;text-decoration:none}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.box{background:#f4f7f5;border-radius:10px;padding:18px;min-width:0}code{font-size:14px;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:12px;border-bottom:1px solid #e1e7e3;vertical-align:top}.scroll{overflow-x:auto}li{margin:10px 0;line-height:1.5}summary{cursor:pointer;padding:12px 0;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.notice{border-left:4px solid #bc8a29;padding:12px 18px;background:#fff9ec}.meta{font-size:13px}.config{border-top:1px solid #e1e7e3;margin-top:16px;padding-top:12px}@media(max-width:700px){.grid{grid-template-columns:1fr}body{padding:0 12px}section{padding:18px}h1{font-size:26px}}
</style>
<a href="/bom-excel/">← Grįžti</a>
<h1>Reform pakeitimų peržiūra</h1>
<p class="muted">Stage pilotas · 3 konkretūs atvejai · kortelių ir ECO kūrimas išjungtas</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
{% macro versions(evidence) %}
{% if evidence.suggestion %}<p class="notice"><strong>Siūloma piloto bazė: BOM #{{ evidence.suggestion.id }}</strong> · {{ evidence.suggestion.reference }} · eiliškumas {{ evidence.suggestion.sequence }}.<br>Pagrindas: sutartas v10 etalonas, vienintelis aktyvus v10 su eiliškumu 0 ir vienodas įmonės bei BOM tipo kontekstas. Tai pasiūlymas peržiūrai, ne patvirtinimas ar leidimas vykdyti.</p>{% else %}<p class="notice">Vienareikšmio v10 kandidato pagal piloto sąlygas nerasta. Reikia rankinio pasirinkimo.</p>{% endif %}
<div class="scroll"><table><tr><th>BOM</th><th>Šaltinio versija</th><th>Eiliškumas</th><th>Tipas / įmonė</th><th>PLM versija</th><th>Pakeista</th></tr>
{% for b in evidence.candidates %}<tr><td><a target="_blank" rel="noopener" href="https://stageodoo.furnibox.lt/web#id={{ b.id }}&model=mrp.bom&view_type=form">#{{ b.id }}</a><br>{{ 'Aktyvus' if b.active else 'Archyvuotas' }}</td><td>{{ b.reference }}</td><td>{{ b.sequence }}</td><td>{{ b.type }}<br>{{ b.company }}</td><td>{{ b.version }}</td><td>{{ b.write_date }}</td></tr>{% endfor %}</table></div>
<p class="meta">Šaltinio žyma „v10“ ir Odoo PLM revizijos numeris yra skirtingi laukai. Pasiūlymas nekeičia R16 būsenos „Reikia peržiūros“ ir nepakeičia patikros produkcijoje.</p>
{% endmacro %}
{% if review %}
<span class="badge">Stage duomenys nuskaityti</span> <span class="badge pending">Laukia sprendimų ir patvirtinimų</span>
<p class="meta">Pasirinktas šaltinis: <strong>{{ review.source.file }}</strong> · pateikė {{ review.source.submitted_by }} · {{ review.source.submitted_at }}.<br>Tai konkretaus eksporto pilotas. Naujesni Reform pateikimai automatiškai neįtraukiami.</p>
<nav><a href="#led">1. LED korekcija</a><a href="#card">2. Naujos kortelės patikra</a><a href="#bom">3. Naujo BOM patikra</a></nav>
<section id="led"><span class="badge pending">{{ review.led_classification.label }}</span><h2>1. LED komponento pakeitimas</h2><p>{{ review.led_classification.reason }}</p>
<div class="grid"><div class="box"><h3>Poul pateikė</h3><p>Produktas: <code>{{ review.led.reform_sku }}</code></p>
<p>Pašalinti <code>{{ review.led.old }}</code><br>Pridėti <code>{{ review.led.new }}</code><br>Kiekis: {{ review.led.qty }}</p></div>
<div class="box"><h3>Furnibox interpretacija</h3><p>Siūlomas produktas: <code>{{ review.led.target }}</code></p>
<p>Tai sutartos interpretavimo taisyklės kandidatas. Konkreti BOM versija dar nepatvirtinta.</p></div></div>
<h3>Kurios BOM versijos bazę siūlome?</h3>{{ versions(review.led_versions) }}<h3>Odoo BOM, kuriuose rastas senas komponentas</h3>
{% if review.led_boms %}<div class="scroll"><table><thead><tr><th>Produktas / paskirtis</th><th>BOM / būsena</th><th>Dabar</th><th>Siūloma</th></tr></thead><tbody>
{% for b in review.led_boms %}<tr><td><code>{{ b.code }}</code><br>{{ b.role }}</td>
<td><a target="_blank" rel="noopener" href="https://stageodoo.furnibox.lt/web#id={{ b.id }}&model=mrp.bom&view_type=form">BOM #{{ b.id }}</a><br>{{ b.reference }} · {{ 'Aktyvus' if b.active else 'Archyvuotas' }}<br>{{ b.type }} · {{ b.write_date }}</td>
<td><code>{{ review.led.old }}</code>{% for l in b.lines %}<p>Eilutė #{{ l.id }}: {{ l.qty }} {{ l.uom }}</p>{% endfor %}</td>
<td>{% if b.code == review.led.target and b.active %}<code>{{ review.led.new }}</code><p>Kiekį ir UOM išlaikyti tik patikrinus vienetų suderinamumą.</p>{% else %}Automatinis pakeitimas nesiūlomas{% endif %}</td></tr>{% endfor %}</tbody></table></div>
{% else %}<p class="notice">Stage nerasta BOM eilutė su senu komponentu. Jokio keitimo nesiūlome.</p>{% endif %}
<h3>Kas stabdo vykdymą</h3><ul>{% for item in review.led_blockers %}<li>{{ item }}</li>{% endfor %}</ul>
<p class="meta">Įrodymai: Changes eksporto eilutės {{ review.led.removed_export_row }} ir {{ review.led.added_export_row }}; šaltinio eilutė {{ review.led.source_row }}.</p></section>
<section id="card"><span class="badge pending">{{ review.card_status }}</span><h2>2. Ar tikrai reikia naujos kortelės?</h2>
<div class="grid"><div class="box"><h3>Reform pozicija</h3><p><code>{{ review.non_bom.code }}</code><br>{{ review.non_bom.name }}</p><p>{{ review.non_bom.category }} · {{ review.non_bom.uom }}<br>Tiekėjo kodas: <code>{{ review.non_bom.vendor_code }}</code></p></div>
<div class="box"><h3>Siūlomas veiksmas</h3>{% if review.matches %}<p>Pirmiausia nuspręsti dėl esamos kortelės susiejimo. Naujos kortelės automatiškai nekurti.</p>{% else %}<p>Palikti kandidatę naujai kortelei. Prieš kūrimą sutikrinti produkcinį Odoo ir patvirtinti konfigūraciją.</p>{% endif %}<p>Šablonas dar neparinktas. Kategorijos pavadinimo nepakanka maršrutams ir apskaitos nustatymams kopijuoti.</p></div></div>
{% if review.matches %}<h3>Stage atitikmenys, įskaitant archyvuotus</h3><div class="scroll"><table><tr><th>Odoo kortelė</th><th>Būsena</th><th>Atitikimo pagrindas</th></tr>
{% for p in review.matches %}<tr><td><a target="_blank" rel="noopener" href="https://stageodoo.furnibox.lt/web#id={{ p.id }}&model=product.product&view_type=form">{{ p.code }}</a><br>{{ p.name }}</td><td>{{ 'Aktyvi' if p.active else 'Archyvuota' }}</td><td>{{ p.basis }}</td></tr>{% endfor %}</table></div>{% endif %}
<p class="notice">Stage patikra nepakeičia aktualios produkcinės patikros. Archyvuota kortelė savaime nėra leidimas kurti naują.</p>
<p class="meta">Įrodymai: New Non-BOM items; Reform šaltinio eilutė {{ review.non_bom.row }}. Tikrintas tik Reform Supply & Logistics, UAB tiekėjo kodas.</p></section>
<section id="bom"><span class="badge pending">{{ review.new_bom_classification.label }}</span><h2>3. BOM sukūrimas ar korekcija?</h2><p>{{ review.new_bom_classification.reason }}</p><p class="meta">Taisyklė R16 · rasti BOM ID: {{ review.new_bom_classification.bom_ids|join(", ") or "Nerasta" }}</p>
<div class="grid"><div class="box"><h3>Eksporte pridėta eilutė</h3><p><code>{{ review.new_bom.sku }}</code><br>Komponentas <code>{{ review.new_bom.component }}</code><br>Kiekis {{ review.new_bom.qty }}</p></div>
<div class="box"><h3>Sprendimas dabar</h3><p>{{ review.new_bom_classification.label }}. „Added“ reiškia skirtumą nuo etalono, o ne naujo BOM įrodymą. Vykdymas blokuojamas, kol nėra visos struktūros ir patvirtinimų.</p></div></div>
{% if review.new_bom_products %}<h3>Stage rastos produkto kortelės</h3><ul>{% for p in review.new_bom_products %}<li>{{ p.code }} · {{ p.name }} · {{ 'Aktyvi' if p.active else 'Archyvuota' }}</li>{% endfor %}</ul>{% endif %}
<h3>Esamos BOM versijos</h3>{{ versions(review.bom_versions) }}<ul><li>Gauti visą šio produkto BOM iš Poul pateikto workbook, ne vien skirtumų eksportą.</li><li>Sutikrinti esamus BOM ir jų versijas, nustatyti Manufacture arba KIT paskirtį.</li><li>Patvirtinti komponentus, kiekius, UOM ir operacijas; tada pasirinkti naują BOM arba esamo BOM korekciją.</li></ul>
<p class="meta">Įrodymai: Changes eksporto eilutė {{ review.new_bom.export_row }}; šaltinio eilutė {{ review.new_bom.source_row }}.</p></section>
<section><h2>Konfigūracijos pavyzdžiai — dar nepatvirtinti šablonai</h2><p class="muted">Šie nustatymai nuskaityti iš Stage. Jie nekopijuojami į naujas korteles.</p>
{% for cfg in review.configs %}<details class="config"><summary>{{ cfg.product.code }} · {{ cfg.product.name }} · {{ 'Aktyvi' if cfg.product.active else 'Archyvuota' }}</summary><table><tr><th>Nustatymas</th><th>Dabar Odoo</th></tr>{% for name,value in cfg.fields %}<tr><td>{{ name }}</td><td>{{ value }}</td></tr>{% endfor %}</table></details>{% endfor %}
</section>
<section><h2>Patvirtinimai ir PLM</h2><p>Interpretacija → Tamaros turinio patvirtinimas → galutinis Furnibox leidimas → vykdymas.</p><p>Šis ekranas dar nefiksuoja patvirtinimų. Nei atverstas puslapis, nei vienas rastas BOM nėra patvirtinimas.</p>
<p>Stage rasta {{ data.eco_types|length }} PLM tipai ir {{ data.eco_stages|length }} etapai. Jie dar nesusieti su šio paketo patvirtinimo eiga.</p>
<details><summary>Techniniai duomenys ir šaltinio kontrolinė suma</summary><p>Eksporto SHA-256: <code>{{ review.source.sha256 }}</code></p><p>Kontrolinė suma identifikuoja naudotą failą; savaime nepatvirtina jo autentiškumo.</p>
{% for title, rows in [('PLM tipai',data.eco_types),('PLM etapai',data.eco_stages)] %}<h3>{{ title }}</h3><pre>{{ rows|tojson(indent=2) }}</pre>{% endfor %}</details></section>
{% endif %}</html>'''

def register(app):
    bp = Blueprint('bom_excel', __name__)

    @bp.route('/bom-excel/', methods=['GET', 'POST'])
    def preview():
        # Do not expose review data if the host app has authentication disabled.
        if not (session.get('actor_id') or session.get('authenticated')):
            abort(403)
        csrf = session.setdefault('bom_excel_csrf', secrets.token_urlsafe(32))
        result, error = None, None
        if request.method == 'POST':
            if not hmac.compare_digest(request.form.get('csrf', ''), csrf):
                abort(400)
            upload = request.files.get('workbook')
            if not upload or not upload.filename.lower().endswith('.xlsx'):
                error = 'Reikalingas .xlsx failas.'
            else:
                try:
                    data = upload.read(10 * 1024 * 1024 + 1)
                    if len(data) > 10 * 1024 * 1024:
                        raise ValueError('Failas viršija 10 MB ribą.')
                    result = review_rows(trusted_baseline(), read_rows(BytesIO(data)))
                    result['file_sha256'] = hashlib.sha256(data).hexdigest()
                    result['stage_mapping_complete'] = False
                except ValueError as exc:
                    error = str(exc)
                except Exception:
                    error = 'Failo nepavyko patikrinti. Patikrinkite formatą ir bazinės kopijos konfigūraciją.'
        return render_template_string(PAGE, csrf=csrf, result=result, error=error,
                                      connection=stage_status())

    @bp.get('/bom-excel/reform-pilot/')
    def reform_pilot():
        if not (session.get('actor_id') or session.get('authenticated')):
            abort(403)
        data, error = None, None
        try:
            data = pilot_inventory()
        except Exception as exc:
            error = 'Stage nuskaitymas nepavyko (' + type(exc).__name__ + '). Patikrinkite Stage ryšį ir skaitymo teises.'
        return render_template_string(PILOT_PAGE, data=data, error=error,
                                      review=build_review(data) if data is not None else None)

    app.register_blueprint(bp)
    if os.getenv('RAILWAY_ENVIRONMENT_ID') == '67ee29c1-07f5-4242-aa13-d3e4972f16a9':
        def probe_stage():
            status = stage_status()
            print('REFORM_STAGE_CONNECTION ' + status, flush=True)
            if status == 'Stage API autentifikacija ir ECO laukų skaitymas patvirtinti.':
                try:
                    inventory = pilot_inventory()
                    print('REFORM_STAGE_INVENTORY ' + str({
                        key: len(inventory[key])
                        for key in ('products', 'boms', 'lines', 'eco_types', 'eco_stages')
                    }), flush=True)
                    interpreted = build_review(inventory)
                    print('REFORM_PILOT_REVIEW ' + str({
                        'non_bom_status': interpreted['card_status'],
                        'non_bom_match_count': len(interpreted['matches']),
                        'led_bom_candidates': [
                            {'id': b['id'], 'product': b['code'], 'active': b['active'], 'reference': b['reference']}
                            for b in interpreted['led_boms']
                        ],
                        'new_component_matches': len(interpreted['new_components']),
                        'new_bom_product_matches': len(interpreted['new_bom_products']),
                        'bom_classification': interpreted['new_bom_classification'],
                        'led_classification': interpreted['led_classification'],
                        'led_version_suggestion': interpreted['led_versions']['suggestion'],
                        'bom_version_suggestion': interpreted['bom_versions']['suggestion'],
                        'ready_to_write': interpreted['ready_to_write'],
                    }), flush=True)
                except Exception as exc:
                    print('REFORM_STAGE_INVENTORY_FAILED ' + type(exc).__name__, flush=True)
        threading.Thread(target=probe_stage, daemon=True).start()
