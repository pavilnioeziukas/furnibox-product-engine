import pytest
from shelf_workbook import load, bom_results, legacy_results, led_results, resolve_price, evidence


def test_complete_import_and_quantity_weighted_bom():
    data=load()
    assert [len(data[k]) for k in ('sheets','purchase','bom','legacy','led')]==[6,659,1655,309,48]
    assert data['sheets'][-1]['rows']==[]
    results=bom_results()
    assert len(results)==224
    assert sum(len(x['lines'])for x in results)==1655
    for group in results:
        assert group['total']==pytest.approx(sum(x['qty']*x['source_unit']for x in group['lines']))
        assert group['unweighted']==pytest.approx(group['source_total'])
    assert results[0]['total']==pytest.approx(13.7304684)
    assert results[1]['total']==pytest.approx(10.58830194)
    assert '0.4' in results[1]['issues'][0]


def test_legacy_and_led_reconcile_without_double_quantity():
    assert all(abs(x['difference'])<1e-8 for x in legacy_results())
    assert all(abs(x['difference'])<1e-8 for x in led_results())
    # Old E cells are extended costs: the 4-piece hardware block must stay 0.7472.
    assert legacy_results()[0]['calculated']==pytest.approx(.7472)


def test_missing_conflicting_and_zero_prices():
    assert resolve_price([])[0]is None
    assert resolve_price([{'reform':'#N/A'}])[0]is None
    assert resolve_price([{'reform':1},{'reform':2}])[0]is None
    assert resolve_price([{'reform':0}])[0]==0
    broken=dict(load(),purchase=[])
    assert all(x['total']is None for x in bom_results(broken))


def test_cross_sheet_links():
    result=evidence('EU-SREW-SHELF-LED-1163x340-WW')
    assert all(result[k]for k in ('purchase','legacy','led','bom'))


def test_full_workbook_views_and_scenarios(monkeypatch,tmp_path):
    from test_webapp import load_webapp
    app=load_webapp(monkeypatch,tmp_path).app
    c=app.test_client()
    for view in ('bom','legacy','led','purchase','rates','source','related'):
        r=c.get('/shelf-workbook',query_string={'view':view,'q':'' if view!='related' else 'EU-SREW-SHELF-1163x340-WW'})
        assert r.status_code==200
    assert 'Lapas tuščias' in c.get('/shelf-workbook?view=source&sheet=5').get_data(as_text=True)
    assert 'VLOOKUP' in c.get('/shelf-workbook?view=source&sheet=4').get_data(as_text=True)
    for q in ('sheet=-1','sheet=invalid'):
        assert c.get('/shelf-workbook?view=source&'+q).status_code==400
    group=bom_results()[0];values={}
    for line in group['lines']:
        values['qty_'+str(line['row'])]=line['qty']*2
        values['unit_'+str(line['row'])]=line['unit']
    response=c.post('/shelf-workbook?view=bom&item='+group['sku'],data=values)
    assert '27.4609' in response.get_data(as_text=True)
    values['qty_'+str(group['lines'][0]['row'])]='nan'
    assert 'netinkama reikšmė' in c.post('/shelf-workbook?view=bom&item='+group['sku'],data=values).get_data(as_text=True)
    led=led_results()[0]
    response=c.post('/shelf-workbook?view=led&item='+led['sku'],data={'cost_'+str(i):1 for i in range(9)})
    assert 'Dalių suma: 9.0000' in response.get_data(as_text=True)
    assert led_results()[0]['total']==led['total']
