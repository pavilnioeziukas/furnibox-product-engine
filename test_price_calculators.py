import pytest
from price_calculators import calculate, defaults, source


def test_all_panel_source_bases():
    rows = source('panel')['rows']
    assert len(rows) == 81
    for row in rows:
        result = calculate('panel', row, defaults('panel'))
        assert dict(result['parts'])['Bazė K'] == pytest.approx(row['sourceK'])
    assert calculate('panel', rows[1], defaults('panel'))['total'] == pytest.approx(40.04052631578948)


def test_all_shelf_source_results_and_missing_packaging():
    rows = source('shelf')['rows']
    assert len(rows) == 297
    missing = 0
    for row in rows:
        result = calculate('shelf', row, defaults('shelf'))
        if row['packaging'] is None or row['cardboard'] is None:
            assert result['total'] is None
            missing += 1
        else:
            assert dict(result['parts'])['Medinė dalis U'] == pytest.approx(row['source_result'])
    assert missing == 66
    assert sum(r['source_multiplier'] == 3 for r in rows) == 3


@pytest.mark.parametrize('area,coefficient',[(.099999,3),(.1,1.5),(.199999,1.5),(.2,1)])
def test_shelf_area_boundaries(area, coefficient):
    row = dict(source('shelf')['rows'][0], length=1000, width=area*1000)
    result = calculate('shelf', row, defaults('shelf'))
    assert dict(result['parts'])['Ploto koeficientas'] == coefficient


def test_rates_recalculate_and_zero_packaging_is_valid():
    row = source('panel')['rows'][0]
    rates = defaults('panel')
    base = calculate('panel', row, rates)['total']
    rates['packaging'] += 1
    assert calculate('panel', row, rates)['total'] == pytest.approx(base+.48)
    shelf = dict(source('shelf')['rows'][-1], packaging=0, cardboard=0)
    assert calculate('shelf', shelf, defaults('shelf'))['total'] is not None


@pytest.mark.parametrize('value',['',-1,float('nan'),float('inf')])
def test_invalid_dimensions(value):
    with pytest.raises(ValueError):
        calculate('panel',dict(source('panel')['rows'][0], length=value),defaults('panel'))


def test_pages_post_export_and_auth(monkeypatch,tmp_path):
    from test_webapp import load_webapp
    webapp=load_webapp(monkeypatch,tmp_path)
    c=webapp.app.test_client()
    for kind,count in [('panel',81),('shelf',297)]:
        assert c.get('/calculators/'+kind).status_code == 200
        rates={'rate_'+k:v for k,v in defaults(kind).items()}
        post=dict(rates,row=0,length=2000,width=600,color='WW',kind='SREW-SHELF-PAPR',packaging=1,cardboard=.9)
        result=c.post('/calculators/'+kind,data=post)
        assert result.status_code == 200
        if kind=='panel':assert '40.0405' in result.get_data(as_text=True)
        export=c.post('/calculators/'+kind,data=dict(rates,row=0,action='export'))
        assert export.status_code == 200
        assert len(export.get_data(as_text=True).splitlines()) == count+1
        bad=c.post('/calculators/'+kind,data=dict(post,length='nan'))
        assert 'netinkama reikšmė' in bad.get_data(as_text=True)
    assert c.get('/calculators/panel?row=-1').status_code==400
    assert c.get('/calculators/unknown').status_code==404
    monkeypatch.setattr(webapp,'auth_enabled',lambda:True)
    assert c.get('/calculators/panel').status_code==302
    assert c.post('/calculators/shelf',data={}).status_code==302


def test_separate_workspaces_and_family_filters(monkeypatch,tmp_path):
    from test_webapp import load_webapp
    c=load_webapp(monkeypatch,tmp_path).app.test_client()
    home=c.get('/calculators/shelves').get_data(as_text=True)
    assert 'LED + ROD' in home and 'Panelių skaičiuoklė' in home
    for family in ('PAPR','FIX','FIXVEN','OVEN','CORNER'):
        response=c.get('/calculators/shelf?family='+family)
        assert response.status_code==200
        text=response.get_data(as_text=True)
        assert 'Tipas: '+family in text
        assert 'name="family" value="'+family+'"' in text
    for family,kind in [('LED','tik LED'),('ROD','ROD'),('LEDROD','LED+ROD')]:
        response=c.get('/shelf-workbook?view=led&family='+family)
        assert response.status_code==200
        assert 'Tipas: '+family in response.get_data(as_text=True)
    assert c.get('/calculators/panel?family=LED').status_code==400
    assert c.get('/calculators/shelf?family=INVALID').status_code==400
    assert c.get('/calculators/shelf?family=FIX&row=0').status_code==400
    rates={'rate_'+k:v for k,v in defaults('shelf').items()}
    first=next(i for i,r in enumerate(source('shelf')['rows'])if r['kind']=='SREW-SHELF-FIX')
    response=c.post('/calculators/shelf',data=dict(rates,family='FIX',row=first,action='export'))
    assert response.status_code==200
    assert len(response.get_data(as_text=True).splitlines())==49
