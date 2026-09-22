"""Separate parameter snapshot for the detail calculator; never writes SO inputs."""
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import calculator_settings
from cabinet_parts_price_parameters import load_parameters, validate_parameters
from cabinet_parts_price_v1 import calculate_unit_price, furnix_transfer_price
from price_calculators import calculate, defaults, number
from detail_edging import quantity as edging_quantity

AREA_DEFAULTS = dict(small_limit=.1, medium_limit=.2, small=3, medium=1.5, large=1)


def validate(document):
    result = dict(document)
    for kind in ('shelf', 'panel'):
        result[kind] = {key: number(document[kind][key], key) for key in defaults(kind)}
    result['area'] = {key: number(document['area'][key], key) for key in AREA_DEFAULTS}
    if not 0 < result['area']['small_limit'] < result['area']['medium_limit']:
        raise ValueError('Ploto ribos turi būti teigiamos ir didėti.')
    cabinet = {key: number(value, key) for key, value in document['cabinet'].items()}
    if not cabinet['output_decimals'].is_integer():
        raise ValueError('Apvalinimo skaitmenų skaičius turi būti sveikas.')
    result['cabinet'] = asdict(validate_parameters(cabinet))
    return result


def save(path, document, *, initialize=False):
    document = validate(document)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
        if initialize:
            try:
                os.link(temporary, path)
            except FileExistsError:
                return validate(json.loads(path.read_text(encoding='utf-8')))
        else:
            os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return document


def load(path, cabinet_path):
    path = Path(path)
    if path.exists():
        return validate(json.loads(path.read_text(encoding='utf-8')))
    # First use atomically freezes all groups; later live edits cannot change this copy.
    live = calculator_settings.load()
    return save(path, dict(version=1, copied_at=datetime.now(timezone.utc).isoformat(),
                         shelf=live['shelf'], panel=live['panel'], area=dict(AREA_DEFAULTS),
                         cabinet=asdict(load_parameters(Path(cabinet_path)))), initialize=True)


def compute(kind, row, config):
    if kind != 'cabinet':
        result = calculate(kind, row, config[kind], area_coefficients=config['area'])
        result['edging'] = edging_quantity(kind, row)
        return result
    parameters = validate_parameters(config['cabinet'])
    # Use the established Cabinet Parts calculation, including BACK and strict < boundary.
    sku = ('BACK' if row['part_type'] == 'BACK' else 'PART') + '-' + row['color']
    calculated = calculate_unit_price(sku, (number(row['length'], 'Ilgis', True),
                                           number(row['width'], 'Plotis', True)), parameters)
    # Match CABINET PART PRICES: round unit cost before applying transfer markup.
    unit_cost = round(calculated.unit_price, parameters.output_decimals)
    markup, total = furnix_transfer_price(unit_cost, parameters)
    total = round(total, parameters.output_decimals)
    area = calculated.area_m2
    return dict(area=area, total=total, message='', edging=edging_quantity(kind, row), parts=[
        ('Medžiaga / BACK', area * (calculated.back_rate_per_m2 + calculated.material_rate_per_m2)),
        ('Apdirbimas', area * calculated.processing_rate_per_m2),
        ('Mažos detalės priedas', calculated.small_part_surcharge),
        ('Savikaina', unit_cost), ('Furnix perdavimo antkainis', markup)])
