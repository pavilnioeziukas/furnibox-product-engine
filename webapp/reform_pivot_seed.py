"""Seed a standalone Pivot reference from a checksum-verified, expiring file URL."""
import argparse
import hashlib
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--label', default='BOM v10 (current)')
    parser.add_argument('--filename', default='Reform-Full-Catalogue (15)(1).xlsx / Product MBOMs - Pivot')
    args = parser.parse_args()
    from webapp.app import app
    from webapp.reform_workspace import db
    from webapp.reform_pivot_compare import parse, reference, save_reference
    from webapp.reform_excel import LIMIT
    with app.app_context():
        with db() as conn:
            existing = reference(conn, args.key)
            if existing:
                if existing['sha256'] != args.sha256:
                    raise ValueError('Reference checksum differs; refusing to replace an immutable baseline.')
                print('REFORM_PIVOT_REFERENCE already complete', args.key, flush=True)
                return
        if not args.url.startswith('https://'):
            raise ValueError('HTTPS is required.')
        with urllib.request.urlopen(args.url, timeout=60) as response:
            raw = response.read(LIMIT + 1)
        if hashlib.sha256(raw).hexdigest() != args.sha256:
            raise ValueError('Reference file checksum does not match.')
        rows = parse(raw)
        with db() as conn:
            save_reference(conn, rows, args.label, args.filename, args.sha256, args.key)
        print('REFORM_PIVOT_REFERENCE seeded', args.key, 'rows', len(rows),
              'parents', len({r['sku'] for r in rows}), 'sha256', args.sha256, flush=True)


if __name__ == '__main__':
    main()
