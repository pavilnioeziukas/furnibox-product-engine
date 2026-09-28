"""Reform change proposals. This module never writes to Odoo."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

reform = Blueprint('reform', __name__, url_prefix='/reform')


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    path = Path(current_app.config['REFORM_STATE_DIR']) / 'reform.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (owner TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (identity TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
    ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def baseline(conn):
    row = conn.execute('SELECT payload FROM state WHERE id=1').fetchone()
    return json.loads(row['payload']) if row else None


def owner():
    return session.get('reform_user') or 'Furnibox'


def admin():
    return bool(current_app.config.get('REFORM_ADMIN_ENABLED')) and bool(session.get('authenticated')) and not session.get('reform_user')


def draft(conn):
    row = conn.execute('SELECT * FROM drafts WHERE owner=?', (owner(),)).fetchone()
    if row:
        return json.loads(row['payload']), row['revision']
    base = baseline(conn)
    if not base:
        abort(409, 'Pirmiausia Furnibox turi pateikti produktų ir BOM duomenis.')
    return {'base': base, 'target': copy.deepcopy(base)}, 0


def changes(base, target):
    result = []
    for kind in ('products', 'boms'):
        for key in sorted(set(base[kind]) | set(target[kind])):
            before, after = base[kind].get(key), target[kind].get(key)
            if before != after:
                result.append({'kind': kind, 'key': key, 'before': before, 'after': after})
    return result


def positive(value):
    try:
        number = float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError('Kiekis turi būti skaičius.')
    if not math.isfinite(number) or number <= 0:
        raise ValueError('Kiekis turi būti didesnis už nulį.')
    return number


def validate(target):
    products, boms = target['products'], target['boms']
    edges = {}
    for bom in boms.values():
        if not bom.get('active', True):
            continue
        parent = bom['sku']
        if parent not in products:
            raise ValueError('BOM produktas nerastas.')
        if not products[parent]['active']:
            continue
        positive(bom['quantity'])
        if not bom['components']:
            raise ValueError('Aktyviame BOM turi būti bent vienas komponentas.')
        for line in bom['components']:
            child = line['sku']
            if child not in products or not products[child]['active']:
                raise ValueError(f'Komponentas {child} neegzistuoja arba jo naudojimas nutrauktas.')
            positive(line['quantity'])
            edges.setdefault(parent, set()).add(child)
    visited, stack = set(), set()
    def visit(sku):
        if sku in stack:
            raise ValueError('BOM sudaro ciklą: produktas negali būti savo paties komponentas.')
        if sku in visited:
            return
        stack.add(sku)
        for child in edges.get(sku, ()):
            visit(child)
        stack.remove(sku)
        visited.add(sku)
    for sku in products:
        visit(sku)


def read_odoo(client, roots):
    """Curated roots + component closure. Prices are never requested."""
    def ident(value):
        return value[0] if isinstance(value, (list, tuple)) and value else value or None
    def label(value):
        return value[1] if isinstance(value, (list, tuple)) and len(value) > 1 else ''
    raw_products = client.search_read_all('product.product', [],
        ['id', 'default_code', 'name', 'active', 'product_tmpl_id', 'uom_id'], context={'active_test': False})
    by_id = {p['id']: p for p in raw_products}
    by_sku = {}
    for p in raw_products:
        if p.get('default_code'):
            by_sku.setdefault(p['default_code'], []).append(p)
    if any(len(by_sku.get(sku, [])) != 1 for sku in roots):
        raise ValueError('Pasirinkti produktų kodai turi egzistuoti Odoo ir būti unikalūs.')
    raw_boms = client.search_read_all('mrp.bom', [('active', '=', True)],
        ['id', 'product_id', 'product_tmpl_id', 'product_qty', 'product_uom_id', 'type', 'code'])
    raw_lines = client.search_read_all('mrp.bom.line', [('bom_id', 'in', [b['id'] for b in raw_boms])],
        ['id', 'bom_id', 'product_id', 'product_qty', 'product_uom_id', 'bom_product_template_attribute_value_ids']) if raw_boms else []
    lines_by_bom = {}
    for line in raw_lines:
        lines_by_bom.setdefault(ident(line['bom_id']), []).append(line)
    selected = {by_sku[sku][0]['id'] for sku in roots}
    included_boms = {}
    pending = list(selected)
    while pending:
        pid = pending.pop()
        p = by_id[pid]
        for b in raw_boms:
            applies = ident(b['product_id']) == pid if b['product_id'] else ident(b['product_tmpl_id']) == ident(p['product_tmpl_id'])
            if not applies:
                continue
            # A shared variant BOM needs a richer editor; do not flatten it silently.
            variants = [v for v in raw_products if ident(v['product_tmpl_id']) == ident(p['product_tmpl_id']) and v['active']]
            if not b['product_id'] and len(variants) > 1:
                raise ValueError('Pasirinktas BOM bendras keliems variantams. Pilotui pasirinkite atskiro produkto BOM.')
            included_boms[b['id']] = b
            for line in lines_by_bom.get(b['id'], []):
                if line.get('bom_product_template_attribute_value_ids'):
                    raise ValueError('BOM turi variantų sąlygų. Šiam BOM reikia išplėsto redaktoriaus.')
                cid = ident(line['product_id'])
                if cid not in by_id:
                    raise ValueError('BOM komponentas nerastas.')
                if cid not in selected:
                    selected.add(cid)
                    pending.append(cid)
    products = {}
    for pid in selected:
        p = by_id[pid]
        sku = p.get('default_code')
        if not sku or len(by_sku.get(sku, [])) != 1:
            raise ValueError('Visi piloto komponentai turi turėti unikalius produktų kodus.')
        products[sku] = {'sku': sku, 'name': p['name'], 'active': p['active'],
            'odoo_id': pid, 'uom': label(p['uom_id']), 'uom_id': ident(p['uom_id'])}
    boms = {}
    for bid, b in included_boms.items():
        candidates = [p for p in raw_products if p['id'] in selected and
            (p['id'] == ident(b['product_id']) if b['product_id'] else ident(p['product_tmpl_id']) == ident(b['product_tmpl_id']))]
        sku = candidates[0]['default_code']
        boms[str(bid)] = {'id': str(bid), 'sku': sku, 'code': b.get('code') or '', 'active': True,
            'quantity': b['product_qty'], 'uom': label(b['product_uom_id']), 'uom_id': ident(b['product_uom_id']),
            'type': b['type'], 'components': [
                {'id': str(line['id']), 'sku': by_id[ident(line['product_id'])]['default_code'],
                 'quantity': line['product_qty'], 'uom': label(line['product_uom_id']), 'uom_id': ident(line['product_uom_id'])}
                for line in lines_by_bom.get(bid, [])]}
    external_usage = {}
    for line in raw_lines:
        if ident(line['bom_id']) not in included_boms and ident(line['product_id']) in selected:
            sku = by_id[ident(line['product_id'])]['default_code']
            external_usage[sku] = external_usage.get(sku, 0) + 1
    return {'products': products, 'boms': boms, 'external_usage': external_usage,
            '_reserved_skus': list(by_sku),
            'source': 'Odoo', 'captured_at': now()}


@reform.before_request
def protect():
    if session.get('reform_user') and session['reform_user'] not in current_app.config.get('REFORM_USERS', {}):
        session.clear()
    token = session.setdefault('reform_csrf', secrets.token_urlsafe(32))
    if request.method == 'POST' and not secrets.compare_digest(request.form.get('csrf', ''), token):
        abort(400, 'Sesija pasikeitė. Atnaujinkite puslapį.')
    if request.endpoint != 'reform.login' and not (session.get('reform_user') or admin()):
        return redirect(url_for('reform.login'))


@reform.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        if len(username) > 100:
            abort(400)
        users = current_app.config.get('REFORM_USERS', {})
        identity = digest(username)
        with db() as conn:
            row = conn.execute('SELECT * FROM attempts WHERE identity=?', (identity,)).fetchone()
            locked = row and row['count'] >= 5 and time.time() - row['started'] < 300
            password_hash = users.get(username)
            if not locked and isinstance(password_hash, str) and check_password_hash(password_hash, request.form.get('password', '')):
                conn.execute('DELETE FROM attempts WHERE identity=?', (identity,))
                session.clear()
                session['reform_user'] = username
                return redirect(url_for('reform.index'))
            if not locked:
                count = row['count'] + 1 if row and time.time() - row['started'] < 300 else 1
                started = row['started'] if row and count > 1 else time.time()
                conn.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (identity, count, started))
            error = 'Prisijungti nepavyko. Patikrinkite duomenis arba bandykite po 5 minučių.'
    return render_template('reform_login.html', error=error)


@reform.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('reform.login'))


@reform.get('/')
def index():
    with db() as conn:
        base = baseline(conn)
        work, revision = draft(conn) if base else (None, 0)
        rows = conn.execute('SELECT id,owner,created FROM submissions ' +
            ('' if admin() else 'WHERE owner=? ') + 'ORDER BY id DESC LIMIT 50', () if admin() else (owner(),)).fetchall()
    return render_template('reform_workspace.html', work=work, revision=revision,
        delta=changes(work['base'], work['target']) if work else [], submissions=rows, is_admin=admin())


@reform.post('/refresh')
def refresh():
    if not admin():
        abort(403)
    roots = [s.strip() for s in request.form.get('skus', '').replace(',', '\n').splitlines() if s.strip()]
    if not roots:
        flash('Įrašykite bent vieną Reform produkto kodą.')
        return redirect(url_for('reform.index'))
    try:
        from config import load_settings
        from odoo_client import OdooClient
        data = read_odoo(OdooClient(load_settings()), roots)
        reserved = data.pop('_reserved_skus')
        with db() as conn:
            conn.execute('INSERT OR REPLACE INTO state VALUES (2,?)', (json.dumps(reserved),))
            conn.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (json.dumps(data),))
        flash('Aktualūs Odoo duomenys pateikti. Ankstesni juodraščiai išsaugoti palyginimui.')
    except Exception:
        current_app.logger.exception('Reform snapshot refresh failed')
        flash('Duomenų atnaujinti nepavyko. Patikrinkite produktų kodus, Odoo prieigą ir BOM variantus.')
    return redirect(url_for('reform.index'))


@reform.post('/save')
def save():
    try:
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            work, revision = draft(conn)
            if str(revision) != request.form.get('revision'):
                abort(409, 'Juodraštis jau pakeistas kitame lange. Atnaujinkite puslapį.')
            target = work['target']
            action = request.form.get('action')
            if action == 'product':
                sku = request.form.get('sku', '').strip()
                name = request.form.get('name', '').strip()
                if not sku or len(sku) > 100 or not name or len(name) > 300:
                    raise ValueError('Įrašykite produkto kodą ir pavadinimą.')
                is_new = request.form.get('new') == '1'
                if is_new and any(k.casefold() == sku.casefold() for k in target['products']):
                    raise ValueError('Produktas tokiu kodu jau egzistuoja.')
                registry = conn.execute('SELECT payload FROM state WHERE id=2').fetchone()
                if is_new and registry and sku.casefold() in {k.casefold() for k in json.loads(registry['payload'])}:
                    raise ValueError('Šis produkto kodas jau naudojamas. Pasirinkite kitą kodą.')
                if not is_new and sku not in target['products']:
                    raise ValueError('Produktas nerastas.')
                product = copy.deepcopy(target['products'].get(sku, {'sku': sku, 'active': True, 'uom': 'Units', 'uom_id': None}))
                product['name'] = name
                if is_new:
                    uom = request.form.get('uom', '').strip()
                    available = {p['uom']: p.get('uom_id') for p in target['products'].values()}
                    if uom not in available:
                        raise ValueError('Pasirinkite matavimo vienetą.')
                    product.update(uom=uom, uom_id=available[uom])
                target['products'][sku] = product
            elif action == 'retire':
                sku = request.form.get('sku')
                if sku not in target['products']:
                    raise ValueError('Produktas nerastas.')
                target['products'][sku]['active'] = False
            elif action == 'bom':
                bid = request.form.get('bom_id', '')
                old = target['boms'].get(bid)
                if bid and not old:
                    raise ValueError('BOM nerastas.')
                sku = old['sku'] if old else request.form.get('sku', '')
                if sku not in target['products'] or not target['products'][sku]['active']:
                    raise ValueError('Pasirinkite aktyvų produktą.')
                bid = bid or 'new-' + secrets.token_hex(8)
                bom = copy.deepcopy(old) if old else {'id': bid, 'sku': sku, 'active': True, 'type': 'normal',
                    'uom': target['products'][sku]['uom'], 'uom_id': target['products'][sku].get('uom_id')}
                bom['code'] = request.form.get('code', '').strip()[:100]
                bom['quantity'] = positive(request.form.get('quantity'))
                skus = request.form.getlist('component_sku')
                quantities = request.form.getlist('component_quantity')
                ids = request.form.getlist('component_id')
                if not (len(skus) == len(quantities) == len(ids)):
                    raise ValueError('Nepilnos BOM eilutės.')
                previous = {line['id']: line for line in old['components']} if old else {}
                lines = []
                seen = set()
                for child, quantity, lid in zip(skus, quantities, ids):
                    if not child and not quantity:
                        continue
                    if child not in target['products'] or not target['products'][child]['active']:
                        raise ValueError('Pasirinkite aktyvų komponentą iš sąrašo.')
                    if lid and (lid not in previous or lid in seen):
                        raise ValueError('BOM eilutė pasikeitė. Atnaujinkite puslapį.')
                    seen.add(lid)
                    line = copy.deepcopy(previous[lid]) if lid else {'id': 'new-' + secrets.token_hex(8)}
                    if not lid or line['sku'] != child:
                        line.update(uom=target['products'][child]['uom'], uom_id=target['products'][child].get('uom_id'))
                    line.update(sku=child, quantity=positive(quantity))
                    lines.append(line)
                bom['components'] = lines
                target['boms'][bid] = bom
            else:
                abort(400)
            # Drafts may temporarily contain unresolved retirements; check at confirmation.
            conn.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?)', (owner(), revision + 1, json.dumps(work)))
        flash('Juodraštis išsaugotas. Peržiūrėkite pakeitimus prieš patvirtindami.')
    except ValueError as exc:
        flash(str(exc))
    return redirect(url_for('reform.index'))


@reform.post('/discard')
def discard():
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        _, revision = draft(conn)
        if str(revision) != request.form.get('revision'):
            abort(409)
        conn.execute('DELETE FROM drafts WHERE owner=?', (owner(),))
    flash('Juodraštis atšauktas. Rodomi naujausi pateikti duomenys.')
    return redirect(url_for('reform.index'))


@reform.post('/submit')
def submit():
    try:
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            work, revision = draft(conn)
            if str(revision) != request.form.get('revision'):
                abort(409)
            if digest(work['base']) != digest(baseline(conn)):
                raise ValueError('Pradiniai duomenys atnaujinti. Išsisaugokite pakeitimus ir pradėkite nuo naujausių duomenų.')
            delta = changes(work['base'], work['target'])
            if not delta:
                raise ValueError('Nėra pakeitimų, kuriuos būtų galima pateikti.')
            validate(work['target'])
            for change in delta:
                if change['kind'] == 'products' and not change['after']['active'] and work['base'].get('external_usage', {}).get(change['key']):
                    raise ValueError('Produktas naudojamas ir kituose BOM už piloto ribų. Reikalinga Furnibox peržiūra prieš nutraukiant naudojimą.')
            if request.form.get('confirm') != 'yes':
                raise ValueError('Patvirtinkite, kad peržiūrėjote pakeitimus.')
            payload = {'schema': 'reform-change-proposal-v1', 'status': 'awaiting_furnibox',
                'baseline_digest': digest(work['base']), 'baseline_captured_at': work['base']['captured_at'],
                'changes': delta, 'target': work['target']}
            keys = {(c['kind'], c['key']) for c in delta}
            for pending in conn.execute('SELECT payload FROM submissions'):
                existing = json.loads(pending['payload'])
                if existing['baseline_digest'] == payload['baseline_digest'] and keys & {(c['kind'], c['key']) for c in existing['changes']}:
                    raise ValueError('Šio produkto arba BOM pakeitimai jau pateikti Furnibox. Palaukite peržiūros ir aktualių duomenų atnaujinimo.')
            conn.execute('INSERT INTO submissions(owner,created,payload) VALUES (?,?,?)', (owner(), now(), json.dumps(payload)))
            conn.execute('DELETE FROM drafts WHERE owner=?', (owner(),))
        flash('Pakeitimai patvirtinti ir pateikti Furnibox peržiūrai. Odoo duomenys dar nepakeisti.')
    except ValueError as exc:
        flash(str(exc))
    return redirect(url_for('reform.index'))


@reform.get('/submissions/<int:sid>')
def download(sid):
    with db() as conn:
        row = conn.execute('SELECT * FROM submissions WHERE id=?', (sid,)).fetchone()
    if not row or (not admin() and row['owner'] != owner()):
        abort(404)
    response = jsonify({'submitted_by': row['owner'], 'submitted_at': row['created'], **json.loads(row['payload'])})
    response.headers['Content-Disposition'] = f'attachment; filename="reform-changes-{sid}.json"'
    return response


@reform.get('/draft/download')
def download_draft():
    with db() as conn:
        work, revision = draft(conn)
    response = jsonify({'schema': 'reform-draft-v1', 'revision': revision, 'owner': owner(),
                        'changes': changes(work['base'], work['target']), **work})
    response.headers['Content-Disposition'] = 'attachment; filename="reform-draft.json"'
    return response


@reform.get('/submissions/<int:sid>/view')
def view_submission(sid):
    with db() as conn:
        row = conn.execute('SELECT * FROM submissions WHERE id=?', (sid,)).fetchone()
    if not row or (not admin() and row['owner'] != owner()):
        abort(404)
    payload = json.loads(row['payload'])
    return render_template('reform_submission.html', submission=row, delta=payload['changes'])
