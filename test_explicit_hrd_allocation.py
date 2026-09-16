import copy
import json
import unittest
import sys
import types
from pathlib import Path
if 'dotenv' not in sys.modules:
    stub = types.ModuleType('dotenv')
    stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules['dotenv'] = stub
from apack_hrd_allocation import apply_allocation
from reform_so_line_prices import component_cost_only_manufacture_products, resolve_component_cost

def product(sku, components):
    return {'sku': sku, 'bom_type': 'MANUFACTURE', 'components': [{'sku': c, 'quantity': q} for c,q in components.items()]}

class AllocationTests(unittest.TestCase):
    def test_approved_family_pairs_have_identical_destinations(self):
        rules = json.loads((Path(__file__).parent / 'manifest/apack_hrd_allocation_rules.json').read_text(encoding='utf-8'))
        self.assertEqual(rules['BNF'], rules['BAS'])
        self.assertEqual(rules['BOH'], rules['BSK'])
        self.assertEqual(set(rules), {'BNF', 'BAS', 'UPP', 'WAL', 'TOP', 'COS', 'WAC', 'BOH', 'BSK', 'HCO', 'HIG', 'HBI'})

    def test_boh_moves_lam186330_to_apack_and_keeps_lam276308_in_hrd(self):
        a='APACK-EU-C-CAB01-BOH001-A'; h='HRD-BOH-A'; c='EU-C-CAB01-BOH001-A'
        ps = {
            a: product(a, {'BOARD': 1, 'LAM186330': 2}),
            h: product(h, {'LAM276308': 3, 'CAB_SPACER': 4, 'CON7X50': 5}),
            c: product(c, {a: 1, h: 1}),
        }
        changed, _ = apply_allocation(ps)
        self.assertEqual(changed, {a, h})
        self.assertEqual({x['sku']: x['quantity'] for x in ps[h]['components']}, {'LAM276308': 3, 'CAB_SPACER': 4})
        self.assertEqual({x['sku']: x['quantity'] for x in ps[a]['components']}, {'BOARD': 1, 'LAM186330': 2, 'CON7X50': 5})

    def fixture(self):
        a='APACK-EU-C-CAB01-HCO001-A';h='HRD209-A';c='EU-C-CAB01-HCO001-A'
        return {a:product(a,{'BOARD':1}), h:product(h,{'CON7X50':43,'CAB_SPACER':4}), c:product(c,{a:1,h:1})},a,h

    def test_explicit_and_idempotent(self):
        ps,a,h=self.fixture()
        changed,audit=apply_allocation(ps)
        self.assertEqual(changed,{a,h})
        self.assertEqual({c['sku']:c['quantity'] for c in ps[h]['components']},{'CAB_SPACER':4})
        self.assertIn({'sku':'CON7X50','quantity':43,'parent_sku':a,'level':1},ps[a]['components'])
        self.assertFalse(apply_allocation(ps)[0])

    def test_shared_hrd_copied_to_all_apacks(self):
        ps,a,h=self.fixture();b='APACK-EU-C-CAB02-HCO001-A'
        ps[b]=product(b,{'BOARD':2});ps['EU-C-CAB02-HCO001-A']=product('EU-C-CAB02-HCO001-A',{b:1,h:1})
        apply_allocation(ps)
        self.assertEqual(next(c['quantity'] for c in ps[b]['components'] if c['sku']=='CON7X50'),43)

    def test_uncovered_consumer_blocks_without_mutation(self):
        ps,a,h=self.fixture();ps['OTHER']=product('OTHER',{h:1});original=copy.deepcopy(ps)
        with self.assertRaisesRegex(ValueError,'quantities'):apply_allocation(ps)
        self.assertEqual(ps,original)

    def test_manufactured_hrd_ignores_direct_price(self):
        p=product('UNI-P-ACC01-HRD205',{'SCREW':3})
        forced=component_cost_only_manufacture_products({'products':[p]})
        result=resolve_component_cost(p['sku'],{'uni-p-acc01-hrd205':('',99,''),'screw':('',2,'purchase')},{'uni-p-acc01-hrd205':[('SCREW',3)]},bom_cost_skus=forced)
        self.assertEqual(result['cost'],6)
        self.assertEqual(result['leaves'][0]['sku'],'SCREW')

    def test_missing_child_price_blocks_hrd(self):
        p=product('HRD205',{'MISSING':1})
        result=resolve_component_cost('HRD205',{'hrd205':('',99,'')},{'hrd205':[('MISSING',1)]},bom_cost_skus=component_cost_only_manufacture_products({'products':[p]}))
        self.assertIsNone(result['cost'])

if __name__=='__main__':unittest.main()
