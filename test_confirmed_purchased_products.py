import unittest
import sys
import types

if "dotenv" not in sys.modules:
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv

from confirmed_purchased_products import (
    APPROVED_SUPPLIER_ALIASES,
    CONFIRMED_PURCHASED_NON_BOM_KEYS,
    CONFIRMED_PURCHASED_NON_BOM_SKUS,
    ODOO_ONLY_PURCHASED_SKUS,
    UNRELEASED_PURCHASED_VARIANTS,
    remove_confirmed_purchased_boms,
)
from reform_so_line_prices import calculate_confirmed_purchased_products
from so_pricing_rules import PricingRule


def _rule(sku):
    return PricingRule(sku, "6", "INTERIOR STORAGE", "INTERIOR STORAGE",
                       storage=4, packaging=1, other=.04)


def _dataset():
    return {"products": [
        {"sku": sku, "name": sku, "product_type": "INTERIOR STORAGE"}
        for sku in CONFIRMED_PURCHASED_NON_BOM_SKUS
    ]}


class ConfirmedPurchasedProductsTests(unittest.TestCase):
 def test_registry_has_exactly_72_unique_exact_skus_and_four_approved_aliases(self):
    self.assertEqual(len(CONFIRMED_PURCHASED_NON_BOM_SKUS), 72)
    self.assertEqual(len(CONFIRMED_PURCHASED_NON_BOM_KEYS), 72)
    self.assertEqual(len(APPROVED_SUPPLIER_ALIASES), 4)
    self.assertIn("uni-p-acc03-mis015", CONFIRMED_PURCHASED_NON_BOM_KEYS)
    self.assertIn("eub-p-acc01-hrd050-a", CONFIRMED_PURCHASED_NON_BOM_KEYS)
    self.assertIn("eub-p-acc01-hrd050", CONFIRMED_PURCHASED_NON_BOM_KEYS)
    self.assertIn("usb-p-acc01-hrd050", CONFIRMED_PURCHASED_NON_BOM_KEYS)


 def test_all_confirmed_products_ignore_present_or_archived_cached_boms(self):
    boms = {sku: ("OLD", [object()]) for sku in CONFIRMED_PURCHASED_NON_BOM_SKUS}
    boms["OTHER"] = ("KEEP", [object()])
    graph = {sku.casefold(): [("COMPONENT", 2)] for sku in CONFIRMED_PURCHASED_NON_BOM_SKUS}
    graph["other"] = [("KEEP", 1)]
    removed = remove_confirmed_purchased_boms(boms, graph)
    self.assertEqual(removed, CONFIRMED_PURCHASED_NON_BOM_KEYS)
    self.assertEqual(set(boms), {"OTHER"})
    self.assertEqual(graph, {"other": [("KEEP", 1)]})


 def test_every_product_is_non_bom_and_uses_one_traceable_direct_purchase_price(self):
    prices = {sku.casefold(): (sku, index + 1.0, f"PURCHASE SOURCE {index}")
              for index, sku in enumerate(CONFIRMED_PURCHASED_NON_BOM_SKUS)}
    rules = {sku.casefold(): _rule(sku) for sku in CONFIRMED_PURCHASED_NON_BOM_SKUS}
    rows = calculate_confirmed_purchased_products(prices, rules, _dataset())
    self.assertEqual(len(rows), 72)
    self.assertEqual({row["sku"].casefold() for row in rows}, CONFIRMED_PURCHASED_NON_BOM_KEYS)
    self.assertTrue(all(row["type"] == "NON-BOM" and row["status"] == "COMPLETE" for row in rows))
    self.assertTrue(all(row["cost_source"].startswith("PURCHASE SOURCE") for row in rows))
    self.assertTrue(all(abs(row["final"] - (row["cost"] + 5.04)) < 1e-9 for row in rows))


 def test_approved_supplier_identity_is_one_to_one_and_never_double_charged(self):
    for furnibox, supplier in APPROVED_SUPPLIER_ALIASES.items():
        with self.subTest(furnibox=furnibox):
            dataset = {"products": [{"sku": furnibox, "name": "Product", "product_type": "TEST"}]}
            rules = {furnibox.casefold(): _rule(furnibox)}
            prices = {supplier.casefold(): ("Supplier identity", 12.5, "LAST PURCHASE PRICE")}
            rows = calculate_confirmed_purchased_products(prices, rules, dataset)
            row = next(row for row in rows if row["sku"] == furnibox)
            self.assertEqual(row["cost"], 12.5)
            self.assertEqual(row["purchase_identity"], supplier.casefold())
            self.assertAlmostEqual(row["final"], 17.54)


 def test_missing_product_price_and_rule_are_separate_and_price_is_not_zero(self):
    rows = calculate_confirmed_purchased_products({}, {}, {"products": []})
    row = rows[0]
    self.assertIsNone(row["cost"])
    self.assertIsNone(row["final"])
    self.assertEqual(row["status"], "BLOCKED")
    self.assertIn("Product not found", row["issues"])
    self.assertIn("Missing purchase price", row["issues"])
    self.assertIn("Missing purchased-product pricing rule", row["issues"])

 def test_non_bom_product_is_found_in_full_product_catalog(self):
    sku = CONFIRMED_PURCHASED_NON_BOM_SKUS[0]
    dataset = {"products": [], "product_catalog": [
        {"sku": sku, "name_2": "Purchased product", "product_type": "INTERIOR STORAGE"}
    ]}
    prices = {sku.casefold(): (sku, 10.0, "LAST PURCHASE PRICE")}
    rules = {sku.casefold(): _rule(sku)}
    row = calculate_confirmed_purchased_products(prices, rules, dataset)[0]
    self.assertEqual(row["status"], "COMPLETE")
    self.assertEqual(row["name"], "Purchased product")
    self.assertNotIn("Product not found", row["issues"])

 def test_confirmed_odoo_only_drivers_do_not_require_reform_catalog(self):
    prices = {sku.casefold(): (sku, 12.0, "PURCHASE PRICE") for sku in ODOO_ONLY_PURCHASED_SKUS}
    rules = {sku.casefold(): _rule(sku) for sku in ODOO_ONLY_PURCHASED_SKUS}
    rows = calculate_confirmed_purchased_products(prices, rules, {"products": []})
    drivers = [row for row in rows if row["sku"] in ODOO_ONLY_PURCHASED_SKUS]
    self.assertEqual(len(drivers), 6)
    self.assertTrue(all(row["status"] == "COMPLETE" for row in drivers))
    self.assertTrue(all(row["type"] == "NON-BOM" for row in drivers))

 def test_unreleased_variants_are_not_invented_without_any_source(self):
    rows = calculate_confirmed_purchased_products({}, {}, {"products": []})
    self.assertFalse({row["sku"] for row in rows} & UNRELEASED_PURCHASED_VARIANTS)


 def test_unlisted_product_keeps_its_bom_unchanged(self):
    boms = {"OTHER": ("KEEP", [object()])}
    graph = {"other": [("COMPONENT", 3)]}
    self.assertEqual(remove_confirmed_purchased_boms(boms, graph), set())
    self.assertIn("OTHER", boms)
    self.assertEqual(graph["other"], [("COMPONENT", 3)])
