"""Explicit read-only Odoo refresh for the persistent Reform workspace."""
import argparse
import copy
import hashlib
import json
import urllib.request

from webapp.reform_workspace import baseline, db, digest, now, pack, unpack


def schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS catalogue_snapshots (digest TEXT PRIMARY KEY, created TEXT NOT NULL, payload BLOB NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS catalogue_refreshes (key TEXT PRIMARY KEY, created TEXT NOT NULL, digest TEXT NOT NULL)')


def already_done(conn, key):
    schema(conn)
    return bool(key and conn.execute('SELECT 1 FROM catalogue_refreshes WHERE key=?', (key,)).fetchone())


def publish(conn, data, key):
    """Publish all catalogue state atomically, retaining the previous source and drafts."""
    if not data.get('products') or not data.get('boms') or data.get('scope') != 'production_catalogue':
        raise ValueError('Refusing to replace the catalogue with empty or partial source data.')
    if not data.get('captured_at') or data.get('source') != 'Odoo Production' or '_reserved_skus' not in data:
        raise ValueError('Production source metadata is missing.')
    data = copy.deepcopy(data)
    reserved = data.pop('_reserved_skus')
    suppliers = {sku: p.get('supplier_codes', []) for sku, p in data['products'].items()}
    schema(conn)
    conn.execute('BEGIN IMMEDIATE')
    if already_done(conn, key):
        return False
    previous = baseline(conn)
    if previous:
        conn.execute('INSERT OR IGNORE INTO catalogue_snapshots VALUES (?,?,?)', (digest(previous), now(), pack(previous)))
    for sid, value in [(1, data), (2, reserved), (3, suppliers)]:
        conn.execute('INSERT OR REPLACE INTO state VALUES (?,?)', (sid, pack(value)))
    conn.execute('INSERT INTO catalogue_refreshes VALUES (?,?,?)', (key, now(), digest(data)))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', required=True, help='Unique refresh key; repeat starts skip this completed refresh.')
    parser.add_argument('--snapshot-url', help='Expiring URL for a previously captured production snapshot; no Odoo credentials required.')
    parser.add_argument('--sha256', help='Required checksum when using --snapshot-url.')
    args = parser.parse_args()
    from webapp.app import app
    with app.app_context():
        with db() as conn:
            if already_done(conn, args.once):
                print('REFORM_CATALOGUE_REFRESH already complete', args.once, flush=True)
                return
        if args.snapshot_url:
            if not args.snapshot_url.startswith('https://') or not args.sha256:
                raise ValueError('HTTPS snapshot URL and SHA256 are required.')
            with urllib.request.urlopen(args.snapshot_url, timeout=60) as response:
                raw = response.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != args.sha256:
                raise ValueError('Snapshot size or checksum does not match.')
            data = json.loads(raw)
        else:
            from config import load_settings
            from odoo_client import OdooClient
            from webapp.reform_catalogue import read_catalogue
            # The catalogue reader calls search_read only; it never executes Odoo writes.
            data = read_catalogue(OdooClient(load_settings()))
        with db() as conn:
            changed = publish(conn, data, args.once)
            current = baseline(conn)
            print('REFORM_CATALOGUE_REFRESH', 'updated' if changed else 'already complete',
                  current['captured_at'], 'products', len(current['products']), 'boms', len(current['boms']),
                  'drafts_preserved', conn.execute('SELECT COUNT(*) FROM drafts').fetchone()[0], flush=True)


if __name__ == '__main__':
    main()

