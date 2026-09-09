"""Apply the user's reviewed workbook as explicit, versioned pricing configuration."""
import copy
import json
from pathlib import Path

REVIEW_PATH = Path(__file__).parent / 'manifest' / 'pricing_review_corrections.json'


def apply_review(document, review=None, known_skus=()):
    from so_pricing_rules import ADDON_FIELDS, compose_bom_category_rule
    review = review or json.loads(REVIEW_PATH.read_text(encoding='utf-8'))
    document = copy.deepcopy(document)
    known = {str(r.get('sku', '')).casefold() for field in ('bom_skus', 'bom_products', 'non_bom_skus') for r in document.get(field, [])}
    known.update(str(sku).casefold() for sku in known_skus)
    applied = document.setdefault('review_corrections_applied', {})
    for change in review['corrections']:
        sku = change['sku']
        normalized = sku.casefold()
        if normalized not in known or applied.get(normalized) == review['version']:
            continue
        metadata = {k: change[k] for k in ('name', 'product_category') if k in change}
        if metadata:
            document.setdefault('product_metadata_overrides', {}).setdefault(normalized, {}).update(metadata)
        expression = change.get('expression')
        if change.get('position_type') == 'NON-BOM':
            matches = [r for r in document['non_bom_categories'] if str(r.get('name', '')).strip() == expression]
            if len(matches) != 1:
                raise ValueError(f'{sku}: reikia vienareikšmės NON-BOM kategorijos {expression}.')
            category = matches[0]
            document['bom_skus'] = [r for r in document['bom_skus'] if r['sku'].casefold() != normalized]
            document['bom_products'] = [r for r in document['bom_products'] if r['sku'].casefold() != normalized]
            document['non_bom_skus'] = [r for r in document['non_bom_skus'] if r['sku'].casefold() != normalized]
            document['non_bom_skus'].append({'sku':sku, 'name':change.get('name', change.get('existing_name', '')),
                'product_category':change.get('product_category', change.get('existing_product_category', '')),
                'category_id':category['id']})
            document.setdefault('pricing_type_overrides', {})[normalized] = 'NON-BOM'
        elif expression:
            rule = compose_bom_category_rule(sku, expression, document)
            category_id = 'REVIEW-BOM-' + expression
            if not any(r['id'] == category_id for r in document['bom_categories']):
                document['bom_categories'].append({'id':category_id, 'name':rule.category_name,
                    'source_category_id':expression, 'odoo_category':'', 'business_expression':expression,
                    **dict(zip(ADDON_FIELDS, rule.addons))})
            assignments = [r for r in document['bom_skus'] if r['sku'].casefold() == normalized]
            if assignments:
                assignments[0]['category_id'] = category_id
            else:
                document['bom_skus'].append({'sku':sku, 'category_id':category_id})
        applied[normalized] = review['version']
    # These categories remain linked to central tariffs, including future changes.
    for category in document['bom_categories']:
        expression = category.get('business_expression')
        if expression:
            rule = compose_bom_category_rule('', expression, document)
            category.update(name=rule.category_name, source_category_id=expression,
                            **dict(zip(ADDON_FIELDS, rule.addons)))
    return document


def explicit_bom_skus(document):
    categories = {r['id'] for r in document['bom_categories'] if r.get('business_expression')}
    return {r['sku'].casefold() for r in document['bom_skus'] if r['category_id'] in categories}


def remove_non_bom_edges(boms, graph, document):
    forced = {sku.casefold() for sku, kind in document.get('pricing_type_overrides', {}).items() if kind == 'NON-BOM'}
    return ({sku: value for sku, value in boms.items() if sku.casefold() not in forced},
            {sku: value for sku, value in graph.items() if sku.casefold() not in forced})


def apply_metadata(rows, document):
    for row in rows:
        metadata = document.get('product_metadata_overrides', {}).get(row['sku'].casefold(), {})
        if 'name' in metadata:
            row['name'] = metadata['name']
        if 'product_category' in metadata:
            row['category'] = metadata['product_category']
