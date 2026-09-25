"""Read-only SO and posted invoice quantities, classified by Internal Reference."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

LABELS = {'assembled': 'Surenkami cabinet (-A)', 'flatpack': 'Flatpack cabinet', 'shelf': 'Shelf'}
# Finished Reform SKUs only: never packaging, hardware, panels or shelf parts.
CODE = re.compile(r'^(?:EUB|USB)-C-CAB\d+-(BAS|BSK|BNF|BOH|COS|HCO|HBI|HIG|TOP|UPP|WAC|WAL|SLF)\d+(?: CUSTOM)?(-A)?$')


def classify(code):
    match = CODE.fullmatch(str(code or '').strip().upper())
    if not match:
        return None
    return 'shelf' if match[1] == 'SLF' else ('assembled' if match[2] else 'flatpack')


def period(start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last:
            raise ValueError
        zone = ZoneInfo('Europe/Vilnius')
        lower = datetime.combine(first, time.min, zone).astimezone(timezone.utc)
        upper = datetime.combine(last + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Pasirinkite galiojančią pradžios ir pabaigos datą; pradžia negali būti vėlesnė už pabaigą.') from None
    return lower.strftime('%Y-%m-%d %H:%M:%S'), upper.strftime('%Y-%m-%d %H:%M:%S')


def relation_id(value):
    return value[0] if value else None


def build_report(client, start, end):
    lower, upper = period(start, end)
    client.authenticate()
    user = client.execute('res.users', 'read', [[client.uid]], {'fields': ['company_id']})[0]
    company = user['company_id']
    context = {'allowed_company_ids': [company[0]], 'active_test': False}
    def read(model, domain, fields):
        return client.search_read_all(model, domain, fields, context=context)
    fields = client.execute('sale.order', 'fields_get', [], {'attributes': ['type']})
    # Older Odoo versions have confirmation_date; current versions write date_order on confirmation.
    confirmation = 'confirmation_date' if 'confirmation_date' in fields else 'date_order'
    orders = read('sale.order', [['company_id', '=', company[0]], ['state', 'in', ['sale', 'done']],
        [confirmation, '>=', lower], [confirmation, '<', upper]], ['name', confirmation])
    invoices = read('account.move', [['company_id', '=', company[0]], ['state', '=', 'posted'],
        ['move_type', 'in', ['out_invoice', 'out_refund']], ['invoice_date', '>=', start],
        ['invoice_date', '<=', end]], ['name', 'invoice_date', 'move_type'])
    so_lines, invoice_lines = [], []
    # Batch ID domains to avoid oversized RPC requests for long periods.
    for model, docs, destination, link, quantity, unit in (
        ('sale.order.line', orders, so_lines, 'order_id', 'product_uom_qty', 'product_uom'),
        ('account.move.line', invoices, invoice_lines, 'move_id', 'quantity', 'product_uom_id')):
        for offset in range(0, len(docs), 500):
            domain = [[link, 'in', [d['id'] for d in docs[offset:offset+500]]], ['product_id', '!=', False]]
            domain += [['display_type', '=', False]] if link == 'order_id' else [['display_type', 'in', [False, 'product']]]
            destination.extend(read(model, domain, [link, 'product_id', quantity, unit]))
    product_ids = sorted({relation_id(line['product_id']) for line in so_lines + invoice_lines})
    products = {}
    for offset in range(0, len(product_ids), 500):
        products.update({p['id']: p for p in read('product.product', [['id', 'in', product_ids[offset:offset+500]]], ['default_code', 'name', 'uom_id'])})
    units = {u['id']: u for u in read('uom.uom', [], ['name', 'factor', 'category_id', 'uom_type'])} if product_ids else {}
    summary = {key: {'label': label, 'so': Decimal(0), 'invoice': Decimal(0), 'credit': Decimal(0), 'net': Decimal(0)} for key, label in LABELS.items()}
    details, excluded = [], {}
    for lines, docs, link, quantity, unit in (
        (so_lines, {d['id']: d for d in orders}, 'order_id', 'product_uom_qty', 'product_uom'),
        (invoice_lines, {d['id']: d for d in invoices}, 'move_id', 'quantity', 'product_uom_id')):
        for line in lines:
            product = products[relation_id(line['product_id'])]
            code = str(product.get('default_code') or '').strip()
            category = classify(code)
            if not category:
                excluded[code or '(be kodo)'] = product['name']
                continue
            source_unit, target_unit = units[relation_id(line[unit])], units[relation_id(product['uom_id'])]
            if source_unit['category_id'][0] != target_unit['category_id'][0] or target_unit['uom_type'] != 'reference':
                raise ValueError(f'{code}: nesuderinami matavimo vienetai. Patikrinkite produkto ir dokumento vienetus.')
            qty = Decimal(str(line[quantity])) / Decimal(str(source_unit['factor'])) * Decimal(str(target_unit['factor']))
            doc = docs[relation_id(line[link])]
            kind = 'so' if link == 'order_id' else ('credit' if doc['move_type'] == 'out_refund' else 'invoice')
            summary[category][kind] += qty
            signed = -qty if kind == 'credit' else qty
            doc_date = doc[confirmation] if kind == 'so' else doc['invoice_date']
            if kind == 'so':
                doc_date = datetime.fromisoformat(doc_date).replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/Vilnius')).strftime('%Y-%m-%d %H:%M:%S')
            details.append({'kind': kind, 'document': doc['name'], 'date': doc_date, 'code': code,
                'category': LABELS[category], 'quantity': signed, 'unit': target_unit['name']})
    for row in summary.values():
        row['net'] = row['invoice'] - row['credit']
    return {'start': start, 'end': end, 'company': company[1], 'confirmation_field': confirmation,
        'summary': list(summary.values()), 'details': details, 'excluded': excluded,
        'generated': datetime.now(ZoneInfo('Europe/Vilnius')).strftime('%Y-%m-%d %H:%M:%S')}
