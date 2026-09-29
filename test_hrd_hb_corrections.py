from copy import deepcopy

import pytest

from hrd_hb_corrections import apply, is_hb
from reform_so_line_prices import Item, calculate_boms, PricingBomMap
from so_pricing_rules import PricingRule


@pytest.mark.parametrize('sku', ['UNI-P-ACC01-HRD201HB', 'UNI-P-ACC01-HRD211HB',
                                'UNI-P-ACC01-HRD221HB', 'UNI-P-ACC01-HRD999HB-A'])
def test_all_hb_variants_remove_only_reviewed_components(sku):
    parts = [('CON7X50', 24), ('DOW8X30', 8), ('NAIL-1', 15),
             ('FPACK-UNI-P-ACC01-HRD029', 2), ('CAB_SPACER', 4), ('PRIZM-1', 8)]
    graph = {sku.casefold(): parts, 'other': [('NAIL-1', 15), ('PRIZM-1', 8)]}
    boms = PricingBomMap({sku: ('HARDWARE', [Item(s, q) for s, q in parts])})
    boms.empty_bom_issues = {'example': 'retained metadata'}
    original = deepcopy((boms, graph))
    updated, corrected, audit = apply(boms, graph)
    expected = [parts[0], parts[1], parts[3], parts[4]]
    assert corrected[sku.casefold()] == expected
    assert [(i.sku, i.qty) for i in updated[sku][1]] == expected
    assert corrected['other'] == graph['other']
    assert updated.empty_bom_issues == boms.empty_bom_issues
    assert (boms, graph) == original
    assert [(r['component'], r['before']) for r in audit['changes']] == [('NAIL-1', 15), ('PRIZM-1', 8)]
    again, again_graph, again_audit = apply(updated, corrected)
    assert (again, again_graph) == (updated, corrected)
    assert again_audit['changes'] == []


def test_nested_hb_price_uses_corrected_bom_even_with_old_direct_price():
    hb = 'UNI-P-ACC01-HRD201HB'
    parts = [('CON7X50', 24), ('DOW8X30', 8), ('NAIL-1', 15),
             ('FPACK-UNI-P-ACC01-HRD029', 2), ('CAB_SPACER', 4), ('PRIZM-1', 8)]
    graph = {hb.casefold(): parts, 'parent': [(hb, 2)]}
    boms = {hb: ('HARDWARE', [Item(s, q) for s, q in parts]),
            'PARENT': ('CABINET', [Item(hb, 2, list(parts))])}
    prices = {s.casefold(): (s, 1., 'TEST') for s, _ in parts}
    prices[hb.casefold()] = ('Old HB price', 999., 'OLD')
    # Removed components need no price and cannot block their HB parent.
    del prices['nail-1']
    del prices['prizm-1']
    rules = {s.casefold(): PricingRule(s, 'TEST', 'Test', '', 0, 0, 0, 0, 0, 0)
             for s in [hb, 'PARENT'] + [s for s, _ in parts]}
    rows, _ = calculate_boms(boms, prices, rules, graph=graph, adjustment=0)
    result = {r['sku']: r for r in rows}
    assert result[hb]['cost'] == pytest.approx(38)
    assert result['PARENT']['cost'] == pytest.approx(76)
    assert all(r['status'] == 'COMPLETE' for r in rows)


@pytest.mark.parametrize('sku', ['UNI-P-ACC01-HRD207D', 'UNI-P-ACC01-HRD201',
                                'EUB-C-CAB01-HBI001', 'UNI-P-ACC01-HRD201HB-OTHER'])
def test_other_families_do_not_match(sku):
    assert not is_hb(sku)
