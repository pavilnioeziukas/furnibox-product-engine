import pytest
import calculator_settings as settings
import unified_calculator_pricing as unified
from reform_so_line_prices import resolve_component_cost


def test_panel_and_pack_no_double_packaging():
    config = settings.validate({'markup_percent': 20})
    registry = unified.recipes(config)
    recipe = registry['eub-c-cab01-pnl002']
    assert recipe['total'] == pytest.approx(40.04052631578948)
    assert sum(v for _,v in recipe['parts']) == pytest.approx(recipe['total'])
    prices = unified.prepare({}, registry)
    resolved = resolve_component_cost('EUB-C-CAB01-PNL002', prices, {}, bom_cost_skus={'eub-c-cab01-pnl002'})
    assert resolved['cost'] == pytest.approx(recipe['total']) # no final markup in recursive cost
    rows = [dict(sku='EUB-C-CAB01-PNL002', final=123., cost=100., addons=(1.,)*6)]
    traces = [dict(top='EUB-C-CAB01-PNL002')]
    unified.finish(rows, traces, registry, config)
    assert rows[0]['final'] == pytest.approx(recipe['total']*1.2)
    assert rows[0]['adjustment'] == 0
    assert not traces


def test_shelf_pack_and_led_match_calculators():
    registry = unified.recipes(settings.validate({}))
    assert registry['eu-srew-shelf-163x564-ww']['total'] == pytest.approx(6.4212342)
    assert registry['eu-srew-shelf-163x564-ww-pp']['total'] == pytest.approx(8.3212342)
    led = registry['eu-srew-shelf-led-1163x340-bb-pp']
    assert led['total'] == pytest.approx(60.0734)
    assert sum(v for _,v in led['parts']) == pytest.approx(led['total'])


def test_conflicting_shelf_blocks_even_with_old_price_and_bom():
    config = settings.validate({})
    registry = unified.recipes(config)
    sku = 'eu-srew-shelf-fixven-564x533-ww'
    assert registry[sku]['total'] is None
    prices = unified.prepare({sku: ('old', 123., 'OLD')}, registry)
    assert resolve_component_cost(sku, prices, {}, bom_cost_skus={sku})['cost'] is None
    rows = [dict(sku=sku, final=123.)]
    unified.finish(rows, [], registry, config)
    assert rows[0]['final'] is None
    assert rows[0]['status'] == 'BLOCKED'


def test_saved_rates_are_reused_without_compounding(tmp_path, monkeypatch):
    monkeypatch.setenv('FURNIBOX_SHARED_DATA', str(tmp_path))
    config = settings.load()
    config['panel']['fixed'] += 2
    config['markup_percent'] = 20
    settings.save(config)
    loaded = settings.load()
    assert loaded == config
    for _ in range(2):
        rows = [dict(sku='other', final=100.)]
        unified.finish(rows, [], {}, loaded)
        assert rows[0]['final'] == 120
    assert unified.recipes(loaded)['eub-c-cab01-pnl002']['total'] == pytest.approx(42.04052631578948)


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf')])
def test_invalid_markup(value):
    with pytest.raises(ValueError):
        settings.validate({'markup_percent': value})


def test_settings_and_led_saved_for_next_so_run(tmp_path, monkeypatch):
    from test_webapp import load_webapp
    app = load_webapp(monkeypatch, tmp_path)
    client = app.app.test_client()
    config = settings.load()
    form = {kind+'_'+k:v for kind in ('panel', 'shelf') for k,v in config[kind].items()}
    form['markup_percent'] = 25
    assert client.post('/calculators/settings', data=form).status_code == 200
    assert settings.load()['markup_percent'] == 25
    assert settings.settings_path().parent == app.SHARED_DATA_DIR
    sku = 'EU-SREW-SHELF-LED-1163x340-BB'
    response = client.post('/shelf-workbook?view=led&item='+sku, data={**{'cost_'+str(i):i+1 for i in range(9)}, 'action':'save'})
    assert response.status_code == 200
    assert unified.recipes(settings.load())[sku.casefold()]['total'] == 45
    # Saving general rates must retain saved LED costs.
    client.post('/calculators/settings', data=form)
    assert unified.recipes(settings.load())[sku.casefold()]['total'] == 45


@pytest.mark.parametrize('sku,area,rate,coefficient', [
    ('EU-SREW-SHELF-CORNER-R_LEFT-963X564-WW-PP', .963*.564, 61, 1),
    ('EU-SREW-SHELF-CORNER-RW_RIGHT-963X340-BB-PP', .963*.340, 61, 1),
    ('US-SREW-SHELF-163 X339-WW-PP', .163*.339, 43.95, 3),
    ('US-SREW-SHELF-FIX-878X339-NO-PP', .878*.339, 45.29, 1),
])
def test_new_dimensions_use_existing_family_formula(sku, area, rate, coefficient):
    config = settings.validate({})
    recipe = unified.dimensional_shelf_recipe(sku, config)
    assert recipe['total'] == pytest.approx((area*rate-1.9)*coefficient+1.9)
    config['shelf']['SREW-SHELF-'+('CORNER' if 'CORNER' in sku else 'FIX' if '-FIX-' in sku else 'PAPR')] += 2
    assert unified.dimensional_shelf_recipe(sku, config)['total'] == pytest.approx(recipe['total']+area*2*coefficient)


@pytest.mark.parametrize('sku', ['EU-SREW-SHELF-LED-999X564-WW-PP', 'EU-SREW-SHELF-ROD-999X564-WW-PP', 'EU-SREW-SHELF-UNKNOWN-999X564-WW-PP'])
def test_no_generic_formula_for_unknown_or_led_breakdown(sku):
    assert unified.dimensional_shelf_recipe(sku, settings.validate({})) is None


def test_order_line_supplier_identity_preserves_existing_prices_and_bom():
    from order_line_pricing import apply
    from so_pricing_rules import load_config
    from pathlib import Path
    sku='EUB-P-ACC02-SLF200'; supplier='UTH1001'
    dataset={'products':[dict(sku=sku, product_type='INTERIOR STORAGE', components=[dict(sku=supplier, quantity=1)])]}
    original={sku.casefold(): ('Purchased shelf', 100., 'APPROVED PURCHASE PRICE ADJUSTMENT')}
    config=load_config(Path(__file__).parent/'manifest/so_pricing_rules.json')
    prices,rules,authoritative=apply(original,{},dataset,config)
    assert prices[supplier.casefold()][1]==100
    assert 'ORDER LINE row 2' in prices[supplier.casefold()][2]
    assert rules[sku.casefold()].category_id=='6'
    assert sku.casefold() in authoritative
    assert supplier.casefold() not in original
    prices2,_,_=apply({**original,supplier.casefold():('Existing supplier',90.,'LAST PURCHASE PRICE')},{},dataset,config)
    assert prices2[supplier.casefold()][1]==90


def test_confirmed_mechanism_adds_extra_components_once():
    import reform_so_line_prices as engine
    from order_line_pricing import apply
    from so_pricing_rules import load_config
    from pathlib import Path
    sku='EUB-P-ACC02-MIS020'
    children=[dict(sku='0217029966',quantity=1),dict(sku='MED4.5X50',quantity=8)]
    dataset={'products':[dict(sku=sku,product_type='INTERIOR STORAGE',components=children)]}
    config=load_config(Path(__file__).parent/'manifest/so_pricing_rules.json')
    prices,rules,authoritative=apply({sku.casefold():('Mechanism',100.,'APPROVED PURCHASE PRICE ADJUSTMENT'),
        'med4.5x50':('Screw',.025,'TEST')},{},dataset,config)
    boms={sku:('INTERIOR STORAGE',[engine.Item(c['sku'],c['quantity'])for c in children])}
    rows,_=engine.calculate_boms(boms,prices,rules,authoritative_rule_tops=authoritative)
    assert rows[0]['status']=='COMPLETE'
    assert rows[0]['cost']==pytest.approx(100.2)
    assert rows[0]['final']==pytest.approx(100.2+5.04*.93)
    assert next(x for x in rows[0]['component_details']if x['component']=='MED4.5X50')['total_qty']==8


@pytest.mark.parametrize('second_fee,expected', [(1.,True),(2.,False)])
def test_front_rules_require_unanimous_existing_prices(second_fee,expected):
    from order_line_pricing import apply
    from so_pricing_rules import PricingRule
    rules={'a':PricingRule('A','','','',assembly=1.),'b':PricingRule('B','','','',assembly=second_fee)}
    dataset={'products':[dict(sku=s,product_type='FRONT HARDWARE',components=[])for s in ('A','B','C')]}
    _,after,_=apply({},rules,dataset,{})
    assert ('c' in after)==expected
    assert after['a']==rules['a']
