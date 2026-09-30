"""Version batches over existing revision-checked drafts and immutable submissions."""
import re
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
        created TEXT NOT NULL, PRIMARY KEY(number, actor));''')


def active(conn):
    return conn.execute("SELECT * FROM reform_versions WHERE status != 'implemented' ORDER BY created LIMIT 1").fetchone()


def event(conn, number, status, note=''):
    conn.execute('INSERT INTO reform_version_events(number,actor,status,note,created) VALUES (?,?,?,?,?)',
                 (number, owner(), status, note, now()))


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
        approvals = []
        if current and current['status'] in ('draft', 'returned'):
            approvals = conn.execute(
                'SELECT actor,created FROM reform_version_approvals WHERE number=? AND revision=? ORDER BY created',
                (current['number'], revision)).fetchall()
        if current and current['status'] in ('submitted', 'accepted'):
            item = conn.execute('SELECT payload FROM submissions WHERE id=?', (current['submission_id'],)).fetchone()
            delta = unpack(item['payload'])['changes']
    return render_template('reform_versions.html', current=current, versions=rows, history=history,
                           delta=delta, revision=revision, approvals=approvals,
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
            pass
        elif action == 'implemented' and row['status'] == 'accepted':
            if request.form.get('verified') != 'yes' or not note:
                abort(400, 'Confirm that Odoo was updated and checked, and record the verification reference.')
            submitted = unpack(conn.execute('SELECT payload FROM submissions WHERE id=?', (row['submission_id'],)).fetchone()[0])
            if digest(baseline(conn)) == submitted['baseline_digest']:
                abort(409, 'Refresh the catalogue from Odoo after applying the version before marking it implemented.')
            if not reflected_in_source(baseline(conn), submitted['changes']):
                abort(409, 'The refreshed Odoo catalogue does not yet contain all changes in this version.')
        else:
            abort(409, 'Invalid status transition.')
        conn.execute('UPDATE reform_versions SET status=?,note=?,updated=? WHERE number=?', (action, note, now(), row['number']))
        event(conn, row['number'], action, note)
    flash('Version status updated. This action does not write to Odoo.')
    return redirect(url_for('reform.versions'))
