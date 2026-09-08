"""Independent review calculators. No Odoo or SO pricing mutations."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'manifest'


def source(kind):
    if kind not in ('panel', 'shelf'):
        raise ValueError('Nežinoma skaičiuoklė')
    return json.loads((ROOT / f'{kind}_calculator_source.json').read_text(encoding='utf-8'))


def defaults(kind):
    if kind == 'panel':
        return dict(WW=45.27 / 5.7, BB=37.09 / 5.7, NO=45.27 / 5.7,
                    work=18.95, fixed=4.17, packaging=2, extra_work=1)
    return source(kind)['rates']


def number(value, name, positive=False):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name}: reikia skaičiaus') from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f'{name}: netinkama reikšmė')
    return result


def calculate(kind, row, rates):
    rates = {key: number(rates[key], key) for key in defaults(kind)}
    area = number(row['length'], 'Ilgis', True) * number(row['width'], 'Plotis', True) / 1_000_000
    if kind == 'panel':
        color = row['color']
        if color not in ('WW', 'BB', 'NO'):
            raise ValueError('Nežinoma spalva')
        material = area * rates[color]
        work = area * rates['work']
        base = material + work + rates['fixed']
        packaging = area * rates['packaging']
        extra = area * rates['extra_work']
        parts = [('Medžiaga', material), ('Bazinis darbas', work),
                 ('Fiksuota dalis', rates['fixed']), ('Bazė K', base),
                 ('Pakuotė W', packaging), ('Papildomas darbas X', extra)]
        total = base + packaging + extra
    else:
        if row['packaging'] is None or row['cardboard'] is None:
            return dict(area=area, parts=[], total=None, message='Trūksta pakuotės arba kartono kainos. Įveskite reikšmes skaičiavimui.')
        packaging = number(row['packaging'], 'Pakuotė')
        cardboard = number(row['cardboard'], 'Kartonas')
        if row['kind'] not in rates:
            raise ValueError('Nežinomas lentynos tipas')
        coefficient = 3 if area < .1 else 1.5 if area < .2 else 1
        multiplier = row.get('source_multiplier', 1)
        wood = (area * rates[row['kind']] - packaging - cardboard) * coefficient * multiplier
        parts = [('Tarifas, €/m²', rates[row['kind']]), ('Ploto koeficientas', coefficient),
                 ('Papildomas šaltinio daugiklis', multiplier),
                 ('Medinė dalis U', wood), ('Pakuotė R', packaging), ('Kartonas S', cardboard)]
        total = wood + packaging + cardboard
    comparison = row.get('current') if kind == 'panel' else row.get('comparison')
    return dict(area=area, parts=parts, total=total,
                difference=total-comparison if isinstance(comparison, (int,float)) else None,
                message='')
