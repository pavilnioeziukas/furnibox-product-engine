from __future__ import annotations

import unittest

from target_reconciliation import reconcile


PROFILE = {
    "category_external_id": "cat.target",
    "route_external_ids": ["route.target"],
    "product_type_field": "product",
    "invoice_policy": "delivery",
}


def catalog(sku, **values):
    return {"sku": sku, "role": "BOM PARENT", "product_type": "TEST",
            "expected": dict(PROFILE), **values}


def product(sku, **values):
    row = {"sku": sku, "name": sku, "active": True,
           "external_id": f"product.{sku.lower()}", **PROFILE}
    row.update(values)
    return row


def target_bom(sku, components=None, bom_type="KIT", operations=None):
    return {"sku": sku, "bom_type": bom_type,
            "components": components or [{"sku": "C", "quantity": 1}],
            "operations": operations or []}


def current_bom(sku, components=None, bom_type="phantom", operations=None, **values):
    return {"sku": sku, "active": True, "sequence": 0, "bom_type": bom_type,
            "components": components or [{"component_sku": "C", "quantity": 1}],
            "operations": operations or [], **values}


class ProductReconciliationTests(unittest.TestCase):
    def test_all_product_status_groups(self):
        dataset = {
            "dataset_id": "D", "product_catalog": [
                catalog("SAME"), catalog("NEW"), catalog("UPDATE"), catalog("DUP"),
            ], "products": [],
        }
        production = {"products": [
            product("SAME"), product("UPDATE", active=False), product("DUP"), product("DUP"),
        ], "boms": []}
        result = {row.sku: row for row in reconcile(dataset, production).products}
        self.assertEqual(result["SAME"].status, "PRODUCT UNCHANGED")
        self.assertEqual(result["NEW"].status, "CREATE PRODUCT")
        self.assertEqual(result["UPDATE"].status, "UPDATE PRODUCT")
        self.assertEqual(result["DUP"].status, "BLOCKED")

    def test_missing_unambiguous_import_profile_is_blocked(self):
        dataset = {"product_catalog": [{"sku": "X", "role": "BOM PARENT"}], "products": []}
        row = reconcile(dataset, {"products": [], "boms": []}).products[0]
        self.assertEqual(row.status, "BLOCKED")
        self.assertIn("etalonas", row.blocking_reasons[0])

    def test_existing_descriptive_name_is_preserved_but_empty_name_is_updated(self):
        dataset = {
            "product_catalog": [catalog("DESCRIPTIVE"), catalog("EMPTY")],
            "products": [],
        }
        production = {"products": [
            product("DESCRIPTIVE", name="Useful production description"),
            product("EMPTY", name=""),
        ], "boms": []}
        rows = {row.sku: row for row in reconcile(dataset, production).products}
        self.assertEqual(rows["DESCRIPTIVE"].status, "PRODUCT UNCHANGED")
        self.assertEqual(rows["EMPTY"].status, "UPDATE PRODUCT")
        self.assertEqual(rows["EMPTY"].changes[0]["field"], "name")


class BomReconciliationTests(unittest.TestCase):
    def run_case(self, target, current=None, extra_products=()):
        component_skus = {line["sku"] for line in target.get("components", [])}
        products = [product(target["sku"])] + [product(sku) for sku in component_skus]
        products += list(extra_products)
        dataset = {"product_catalog": [catalog(target["sku"])], "products": [target]}
        result = reconcile(dataset, {"products": products, "boms": current or []})
        return result.boms[0]

    def test_unchanged_and_create(self):
        target = target_bom("P")
        self.assertEqual(self.run_case(target, [current_bom("P")]).status, "BOM UNCHANGED")
        self.assertEqual(self.run_case(target).status, "CREATE BOM")

    def test_add_component(self):
        target = target_bom("P", [{"sku": "C", "quantity": 1}, {"sku": "D", "quantity": 2}])
        self.assertEqual(self.run_case(target, [current_bom("P")]).status, "ADD COMPONENT")

    def test_remove_component(self):
        target = target_bom("P")
        current = current_bom("P", [{"component_sku": "C", "quantity": 1},
                                     {"component_sku": "D", "quantity": 2}])
        self.assertEqual(self.run_case(target, [current], [product("D")]).status, "REMOVE COMPONENT")

    def test_change_quantity(self):
        target = target_bom("P", [{"sku": "C", "quantity": 2}])
        self.assertEqual(self.run_case(target, [current_bom("P")]).status, "CHANGE QUANTITY")

    def test_change_bom_type(self):
        target = target_bom("P", bom_type="MANUFACTURE")
        self.assertEqual(self.run_case(target, [current_bom("P")]).status, "CHANGE BOM TYPE")

    def test_update_operations_compares_name_center_time_and_sequence(self):
        target = target_bom("P", bom_type="MANUFACTURE", operations=[{
            "name": "Packing", "workcenter": "Packers", "time_mode": "manual",
            "time_minutes": 2, "sequence": 10,
        }])
        current = current_bom("P", bom_type="normal", operations=[{
            "name": "Packing", "workcenter": "Packers", "time_mode": "manual",
            "time_minutes": 3, "sequence": 10,
        }])
        self.assertEqual(self.run_case(target, [current]).status, "UPDATE OPERATIONS")

    def test_duplicate_sequence_zero_and_missing_component_are_blocked(self):
        target = target_bom("P", [{"sku": "MISSING", "quantity": 1}])
        dataset = {"product_catalog": [catalog("P")], "products": [target]}
        production = {"products": [product("P")],
                      "boms": [current_bom("P"), current_bom("P", id=2)]}
        row = reconcile(dataset, production).boms[0]
        self.assertEqual(row.status, "BLOCKED")
        self.assertEqual(len(row.blocking_reasons), 2)

    def test_component_created_by_same_target_plan_is_a_dependency_not_blocker(self):
        target = target_bom("P", [{"sku": "NEW-PP", "quantity": 1}])
        dataset = {
            "product_catalog": [catalog("P"), catalog("NEW-PP")],
            "products": [target],
        }
        production = {
            "products": [product("P")],
            "boms": [current_bom("P", [{"component_sku": "OLD", "quantity": 1}])],
        }
        row = reconcile(dataset, production).boms[0]
        self.assertNotEqual(row.status, "BLOCKED")
        self.assertIn("NEW-PP", row.warnings[0])

    def test_sequence_zero_blocker_contains_production_bom_ids(self):
        target = target_bom("P")
        row = self.run_case(target, [current_bom("P", id=7), current_bom("P", id=8)])
        self.assertEqual(row.status, "BLOCKED")
        self.assertEqual(row.changes[0]["production_bom_ids"], [7, 8])


class ShelfContractReconciliationTests(unittest.TestCase):
    def test_shelf_kit_and_shelf_pp_manufacture_are_compared_as_final_target(self):
        shelf, pp, part, rest, packaging, sticker = "SHELF", "PART-PP", "PART", "PINS", "BOX", "LABEL"
        packing = [{"name": "Packing", "workcenter": "Packers", "time_mode": "manual",
                    "time_minutes": 1, "sequence": 10}]
        dataset = {
            "product_catalog": [catalog(x) for x in (shelf, pp, part, rest, packaging, sticker)],
            "products": [
                target_bom(shelf, [{"sku": pp, "quantity": 1}, {"sku": rest, "quantity": 1}], "KIT"),
                target_bom(pp, [{"sku": part, "quantity": 1}, {"sku": packaging, "quantity": .4},
                                {"sku": sticker, "quantity": 2}], "MANUFACTURE", packing),
            ],
        }
        products = [product(x) for x in (shelf, pp, part, rest, packaging, sticker)]
        production = {"products": products, "boms": [
            current_bom(shelf, [{"component_sku": pp, "quantity": 1},
                                {"component_sku": rest, "quantity": 1}], "phantom"),
            current_bom(pp, [{"component_sku": part, "quantity": 1},
                             {"component_sku": packaging, "quantity": .4},
                             {"component_sku": sticker, "quantity": 2}], "normal", packing),
        ]}
        result = reconcile(dataset, production)
        self.assertEqual([row.status for row in result.boms], ["BOM UNCHANGED", "BOM UNCHANGED"])


if __name__ == "__main__":
    unittest.main()
