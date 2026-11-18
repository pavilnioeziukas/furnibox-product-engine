"""Read-only SO and posted invoice quantities, classified by Internal Reference."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from zoneinfo import ZoneInfo

LABELS = {'assembled': 'Surenkami cabinet (-A)', 'flatpack': 'Flatpack cabinet', 'shelf': 'Shelf'}
SO_TAGS = ('Pakuojamas', 'Renkamas Furniboxe')

# Finished Reform SKUs only: never packaging, hardware, panels or shelf parts.
CODE = re.compile(r'^(?:EUB|USB)-C-CAB\d+-(BAS|BSK|BNF|BOH|COS|HCO|HBI|HIG|TOP|UPP|WAC|WAL|SLF)\d+(?: CUSTOM)?(-A)?$')


def classify(code):
    match = CODE.fullmatch(str(code or '').strip().upper())
    if not match:
        return None
    return 'shelf' if match[1] == 'SLF' else ('assembled' if match[2] else 'flatpack')


def whole_quantity(value):
    """Round only for display; keep unrounded quantities in all calculations."""
    rounded = Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return '0' if rounded == 0 else str(rounded)


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


def invoice_amount_summary(invoices, invoice_lines, invoice_orders):
    """Reconcile untaxed amounts in company currency to posted documents."""
    other = 'Kita / be žymos'
    overlap = 'Abi žymos'
    groups = (*SO_TAGS, other, overlap)
    rows = {name: {'label': name, 'invoice': Decimal(0), 'credit': Decimal(0)} for name in groups}
    totals = {'invoice': Decimal(0), 'credit': Decimal(0)}
    kinds = {}
    for doc in invoices:
        kind = 'credit' if doc['move_type'] == 'out_refund' else 'invoice'
        kinds[doc['id']] = kind
        amount = Decimal(str(doc['amount_untaxed_signed']))
        totals[kind] += -amount if kind == 'credit' else amount
    for line in invoice_lines:
        tags = {tag for order in invoice_orders[line['id']] for tag in order['report_tags']}
        if tags:
            group = overlap if len(tags) > 1 else next(iter(tags))
            kind = kinds[relation_id(line['move_id'])]
            balance = Decimal(str(line['balance']))
            rows[group][kind] += balance if kind == 'credit' else -balance
    # The remainder includes untagged lines and any unallocated invoice adjustments.
    for kind in totals:
        rows[other][kind] = totals[kind] - sum(rows[group][kind] for group in (*SO_TAGS, overlap))
    for row in [*rows.values(), totals]:
        row['net'] = row['invoice'] - row['credit']
    currency = next((doc['company_currency_id'][1] for doc in invoices if doc.get('company_currency_id')), 'EUR')
    return {'rows': list(rows.values()), 'total': totals, 'currency': currency}


def add_material_costs(read, amounts, start, end, company_id):
    """Count posted material issues once, on their ledger posting date."""
    from collections import defaultdict

    def related(model, field, ids, fields, extra=()):
        ids = sorted(set(ids))
        for offset in range(0, len(ids), 500):
            yield from read(model, [[field, 'in', ids[offset:offset + 500]], *extra], fields)

    company = ['company_id', '=', company_id]
    credits = read('account.move.line', [company, ['move_id.state', '=', 'posted'],
        ['move_id.move_type', '=', 'entry'], ['account_id.code', '=', '201000'],
        ['date', '>=', start], ['date', '<=', end], ['balance', '!=', 0]],
        ['move_id', 'balance', 'product_id'])
    entry_ids = {relation_id(line['move_id']) for line in credits}
    wip_entries = {relation_id(line['move_id']) for line in related(
        'account.move.line', 'move_id', entry_ids, ['move_id'],
        [company, ['account_id.code', '=', '202000'], ['balance', '!=', 0]])}
    layers = list(related('stock.valuation.layer', 'account_move_id', wip_entries,
                          ['account_move_id', 'stock_move_id', 'product_id'], [company]))
    raw_moves = {move['id']: relation_id(move['raw_material_production_id'])
                 for move in related('stock.move', 'id',
                     {relation_id(layer['stock_move_id']) for layer in layers if layer['stock_move_id']},
                     ['raw_material_production_id'], [company, ['state', '=', 'done'],
                     ['raw_material_production_id', '!=', False]])}
    productions_by_line = defaultdict(set)
    for layer in layers:
        production = raw_moves.get(relation_id(layer['stock_move_id']))
        if production:
            key = relation_id(layer['account_move_id']), relation_id(layer['product_id'])
            productions_by_line[key].add(production)

    productions = {row['id']: row for row in related('mrp.production', 'id',
        {pid for ids in productions_by_line.values() for pid in ids},
        ['origin', 'procurement_group_id'], [company])}
    groups = {row['id']: relation_id(row['sale_id']) for row in related('procurement.group', 'id',
        {relation_id(row['procurement_group_id']) for row in productions.values() if row['procurement_group_id']},
        ['sale_id'])}
    origins = {row['origin'] for row in productions.values() if row['origin']}
    orders = {row['id']: row for row in related('sale.order', 'id',
        {oid for oid in groups.values() if oid}, ['name', 'tag_ids'], [company])}
    orders.update({row['id']: row for row in related('sale.order', 'name', origins, ['name', 'tag_ids'], [company])})
    orders_by_name = {row['name']: row for row in orders.values()}
    tags = {row['id']: row['name'] for row in related('crm.tag', 'id',
        {tid for order in orders.values() for tid in order['tag_ids']}, ['name'],
        [['name', 'in', list(SO_TAGS)]])}

    costs = defaultdict(Decimal)
    for line in credits:
        production_ids = productions_by_line.get((relation_id(line['move_id']), relation_id(line['product_id'])))
        if not production_ids:
            continue
        labels = set()
        for production_id in production_ids:
            production = productions.get(production_id, {})
            order = orders.get(groups.get(relation_id(production.get('procurement_group_id'))))
            order = order or orders_by_name.get(production.get('origin'))
            selected = {tags[tid] for tid in order['tag_ids'] if tid in tags} if order else set()
            labels.add('Abi žymos' if len(selected) > 1 else next(iter(selected), 'Kita / be žymos'))
        group = next(iter(labels)) if len(labels) == 1 else 'Kita / be žymos'
        costs[group] -= Decimal(str(line['balance']))

    for row in amounts['rows']:
        row['material_cost'] = costs[row['label']]
    amounts['total']['material_cost'] = sum(costs.values(), Decimal(0))
    for row in [*amounts['rows'], amounts['total']]:
        row['throughput'] = (row['net'] - row['material_cost']) / row['net'] * 100 if row['net'] > 0 else None


def build_report(client, start, end, selected_tags=(), *, include_materials=False):
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
        [confirmation, '>=', lower], [confirmation, '<', upper]], ['name', confirmation, 'tag_ids'])
    invoices = read('account.move', [['company_id', '=', company[0]], ['state', '=', 'posted'],
        ['move_type', 'in', ['out_invoice', 'out_refund']], ['invoice_date', '>=', start],
        ['invoice_date', '<=', end]], ['name', 'invoice_date', 'move_type', 'amount_untaxed_signed', 'company_currency_id'])
    so_lines, invoice_lines = [], []
    # Batch ID domains to avoid oversized RPC requests for long periods.
    for model, docs, destination, link, quantity, unit in (
        ('sale.order.line', orders, so_lines, 'order_id', 'product_uom_qty', 'product_uom'),
        ('account.move.line', invoices, invoice_lines, 'move_id', 'quantity', 'product_uom_id')):
        for offset in range(0, len(docs), 500):
            domain = [[link, 'in', [d['id'] for d in docs[offset:offset+500]]]]
            if link == 'order_id':
                domain.append(['product_id', '!=', False])
            domain += [['display_type', '=', False]] if link == 'order_id' else [['display_type', 'in', [False, 'product']]]
            line_fields = [link, 'product_id', quantity, unit]
            if link == 'move_id':
                line_fields.extend(['sale_line_ids', 'balance'])
            destination.extend(read(model, domain, line_fields))

    orders_by_id = {order['id']: order for order in orders}
    sale_line_ids = sorted({line_id for line in invoice_lines for line_id in line.get('sale_line_ids', [])})
    order_by_sale_line = {
        line['id']: relation_id(line['order_id']) for line in so_lines if 'id' in line
    }
    missing_line_ids = sorted(set(sale_line_ids) - order_by_sale_line.keys())
    for offset in range(0, len(missing_line_ids), 500):
        batch = missing_line_ids[offset:offset + 500]
        order_by_sale_line.update({
            line['id']: relation_id(line['order_id'])
            for line in read('sale.order.line', [['id', 'in', batch]], ['order_id'])
        })
    # Invoice dates are independent of order confirmation dates.
    missing_order_ids = sorted({oid for oid in order_by_sale_line.values() if oid} - orders_by_id.keys())
    for offset in range(0, len(missing_order_ids), 500):
        batch = missing_order_ids[offset:offset + 500]
        orders_by_id.update({
            order['id']: order for order in read('sale.order',
                [['id', 'in', batch], ['company_id', '=', company[0]]], ['name', 'tag_ids'])
        })
    tag_ids = sorted({tag_id for order in orders_by_id.values() for tag_id in order.get('tag_ids', [])})
    tag_names = {
        tag['id']: tag['name'] for tag in read('crm.tag',
            [['id', 'in', tag_ids], ['name', 'in', list(SO_TAGS)]], ['name'])
    } if tag_ids else {}
    for order in orders_by_id.values():
        order['report_tags'] = sorted({
            tag_names[tag_id] for tag_id in order.get('tag_ids', []) if tag_id in tag_names
        })
    selected_tags = set(selected_tags)
    if selected_tags:
        orders = [order for order in orders if selected_tags.intersection(order['report_tags'])]
        matching_order_ids = {order['id'] for order in orders}
        so_lines = [line for line in so_lines if relation_id(line['order_id']) in matching_order_ids]
    invoice_orders = {}
    for line in invoice_lines:
        linked_ids = {
            order_by_sale_line.get(line_id) for line_id in line.get('sale_line_ids', [])
        }
        invoice_orders[line['id']] = [
            orders_by_id[order_id] for order_id in sorted(linked_ids & orders_by_id.keys())
        ]
    amounts = invoice_amount_summary(invoices, invoice_lines, invoice_orders)
    if include_materials:
        add_material_costs(read, amounts, start, end, company[0])
    invoice_lines = [line for line in invoice_lines if line['product_id']]
    if selected_tags:
        for line_id, linked_orders in invoice_orders.items():
            invoice_orders[line_id] = [
                order for order in linked_orders if selected_tags.intersection(order['report_tags'])
            ]
        invoice_lines = [line for line in invoice_lines if invoice_orders[line['id']]]

    product_ids = sorted({relation_id(line['product_id']) for line in so_lines + invoice_lines})
    products = {}
    for offset in range(0, len(product_ids), 500):
        products.update({p['id']: p for p in read('product.product', [['id', 'in', product_ids[offset:offset+500]]], ['default_code', 'name', 'uom_id'])})
    units = {u['id']: u for u in read('uom.uom', [], ['name', 'factor', 'category_id', 'uom_type'])} if product_ids else {}
    summary = {key: {'label': label, 'so': Decimal(0), 'invoice': Decimal(0), 'credit': Decimal(0), 'net': Decimal(0)} for key, label in LABELS.items()}
    types = {'assembled': {}, 'flatpack': {}}
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
            product_type = CODE.fullmatch(code.upper())[1]
            if category in types:
                type_row = types[category].setdefault(product_type, {
                    'label': product_type, 'so': Decimal(0), 'invoice': Decimal(0),
                    'credit': Decimal(0), 'net': Decimal(0)})
                type_row[kind] += qty
            signed = -qty if kind == 'credit' else qty
            doc_date = doc[confirmation] if kind == 'so' else doc['invoice_date']
            if kind == 'so':
                doc_date = datetime.fromisoformat(doc_date).replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/Vilnius')).strftime('%Y-%m-%d %H:%M:%S')
            linked_orders = [doc] if kind == 'so' else invoice_orders[line['id']]
            details.append({'orders': [
                {'name': order['name'], 'tags': order['report_tags']} for order in linked_orders
            ], 'kind': kind, 'document': doc['name'], 'date': doc_date, 'code': code,
                'category': LABELS[category], 'product_type': product_type,
                'quantity': signed, 'unit': target_unit['name']})
    for category, row in summary.items():
        row['net'] = row['invoice'] - row['credit']
        row['types'] = []
        for key, type_row in sorted(types.get(category, {}).items()):
            type_row['net'] = type_row['invoice'] - type_row['credit']
            row['types'].append(type_row)
    return {'start': start, 'end': end, 'company': company[1], 'confirmation_field': confirmation,
        'amounts': amounts, 'summary': list(summary.values()), 'details': details, 'excluded': excluded,
        'generated': datetime.now(ZoneInfo('Europe/Vilnius')).strftime('%Y-%m-%d %H:%M:%S')}
