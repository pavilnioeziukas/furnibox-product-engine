import sys
import types
import unittest
import tempfile
from pathlib import Path
from openpyxl import Workbook

if 'dotenv' not in sys.modules:
    stub = types.ModuleType('dotenv')
    stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules['dotenv'] = stub

from reform_so_line_prices import Item, apply_target_business_category_rules, calculate_boms, key, load_prices, exclude_bom_products_from_non_bom
from so_pricing_rules import PricingRule, empty_config
from cabinet_parts_price_v1 import pricing_audit_skus


def component(sku, group, **extra):
    return dict(sku=sku, part_group=group, is_component=True, has_bom=False, **extra)


class RemainingPricingRulesTests(unittest.TestCase):
    def test_shelf_pack_market_overrides_reference_and_component_hints(self):
        for market, expected, wrong in [('EU', '25.1', '26.1'), ('US', '26.1', '25.1')]:
            with self.subTest(market=market):
                sku = f'{market}-SREW-SHELF-CORNER-R_LEFT-963X564-BB-PP'
                dataset = {'products': [{'sku': sku, 'product_type': 'SHELF PREPACK',
                            'components': [{'sku': 'L0377', 'quantity': 1}]}]}
                rules, _ = apply_target_business_category_rules({}, dataset, empty_config(),
                              reference={key(sku): f'8+{wrong}'})
                self.assertEqual(rules[key(sku)].category_id, f'8+{expected}')

    def test_pricing_exclusions_do_not_remove_graph_dependencies(self):
        graph = {'fpack-wtp92-hrd001': [('050119021', 4)]}
        items = [('FPACK-WTP92-HRD001',), ('FPACK-WTP92-HRD001-A',),
                 ('050119021',), ('290.08.005',), ('M0450161SPUS',),
                 ('UNI-D-GEN99-DOC116',), ('EUB-D-GEN99-DOC001',)]
        self.assertEqual(exclude_bom_products_from_non_bom(items, graph), [('EUB-D-GEN99-DOC001',)])
        self.assertEqual(graph, {'fpack-wtp92-hrd001': [('050119021', 4)]})

    def test_confirmed_purchase_aliases_preserve_prices_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'prices.xlsx'
            wb = Workbook()
            ws = wb.active
            ws.title = 'Purchase prices'
            ws.append(['SKU', 'Name', '', '', '', '', '', 'Price'])
            ws.append(['43509846', 'Stabilizer', None, None, None, None, None, 2.5095])
            ws.append(['54559846', 'Dispensa', None, None, None, None, None, 48.9195])
            ws.append(['123', 'Unrelated', None, None, None, None, None, 5])
            wb.save(path)
            prices = load_prices(path)
            self.assertEqual(prices['0043509846'][1], 2.5095)
            self.assertEqual(prices['0054559846'][1], 48.9195)
            self.assertIn('43509846', prices['0043509846'][2])
            self.assertNotIn('050119021', prices)
            self.assertNotIn('00123', prices)
            ws.append(['50119021', 'Source without a usable price', None, None, None, None, None, 0])
            ws.append(['0043509846', 'Explicit price', None, None, None, None, None, 9])
            wb.save(path)
            prices = load_prices(path)
            self.assertEqual(prices['0043509846'][1], 9)
            self.assertNotIn('050119021', prices)
            wb.close()

    def test_target_leaf_categories_use_configured_rates(self):
        document = empty_config()
        next(r for r in document['bom_category_rates'] if r['code'] == '32')['storage'] = 1.25
        dataset = {'product_catalog': [component('0043509846', 'INTERIOR STORAGE'),
                   component('0054559846', 'INTERIOR STORAGE'), component('OL 0001', 'PAPER PRINT'),
                   component('UNI-D-DGN99-DOC103', 'PAPER PRINT')]}
        rules, authoritative = apply_target_business_category_rules({}, dataset, document, reference={})
        self.assertEqual(rules[key('0043509846')].addons, (0, 1.25, 1, 0, 0, 0))
        self.assertEqual(rules[key('0054559846')].category_id, '32')
        self.assertEqual(rules[key('OL 0001')].addons, (0, 0, 0, 0, 0, 0))
        self.assertEqual(rules[key('UNI-D-DGN99-DOC103')].category_id, '36')
        self.assertFalse(authoritative)

    def test_existing_rules_and_unknown_or_bom_classifications_are_preserved(self):
        existing = PricingRule('OL 0001', 'legacy', '', '', storage=.02)
        dataset = {'products': [{'sku': 'PARENT'}], 'product_catalog': [
            component('OL 0001', 'PAPER PRINT'), component('PARENT', 'INTERIOR STORAGE'),
            component('UNKNOWN', 'OTHER'),
            dict(sku='BOM', part_group='INTERIOR STORAGE', is_component=True, has_bom=True)]}
        rules, _ = apply_target_business_category_rules({key(existing.sku): existing}, dataset, empty_config(), reference={})
        self.assertEqual(rules, {key(existing.sku): existing})

    def test_direct_component_addon_per_unit_with_parent_expression(self):
        top = 'TOP'
        dataset = {'product_catalog': [component('0043509846', 'INTERIOR STORAGE')]}
        rules, _ = apply_target_business_category_rules({key(top): PricingRule(top, '', '', '', storage=4)}, dataset, empty_config(), reference={})
        args = ({top: ('INTERIOR STORAGE', [Item('0043509846', 4)])},
                {key('0043509846'): ('Part', 10, 'PURCHASE')}, rules)
        rows, _ = calculate_boms(*args, adjustment=0)
        self.assertEqual(rows[0]['cost'], 40)
        self.assertEqual(sum(rows[0]['addons']), 12)
        # This legacy category has no explicit Components classification.
        rows, _ = calculate_boms(*args, adjustment=0, authoritative_rule_tops={key(top)})
        self.assertEqual(sum(rows[0]['addons']), 4)
        # Classification must never replace a missing purchase price with zero.
        rows, _ = calculate_boms(args[0], {}, rules, adjustment=0)
        self.assertEqual(rows[0]['status'], 'BLOCKED')
        self.assertIn('Missing component price', rows[0]['issues'])

    def test_confirmed_invalid_orphans_are_ignored_without_hiding_bom_costs(self):
        invalid = {'489X478 (U732ST9)', '68X476 (U732ST9 16MM)'}
        other = {'EU-SREW-FILLER-100X200-WW', '100X200 (UNKNOWN)'}
        dimensions = {sku: (100, 200) for sku in invalid | other}
        self.assertEqual(pricing_audit_skus(dimensions, set()), other)
        self.assertEqual(pricing_audit_skus(dimensions, invalid), invalid | other)


if __name__ == '__main__':
    unittest.main()
