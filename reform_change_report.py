"""Human-readable views of saved version reports, including older reports."""
from collections import Counter, defaultdict

CATEGORIES = {
    'CABINET SHELF': 'Spintelių lentynos', 'SHELF PART': 'Lentynų detalės',
    'LED HARDWARE': 'LED furnitūra', 'SHELF HARDWARE': 'Lentynų furnitūra',
    'CABINET PART': 'Spintelių detalės', 'PAPER PRINT': 'Spausdinti dokumentai',
}
FIELDS = {
    'Kiekis': 'Kiekis', 'Group': 'Grupė', 'Unit Price': 'Vieneto kaina',
    'Product Catagory': 'Produkto kategorija', 'Product Category': 'Produkto kategorija',
    'SKU name 1': 'Pavadinimas', 'SKU name 2': 'Produkto aprašymas', 'SKU Name': 'Pavadinimas',
    'Real width [mm]': 'Plotis, mm', 'Real height [mm]': 'Aukštis, mm',
    'Real depth / thickness  [mm]': 'Gylis / storis, mm', 'Prod. cost [EUR]': 'Savikaina, EUR',
}


def describe(row):
    part, before, after = row['part'], row['before'], row['after']
    status = row['status']
    if status == 'Pridėtas komponentas' and row['field'] == 'Kiekis':
        return f'Pridėtas komponentas {part}, kiekis {after}.'
    if status == 'Pašalintas komponentas' and row['field'] == 'Kiekis':
        return f'Pašalintas komponentas {part}, ankstesnis kiekis {before}.'
    if status == 'Pakeistas kiekis':
        return f'Komponento {part} kiekis pakeistas iš {before} į {after}.'
    prefix = f'Komponentas {part}: ' if part else ''
    field = FIELDS.get(row['field'], row['field'])
    if not before:
        return f'{prefix}{field} papildyta reikšme „{after}“.'
    if not after:
        return f'{prefix}{field}: pašalinta reikšmė „{before}“.'
    return f'{prefix}{field}: „{before}“ → „{after}“.'


def present(report):
    """Rebuild summaries from the immutable diff, never from a newer source file."""
    grouped = defaultdict(list)
    for row in report['changes']:
        grouped[row['sku']].append(row)
    new_boms = {sku for sku, rows in grouped.items() if any(r['status'] == 'Naujas BOM' for r in rows)}
    removed_boms = {sku for sku, rows in grouped.items() if any(r['status'] == 'Pašalintas BOM' for r in rows)}
    component_groups = defaultdict(set)
    usages = defaultdict(set)
    for row in report['changes']:
        if row['part']:
            usages[row['part']].add(row['sku'])
            if row['field'] == 'Group':
                component_groups[row['part']].add(row['after'] or row['before'])

    def product(sku, removed=False):
        value = 'before' if removed else 'after'
        rows = grouped.get(sku, [])
        fields = {r['field']: r[value] for r in rows if not r['part'] and r['field']}
        name = ' — '.join(fields[k] for k in ('SKU name 1','SKU name 2') if fields.get(k))
        name = name or fields.get('SKU Name') or fields.get('Name') or ''
        category = fields.get('Product Category') or fields.get('Product Catagory')
        category = category or ' / '.join(sorted(component_groups[sku])) or 'Nenurodyta'
        parts = {}
        for row in rows:
            if not row['part']:
                continue
            part = parts.setdefault(row['part'], {'sku':row['part'], 'quantity':'', 'group':'', 'price':''})
            key = {'Kiekis':'quantity','Group':'group','Unit Price':'price'}.get(row['field'])
            if key:
                part[key] = row[value]
        return dict(sku=sku, name=name, category=CATEGORIES.get(category, category), source_category=category,
                    has_bom=sku in (removed_boms if removed else new_boms),
                    width=fields.get('Real width [mm]', ''), height=fields.get('Real height [mm]', ''),
                    depth=fields.get('Real depth / thickness  [mm]', fields.get('Real depth / thickness [mm]', '')),
                    parts=sorted(parts.values(), key=lambda p:p['sku']), usage=sorted(usages[sku]),
                    code_group='-'.join(sku.split('-')[:2]) if '-' in sku else sku)

    added = [product(sku) for sku in report['added_skus']]
    removed = [product(sku, True) for sku in report['removed_skus']]
    boms = [product(sku) for sku in sorted(new_boms)]
    changed = []
    for sku, rows in sorted(grouped.items()):
        if sku in new_boms or sku in removed_boms:
            continue
        narrative = [describe(r) for r in rows if r['status'] not in ('Pridėtas komponentas','Pašalintas komponentas') or r['field']=='Kiekis']
        changed.append(dict(sku=sku, descriptions=narrative, rows=rows))
    categories = Counter((p['category'], p['has_bom']) for p in added)
    bom_groups = Counter((p['category'], p['code_group']) for p in boms)
    with_bom = sum(p['has_bom'] for p in added)
    return dict(added=added, removed=removed, boms=boms, changed=changed,
                removed_boms=[product(sku, True) for sku in sorted(removed_boms)],
                with_bom=with_bom, without_bom=len(added)-with_bom,
                sku_groups=[dict(category=c, has_bom=b, count=n) for (c,b),n in sorted(categories.items())],
                bom_groups=[dict(category=c, code_group=g, count=n) for (c,g),n in sorted(bom_groups.items())],
                unchanged=report['counts'].get('Nepakitęs BOM',0))
