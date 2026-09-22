"""Tamara's Furnix -> Furnibox edging quantities, in metres per part."""
import re
from price_calculators import number

MATERIAL_FACTOR = 1.1
RULES = {
    'PERIMETER': 'Visas perimetras (SIDE / SIDEL)',
    'WIDTH': 'Abi pločio kraštinės (BOT / TOP)',
    'LONG': 'Abi ilgosios kraštinės (STIFF)',
    'NONE': 'Nebriaunuojama (BACK)',
    'UNKNOWN': 'Taisyklė nenustatyta – pasirinkite',
}


def infer_rule(sku):
    tokens = set(re.split(r'[^A-Z0-9]+', str(sku).upper()))
    if 'BACK' in tokens:
        return 'NONE'
    matches = set()
    if tokens & {'SIDE', 'SIDEL', 'SHELF', 'PANEL'}:
        matches.add('PERIMETER')
    if tokens & {'BOT', 'TOP'}:
        matches.add('WIDTH')
    if 'STIFF' in tokens:
        matches.add('LONG')
    return matches.pop() if len(matches) == 1 else 'UNKNOWN'


def quantity(kind, row):
    length = number(row['length'], 'Ilgis', True)
    width = number(row['width'], 'Plotis', True)
    if kind in ('shelf', 'panel'):
        rule = 'PERIMETER'
    elif row.get('part_type') == 'BACK':
        rule = 'NONE'
    else:
        rule = row.get('edging_rule', infer_rule(row.get('sku', '')))
    if rule not in RULES:
        raise ValueError('Nežinoma briaunavimo taisyklė.')
    mm = {'PERIMETER': 2 * (length + width), 'WIDTH': 2 * width,
          'LONG': 2 * max(length, width), 'NONE': 0}.get(rule)
    return dict(rule=rule, label=RULES[rule], factor=MATERIAL_FACTOR,
                length_m=mm / 1000 if mm is not None else None,
                material_m=mm / 1000 * MATERIAL_FACTOR if mm is not None else None)
