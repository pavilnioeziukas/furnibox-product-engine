"""Tamara's corrected C1-C12 table, confirmed per component unit."""
import copy

VERSION = '2026-09-10-c1-c12-per-unit'
# assembly, storage, packaging, pallet, other, markup; EUR per unit.
TARIFFS = {
    'C1': ('Components / ACCESSORIES', (0, .05, 0, 0, 0, 0)),
    'C2': ('Components / CABINET ACCESSORIES', (0, .05, 0, 0, 0, 0)),
    'C3': ('Components / CABINET HARDWARE', (0, .05, 0, 0, 0, 0)),
    'C4': ('Components / FASTENERS', (0, .01, 0, 0, 0, 0)),
    'C5': ('Components / FRONT HARDWARE', (0, .04, 0, 0, .01, 0)),
    'C6': ('Components / INTERIOR STORAGE', (0, 2, 0, 0, 0, 0)),
    'C7': ('Components / LED HARDWARE', (.1, .05, .05, .02, 0, 0)),
    'C8': ('Components / OTHER', (.04, .04, 0, 0, 0, 0)),
    'C9': ('Components / PAPER PRINT', (0, .05, .05, .02, 0, 0)),
    'C10': ('Components / SHELF HARDWARE', (0, .15, .05, .02, 0, 0)),
    'C11': ('Packing material', (0, 1.04, 0, 0, 0, 0)),
    'C12': ('TRANSPORT BOX', (0, 0, 0, 0, 4, 0)),
}

def normalize(value):
    return '/'.join(' '.join(p.split()).casefold() for p in str(value or '').split('/'))

def category_code(path):
    names = {normalize(name): code for code, (name, _) in TARIFFS.items()}
    names['packaging material'] = 'C11'
    return names.get(normalize(path))

def apply_config(document):
    from so_pricing_rules import ADDON_FIELDS
    document = copy.deepcopy(document)
    if document.get('component_tariffs_version') == VERSION:
        return document
    for code, (name, amounts) in TARIFFS.items():
        for category in document['bom_categories']:
            if category_code(category.get('odoo_category')) == code:
                category.update(name=name, source_category_id=code,
                                **dict(zip(ADDON_FIELDS, amounts)))
        document['bom_categories'].append({'id':'COMPONENT-'+code, 'name':name,
            'source_category_id':code, 'odoo_category':name,
            **dict(zip(ADDON_FIELDS, amounts))})
    by_id = {c['id']: c for c in document['bom_categories']}
    for assignment in document['bom_skus']:
        code = category_code(by_id[assignment['category_id']].get('odoo_category'))
        if code:
            assignment['category_id'] = 'COMPONENT-'+code
    document['component_tariffs_version'] = VERSION
    return document

def apply_rules(rules, document, dataset=None):
    """Classify by explicit category paths, never by SKU or equal rate sums."""
    from so_pricing_rules import ADDON_FIELDS, PricingRule
    result = dict(rules)
    categories = {r['source_category_id']:r for r in document['bom_categories']
                  if r['id'].startswith('COMPONENT-')}
    paths = {sku:rule.odoo_category for sku,rule in result.items()}
    for product in (dataset or {}).get('product_catalog', []):
        if product.get('is_component') and not product.get('has_bom'):
            group = str(product.get('part_group') or '')
            path = group if category_code(group) else 'Components / '+group
            if category_code(path):
                paths.setdefault(product['sku'].strip().casefold(), path)
                if not category_code(paths[product['sku'].strip().casefold()]):
                    paths[product['sku'].strip().casefold()] = path
    for sku,path in paths.items():
        code = category_code(path)
        if code and code in categories:
            c = categories[code]
            result[sku] = PricingRule(result[sku].sku if sku in result else sku,
                code, c['name'], c['odoo_category'],
                *(float(c.get(f,0)) for f in ADDON_FIELDS))
    return result
