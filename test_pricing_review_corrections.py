from pathlib import Path
from copy import deepcopy
from so_pricing_rules import load_config, pricing_rules_from_config
from pricing_review_corrections import apply_review, explicit_bom_skus, remove_non_bom_edges, apply_metadata


def test_reviewed_names_categories_and_non_bom_are_applied_once():
    d = load_config(Path('manifest/so_pricing_rules.json'))
    rules = {r.sku: r for r in pricing_rules_from_config(d)}
    assert rules['UNI-P-ACC01-HRD019'].category_id == '7'
    assert abs(sum(rules['UNI-P-ACC01-HRD019'].addons)-.44) < 1e-9
    assert rules['UNI-P-ACC01-HRD027'].category_id == '9+30+33+34'
    assert abs(sum(rules['UNI-P-ACC01-HRD027'].addons)-1.73) < 1e-9
    assert rules['HRDW-ACC01-MIS101'].category_id == '9+34'
    assert 'UNI-P-ACC02-MIS952' not in rules
    assert any(r['sku']=='UNI-P-ACC02-MIS952' for r in d['non_bom_skus'])
    assert apply_review(d) == d
    edited = deepcopy(d)
    edited['product_metadata_overrides']['uni-p-acc01-hrd019']['name'] = 'Later user edit'
    assert apply_review(edited)['product_metadata_overrides']['uni-p-acc01-hrd019']['name'] == 'Later user edit'
    rows = [{'sku':'UNI-P-ACC01-HRD019','name':'Old'}, {'sku':'UNRELATED','name':'Keep'}]
    apply_metadata(rows,d)
    assert rows[0]['name'] == 'Hardware - Ventilation grill / Black'
    assert rows[1]['name'] == 'Keep'


def test_reviewed_categories_follow_central_rates():
    d = load_config(Path('manifest/so_pricing_rules.json'))
    next(r for r in d['bom_category_rates'] if r['code']=='7')['assembly'] = .5
    changed = apply_review(d)
    rules = {r.sku:r for r in pricing_rules_from_config(changed)}
    assert rules['UNI-P-ACC01-HRD019'].assembly == .5


def test_non_bom_removal_keeps_parent_reference_for_direct_price():
    d = load_config(Path('manifest/so_pricing_rules.json'))
    boms={'UNI-P-ACC02-MIS952':[], 'PARENT':['UNI-P-ACC02-MIS952']}
    graph={k.casefold():v for k,v in boms.items()}
    kept, edges=remove_non_bom_edges(boms,graph,d)
    assert 'UNI-P-ACC02-MIS952' not in kept
    assert edges['parent'] == ['UNI-P-ACC02-MIS952']
    assert 'uni-p-acc02-mis952' not in edges
    assert 'uni-p-acc01-hrd019' in explicit_bom_skus(d)


def test_generated_variants_are_reviewed_after_dataset_discovery():
    import json
    from so_pricing_rules import validate_config
    d = validate_config(json.loads(Path('manifest/so_pricing_rules.json').read_text(encoding='utf-8')))
    sku = 'EUB-P-ACC01-HRD105-A'
    d['bom_skus'] = [r for r in d['bom_skus'] if r['sku'] != sku]
    d['bom_products'] = [r for r in d['bom_products'] if r['sku'] != sku]
    applied = apply_review(d, known_skus=[sku])
    assert sku.casefold() in explicit_bom_skus(applied)
    assert applied['product_metadata_overrides'][sku.casefold()]['name'] == 'Hardware - Ventilation rail - W60 / White'
