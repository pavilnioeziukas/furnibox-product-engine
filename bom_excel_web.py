"""Authenticated read-only ticket #28 review screen; no PLM write endpoint."""
import hashlib
import hmac
from io import BytesIO
import os
from pathlib import Path
import secrets
import socket
import xmlrpc.client

from flask import Blueprint, abort, jsonify, render_template_string, request, session

from bom_excel_review import read_rows, require_stage, review_rows

PAGE = '''<!doctype html><html lang="lt"><meta charset="utf-8">
<title>BOM Excel → PLM · Peržiūra</title>
<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#f5f6f8;color:#17212b}section{background:white;border-radius:12px;padding:24px;margin:18px 0}button{background:#684863;color:white;padding:12px 20px;border:0;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.error{color:#a12424}input{margin:12px}</style>
<h1>BOM Excel → PLM</h1><p>1. Failo patikra → 2. Stage susiejimas → 3. Patvirtinimas → 4. ECO revizijos</p>
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

    app.register_blueprint(bp)
