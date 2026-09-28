import unittest
from pathlib import Path

from final_price_exceptions import apply as apply_final_prices
from pricing_review_corrections import apply_review, remove_non_bom_edges
from reform_so_line_prices import calculate_non_bom, non_bom_from_config
from so_pricing_rules import load_config, validate_config


class Hrd022NonBomTests(unittest.TestCase):
    def test_migration_is_persistent_and_preserves_assembled_variant(self):
        document = load_config(Path('manifest/so_pricing_rules.json'))
        validate_config(document)
        self.assertFalse(any(r['sku'] == 'UNI-P-ACC01-HRD022' for r in document['bom_skus']))
        self.assertTrue(any(r['sku'] == 'UNI-P-ACC01-HRD022-A' for r in document['bom_skus']))
        self.assertEqual(sum(r['sku'] == 'UNI-P-ACC01-HRD022' for r in document['non_bom_skus']), 1)
        self.assertEqual(apply_review(document), document)
        boms, graph = remove_non_bom_edges(
            {'UNI-P-ACC01-HRD022': [], 'UNI-P-ACC01-HRD022-A': []},
            {'uni-p-acc01-hrd022': [], 'parent': [('UNI-P-ACC01-HRD022', 1)]}, document)
        self.assertNotIn('UNI-P-ACC01-HRD022', boms)
        self.assertIn('UNI-P-ACC01-HRD022-A', boms)
        self.assertNotIn('uni-p-acc01-hrd022', graph)
        self.assertIn('parent', graph)

    def test_direct_cost_and_approved_final_price_without_bom(self):
        document = load_config(Path('manifest/so_pricing_rules.json'))
        rules = [r for r in non_bom_from_config(document) if r[0] == 'UNI-P-ACC01-HRD022']
        rows = calculate_non_bom(rules, {'uni-p-acc01-hrd022': ('Leg set', 2.772, 'Tamara')})
        apply_final_prices(rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['type'], 'NON-BOM')
        self.assertEqual(rows[0]['status'], 'COMPLETE')
        self.assertEqual(rows[0]['cost'], 2.772)
        self.assertEqual(rows[0]['final'], 3.3874)
        missing = calculate_non_bom(rules, {})
        apply_final_prices(missing)
        self.assertEqual(missing[0]['status'], 'BLOCKED')
        self.assertIsNone(missing[0]['final'])
