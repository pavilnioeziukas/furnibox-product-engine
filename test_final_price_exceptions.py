import pytest
from final_price_exceptions import apply, PRICES, SOURCE
from pricing_table_view import steps


def test_all_pairs_fixed_after_markup_without_changing_costs():
    rows = [dict(sku='UNI-P-ACC01-HRD'+code+suffix, final=8.9,
                 cost=3.71, addons=(1, 0, 0, 0, 0, 0), status='COMPLETE')
            for code in PRICES for suffix in ('', '-A')]
    rows += [dict(sku='OTHER', final=8.9, status='COMPLETE'),
             dict(sku='UNI-P-ACC01-HRD022', final=None, status='BLOCKED')]
    apply(rows)
    apply(rows)
    for row in rows[:12]:
        code = row['sku'].removesuffix('-A')[-3:]
        assert row['final'] == PRICES[code]
        assert row['cost'] == 3.71
        assert row['before_exception'] + row['price_exception'] == pytest.approx(row['final'])
    assert rows[-2]['final'] == 8.9
    assert rows[-1]['final'] is None


def test_explanation_reconciles_exception_separately():
    match = dict(sku='UNI-P-ACC01-HRD022', position_type='BOM',
                 cost=2.29, addons=3.68, adjustment=-.2576, final=3.3874)
    data = {'SO LINE PRICES': [{'SKU': match['sku'],
            'Final Price Exception Amount': -2.325,
            'Final Price Exception Source': SOURCE}]}
    trace = steps(data, match, [])
    assert trace[-2]['rule'] == 'EXCEPTION'
    assert trace[-2]['amount'] == -2.325
    assert '-2,325' in trace[-1]['formula']
