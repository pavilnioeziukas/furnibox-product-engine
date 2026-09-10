from component_tariffs import apply_config, apply_rules, TARIFFS
from so_pricing_rules import empty_config, pricing_rules_from_config, PricingRule
from reform_so_line_prices import calculate_boms, Item, key

def test_corrected_table_and_migration_preserve_future_edits():
    doc=empty_config()
    doc['bom_categories']=[{'id':'old','name':'', 'source_category_id':'',
        'odoo_category':'Components/SHELF HARDWARE','storage':.1}]
    doc['bom_skus']=[{'sku':'RAIL','category_id':'old'}]
    doc=apply_config(doc)
    assert doc['bom_skus'][0]['category_id']=='COMPONENT-C10'
    assert sum(TARIFFS['C8'][1])==.08
    assert abs(sum(TARIFFS['C7'][1])-.22)<1e-9
    assert abs(sum(TARIFFS['C10'][1])-.22)<1e-9
    c=next(c for c in doc['bom_categories'] if c['id']=='COMPONENT-C10')
    c['storage']=.2
    assert apply_config(doc)==doc

def test_venrail_and_four_screws_per_unit():
    doc=apply_config(empty_config())
    rules={key('TOP'):PricingRule('TOP','7','SHELF HARDWARE','',.3,.05,.03,.02,.04),
           key('RAIL'):PricingRule('RAIL','','','Components/SHELF HARDWARE'),
           key('SCREW'):PricingRule('SCREW','','','Components / FASTENERS')}
    rules=apply_rules(rules,doc)
    rows,details=calculate_boms({'TOP':('ACCESSORIES',[Item('RAIL',1),Item('SCREW',4)])},
        {key('RAIL'):('Rail',6.55,'DIRECT PRICE'),key('SCREW'):('Screw',.03,'DIRECT PRICE')},
        rules,adjustment=-.07,authoritative_rule_tops={'TOP'})
    assert rows[0]['status']=='COMPLETE'
    assert abs(sum(rows[0]['addons'])-.70)<1e-9
    assert abs(rows[0]['final']-7.321)<1e-9
    screw=next(d for d in details if d['rule'].sku=='SCREW')
    assert abs(sum(screw['addons'])-.04)<1e-9
