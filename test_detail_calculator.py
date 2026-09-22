import copy
import csv
import io
import json
from dataclasses import asdict

import pytest
import calculator_settings
import detail_calculator as model
from cabinet_parts_price_parameters import DEFAULT_PARAMETERS
from price_calculators import calculate, source


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR', str(tmp_path))
    return model.load(tmp_path / 'copy.json', tmp_path / 'cabinet_parts_price_parameters.json')


def test_snapshot_is_independent_in_both_directions(config, tmp_path):
    original = copy.deepcopy(config)
    live = calculator_settings.load()
    live['panel']['work'] = 900
    calculator_settings.save(live)
    cabinet_path = tmp_path / 'cabinet_parts_price_parameters.json'
    cabinet_path.write_text(json.dumps(dict(asdict(DEFAULT_PARAMETERS), processing_rate_per_m2=777)))
    assert model.load(tmp_path / 'copy.json', cabinet_path) == original
    original_bytes = (tmp_path / 'calculator_settings.json').read_bytes(), cabinet_path.read_bytes()
    config['panel']['work'] = 51
    config['cabinet']['processing_rate_per_m2'] = 42
    model.save(tmp_path / 'copy.json', config)
    assert model.load(tmp_path / 'copy.json', cabinet_path)['panel']['work'] == 51
    assert original_bytes == ((tmp_path / 'calculator_settings.json').read_bytes(), cabinet_path.read_bytes())


def test_default_copy_matches_every_existing_source_row(config):
    for kind in ('shelf', 'panel'):
        for row in source(kind)['rows']:
            result = model.compute(kind, row, config)
            result.pop('edging')
            assert result == calculate(kind, row, config[kind])


@pytest.mark.parametrize('area,coefficient', [(.099999, 4), (.1, 2), (.199999, 2), (.2, .5)])
def test_editable_shelf_coefficients_and_boundaries(config, area, coefficient):
    config['area'].update(small=4, medium=2, large=.5)
    row = dict(source('shelf')['rows'][0], length=1000, width=area*1000, packaging=0, cardboard=0)
    result = model.compute('shelf', row, config)
    assert dict(result['parts'])['Ploto koeficientas'] == coefficient


@pytest.mark.parametrize('part_type,area,expected', [('STANDARD', .24, .24*(8.720350877192983+17.04)+1),
                                                   ('BACK', .24, .24*11+1), ('BACK', .5, .5*11)])
def test_cabinet_formula_markup_and_small_part_boundary(config, part_type, area, expected):
    config['cabinet']['furnix_markup_percent'] = 10
    row = dict(length=1000, width=area*1000, color='WW', part_type=part_type)
    assert model.compute('cabinet', row, config)['total'] == round(round(expected, 4) * 1.1, 4)


@pytest.mark.parametrize('group,key,value', [('area', 'small_limit', .3), ('area', 'medium', float('nan')),
    ('cabinet', 'processing_rate_per_m2', float('inf')), ('cabinet', 'output_decimals', 2.5),
    ('panel', 'work', -1)])
def test_invalid_parameters_cannot_overwrite_copy(config, tmp_path, group, key, value):
    path = tmp_path / 'copy.json'
    previous = path.read_bytes()
    config[group][key] = value
    with pytest.raises(ValueError):
        model.save(path, config)
    assert path.read_bytes() == previous


def test_pages_save_export_and_auth(monkeypatch, tmp_path):
    from test_webapp import load_webapp
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR', str(tmp_path / 'shared'))
    webapp = load_webapp(monkeypatch, tmp_path)
    client = webapp.app.test_client()
    for kind in ('shelf', 'panel', 'cabinet'):
        response = client.get('/detail-calculator/' + kind)
        assert response.status_code == 200
        assert 'Detalių skaičiuoklė' in response.get_data(as_text=True)
    paths = webapp.app.config['DETAIL_CALCULATOR_PATHS']
    config = model.load(paths['copy'], paths['cabinet'])
    with client.session_transaction() as state:
        token = state['detail_calculator_csrf']
    form = {'csrf_token': token, 'row': 0, 'action': 'save', **{'panel_'+k: v for k, v in config['panel'].items()}}
    form['panel_work'] = 29
    assert client.post('/detail-calculator/panel', data=form).status_code == 200
    assert model.load(paths['copy'], paths['cabinet'])['panel']['work'] == 29
    assert calculator_settings.load()['panel']['work'] != 29
    form['action'] = 'export'
    response = client.post('/detail-calculator/panel', data=form)
    exported = list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip('\ufeff')), delimiter=';'))
    assert len(exported) == len(source('panel')['rows']) + 1
    first = source('panel')['rows'][0]
    assert exported[0][8] == 'Briaunos sunaudojimas, m/vnt.'
    assert float(exported[1][8]) == pytest.approx(2 * (first['length'] + first['width']) / 1000 * 1.1)
    assert float(exported[1][3]) == pytest.approx(calculate('panel', first, dict(config['panel'], work=29))['total'])
    form['action'] = 'save'
    form['panel_work'] = 'nan'
    assert 'netinkama' in client.post('/detail-calculator/panel', data=form).get_data(as_text=True)
    assert model.load(paths['copy'], paths['cabinet'])['panel']['work'] == 29
    form['csrf_token'] = 'wrong'
    assert client.post('/detail-calculator/panel', data=form).status_code == 400
    monkeypatch.setattr(webapp, 'auth_enabled', lambda: True)
    assert client.get('/detail-calculator/panel').status_code == 302


def test_cabinet_catalog_and_shelf_save_are_isolated(monkeypatch, tmp_path):
    from test_webapp import load_webapp
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR', str(tmp_path / 'shared'))
    webapp = load_webapp(monkeypatch, tmp_path)
    paths = webapp.app.config['DETAIL_CALCULATOR_PATHS']
    paths['dataset'].write_text(json.dumps({'product_catalog': [
        {'sku': 'PART-600x400-WW', 'product_type': 'Cabinet Parts'},
        {'sku': 'BACK-1000x500-WW', 'product_type': 'Cabinet Parts'},
        {'sku': 'OTHER-600x400-WW', 'product_type': 'Hardware'},
    ]}))
    client = webapp.app.test_client()
    page = client.get('/detail-calculator/cabinet').get_data(as_text=True)
    assert 'PART-600x400-WW' in page and 'OTHER-600x400-WW' not in page
    config = model.load(paths['copy'], paths['cabinet'])
    with client.session_transaction() as state:
        token = state['detail_calculator_csrf']
    form = dict(row=-1, csrf_token=token, action='export',
                **{'cabinet_'+k: v for k,v in config['cabinet'].items()})
    response = client.post('/detail-calculator/cabinet', data=form)
    assert response.mimetype == 'text/csv'
    assert '7.1825' in response.get_data(as_text=True)
    form = dict(row=0, csrf_token=token, action='save',
                **{group+'_'+k: v for group in ('shelf', 'area') for k,v in config[group].items()})
    form['area_small'] = 4
    assert client.post('/detail-calculator/shelf', data=form).status_code == 200
    saved = model.load(paths['copy'], paths['cabinet'])
    assert saved['area']['small'] == 4
    assert saved['panel'] == config['panel'] and saved['cabinet'] == config['cabinet']
    original = client.get('/calculators/shelf').get_data(as_text=True)
    assert '8.3212' in original
    copied = client.get('/detail-calculator/shelf').get_data(as_text=True)
    assert '10.4616' in copied


def test_cabinet_uses_latest_pricing_catalog_when_approved_catalog_is_absent(monkeypatch, tmp_path):
    from test_webapp import load_webapp
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR', str(tmp_path / 'shared'))
    webapp = load_webapp(monkeypatch, tmp_path)
    dataset = tmp_path / 'Furnibox_Target_Dataset.json'
    dataset.write_text(json.dumps({'product_catalog': [
        {'sku': 'PART-600x400-WW', 'product_type': 'Cabinet Parts'}]}))
    monkeypatch.setattr(webapp, '_latest_job_for', lambda action: {
        'files': [{'name': dataset.name, 'path': str(dataset)}]})
    page = webapp.app.test_client().get('/detail-calculator/cabinet').get_data(as_text=True)
    assert 'PART-600x400-WW' in page
    assert 'Paskutinio kainodaros perskaičiavimo' in page
    assert 'Detalių: 1' in page
