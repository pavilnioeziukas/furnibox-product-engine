"""Version batches over existing revision-checked drafts and immutable submissions."""
import re
import sqlite3
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from webapp.reform_workspace import reform, db, owner, admin, draft, baseline, digest, pack, unpack, now, changes


def schema(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS reform_versions (
        number TEXT PRIMARY KEY, owner TEXT NOT NULL, description TEXT NOT NULL,
        status TEXT NOT NULL, submission_id INTEGER, created TEXT NOT NULL,
        updated TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS reform_version_events (
        id INTEGER PRIMARY KEY, number TEXT NOT NULL, actor TEXT NOT NULL,
        status TEXT NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reform_version_approvals (
        number TEXT NOT NULL, actor TEXT NOT NULL, revision INTEGER NOT NULL,
        created TEXT NOT NULL, package_digest TEXT NOT NULL DEFAULT '', PRIMARY KEY(number, actor));
        CREATE TABLE IF NOT EXISTS reform_bom_revisions (
        product_code TEXT NOT NULL, revision TEXT NOT NULL, bom_id TEXT NOT NULL,
        change_number TEXT NOT NULL, status TEXT NOT NULL, snapshot BLOB NOT NULL,
        created TEXT NOT NULL, PRIMARY KEY(product_code, revision));''')

    columns = {row['name'] for row in conn.execute('PRAGMA table_info(reform_version_approvals)')}
    if 'package_digest' not in columns:
        try:
            conn.execute("ALTER TABLE reform_version_approvals ADD COLUMN package_digest TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            # Another worker may complete the same additive migration first.
            if 'package_digest' not in {row['name'] for row in conn.execute('PRAGMA table_info(reform_version_approvals)')}:
                raise


def approval_digest(version, work, revision):
    return digest({'number': version['number'], 'description': version['description'],
                   'revision': revision, 'work': work})


def invalidate_approvals(conn):
    current = active(conn)
    if current and current['status'] in ('draft', 'returned'):
        removed = conn.execute('DELETE FROM reform_version_approvals WHERE number=?',
                               (current['number'],)).rowcount
        if removed:
            event(conn, current['number'], 'approvals_reset', 'Package changed; all reviewers must approve again.')


def next_revision(value):
    """Return the next alphabetic PLM revision: A..Z, AA..AZ, BA..."""
    if not value:
        return 'A'
    number = 0
    for char in value.upper():
        if not ('A' <= char <= 'Z'):
            raise ValueError('BOM revision must contain letters only.')
        number = number * 26 + ord(char) - 64
    number += 1
    result = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def released_revisions(conn):
    rows = conn.execute("SELECT product_code,revision FROM reform_bom_revisions WHERE status='current' ORDER BY created").fetchall()
    return {row['product_code']: row['revision'] for row in rows}


def bom_revision_plan(conn, delta):
    """Describe immutable current/proposed BOM revisions for a change package."""
    released = released_revisions(conn)
    result = {}
    for change in delta:
        if change['kind'] != 'boms':
            continue
        sku = change['after']['sku']
        current = released.get(sku, 'A' if change['before'] else None)
        result[change['key']] = {'product_code': sku, 'current': current,
                                 'proposed': next_revision(current) if change['before'] else 'A'}
    return result


def record_bom_revisions(conn, change_number, delta, plan):
    """Freeze old and newly implemented BOM states without overwriting history."""
    created = now()
    for change in delta:
        if change['kind'] != 'boms':
            continue
        item = plan[change['key']]
        sku, before, after = item['product_code'], change['before'], change['after']
        if before and not conn.execute(
                'SELECT 1 FROM reform_bom_revisions WHERE product_code=?', (sku,)).fetchone():
            conn.execute('INSERT INTO reform_bom_revisions VALUES (?,?,?,?,?,?,?)',
                         (sku, item['current'], str(before['id']), 'Odoo baseline', 'superseded',
                          pack(before), created))
        conn.execute("UPDATE reform_bom_revisions SET status='superseded' WHERE product_code=?", (sku,))
        conn.execute('INSERT INTO reform_bom_revisions VALUES (?,?,?,?,?,?,?)',
                     (sku, item['proposed'], str(after['id']), change_number, 'current',
                      pack(after), created))


def active(conn):
    return conn.execute("SELECT * FROM reform_versions WHERE status != 'implemented' ORDER BY created LIMIT 1").fetchone()


def editable_version(conn):
    """Require an open shared version and an authenticated Reform contributor."""
    schema(conn)
    return require_open_version(conn)


def require_open_version(conn):
    from flask import session
    if not session.get('reform_user'):
        abort(403)
    row = active(conn)
    if not row:
        raise ValueError('Open a version draft before downloading or uploading changes.')
    if row['status'] not in ('draft', 'returned'):
        raise ValueError(f"Version {row['number']} is locked for review and cannot accept more changes.")
    return row


def record_edit(conn, before, after, revision, method):
    version = active(conn)
    delta = changes({'products': before['products'], 'boms': before['boms']}, after)
    conn.execute('CREATE TABLE IF NOT EXISTS reform_change_authors (number TEXT, kind TEXT, record_key TEXT, actor TEXT, revision INTEGER, PRIMARY KEY(number,kind,record_key))')
    for change in delta:
        conn.execute('INSERT OR REPLACE INTO reform_change_authors VALUES (?,?,?,?,?)',
                     (version['number'], change['kind'], change['key'], owner(), revision))
    event(conn, version['number'], 'edited', f'{method}: revision {revision}, {len(delta)} changed record(s).')


def event(conn, number, status, note=''):
    conn.execute('INSERT INTO reform_version_events(number,actor,status,note,created) VALUES (?,?,?,?,?)',
                 (number, owner(), status, note, now()))


def change_authors(conn, number):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='reform_change_authors'").fetchone():
        return {}
    return {(r['kind'], r['record_key']): r['actor'] for r in conn.execute(
        'SELECT kind,record_key,actor FROM reform_change_authors WHERE number=?', (number,))}


def reflected_in_source(source, delta):
    for change in delta:
        proposed = change['after']
        if change['kind'] == 'products':
            actual = source['products'].get(proposed['sku'])
            if not proposed['active'] and (not actual or not actual['active']):
                continue
            if not actual or any(actual.get(k, '') != proposed.get(k, '') for k in ('name', 'category', 'uom', 'active')):
                return False
        else:
            lines = lambda bom: sorted((line['sku'], float(line['quantity']), line['uom']) for line in bom['components'])
            matches = [b for b in source['boms'].values() if b['sku'] == proposed['sku']]
            if not any(all(b.get(k) == proposed.get(k) for k in ('code', 'quantity', 'uom', 'active')) and lines(b) == lines(proposed) for b in matches):
                return False
    return True


@reform.get('/versions')
def versions():
    with db() as conn:
        schema(conn)
        current = active(conn)
        work, revision = (None, 0)
        if current and current['status'] in ('draft', 'returned'):
            row = conn.execute('SELECT revision,payload FROM drafts WHERE owner=?', (current['owner'],)).fetchone()
            work, revision = (unpack(row['payload']), row['revision']) if row else (None, 0)
        elif not current and baseline(conn):
            work, revision = draft(conn)
        rows = conn.execute('SELECT * FROM reform_versions ORDER BY created DESC').fetchall()
        history = conn.execute('SELECT * FROM reform_version_events ORDER BY id DESC LIMIT 100').fetchall()
        delta = changes(work['base'], work['target']) if work else []
        package_digest = approval_digest(current, work, revision) if current and work else ''
        approvals = []
        if current and current['status'] in ('draft', 'returned'):
            approvals = conn.execute(
                'SELECT actor,created FROM reform_version_approvals WHERE number=? AND revision=? AND package_digest=? ORDER BY created',
                (current['number'], revision, package_digest)).fetchall()
        submitted = {}
        if current and current['status'] in ('submitted', 'accepted'):
            item = conn.execute('SELECT payload FROM submissions WHERE id=?', (current['submission_id'],)).fetchone()
            submitted = unpack(item['payload'])
            delta = submitted['changes']
        revision_plan = (submitted.get('bom_revision_plan', {}) if submitted else bom_revision_plan(conn, delta))
        bom_history = conn.execute('''SELECT r.product_code,r.revision,r.change_number,r.status,r.created,
                v.owner AS proposed_by
            FROM reform_bom_revisions r
            LEFT JOIN reform_versions v ON v.number=r.change_number
            ORDER BY r.product_code,r.created DESC''').fetchall()
    return render_template('reform_versions.html', current=current, versions=rows, history=history,
                           delta=delta, revision=revision, approvals=approvals, package_digest=package_digest,
                           already_approved=owner() in [a['actor'] for a in approvals],
                           submitted_approvers=submitted.get('approved_by', []),
                           revision_plan=revision_plan, bom_history=bom_history,
                           approvals_required=current_app.config.get('REFORM_APPROVALS_REQUIRED', 2),
                           is_admin=admin(), username=owner())


@reform.post('/versions/save')
def save_version():
    number = request.form.get('number', '').strip().lower()
    description = request.form.get('description', '').strip()
    if not re.fullmatch(r'v[1-9][0-9]{0,3}\.(0|[1-9][0-9]{0,3})', number) or not description or len(description) > 1000:
        abort(400, 'Enter a version such as v11.1 and a description.')
    with db() as conn:
        schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        work, revision = draft(conn)
        if str(revision) != request.form.get('revision'):
            abort(409, 'Your draft changed. Refresh the page.')
        current = active(conn)
        if current and (current['owner'] != owner() or current['status'] not in ('draft', 'returned') or current['number'] != number):
            abort(409, 'Finish the current version before opening another.')
        if not current:
            if conn.execute('SELECT 1 FROM reform_versions WHERE number=?', (number,)).fetchone():
                abort(409, 'This version number is already used.')
            existing = conn.execute('SELECT number FROM reform_versions').fetchall()
            numeric = lambda value: tuple(map(int, value[1:].split('.')))
            if existing and numeric(number) <= max(numeric(row['number']) for row in existing):
                abort(409, 'Use a number higher than the previous version.')
            conn.execute('INSERT INTO reform_versions VALUES (?,?,?,?,?,?,?,?)',
                         (number, owner(), description, 'draft', None, now(), now(), ''))
            event(conn, number, 'draft', description)
        else:
            if description != current['description']:
                invalidate_approvals(conn)
            conn.execute('UPDATE reform_versions SET description=?,updated=? WHERE number=?', (description, now(), number))
    flash('Version draft saved. Continue editing products and BOMs, or review the complete version here.')
    return redirect(url_for('reform.versions'))


@reform.post('/versions/review')
def review_version():
    if not admin():
        abort(403)
    action = request.form.get('action')
    note = request.form.get('note', '').strip()
    with db() as conn:
        schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        row = active(conn)
        if not row or row['number'] != request.form.get('number') or str(row['submission_id']) != request.form.get('submission_id'):
            abort(409)
        if action == 'returned' and row['status'] in ('submitted', 'accepted'):
            if not note:
                abort(400, 'Explain what needs to be corrected.')
            if conn.execute('SELECT 1 FROM drafts WHERE owner=?', (row['owner'],)).fetchone():
                abort(409, 'An existing draft must be resolved before returning this version.')
            payload = unpack(conn.execute('SELECT payload FROM submissions WHERE id=?', (row['submission_id'],)).fetchone()[0])
            conn.execute('INSERT INTO drafts VALUES (?,?,?)', (row['owner'], payload['draft_revision'] + 1,
                         pack({'base': payload['base'], 'target': payload['target']})))
        elif action == 'accepted' and row['status'] == 'submitted':
            if request.form.get('approve_odoo_sync') != 'yes' or not note:
                abort(400, 'A Furnibox representative must explicitly approve production Odoo synchronization and record the approval note.')
        elif action == 'implemented' and row['status'] == 'accepted':
            if request.form.get('verified') != 'yes' or not note:
                abort(400, 'Confirm that Odoo was updated and checked, and record the verification reference.')
            submitted = unpack(conn.execute('SELECT payload FROM submissions WHERE id=?', (row['submission_id'],)).fetchone()[0])
            if digest(baseline(conn)) == submitted['baseline_digest']:
                abort(409, 'Refresh the catalogue from Odoo after applying the version before marking it implemented.')
            if not reflected_in_source(baseline(conn), submitted['changes']):
                abort(409, 'The refreshed Odoo catalogue does not yet contain all changes in this version.')
            record_bom_revisions(conn, row['number'], submitted['changes'],
                                 submitted.get('bom_revision_plan') or bom_revision_plan(conn, submitted['changes']))
        else:
            abort(409, 'Invalid status transition.')
        conn.execute('UPDATE reform_versions SET status=?,note=?,updated=? WHERE number=?', (action, note, now(), row['number']))
        event(conn, row['number'], 'odoo_sync_approved' if action == 'accepted' else action, note)
    flash('Version status updated. This action does not write to Odoo.')
    return redirect(url_for('reform.versions'))

