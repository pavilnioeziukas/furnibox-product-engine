"""Read saved pricing evidence for tables; never use current tariffs to explain old runs."""
from functools import lru_cache
from pathlib import Path
from openpyxl import load_workbook
from current_reference_prices import COLUMN, current_price

ADDONS = [('Assembly', 'Surinkimas'), ('Storage', 'Sandėliavimas'),
          ('Packaging', 'Pakavimas'), ('Put on pallet', 'Padėjimas ant paletės'),
          ('Other', 'Kita'), ('Markup', 'Kategorijos antkainio priedas')]
MISSING = 'Nepriskirta — reikia papildyti'


def num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fmt(value):
    return f'{value:.6f}'.rstrip('0').rstrip('.').replace('.', ',') if num(value) else '—'


@lru_cache(maxsize=2)
def _snapshot(path, mtime, size):
    book = load_workbook(path, read_only=True, data_only=True)
    data = {}
    try:
        for name in ('SO LINE PRICES', 'PRICE RESULTS', 'BOM CATEGORY BREAKDOWN', 'NON-BOM RULES'):
            data[name] = []
            if name not in book.sheetnames:
                continue
            rows = book[name].iter_rows(values_only=True)
            headers = [str(v or '').strip() for v in next(rows, ())]
            data[name] = [dict(zip(headers, row)) for row in rows if any(v is not None for v in row)]
    finally:
        book.close()
    return data


def snapshot(path):
    if not path:
        return {}
    path = Path(path)
    stat = path.stat()
    return _snapshot(str(path), stat.st_mtime_ns, stat.st_size)


def category(row):
    code = str(row.get('Category ID') or '').strip()
    name = str(row.get('Category Name') or '').strip()
    return f'{code} · {name}' if code and name else MISSING


def summary(data, query='', page=1, limit=50):
    rows = data.get('SO LINE PRICES') or data.get('PRICE RESULTS') or []
    categories = {}
    for row in data.get('BOM CATEGORY BREAKDOWN', []):
        categories.setdefault(str(row.get('Top SKU', '')).casefold(), set()).add(category(row))
    for row in data.get('NON-BOM RULES', []):
        categories.setdefault(str(row.get('SKU', '')).casefold(), set()).add(str(row.get('Pricing Category') or MISSING))
    result = []
    for original in rows:
        if query.casefold() not in f"{original.get('SKU', '')} {original.get('Name', '')}".casefold():
            continue
        row = dict(original)
        if COLUMN not in row:
            row[COLUMN] = current_price(row.get('SKU'))
        assigned = categories.get(str(row.get('SKU', '')).casefold(), set())
        row['Tariff Category'] = '; '.join(sorted(assigned)) if assigned else 'Priskyrimo duomenų šiame rezultate nėra'
        result.append(row)
    total = len(result)
    pages = max(1, (total + limit - 1) // limit)
    page = min(max(1, page), pages)
    return dict(rows=result[(page-1)*limit:page*limit], total=total, page=page, pages=pages, query=query)


def steps(data, match, trace):
    if not match:
        return []
    sku = str(match['sku'])
    result = []
    def add(rule, title, target, source, formula, amount, purpose, note='', review=False):
        result.append(dict(number=len(result)+1, rule=rule, title=title, target=target,
                           source=source, formula=formula, amount=amount, purpose=purpose,
                           note=note, review=review))
    for row in trace:
        if row.get('Step Type') != 'MATERIAL':
            continue
        add('R001', 'Komponento savikaina', row.get('Input / Component / Rule'),
            row.get('Source Label') or row.get('Source'),
            f"{fmt(row.get('Unit Price'))} × {fmt(row.get('Qty / Multiplier'))} = {fmt(row.get('Amount'))}",
            row.get('Amount'), 'Savikainos dalis', row.get('Explanation', ''), row.get('Step Status') == 'BLOCKED')
    bom = match.get('position_type') == 'BOM'
    add('R002' if bom else 'R007', 'BOM komponentų suma' if bom else 'Pirkimo savikaina', sku,
        'Išsaugotas skaičiavimo rezultatas', fmt(match.get('cost')), match.get('cost'), 'Tarpinė suma',
        'Apibendrina savikainą; prie komponentų eilučių antrą kartą nepridedama.')
    details = [r for r in data.get('BOM CATEGORY BREAKDOWN', []) if str(r.get('Top SKU', '')).casefold() == sku.casefold()]
    for row in details:
        label = category(row)
        for key, title in ADDONS:
            amount = row.get(key)
            multiplier = row.get('Multiplier')
            formula = f'{fmt(amount)} = {fmt(amount)}'
            if num(amount) and num(multiplier) and multiplier != 0:
                formula = f'{fmt(amount / multiplier)} × {fmt(multiplier)} = {fmt(amount)}'
            # Breakdown amounts already include the multiplier. Never multiply twice.
            add('R003', title, f"{row.get('Pricing Rule SKU', sku)} · {row.get('Application Level', '')}",
                label, formula, amount, 'Priedų dalis',
                f"BOM CATEGORY BREAKDOWN · vieneto dalis parodyta iš išsaugotos sumos; suma jau apima daugiklį {fmt(multiplier)}. "
                + str(row.get('Calculation Basis') or ''), label == MISSING)
    non = next((r for r in data.get('NON-BOM RULES', []) if str(r.get('SKU', '')).casefold() == sku.casefold()), None)
    if not details and non and not bom:
        for key, title in [('Pack Preparation', 'Paruošimas'), ('Storage', 'Sandėliavimas'), ('Bag', 'Maišelis'), ('Sticker', 'Lipdukas')]:
            add('R007', title, sku, str(non.get('Pricing Category') or MISSING), fmt(non.get(key)), non.get(key), 'Priedų dalis')
    elif not details:
        for row in trace:
            if row.get('Step Type') == 'PRICING ADD-ON':
                add('R003/R004', 'Išsaugota priedų suma po korekcijos', sku,
                    row.get('Input / Component / Rule') or MISSING, fmt(row.get('Amount')),
                    row.get('Amount'), 'Priedų paaiškinimas', 'Atskirų tarifų išskaidymo šiame faile nėra. Suma nenaudojama pakartotinai.')
    add('R003' if bom else 'R007', 'Priedų suma prieš korekciją', sku, 'SO LINE PRICES',
        fmt(match.get('addons')), match.get('addons'), 'Tarpinė suma', 'Apibendrina priedus; antrą kartą nepridedama.')
    saved_row = next((r for r in data.get('SO LINE PRICES', []) if str(r.get('SKU', '')).casefold() == sku.casefold()), {})
    rate = saved_row.get('Adjustment Rate')
    correction_formula = (f"{fmt(match.get('addons'))} × {fmt(rate)} = {fmt(match.get('adjustment'))}"
                          if num(rate) else fmt(match.get('adjustment')))
    add('R004' if bom else 'R007', 'Priedų korekcija', sku, 'Išsaugota korekcija',
        correction_formula, match.get('adjustment'), 'Korekcija',
        'Rodoma konkretaus paleidimo suma, o ne dabartinis nustatymų procentas. Komponentų savikaina nekoreguojama.')
    markup = match.get('markup_amount')
    if num(markup) and markup != 0:
        add('—', 'Galutinis antkainis', sku, 'Išsaugotas galutinis antkainis', fmt(markup), markup, 'Antkainis')
    amounts = [match.get(k) for k in ('cost', 'addons', 'adjustment')]
    formula = ' + '.join(fmt(v) for v in amounts)
    if num(markup) and markup != 0:
        formula += ' + ' + fmt(markup)
    exception = saved_row.get('Final Price Exception Amount')
    exception_source = saved_row.get('Final Price Exception Source')
    if exception_source and num(exception):
        add('EXCEPTION', 'Patvirtinta galutinės kainos išimtis', sku,
            exception_source, fmt(exception), exception, 'Kainos išimtis',
            'Taikoma po visų priedų ir galutinio antkainio.')
        formula += ' + ' + fmt(exception)
    add('R002–R007', 'Galutinė SO kaina', sku, 'Išsaugotas skaičiavimo rezultatas',
        formula + ' = ' + fmt(match.get('final')), match.get('final'), 'Galutinis rezultatas',
        match.get('issues') or '', match.get('status') in ('BLOCKED', 'NEĮTRAUKTAS'))
    return result
