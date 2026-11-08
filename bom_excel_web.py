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
    codes = ['UNI-P-ACC02-MIS017', 'EUB-PACK-CAB03-SLF901-PP', 'EUB-C-CAB03-SLF901', 'EUB-LED-LAB01-1163-MS']
    products = read('product.product', [('default_code', 'in', codes)],
        ['id','default_code','name','active','product_tmpl_id','type','is_storable','categ_id','uom_id','uom_po_id','route_ids','purchase_ok','sale_ok','invoice_policy','purchase_method','taxes_id','supplier_taxes_id','tracking','company_id','write_date'])
    templates = sorted({p['product_tmpl_id'][0] for p in products if p.get('product_tmpl_id')})
    boms = read('mrp.bom', [('product_tmpl_id', 'in', templates)],
        ['id','product_tmpl_id','product_id','active','type','code','sequence','product_qty','product_uom_id','write_date'])
    lines = read('mrp.bom.line', [('bom_id', 'in', [b['id'] for b in boms])],
        ['id','bom_id','product_id','product_qty','product_uom_id'])
    routes = sorted({r for p in products for r in p.get('route_ids', [])})
    return dict(products=products, boms=boms, lines=lines,
        routes=read('stock.route', [('id','in',routes)], ['id','name','active']),
        eco_types=read('mrp.eco.type', [], ['id','name']),
        eco_stages=read('mrp.eco.stage', [], ['id','name','type_ids','allow_apply_change','final_stage','approval_ids']),
        ready_to_write=False)

PILOT_PAGE = '''<!doctype html><html lang="lt"><meta charset="utf-8"><title>Reform · Stage pilotas</title>
<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#f5f6f8;color:#17212b}section{background:white;border-radius:12px;padding:24px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}.error{color:#a12424}</style>
<a href="/bom-excel/">Grįžti</a><h1>Reform → Odoo Stage pilotas</h1>
<p>Konfigūracijos patikra. Kortelių ir ECO kūrimas dar neįjungtas.</p>
<section><h2>Trys bandymo atvejai</h2><table><tr><th>Atvejis</th><th>Kas tikrinama</th><th>Ko dar reikia</th></tr>
<tr><td>Nauja perkama prekė</td><td>UNI-P-ACC02-MIS017 kaip galimas konfigūracijos pavyzdys</td><td>Patvirtinti šabloną ir tikrai naują Reform poziciją</td></tr>
<tr><td>Naujas BOM</td><td>Gaminamo pusgaminio ir KIT skirtumai</td><td>Patvirtinti produkto paskirtį, komponentus, operacijas ir PLM eigą</td></tr>
<tr><td>LED korekcija</td><td>EUB-C-CAB03-SLF901: 1163-MB → 1163-MS</td><td>Patvirtinti aktualų BOM ir poveikį susijusiems gaminiams</td></tr></table></section>
{% if error %}<section class="error">{{ error }}</section>{% endif %}
{% if data %}<section><h2>Stage nuskaitymo rezultatas</h2><p>{{ data.products|length }} kortelės, {{ data.boms|length }} BOM, {{ data.eco_types|length }} PLM tipai, {{ data.eco_stages|length }} etapai.</p>
<p>Įtraukti archyvuoti įrašai. Šis nuskaitymas nepatvirtina šablono ar aktualios BOM versijos.</p>
{% for title, rows in [('Kortelių konfigūracija',data.products),('Maršrutai',data.routes),('BOM versijos',data.boms),('BOM komponentai',data.lines),('PLM tipai',data.eco_types),('PLM etapai',data.eco_stages)] %}
<details><summary>{{ title }} ({{ rows|length }})</summary><pre>{{ rows|tojson(indent=2) }}</pre></details>{% endfor %}</section>{% endif %}</html>'''


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
        return render_template_string(PILOT_PAGE, data=data, error=error)

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
                except Exception as exc:
                    print('REFORM_STAGE_INVENTORY_FAILED ' + type(exc).__name__, flush=True)
        threading.Thread(target=probe_stage, daemon=True).start()
