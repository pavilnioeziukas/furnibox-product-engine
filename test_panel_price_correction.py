import copy
import csv
import io
import json

import pytest

import calculator_settings
import detail_calculator
from price_calculators import calculate, defaults, source
from unified_calculator_pricing import recipes


@pytest.mark.parametrize('correction', [0, 1.5, 3.75])
def test_every_panel_gets_one_fixed_correction(correction):
    rates = dict(defaults('panel'), price_correction=correction)
    registry = recipes(calculator_settings.validate({'panel': rates}))
    for row in source('panel')['rows']:
        area = row['length'] * row['width'] / 1_000_000
        before = row['sourceK'] + area * 3
        result = calculate('panel', row, rates)
        assert result['total'] == pytest.approx(before + correction)
        assert dict(result['parts'])['Kainos korekcija'] == correction
        assert dict(result['parts'])['Bazė K'] == pytest.approx(row['sourceK'])
        recipe = registry[row['sku'].casefold()]
        assert recipe['total'] == pytest.approx(before + correction)
        assert sum(value for _, value in recipe['parts']) == pytest.approx(recipe['total'])
        assert registry[row['detail'].casefold()]['total'] == pytest.approx(row['sourceK'])


def test_legacy_saved_settings_get_new_field_without_losing_rates(tmp_path, monkeypatch):
    monkeypatch.setenv('PRODUCT_ENGINE_SHARED_DATA_DIR', str(tmp_path))
    legacy = calculator_settings.validate({})
    del legacy['panel']['price_correction']
    legacy['panel']['work'] = 23.45
    calculator_settings.settings_path().write_text(json.dumps(legacy))
    loaded = calculator_settings.load()
    assert loaded['panel'] == dict(legacy['panel'], price_correction=1.5)
    assert loaded['shelf'] == legacy['shelf']
    loaded['panel']['price_correction'] = 0
    calculator_settings.save(loaded)
    assert calculator_settings.load()['panel']['price_correction'] == 0

    path = tmp_path / 'copy.json'
    config = detail_calculator.load(path, tmp_path / 'cabinet.json')
    del config['panel']['price_correction']
    path.write_text(json.dumps(config))
    migrated = detail_calculator.load(path, tmp_path / 'cabinet.json')
    assert migrated['panel'] == dict(config['panel'], price_correction=1.5)
    assert migrated['shelf'] == config['shelf']
    assert migrated['cabinet'] == config['cabinet']


@pytest.mark.parametrize('value', ['', -1, 'nan', 'inf'])
def test_invalid_correction_is_rejected(value):
    with pytest.raises(ValueError):
        calculate('panel', source('panel')['rows'][0], dict(defaults('panel'), price_correction=value))


def test_ui_saved_rates_and_export_use_correction(monkeypatch, tmp_path):
    from test_webapp import load_webapp
    webapp = load_webapp(monkeypatch, tmp_path)
    client = webapp.app.test_client()
    for route in ('/calculators/panel', '/calculators/settings', '/detail-calculator/panel'):
        page = client.get(route)
        assert page.status_code == 200
        assert 'Kainos korekcija, €/vnt.' in page.get_data(as_text=True)
    config = calculator_settings.load()
    previous = copy.deepcopy(config)
    form = {kind + '_' + key: value for kind in ('panel', 'shelf') for key, value in config[kind].items()}
    form.update(markup_percent=0, panel_price_correction=2.75)
    assert 'Išsaugota.' in client.post('/calculators/settings', data=form).get_data(as_text=True)
    config = calculator_settings.load()
    assert config['panel']['price_correction'] == 2.75
    assert config['shelf'] == previous['shelf']
    rates = {'rate_' + key: value for key, value in config['panel'].items()}
    response = client.post('/calculators/panel', data=dict(rates, row=0, action='export'))
    assert response.mimetype == 'text/csv'
    exported = list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip('\ufeff')), delimiter=';'))
    rows = source('panel')['rows']
    assert len(exported) == len(rows) + 1
    for exported_row, row in zip(exported[1:], rows):
        area = row['length'] * row['width'] / 1_000_000
        assert float(exported_row[3]) == pytest.approx(row['sourceK'] + area * 3 + 2.75)
