from openpyxl import Workbook
from pricing_table_view import snapshot, summary, steps, MISSING


def test_saved_weighted_addons_are_not_multiplied_twice():
    match = dict(sku='CAB', position_type='BOM', cost=10, addons=6, adjustment=-.42, final=15.58, status='CALCULATED')
    data = {'BOM CATEGORY BREAKDOWN': [{'Top SKU': 'CAB', 'Multiplier': 3, 'Assembly': 6,
             'Category ID': '', 'Category Name': '', 'Pricing Rule SKU': 'CHILD'}]}
    rows = steps(data, match, [])
    assembly = next(r for r in rows if r['title'] == 'Surinkimas')
    assert assembly['amount'] == 6
    assert assembly['formula'] == '2 × 3 = 6'
    assert assembly['source'] == MISSING and assembly['review']
    assert rows[-1]['amount'] == 15.58
    assert next(r for r in rows if r['title'] == 'Pakavimas')['amount'] is None


def test_summary_search_pagination_and_no_invented_zero():
    data = {'SO LINE PRICES': [{'SKU': f'A-{i}', 'Name': 'Cabinet'} for i in range(101)]}
    page = summary(data, 'cabinet', 2)
    assert page['total'] == 101 and len(page['rows']) == 50
    assert page['rows'][0]['SKU'] == 'A-50'
    assert 'Assembly' not in page['rows'][0]
    assert summary(data, 'missing')['total'] == 0
    assert summary(data, '', 999)['page'] == 3


def test_read_saved_values_and_cache_invalidation(tmp_path):
    path = tmp_path / 'prices.xlsx'
    book = Workbook()
    book.active.title = 'SO LINE PRICES'
    book.active.append(['SKU', 'Assembly'])
    book.active.append(['CAB', 0])
    book.save(path)
    assert summary(snapshot(path))['rows'][0]['Assembly'] == 0
    book.active.append(['CAB2', 5])
    book.save(path)
    assert summary(snapshot(path))['total'] == 2


def test_non_bom_parts_and_saved_correction():
    match = dict(sku='BUY', position_type='NON-BOM', cost=5, addons=.54, adjustment=0, final=5.54)
    data = {'NON-BOM RULES': [{'SKU': 'BUY', 'Pack Preparation': .2, 'Storage': .3, 'Bag': .02, 'Sticker': .02}],
            'SO LINE PRICES': [{'SKU': 'BUY', 'Adjustment Rate': 0}]}
    rows = steps(data, match, [])
    assert sum(r['amount'] for r in rows if r['purpose'] == 'Priedų dalis') == .54
    assert next(r for r in rows if r['title'] == 'Priedų korekcija')['formula'] == '0,54 × 0 = 0'
    assert rows[-1]['amount'] == 5.54
