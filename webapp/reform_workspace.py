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
import zlib
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


def pack(value):
    return zlib.compress(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def unpack(value):
    return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)


def baseline(conn):
    row = conn.execute('SELECT payload FROM state WHERE id=1').fetchone()
    return unpack(row['payload']) if row else None


def owner():
    return session.get('reform_user') or 'Furnibox'


def admin():
    return bool(current_app.config.get('REFORM_ADMIN_ENABLED')) and bool(session.get('authenticated')) and not session.get('reform_user')


def draft(conn):
    row = conn.execute('SELECT * FROM drafts WHERE owner=?', (owner(),)).fetchone()
    if row:
        return unpack(row['payload']), row['revision']
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


def validate_proposal(target, delta):
    """Validate edited BOM subtrees; unrelated legacy issues do not block edits."""
    edited_boms = {c['key']: c['after'] for c in delta if c['kind'] == 'boms'}
    retired = {c['key'] for c in delta if c['kind'] == 'products' and not c['after']['active']}
    by_product = {}
    for bid, bom in target['boms'].items():
        if not bom.get('active', True) or not target['products'][bom['sku']]['active']:
            continue
        by_product.setdefault(bom['sku'], []).append((bid, bom))
        for line in bom['components']:
            if line['sku'] in retired:
                raise ValueError(f"Komponento {line['sku']} naudojimas nutrauktas, bet jis dar naudojamas produkto {bom['sku']} BOM.")
    relevant = dict(edited_boms)
    seen = set()
    pending = [line['sku'] for b in edited_boms.values() for line in b['components']]
    while pending:
        sku = pending.pop()
        if sku in seen:
            continue
        seen.add(sku)
        for bid, bom in by_product.get(sku, []):
            relevant[bid] = bom
            pending.extend(line['sku'] for line in bom['components'])
    validate({**target, 'boms': relevant})


def read_odoo(client, roots=None):
    from webapp.reform_catalogue import read_catalogue
    return read_catalogue(client, roots)


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
    query = request.args.get('q', '').strip()[:200]
    view = request.args.get('view', 'catalogue')
    selected = request.args.get('product', '')
    product_rows, product_boms, usage = [], [], []
    page, pages, total = 1, 1, 0
    counts = {}
    if work:
        target = work['target']
        for bom in target['boms'].values():
            counts[bom['sku']] = counts.get(bom['sku'], 0) + 1
            if bom['sku'] == selected:
                product_boms.append(bom)
            if any(line['sku'] == selected for line in bom['components']):
                usage.append(bom)
        product_rows = [(sku, p) for sku, p in target['products'].items()
                        if not query or query.casefold() in (p.get('display_sku', sku) + ' ' + p['name']).casefold()]
        product_rows.sort(key=lambda row: (not bool(counts.get(row[0])), row[1].get('display_sku', row[0]).casefold()))
        total = len(product_rows)
        pages = max(1, math.ceil(total / 30))
        try:
            page = max(1, min(pages, int(request.args.get('page', 1))))
        except ValueError:
            page = 1
        product_rows = product_rows[(page-1)*30:page*30]
        if selected not in target['products']:
            selected = ''
    return render_template('reform_catalogue.html', work=work, revision=revision,
        delta=changes(work['base'], work['target']) if work else [], submissions=rows, is_admin=admin(),
        query=query, view=view, selected=selected, product_rows=product_rows, product_boms=product_boms,
        usage=usage, counts=counts, page=page, pages=pages, total=total)


@reform.post('/refresh')
def refresh():
    if not admin():
        abort(403)
    roots = [s.strip() for s in request.form.get('skus', '').replace(',', '\n').splitlines() if s.strip()]
    try:
        from config import load_settings
        from odoo_client import OdooClient
        data = read_odoo(OdooClient(load_settings()), roots)
        reserved = data.pop('_reserved_skus')
        with db() as conn:
            conn.execute('INSERT OR REPLACE INTO state VALUES (2,?)', (pack(reserved),))
            conn.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (pack(data),))
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
                if is_new and registry and sku.casefold() in {k.casefold() for k in unpack(registry['payload'])}:
                    raise ValueError('Šis produkto kodas jau naudojamas. Pasirinkite kitą kodą.')
                if not is_new and sku not in target['products']:
                    raise ValueError('Produktas nerastas.')
                if not is_new and target['products'][sku].get('read_only'):
                    raise ValueError(target['products'][sku]['read_only'])
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
                if target['products'][sku].get('read_only'):
                    raise ValueError(target['products'][sku]['read_only'])
                target['products'][sku]['active'] = False
            elif action == 'bom':
                bid = request.form.get('bom_id', '')
                old = target['boms'].get(bid)
                if bid and not old:
                    raise ValueError('BOM nerastas.')
                if old and old.get('read_only'):
                    raise ValueError(old['read_only'])
                sku = old['sku'] if old else request.form.get('sku', '')
                if sku not in target['products'] or not target['products'][sku]['active']:
                    raise ValueError('Pasirinkite aktyvų produktą.')
                if target['products'][sku].get('read_only'):
                    raise ValueError(target['products'][sku]['read_only'])
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
            conn.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?)', (owner(), revision + 1, pack(work)))
        flash('Juodraštis išsaugotas. Peržiūrėkite pakeitimus prieš patvirtindami.')
    except ValueError as exc:
        flash(str(exc))
    selected = request.form.get('return_product') or request.form.get('sku', '')
    return redirect(url_for('reform.index', product=selected, q=request.form.get('q', ''), view=request.form.get('return_view', 'catalogue')))


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
            validate_proposal(work['target'], delta)
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
                existing = unpack(pending['payload'])
                if existing['baseline_digest'] == payload['baseline_digest'] and keys & {(c['kind'], c['key']) for c in existing['changes']}:
                    raise ValueError('Šio produkto arba BOM pakeitimai jau pateikti Furnibox. Palaukite peržiūros ir aktualių duomenų atnaujinimo.')
            conn.execute('INSERT INTO submissions(owner,created,payload) VALUES (?,?,?)', (owner(), now(), pack(payload)))
            conn.execute('DELETE FROM drafts WHERE owner=?', (owner(),))
        flash('Pakeitimai patvirtinti ir pateikti Furnibox peržiūrai. Odoo duomenys dar nepakeisti.')
        return redirect(url_for('reform.index', view='sent'))
    except ValueError as exc:
        flash(str(exc))
    return redirect(url_for('reform.index', view='review'))


@reform.get('/submissions/<int:sid>')
def download(sid):
    with db() as conn:
        row = conn.execute('SELECT * FROM submissions WHERE id=?', (sid,)).fetchone()
    if not row or (not admin() and row['owner'] != owner()):
        abort(404)
    response = jsonify({'submitted_by': row['owner'], 'submitted_at': row['created'], **unpack(row['payload'])})
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
    payload = unpack(row['payload'])
    return render_template('reform_submission.html', submission=row, delta=payload['changes'])
