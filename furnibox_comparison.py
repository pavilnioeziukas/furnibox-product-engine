"""Furnix/Furnibox comparison from Tamara's reviewed catalog and formulas."""
import hashlib
import json
import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path

SOURCE = Path(__file__).parent / 'manifest' / 'furnibox_comparison_20260924.json'
RATE_LABELS = {'WW': 'WW plokštė, €/m²', 'BB': 'BB plokštė, €/m²',
               'NO': 'NO plokštė, €/m²', 'BACK': 'BACK plokštė, €/m²',
               'material_factor': 'Plokštės sunaudojimo koeficientas',
               'edge_factor': 'Briaunos sunaudojimo koeficientas', 'edge_rate': 'Briaunavimas, €/m'}


@lru_cache(maxsize=1)
def source():
    return json.loads(SOURCE.read_text(encoding='utf-8'))


def number(value, label, positive=False):
    try:
        result = float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError(f'{label}: įveskite skaičių.') from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f'{label}: įveskite teigiamą baigtinį skaičių.')
    return result


def calculate(row, rates, coefficient=None):
    coefficient = row['coefficient'] if coefficient is None else coefficient
    result = dict(row, coefficient=coefficient, area=None, edge_m=None, edge_quantity=None,
                  material=None, calculated_purchase=None, furnibox_coefficient=None,
                  difference=None, difference_pct=None, reform_difference=None, reform_markup=None)
    if row['length'] is not None and row['width'] is not None:
        back = 'BACK' in row['sku'].upper()
        area = row['length'] * row['width'] / 1_000_000
        edge = 0 if back else 2 * (row['length'] + row['width']) / 1000
        rate = rates['BACK'] if back else rates.get(row['color'])
        result.update(area=area, edge_m=edge, edge_quantity=edge*rates['edge_factor'])
        if rate is not None:
            result['material'] = area*rate*rates['material_factor'] + edge*rates['edge_factor']*rates['edge_rate']
            if coefficient is not None:
                result['calculated_purchase'] = result['material'] * coefficient
    reform, purchase, material = row['reform'], row['purchase'], result['material']
    if reform is not None and result['calculated_purchase'] is not None and result['calculated_purchase'] > 0:
        result['furnibox_coefficient'] = reform / result['calculated_purchase']
    if purchase is not None and material is not None:
        result['difference'] = purchase - material
        if purchase > 0:
            result['difference_pct'] = result['difference'] / purchase
    if reform is not None and purchase is not None:
        result['reform_difference'] = reform - purchase
        if purchase > 0:
            result['reform_markup'] = result['reform_difference'] / purchase
    return result


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temporary = f.name
            json.dump(value, f, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_rates(directory):
    path = Path(directory) / 'rates.json'
    return source()['rates'] | (json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})


def save_rates(directory, values):
    rates = {k: number(values.get(k), label, positive=k.endswith('factor')) for k, label in RATE_LABELS.items()}
    _write(Path(directory)/'rates.json', rates)


def save_coefficient(directory, sku, value):
    row = next((r for r in source()['rows'] if r['sku'] == sku), None)
    if not row or row['coefficient'] is None:
        raise ValueError('Šiam kodui Furnix koeficientas netaikomas.')
    coefficient = number(value, 'Furnix koeficientas', positive=True)
    key = hashlib.sha256(sku.encode()).hexdigest()
    _write(Path(directory)/'coefficients'/f'{key}.json', dict(sku=sku, coefficient=coefficient))


def results(directory):
    overrides = {}
    for path in (Path(directory)/'coefficients').glob('*.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        overrides[value['sku']] = number(value['coefficient'], 'Furnix koeficientas', positive=True)
    rates = load_rates(directory)
    return rates, [calculate(row, rates, overrides.get(row['sku'])) for row in source()['rows']]
