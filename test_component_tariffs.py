from component_tariffs import apply_config, apply_rules, TARIFFS
from so_pricing_rules import empty_config, pricing_rules_from_config, PricingRule
from reform_so_line_prices import calculate_boms, Item, key

def test_fpack_named_component_never_gets_cabinet_packing_labour():
    from reform_so_line_prices import uses_fpack_labour
    part=PricingRule('FPACK-HARDWARE','C3','','Components / CABINET HARDWARE',0,.05)
    assert not uses_fpack_labour(part.sku,part)
    assert uses_fpack_labour('FPACK-CAB',PricingRule('FPACK-CAB','1','','PREPACK CABINETS'))
    rules={key(part.sku):part,key('TOP'):PricingRule('TOP','12','','',50)}
    rows,details=calculate_boms({'TOP':('',[Item(part.sku,2)])},
        {key(part.sku):('Hardware',1.15,'DIRECT PRICE')}, rules,
        authoritative_rule_tops={'TOP'})
    assert rows[0]['addons'][0]==50
    assert rows[0]['addons'][1]==.1

def test_nested_component_handling_multiplies_quantities_without_product_charges():
    rules={key('TOP'):PricingRule('TOP','12','','',50),
           key('INNER'):PricingRule('INNER','12','','PREPACK CABINETS',50),
           key('SCREW'):PricingRule('SCREW','C4','','Components / FASTENERS',0,.01)}
    rows,details=calculate_boms({'TOP':('',[Item('INNER',2),Item('SCREW',1)])},
        {key('SCREW'):('Screw',.1,'DIRECT PRICE')},rules,
        graph={'INNER':[('SCREW',3)]},component_cost_only_tops={'INNER'},
        authoritative_rule_tops={'TOP'})
    assert rows[0]['status']=='COMPLETE'
    assert rows[0]['addons'][0]==50
    assert abs(rows[0]['addons'][1]-.07)<1e-9
    assert abs(rows[0]['cost']-.7)<1e-9

def test_corrected_table_and_migration_preserve_future_edits():
    doc=empty_config()
    doc['bom_categories']=[{'id':'old','name':'', 'source_category_id':'',
        'odoo_category':'Components/SHELF HARDWARE','storage':.1}]
    doc['bom_skus']=[{'sku':'RAIL','category_id':'old'}]
    doc=apply_config(doc)
    assert doc['bom_skus'][0]['category_id']=='COMPONENT-C10'
    assert sum(TARIFFS['C8'][1])==.04
    assert abs(sum(TARIFFS['C7'][1])-.22)<1e-9
    assert abs(sum(TARIFFS['C10'][1])-.22)<1e-9
    c=next(c for c in doc['bom_categories'] if c['id']=='COMPONENT-C10')
    c['storage']=.2
    assert apply_config(doc)==doc

def test_c8_existing_production_migration_only_changes_c8():
    doc=apply_config(empty_config())
    del doc['component_c8_correction']
    c8=next(c for c in doc['bom_categories'] if c['id']=='COMPONENT-C8')
    c8['assembly']=.04
    c10=next(c for c in doc['bom_categories'] if c['id']=='COMPONENT-C10')
    c10['storage']=.19
    fixed=apply_config(doc)
    assert len(fixed['bom_categories'])==len(doc['bom_categories'])
    result=next(c for c in fixed['bom_categories'] if c['id']=='COMPONENT-C8')
    assert result['assembly']==0 and result['storage']==.04
    assert next(c for c in fixed['bom_categories'] if c['id']=='COMPONENT-C10')['storage']==.19
    assert apply_config(fixed)==fixed

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
