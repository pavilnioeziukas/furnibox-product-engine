"""Read-only production catalogue, including BOMs unsuitable for the pilot editor."""
from collections import defaultdict
from datetime import datetime, timezone


def read_catalogue(client, roots=None):
    def ident(value):
        return value[0] if isinstance(value, (list, tuple)) and value else value or None
    def label(value):
        return value[1] if isinstance(value, (list, tuple)) and len(value) > 1 else ''
    raw_products = client.search_read_all('product.product', [],
        ['id', 'default_code', 'name', 'active', 'product_tmpl_id', 'uom_id', 'categ_id'], context={'active_test': False})
    by_id = {p['id']: p for p in raw_products}
    by_sku, by_template = defaultdict(list), defaultdict(list)
    for p in raw_products:
        if p.get('default_code'):
            by_sku[p['default_code']].append(p)
        by_template[ident(p['product_tmpl_id'])].append(p)
    keys = {p['id']: p['default_code'] if p.get('default_code') and len(by_sku[p['default_code']]) == 1
            else f"odoo-{p['id']}" for p in raw_products}
    raw_boms = client.search_read_all('mrp.bom', [('active', '=', True)],
        ['id', 'product_id', 'product_tmpl_id', 'product_qty', 'product_uom_id', 'type', 'code', 'sequence', 'write_date'])
    raw_lines = client.search_read_all('mrp.bom.line', [('bom_id', 'in', [b['id'] for b in raw_boms])],
        ['id', 'bom_id', 'product_id', 'product_qty', 'product_uom_id', 'bom_product_template_attribute_value_ids']) if raw_boms else []
    lines_by_bom, boms_by_product = defaultdict(list), defaultdict(list)
    for line in raw_lines:
        lines_by_bom[ident(line['bom_id'])].append(line)
    for b in raw_boms:
        candidates = [by_id[ident(b['product_id'])]] if ident(b['product_id']) in by_id else by_template[ident(b['product_tmpl_id'])]
        for p in candidates:
            boms_by_product[p['id']].append(b)
    # Match the engine priority: lowest sequence, then latest modification.
    for pid, candidates in boms_by_product.items():
        minimum = min(int(b.get('sequence') or 0) for b in candidates)
        preferred = [b for b in candidates if int(b.get('sequence') or 0) == minimum]
        preferred.sort(key=lambda b: (str(b.get('write_date') or ''), int(b['id'])), reverse=True)
        boms_by_product[pid] = preferred[:1]
    if roots:
        if any(len(by_sku.get(sku, [])) != 1 for sku in roots):
            raise ValueError('Selected product codes must exist in Odoo and be unique.')
        selected = {by_sku[sku][0]['id'] for sku in roots}
    else:
        selected = {p['id'] for p in raw_products if p['active']}
    pending = list(selected)
    while pending:
        pid = pending.pop()
        for b in boms_by_product[pid]:
            for line in lines_by_bom[b['id']]:
                cid = ident(line['product_id'])
                if cid in by_id and cid not in selected:
                    selected.add(cid)
                    pending.append(cid)
    products, boms, included_bids = {}, {}, set()
    for pid in sorted(selected):
        p, key = by_id[pid], keys[pid]
        lock = '' if p.get('default_code') and len(by_sku[p['default_code']]) == 1 else 'The product code is missing or duplicated. Furnibox review is required.'
        products[key] = {'sku': key, 'display_sku': p.get('default_code') or 'No code', 'name': p['name'],
            'active': p['active'], 'odoo_id': pid, 'category': label(p.get('categ_id')), 'category_id': ident(p.get('categ_id')),
            'uom': label(p['uom_id']), 'uom_id': ident(p['uom_id']), 'read_only': lock}
        for b in boms_by_product[pid]:
            bid = str(b['id'])
            shared = not b['product_id'] and len(by_template[ident(b['product_tmpl_id'])]) > 1
            if shared:
                bid += f':{pid}'
            reason = lock
            if shared:
                reason = 'This BOM is shared by several product variants. It is read-only in this pilot.'
            components = []
            for line in lines_by_bom[b['id']]:
                cid = ident(line['product_id'])
                if cid not in keys:
                    raise ValueError('Odoo returned a BOM row without a product.')
                if line.get('bom_product_template_attribute_value_ids'):
                    reason = 'BOM components depend on the product variant. This BOM is read-only in this pilot.'
                components.append({'id': str(line['id']), 'sku': keys[cid], 'quantity': line['product_qty'],
                    'uom': label(line['product_uom_id']), 'uom_id': ident(line['product_uom_id'])})
            included_bids.add(b['id'])
            boms[bid] = {'id': bid, 'odoo_id': b['id'], 'sku': key, 'code': b.get('code') or '',
                'sequence': b.get('sequence', 0), 'write_date': b.get('write_date', ''),
                'active': True, 'quantity': b['product_qty'], 'uom': label(b['product_uom_id']),
                'uom_id': ident(b['product_uom_id']), 'type': b['type'], 'components': components, 'read_only': reason}
    current_ids = {b['id'] for items in boms_by_product.values() for b in items}
    external_usage = defaultdict(int)
    for line in raw_lines:
        if ident(line['bom_id']) in current_ids - included_bids and ident(line['product_id']) in selected:
            external_usage[keys[ident(line['product_id'])]] += 1
    return {'products': products, 'boms': boms, 'external_usage': dict(external_usage),
        '_reserved_skus': list(by_sku), 'source': 'Odoo Production',
        'scope': 'selected' if roots else 'production_catalogue',
        'captured_at': datetime.now(timezone.utc).isoformat()}
