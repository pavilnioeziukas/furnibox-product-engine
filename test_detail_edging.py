import pytest
from detail_edging import infer_rule, quantity


@pytest.mark.parametrize('kind,sku,length,width,expected', [
    ('shelf','SHELF',344,600,2.0768),
    ('panel','PNL001',344,600,2.0768),
    ('cabinet','EU-SIDE-344X600-WW',344,600,2.0768),
    ('cabinet','EU-SIDEL-344X600-WW',344,600,2.0768),
    ('cabinet','EU-BOT-344X600-WW',344,600,1.32),
    ('cabinet','EU-TOP-600X344-WW',600,344,.7568),
    ('cabinet','EU-STIFF-100X565-WW',100,565,1.243),
    ('cabinet','EU-STIFF-565X100-WW',565,100,1.243),
    ('cabinet','EU-BACK-344X600-WW',344,600,0),
])
def test_confirmed_quantities(kind,sku,length,width,expected):
    result=quantity(kind,dict(sku=sku,length=length,width=width))
    assert result['material_m']==pytest.approx(expected)
    assert result['material_m']==pytest.approx(result['length_m']*1.1)


def test_unknown_is_not_silently_zero_or_perimeter():
    assert infer_rule('EU-STOP-100X565-WW')=='UNKNOWN'
    result=quantity('cabinet',dict(sku='PART',length=100,width=565))
    assert result['material_m'] is None
    assert infer_rule('EU-SIDE-TOP-100X565-WW')=='UNKNOWN'


def test_back_overrides_manual_rule_and_manual_width_is_respected():
    row=dict(length=100,width=565,part_type='BACK',edging_rule='PERIMETER')
    assert quantity('cabinet',row)['material_m']==0
    row.update(part_type='STANDARD',edging_rule='WIDTH')
    assert quantity('cabinet',row)['material_m']==pytest.approx(1.243)
