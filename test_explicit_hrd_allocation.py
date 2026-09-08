import copy
import unittest
import sys
import types
if 'dotenv' not in sys.modules:
    stub = types.ModuleType('dotenv')
    stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules['dotenv'] = stub
from apack_hrd_allocation import apply_allocation
from reform_so_line_prices import component_cost_only_manufacture_products, resolve_component_cost

def product(sku, components):
    return {'sku': sku, 'bom_type': 'MANUFACTURE', 'components': [{'sku': c, 'quantity': q} for c,q in components.items()]}

class AllocationTests(unittest.TestCase):
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
