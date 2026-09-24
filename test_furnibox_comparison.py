import csv
import io
import pytest
from flask import Flask
import furnibox_comparison as model
from webapp.furnibox_comparison import comparison


def test_catalog_and_tamara_coefficients():
    rows=model.source()['rows']
    assert len(rows)==len({r['sku'] for r in rows})==1884
    assert sum(r['coefficient']==4 for r in rows)==48
    assert sum(r['coefficient']==2.2 for r in rows)==30
    assert not any('U732ST9' in r['sku'] for r in rows)


@pytest.mark.parametrize('sku,edge',[('EU-CUTBACK-600x400-WW',0),('EU-HALFBACK-600x400-WW',0),('EU-BOT-600x400-WW',2),('EU-STIFF-600x400-WW',2)])
def test_material_and_perimeter(sku,edge):
    row=dict(model.source()['rows'][2],sku=sku,length=600,width=400,color='WW',coefficient=2)
    v=model.calculate(row,model.source()['rates'])
    expected=.24*(2.85 if 'BACK' in sku else 8.72035)*1.1+edge*1.1*.2
    assert v['material']==pytest.approx(expected)
    assert v['calculated_purchase']==pytest.approx(expected*2)
    assert v['furnibox_coefficient']==pytest.approx(row['reform']/(expected*2))


def test_persistence_and_override_isolation(tmp_path):
    rows=model.source()['rows'];row=rows[2]
    rates,before=model.results(tmp_path)
    model.save_coefficient(tmp_path,row['sku'],'2,5')
    _,after=model.results(tmp_path)
    assert after[2]['coefficient']==2.5
    assert after[2]['calculated_purchase']==pytest.approx(before[2]['material']*2.5)
    assert before[3:]==after[3:]
    assert after[2]['purchase']==before[2]['purchase']
    assert after[2]['difference']==before[2]['difference']
    model.save_rates(tmp_path,dict(rates,BACK=3))
    _,updated=model.results(tmp_path)
    assert updated[2]['coefficient']==2.5
    assert updated[2]['material']>after[2]['material']


@pytest.mark.parametrize('value',['0','-1','nan','inf','abc'])
def test_reject_invalid_coefficient(tmp_path,value):
    with pytest.raises(ValueError):model.save_coefficient(tmp_path,model.source()['rows'][2]['sku'],value)
    assert not list(tmp_path.rglob('*.json'))


def test_aluminium_not_invented():
    value=model.calculate(model.source()['rows'][0],model.source()['rates'])
    assert value['material'] is None and value['calculated_purchase'] is None


def test_http_csrf_export_filter_and_saving(tmp_path):
    app=Flask(__name__);app.secret_key='test'
    app.config['DETAIL_CALCULATOR_PATHS']={'copy':tmp_path/'copy.json'}
    app.register_blueprint(comparison)
    client=app.test_client()
    assert client.post('/detail-comparison',data={'action':'coefficient'}).status_code==400
    with client.session_transaction() as session:token=session['comparison_csrf']
    sku=model.source()['rows'][2]['sku']
    response=client.post('/detail-comparison',data={'csrf_token':token,'action':'coefficient','sku':sku,'coefficient':'3'})
    assert response.status_code==302
    response=client.get('/detail-comparison',query_string={'q':sku,'export':'csv'})
    data=list(csv.reader(io.StringIO(response.data.decode('utf-8-sig')),delimiter=';'))
    assert len(data)==2 and data[1][0]==sku and data[1][6]=='3,000000'
    assert float(data[1][5].replace(',','.'))==pytest.approx(float(data[1][8].replace(',','.'))*3,abs=2e-6)


def test_full_page_navigation_and_auth(monkeypatch,tmp_path):
    from test_webapp import load_webapp
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR',str(tmp_path/'shared'))
    web=load_webapp(monkeypatch,tmp_path)
    client=web.app.test_client()
    response=client.get('/detail-comparison')
    assert response.status_code==200
    text=response.get_data(as_text=True)
    assert '1884 katalogo pozicijos' in text
    assert 'name="coefficient"' in text
    assert '/detail-comparison' in text
    assert client.get('/detail-comparison?page=19').status_code==200
    assert client.get('/detail-comparison?page=bad').status_code==400
    monkeypatch.setattr(web,'auth_enabled',lambda:True)
    assert client.get('/detail-comparison').status_code==302
    assert client.get('/detail-comparison?export=csv').status_code==302
