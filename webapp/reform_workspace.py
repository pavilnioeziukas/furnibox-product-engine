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


def reform_visible(sku):
    code = (sku or '').strip().upper()
    return not (code.startswith('APACK') or code.endswith('-A'))


def visible_work(work):
    """Keep internal BOM dependencies intact while presenting the Reform scope."""
    if not work:
        return work
    shown = copy.deepcopy(work)
    target = shown['target']
    target['products'] = {k: p for k, p in target['products'].items() if reform_visible(p.get('display_sku', k))}
    target['boms'] = {k: b for k, b in target['boms'].items() if b['sku'] in target['products']}
    for bom in target['boms'].values():
        visible_lines = [line for line in bom['components'] if line['sku'] in target['products']]
        if len(visible_lines) != len(bom['components']):
            bom['read_only'] = 'This BOM includes internal Furnibox assembly components. Furnibox must review it before editing.'
        bom['components'] = visible_lines
    return shown


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
        abort(409, 'Furnibox must first provide the product and BOM data.')
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
        raise ValueError('Quantity must be a number.')
    if not math.isfinite(number) or number <= 0:
        raise ValueError('Quantity must be greater than zero.')
    return number


def validate(target):
    products, boms = target['products'], target['boms']
    edges = {}
    for bom in boms.values():
        if not bom.get('active', True):
            continue
        parent = bom['sku']
        if parent not in products:
            raise ValueError('BOM product not found.')
        if not products[parent]['active']:
            continue
        positive(bom['quantity'])
        if not bom['components']:
            raise ValueError('An active BOM must contain at least one component.')
        for line in bom['components']:
            child = line['sku']
            if child not in products or not products[child]['active']:
                raise ValueError(f'Component {child} does not exist or has been retired.')
            positive(line['quantity'])
            edges.setdefault(parent, set()).add(child)
    visited, stack = set(), set()
    def visit(sku):
        if sku in stack:
            raise ValueError('BOM contains a cycle: a product cannot be its own component.')
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
                raise ValueError(f"Component {line['sku']} has been retired but is still used in the BOM for {bom['sku']}.")
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
        abort(400, 'Your session has changed. Refresh the page.')
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
            error = 'Sign-in failed. Check your details or try again in 5 minutes.'
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
        delta = changes(work['base'], work['target']) if work else []
        rows = conn.execute('SELECT id,owner,created FROM submissions ' +
            ('' if admin() else 'WHERE owner=? ') + 'ORDER BY id DESC LIMIT 50', () if admin() else (owner(),)).fetchall()
    work = visible_work(work)
    query = request.args.get('q', '').strip()[:200]
    view = request.args.get('view') or ('catalogue' if request.args else 'home')
    intent = request.args.get('intent', '')
    selected = request.args.get('product', '')
    selected_bom = request.args.get('bom_id', '')
    if work and selected_bom:
        if selected_bom not in work['target']['boms']:
            abort(404)
        selected = work['target']['boms'][selected_bom]['sku']
    if view == 'edit-bom' and not selected_bom:
        return redirect(url_for('reform.index', view='bom-list', intent='edit'))
    product_rows, product_boms, usage = [], [], []
    bom_rows = []
    page, pages, total = 1, 1, 0
    counts = {}
    if work:
        target = work['target']
        for bom in target['boms'].values():
            counts[bom['sku']] = counts.get(bom['sku'], 0) + 1
            if bom['sku'] == selected and (not selected_bom or bom['id'] == selected_bom):
                product_boms.append(bom)
            if any(line['sku'] == selected for line in bom['components']):
                usage.append(bom)
        product_rows = [(sku, p) for sku, p in target['products'].items()
                        if not query or query.casefold() in (p.get('display_sku', sku) + ' ' + p['name']).casefold()]
        product_rows.sort(key=lambda row: (not bool(counts.get(row[0])), row[1].get('display_sku', row[0]).casefold()))
        bom_rows = [b for b in target['boms'].values() if not query or query.casefold() in
                    (b['sku'] + ' ' + b.get('code', '') + ' ' + target['products'][b['sku']]['name']).casefold()]
        bom_rows.sort(key=lambda b: (b['sku'].casefold(), b.get('code', '').casefold(), b['id']))
        total = len(bom_rows) if view == 'bom-list' else len(product_rows)
        pages = max(1, math.ceil(total / 30))
        try:
            page = max(1, min(pages, int(request.args.get('page', 1))))
        except ValueError:
            page = 1
        product_rows = product_rows[(page-1)*30:page*30]
        bom_rows = bom_rows[(page-1)*30:page*30]
        if selected not in target['products']:
            selected = ''
    return render_template('reform_catalogue.html', work=work, revision=revision,
        delta=delta, submissions=rows, is_admin=admin(),
        query=query, view=view, selected=selected, product_rows=product_rows, product_boms=product_boms,
        usage=usage, counts=counts, page=page, pages=pages, total=total,
        bom_rows=bom_rows, selected_bom=selected_bom, intent=intent)


@reform.post('/initialize')
def initialize():
    """Seed an empty review installation from an administrator's snapshot."""
    if not admin():
        abort(403)
    upload = request.files.get('file')
    if not upload:
        abort(400, 'Select a catalogue snapshot.')
    raw = upload.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        abort(413)
    def require(condition):
        if not condition:
            raise ValueError()
    try:
        bundle = json.loads(raw)
        if bundle['schema'] != 'reform-catalogue-seed-v1':
            raise ValueError()
        data, reserved = bundle['catalogue'], bundle['reserved_skus']
        require(isinstance(reserved, list) and all(isinstance(s, str) for s in reserved))
        require(isinstance(data['source'], str) and isinstance(data['captured_at'], str))
        require(isinstance(data['external_usage'], dict))
        products, boms = data['products'], data['boms']
        require(isinstance(products, dict) and products and isinstance(boms, dict))
        for sku, product in products.items():
            require(product['sku'] == sku)
            require(all(isinstance(product[k], str) for k in ('sku', 'name', 'uom')))
            require(isinstance(product['active'], bool))
        for bid, bom in boms.items():
            require(bom['id'] == bid and bom['sku'] in products)
            positive(bom['quantity'])
            require(isinstance(bom['code'], str) and isinstance(bom['uom'], str))
            require(isinstance(bom['components'], list))
            for line in bom['components']:
                require(isinstance(line['id'], str) and line['sku'] in products)
                require(isinstance(line['uom'], str))
                positive(line['quantity'])
    except (ValueError, KeyError, TypeError, AssertionError):
        abort(400, 'Invalid catalogue snapshot.')
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if baseline(conn) is not None:
            abort(409, 'This workspace already has a catalogue. Initialization cannot replace it.')
        conn.execute('INSERT INTO state VALUES (1,?)', (pack(data),))
        conn.execute('INSERT OR REPLACE INTO state VALUES (2,?)', (pack(reserved),))
    flash('Catalogue initialized. No Odoo connection or changes were made.')
    return redirect(url_for('reform.index'))


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
        flash('Current Odoo data is available. Previous drafts have been kept for comparison.')
    except Exception:
        current_app.logger.exception('Reform snapshot refresh failed')
        flash('Unable to refresh data. Check product codes, Odoo access and BOM variants.')
    return redirect(url_for('reform.index'))


@reform.post('/save')
def save():
    try:
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            work, revision = draft(conn)
            if str(revision) != request.form.get('revision'):
                abort(409, 'The draft was changed in another window. Refresh the page.')
            target = work['target']
            action = request.form.get('action')
            if action == 'product':
                sku = request.form.get('sku', '').strip()
                if not reform_visible(sku):
                    raise ValueError('Assembly products are managed by Furnibox.')
                name = request.form.get('name', '').strip()
                if not sku or len(sku) > 100 or not name or len(name) > 300:
                    raise ValueError('Enter a product code and name.')
                is_new = request.form.get('new') == '1'
                if is_new and any(k.casefold() == sku.casefold() for k in target['products']):
                    raise ValueError('A product with this code already exists.')
                registry = conn.execute('SELECT payload FROM state WHERE id=2').fetchone()
                if is_new and registry and sku.casefold() in {k.casefold() for k in unpack(registry['payload'])}:
                    raise ValueError('This product code is already in use. Choose another code.')
                if not is_new and sku not in target['products']:
                    raise ValueError('Product not found.')
                if not is_new and target['products'][sku].get('read_only'):
                    raise ValueError(target['products'][sku]['read_only'])
                product = copy.deepcopy(target['products'].get(sku, {'sku': sku, 'active': True, 'uom': 'Units', 'uom_id': None}))
                product['name'] = name
                if is_new:
                    uom = request.form.get('uom', '').strip()
                    available = {p['uom']: p.get('uom_id') for p in target['products'].values()}
                    if uom not in available:
                        raise ValueError('Select a unit of measure.')
                    product.update(uom=uom, uom_id=available[uom])
                target['products'][sku] = product
            elif action == 'retire':
                sku = request.form.get('sku')
                if not reform_visible(sku):
                    raise ValueError('Assembly products are managed by Furnibox.')
                if sku not in target['products']:
                    raise ValueError('Product not found.')
                if target['products'][sku].get('read_only'):
                    raise ValueError(target['products'][sku]['read_only'])
                target['products'][sku]['active'] = False
            elif action == 'bom':
                bid = request.form.get('bom_id', '')
                old = target['boms'].get(bid)
                if bid and not old:
                    raise ValueError('BOM not found.')
                if old and old.get('read_only'):
                    raise ValueError(old['read_only'])
                sku = old['sku'] if old else request.form.get('sku', '')
                if not reform_visible(sku) or (old and any(not reform_visible(line['sku']) for line in old['components'])):
                    raise ValueError('This BOM includes internal Furnibox assembly products and requires Furnibox review.')
                if sku not in target['products'] or not target['products'][sku]['active']:
                    raise ValueError('Select an active product.')
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
                    raise ValueError('Incomplete BOM rows.')
                previous = {line['id']: line for line in old['components']} if old else {}
                lines = []
                seen = set()
                for child, quantity, lid in zip(skus, quantities, ids):
                    if not child and not quantity:
                        continue
                    if not reform_visible(child):
                        raise ValueError('Assembly components are managed by Furnibox.')
                    if child not in target['products'] or not target['products'][child]['active']:
                        raise ValueError('Select an active component from the list.')
                    if lid and (lid not in previous or lid in seen):
                        raise ValueError('The BOM row has changed. Refresh the page.')
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
        flash('Draft saved. Review your changes before confirming.')
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
    flash('Draft discarded. The latest available data is now shown.')
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
                raise ValueError('The source data has changed. Download your draft and start from the latest data.')
            delta = changes(work['base'], work['target'])
            if not delta:
                raise ValueError('There are no changes to submit.')
            validate_proposal(work['target'], delta)
            for change in delta:
                if change['kind'] == 'products' and not change['after']['active'] and work['base'].get('external_usage', {}).get(change['key']):
                    raise ValueError('This product is used in other BOMs outside the pilot scope. Furnibox must review it before retirement.')
            if request.form.get('confirm') != 'yes':
                raise ValueError('Confirm that you have reviewed the changes.')
            payload = {'schema': 'reform-change-proposal-v1', 'status': 'awaiting_furnibox',
                'baseline_digest': digest(work['base']), 'baseline_captured_at': work['base']['captured_at'],
                'changes': delta, 'target': work['target']}
            keys = {(c['kind'], c['key']) for c in delta}
            for pending in conn.execute('SELECT payload FROM submissions'):
                existing = unpack(pending['payload'])
                if existing['baseline_digest'] == payload['baseline_digest'] and keys & {(c['kind'], c['key']) for c in existing['changes']}:
                    raise ValueError('Changes to this product or BOM have already been submitted to Furnibox. Wait for review and a source data refresh.')
            conn.execute('INSERT INTO submissions(owner,created,payload) VALUES (?,?,?)', (owner(), now(), pack(payload)))
            conn.execute('DELETE FROM drafts WHERE owner=?', (owner(),))
        flash('Changes confirmed and submitted to Furnibox for review. Odoo data has not yet changed.')
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

# Register file exchange routes on the same protected blueprint.
from webapp import reform_excel  # noqa: E402,F401
