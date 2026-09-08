"""Persistent calculator rates; one immutable snapshot per price run."""
import json
import os
import tempfile
from pathlib import Path
from price_calculators import defaults, number
from webapp.product_engine import ProductEngineSettings


def settings_path():
    shared = (os.environ.get('PRODUCT_ENGINE_SHARED_DATA_DIR') or
              os.environ.get('FURNIBOX_SHARED_DATA_DIR') or os.environ.get('FURNIBOX_SHARED_DATA') or
              ProductEngineSettings.from_env(Path(__file__).parent).shared_data_dir)
    return Path(shared) / 'calculator_settings.json'


def validate(data):
    result = {'version': 1, 'markup_percent': number(data.get('markup_percent', 0), 'Antkainis')}
    for kind in ('panel', 'shelf'):
        rates = data.get(kind, defaults(kind))
        result[kind] = {k: number(rates[k], k) for k in defaults(kind)}
    result['led_costs'] = {}
    for sku, costs in data.get('led_costs', {}).items():
        if len(costs) != 9:
            raise ValueError('LED / ROD turi turėti 9 kainos dalis')
        result['led_costs'][sku] = [number(v, sku) for v in costs]
    return result


def load():
    path = settings_path()
    return validate(json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})


def save(data):
    data = validate(data)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        temporary = f.name
    os.replace(temporary, path)
    return data
