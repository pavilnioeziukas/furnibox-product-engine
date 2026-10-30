import copy

import pytest

from test_reform_workspace import setup, sample
from test_reform_bom import export
from test_reform_excel import upload_book
from webapp.reform_workspace import db, pack, unpack, baseline
from webapp.reform_pivot import NAME


def saved(app):
    with app.app_context(), db() as conn:
        row = conn.execute('SELECT payload FROM drafts WHERE owner=?', ('paul',)).fetchone()
        return unpack(row[0])['target'] if row else baseline(conn)


def paste(book, rows):
    ws = book[NAME]
    ws.delete_rows(3, ws.max_row)
    for row in rows:
        ws.append(row)


def test_pivot_export_empty_and_roundtrip_unchanged(setup):
    app, client = setup
    book = export(client)
    assert book.sheetnames[0] == NAME and book.active.title == NAME
    assert list(book[NAME].values) == [('Sum of Part Qty.', None, None), ('SKU', 'MATERIAL_SKU', 'Total')]
    paste(book, [('CAB-01', 'HINGE-01', 4), ('CAB-01', 'PANEL-01', 2)])
    assert 'No changes detected' in upload_book(client, book).text
    assert client.get('/reform/excel/catalogue').status_code == 200


def test_pivot_changes_only_supplied_parent_and_preserves_source(setup):
    app, client = setup
    data = sample()
    data['products']['CAB-02'] = dict(data['products']['CAB-01'], sku='CAB-02')
    data['boms']['2'] = dict(copy.deepcopy(data['boms']['1']), id='2', sku='CAB-02')
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 3)])
    assert 'Excel changes saved' in upload_book(client, book).text
    target = saved(app)
    assert target['boms']['1']['components'] == [dict(data['boms']['1']['components'][0], quantity=3)]
    assert target['boms']['2'] == data['boms']['2']
    with app.app_context(), db() as conn:
        assert baseline(conn) == data
    assert 'Your draft has changed' in upload_book(client, book).text


def test_pivot_addition_zero_removal_and_numeric_codes(setup):
    app, client = setup
    data = sample()
    data['products']['12345'] = dict(data['products']['HINGE-01'], sku='12345')
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 2), ('CAB-01', 'HINGE-01', 0), ('CAB-01', 12345, '1,5')])
    assert 'Excel changes saved' in upload_book(client, book).text
    assert [(l['sku'], l['quantity']) for l in saved(app)['boms']['1']['components']] == [('PANEL-01', 2), ('12345', 1.5)]


@pytest.mark.parametrize('rows,error', [
    ([('CAB-01', 'MISSING', 1)], 'unknown or unavailable'),
    ([('MISSING', 'PANEL-01', 1)], 'exactly one existing BOM'),
    ([('CAB-01', 'PANEL-01', -1)], 'finite number'),
    ([('CAB-01', 'PANEL-01', 'NaN')], 'finite number'),
    ([('CAB-01', 'PANEL-01', '=1+2')], 'replace formulas'),
    ([('CAB-01', 'PANEL-01', 1), ('CAB-01', 'PANEL-01', 2)], 'duplicate'),
    ([('CAB-01', 'CAB-01', 1)], 'cycle'),
    ([('CAB-01', 'PANEL-01', 1), (None, 'HINGE-01', 1)], 'required on every row'),
    ([('Grand Total', None, 4)], 'required on every row'),
])
def test_invalid_pivot_is_atomic(setup, rows, error):
    app, client = setup
    book = export(client)
    paste(book, rows)
    assert error in upload_book(client, book).text
    assert saved(app)['boms'] == sample()['boms']


def test_pivot_rejects_mixed_edits(setup):
    app, client = setup
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 3)])
    book['BOM']['C2'] = 8
    assert 'leave the other editable sheets unchanged' in upload_book(client, book).text
    assert saved(app)['boms'] == sample()['boms']


@pytest.mark.parametrize('mode', ['locked', 'ambiguous', 'source'])
def test_pivot_source_and_bom_guards(setup, mode):
    app, client = setup
    data = sample()
    if mode == 'locked':
        data['boms']['1']['read_only'] = 'Protected'
    if mode == 'ambiguous':
        data['boms']['2'] = dict(copy.deepcopy(data['boms']['1']), id='2')
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 3)])
    if mode == 'source':
        data['captured_at'] = '2026-10-30T10:00:00+00:00'
        with app.app_context(), db() as conn:
            conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    page = upload_book(client, book).text
    assert ('read-only' if mode == 'locked' else 'exactly one existing BOM' if mode == 'ambiguous' else 'Source data has changed') in page
    assert saved(app)['boms'] == data['boms']


def test_pivot_quantities_per_unit_and_original_sheet_alias(setup):
    app, client = setup
    data = sample()
    data['boms']['1']['quantity'] = 2
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 1), ('CAB-01', 'HINGE-01', 2)])
    book[NAME].title = 'Product MBOMs - Pivot'
    assert 'No changes detected' in upload_book(client, book).text


def test_pivot_locked_unchanged_and_private_component_protection(setup):
    app, client = setup
    data = sample()
    data['boms']['1']['read_only'] = 'Protected'
    data['products']['APACK-PRIVATE'] = dict(data['products']['HINGE-01'], sku='APACK-PRIVATE')
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 2), ('CAB-01', 'HINGE-01', 4)])
    assert 'No changes detected' in upload_book(client, book).text
    paste(book, [('CAB-01', 'APACK-PRIVATE', 1)])
    assert 'unknown or unavailable' in upload_book(client, book).text
    assert saved(app) == data


def test_pivot_cannot_remove_hidden_internal_lines(setup):
    app, client = setup
    data = sample()
    data['products']['APACK-PRIVATE'] = dict(data['products']['HINGE-01'], sku='APACK-PRIVATE')
    data['boms']['1']['components'].append(dict(data['boms']['1']['components'][1], id='hidden', sku='APACK-PRIVATE'))
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(data),))
    book = export(client)
    paste(book, [('CAB-01', 'PANEL-01', 2), ('CAB-01', 'HINGE-01', 4)])
    assert 'read-only' in upload_book(client, book).text
    assert saved(app) == data
