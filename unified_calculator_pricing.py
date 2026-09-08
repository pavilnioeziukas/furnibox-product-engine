"""Exact-SKU calculator recipes shared with SO pricing, before final markup.

Calculator pack prices replace the complete pack calculation, including its
packaging. They are never added on top of historical pack add-ons.
Ambiguous recipes deliberately have no price and cannot fall back to old costs.
"""
from collections import defaultdict
import re
import copy
from price_calculators import calculate, source
import shelf_workbook


def key(sku):
    return sku.strip().casefold()


def led_results(settings):
    data = copy.deepcopy(shelf_workbook.load())
    for row in data['led']:
        row['costs'] = settings.get('led_costs', {}).get(row['sku'], row['costs'])
    return shelf_workbook.led_results(data)


def recipes(settings):
    candidates = defaultdict(list)

    def add(sku, total, parts, origin, issue=''):
        if sku:
            candidates[key(sku)].append(dict(sku=sku, total=total, parts=parts, origin=origin, issue=issue))

    for row in source('panel')['rows']:
        result = calculate('panel', row, settings['panel'])
        parts = result['parts']
        add(row['sku'], result['total'], parts[:3]+parts[4:], 'Panelių skaičiuoklė: K + W + X')
        add(row['detail'], parts[3][1], parts[:3], 'Panelių skaičiuoklė: bazė K')

    for row in source('shelf')['rows']:
        result = calculate('shelf', row, settings['shelf'])
        # Exact duplicate rows may agree, but a source type mismatch is not an
        # approved classification. Never silently prefer one conflicting row.
        issue = '; '.join(x for x in row.get('issues', []) if 'tip' in x.casefold())
        total = result['total'] if not issue else None
        issue = issue or result.get('message', '')
        parts = result['parts'][3:] if total is not None else []
        wood = parts[0][1] if parts else None
        add(row['sku'], wood, parts[:1], 'Lentynų skaičiuoklė: U', issue)
        add(row['pack'], total, parts, 'Lentynų skaičiuoklė: U + R + S', issue)

    result = {}
    for sku, rows in candidates.items():
        signatures = {(r['total'], tuple(r['parts']), r['issue']) for r in rows}
        recipe = dict(rows[0])
        if len(signatures) != 1:
            recipe.update(total=None, issue='Prieštaringos skaičiuoklės eilutės tam pačiam SKU', parts=[])
        if recipe['total'] is not None and recipe['total'] <= 0:
            recipe.update(total=None, issue='Skaičiuoklės rezultatas nėra teigiamas', parts=[])
        result[sku] = recipe

    # The dedicated nine-part LED / ROD calculation is the finished shelf
    # recipe. Its packaging is already included. A PP SKU denotes that same
    # packaged shelf, not a second packaging operation.
    for row in led_results(settings):
        recipe = dict(sku=row['sku'], total=row['total'], parts=[(k,v if v is not None else 0.) for k,v in row['parts']],
                      origin='LED / ROD skaičiuoklė: C:K', issue='')
        if row['total'] is None:
            recipe['issue'] = 'Nepilnas LED / ROD išskaidymas'
        result[key(row['sku'])] = recipe
        result[key(row['sku']+'-PP')] = dict(recipe, sku=row['sku']+'-PP')
    return result


def prepare(prices, registry):
    prices = dict(prices)
    for sku, recipe in registry.items():
        prices[sku] = (recipe['sku'], recipe['total'] or 0,
                       'CALCULATOR: '+recipe['origin']+(' | '+recipe['issue'] if recipe['issue'] else ''))
    return prices


def dimensional_shelf_recipe(sku, settings):
    """Apply the published family formula to new dimensions, not new prices.

    R/S are inherited only when all populated source rows of the same market
    and family agree. LED/ROD require their dedicated cost breakdown.
    Source-specific extra multipliers are never generalized to new sizes.
    """
    match = re.fullmatch(r'(EU|US)-SREW-SHELF-(?:(FIXVEN|FIX|OVEN|CORNER)(?:-[A-Z_]+)?-)?'
                         r'(\d+(?:[.,]\d+)?)\s*X\s*(\d+(?:[.,]\d+)?)-(WW|BB|NO)(-PP)?', sku.upper())
    if not match:
        return None
    market, family, length, width, color, packed = match.groups()
    family = 'SREW-SHELF-' + (family or 'PAPR')
    reference = [r for r in source('shelf')['rows']
                 if r['sku'].upper().startswith(market+'-') and r['kind'] == family
                 and r['packaging'] is not None and r['cardboard'] is not None
                 and not any('tip' in issue.casefold() for issue in r.get('issues', []))]
    charges = {(r['packaging'], r['cardboard']) for r in reference}
    if len(charges) != 1:
        return None
    packaging, cardboard = charges.pop()
    row = dict(length=float(length.replace(',', '.')), width=float(width.replace(',', '.')),
               kind=family, packaging=packaging, cardboard=cardboard, source_multiplier=1)
    calculated = calculate('shelf', row, settings['shelf'])
    parts = calculated['parts'][3:]
    if not packed:
        parts = parts[:1]
    total = sum(v for _,v in parts)
    if total <= 0:
        return None
    return dict(sku=sku, total=total, parts=parts, issue='',
                origin=f'Lentynų skaičiuoklė: {family}, {row["length"]:g}×{row["width"]:g} mm; '
                       f'R={packaging:g}, S={cardboard:g}; pagal tipo formulę')


def cover_missing(registry, skus, settings=None):
    if settings is None:
        import calculator_settings
        settings = calculator_settings.load()
    for sku in skus:
        if key(sku) not in registry and re.search(r'SREW-SHELF|^(?:EU|US)-(?:PNL|PCL)-|CAB01-(?:PNL|PCL)\d', sku, re.I):
            registry[key(sku)] = dimensional_shelf_recipe(sku, settings) or dict(sku=sku, total=None, parts=[],
                origin='Panelių / lentynų skaičiuoklė',
                issue='Nėra vienareikšmės šio SKU skaičiuoklės eilutės; sena kaina nenaudojama')


def finish(rows, details, registry, settings):
    """Replace pack totals, remove duplicate rule traces, then mark up once."""
    details[:] = [d for d in details if key(d['top']) not in registry]
    for row in rows:
        recipe = registry.get(key(row['sku']))
        if recipe:
            total = recipe['total']
            row.update(cost=total, addons=(0.,)*6, adjustment=0., adjustment_rate=0.,
                       final=total, status='COMPLETE' if total is not None else 'BLOCKED',
                       issues=recipe['issue'], calculator=recipe['origin'])
            row['component_details'] = [dict(top=row['sku'], level_ii=row['sku'], level_ii_qty=1,
                component=label, component_qty=1, total_qty=1, unit_price=value, line_cost=value,
                status='OK', cost_source='CALCULATOR: '+recipe['origin']) for label,value in recipe['parts']]
        row['before_markup'] = row['final']
        row['markup_percent'] = settings['markup_percent']
        row['markup_amount'] = None if row['final'] is None else row['final']*settings['markup_percent']/100
        if row['final'] is not None:
            row['final'] += row['markup_amount']
    return rows
