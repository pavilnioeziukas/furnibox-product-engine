"""Restore explicit ORDER LINE supplier identities and category assignments."""
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from so_pricing_rules import compose_bom_category_rule

# User confirmed that purchase prices under these finished product codes are
# for the main mechanism only. Extra screws/documents remain BOM costs.
PRIMARY_MECHANISMS = {
    'EUB-P-ACC02-MIS020': '0217029966', 'EUB-P-ACC02-MIS021': '0217129966',
    'EUB-P-ACC02-MIS022': '0217029846', 'EUB-P-ACC02-MIS023': '0217129846',
    'EUB-P-ACC05-MIS001': 'OL8675-60', 'EUB-P-ACC05-MIS002': 'OL8675-80',
    'EUB-P-ACC05-MIS003': 'OL8677-60', 'EUB-P-ACC05-MIS004': 'OL8677-80',
    'UNI-P-ACC02-MIS050': 'OL K11', 'UNI-P-ACC02-MIS051': 'OL K13',
}


def apply(prices, rules, dataset, document):
    prices, rules = dict(prices), dict(rules)
    reference = json.loads((Path(__file__).parent / 'manifest/order_line_pricing_reference.json').read_text(encoding='utf-8'))
    products = {p['sku'].strip().casefold():p for p in dataset.get('products', [])}
    aliases = defaultdict(list)
    authoritative = set()
    for row in reference['rows']:
        parent, supplier = row['sku'].casefold(), row['supplier_sku'].casefold()
        product = products.get(parent)
        if not product or not any(c['sku'].strip().casefold() == supplier for c in product.get('components', [])):
            continue
        if parent not in rules:
            rules[parent] = compose_bom_category_rule(row['sku'], row['category'], document)
            authoritative.add(parent)
        price = prices.get(parent)
        if price and price[1] > 0:
            aliases[supplier].append((row, price))
    for supplier, candidates in aliases.items():
        # Existing supplier purchase prices always win. Conflicting identities
        # are never averaged or resolved by taking the first occurrence.
        if supplier in prices or len({p[1] for _,p in candidates}) != 1:
            continue
        row, price = candidates[0]
        prices[supplier] = (price[0], price[1],
            f'{price[2]} / ORDER LINE row {row["row"]}: {row["sku"]} -> {row["supplier_sku"]}')

    for sku, supplier in PRIMARY_MECHANISMS.items():
        parent = products.get(sku.casefold())
        price = prices.get(sku.casefold())
        if parent and price and price[1] > 0 and any(
                c['sku'].casefold() == supplier.casefold() and c['quantity'] == 1
                for c in parent.get('components', [])):
            prices[supplier.casefold()] = (price[0], price[1],
                f'{price[2]} / USER CONFIRMED PRIMARY MECHANISM: {sku} -> {supplier}')

    # Same screw dimensions, head/finish and coating; only the delimiters in
    # the two source codes differ. Do not generalize to uncoated screws.
    source_code = 'med4.0*16 ap ral9005'
    target_code = 'med4.0x16_ap_ral9005'
    if target_code not in prices and source_code in prices:
        name, value, provenance = prices[source_code]
        prices[target_code] = (name, value, provenance+' / EXACT SCREW CODE '+source_code)

    # CATEGORY 6 explicitly names INTERIOR STORAGE. Preserve all existing
    # exact SKU assignments (including ORDER LINE category 11 exceptions).
    # Assembled -A variants have different operations and need their own rule.
    for k,p in products.items():
        if p.get('product_type') == 'INTERIOR STORAGE' and k not in rules and not k.endswith('-a'):
            rules[k] = compose_bom_category_rule(p['sku'], '6', document)
            authoritative.add(k)

    # All configured FRONT HARDWARE parents agree. Fill absent parent rules
    # only from this unanimous, original rule set; never from inferred rules.
    originals = [rules[k] for k,p in products.items()
                 if p.get('product_type') == 'FRONT HARDWARE' and k in rules]
    if len(originals) >= 2 and len({r.addons for r in originals}) == 1:
        for k,p in products.items():
            if p.get('product_type') == 'FRONT HARDWARE' and k not in rules:
                rules[k] = replace(originals[0], sku=p['sku'],
                    category_name='FRONT HARDWARE: sutampantys esamų produktų tarifai')
    return prices, rules, authoritative
