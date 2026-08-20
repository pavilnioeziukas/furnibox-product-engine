from __future__ import annotations

import unittest
import sys
import types
from unittest.mock import patch

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from generate_full_validated_dataset import (
    add_full_target_metadata,
    apply_apack_hrd_target_rules,
)


class FullDatasetTargetRulesTests(unittest.TestCase):
    def test_full_catalog_keeps_non_bom_and_generated_products(self):
        reform_products = {
            "CABINET": {
                "is_parent": True,
                "is_component": False,
                "category": "CABINETS",
            },
            "HANDLE": {
                "is_parent": False,
                "is_component": True,
                "part_group": "ACCESSORIES",
            },
        }
        dataset = {
            "statistics": {},
            "products": [
                {"sku": "CABINET"},
                {
                    "sku": "CABINET-A",
                    "generated_from": "CABINET",
                    "product_type": "CABINETS (Assembled)",
                },
            ],
        }
        result = add_full_target_metadata(dataset, reform_products)
        catalog = {row["sku"]: row for row in result["product_catalog"]}
        self.assertEqual(set(catalog), {"CABINET", "CABINET-A", "HANDLE"})
        self.assertEqual(catalog["HANDLE"]["role"], "NON-BOM COMPONENT")
        self.assertFalse(catalog["HANDLE"]["has_bom"])
        self.assertEqual(catalog["CABINET-A"]["origin"], "FURNIBOX GENERATED")
        self.assertEqual(result["statistics"]["non_bom_product_count"], 1)
        self.assertEqual(len(result["transformation_rules"]), 4)

    def test_no_apack_is_a_valid_noop(self):
        dataset = {
            "environment": "production",
            "products": [{"sku": "SHELF-PP"}],
        }
        analysis = {
            "status": "PASS",
            "statistics": {"apack_total": 0},
            "results": [],
        }
        with patch(
            "generate_full_validated_dataset.analyze_all",
            return_value=analysis,
        ):
            transformed, actual_analysis, audit = (
                apply_apack_hrd_target_rules(dataset, object())
            )
        self.assertIs(transformed, dataset)
        self.assertEqual(actual_analysis, analysis)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["statistics"]["component_transfers"], 0)

    def test_apack_transfer_is_part_of_target_generation(self):
        def product(sku, components):
            return {
                "sku": sku,
                "product_type": "TEST",
                "bom_type": "MANUFACTURE",
                "level": 1,
                "source_sku": sku,
                "generated_from": "",
                "reform_category": "TEST",
                "content_hash": "old",
                "content_signature": "old",
                "components": [
                    {
                        "sku": component,
                        "quantity": quantity,
                        "parent_sku": sku,
                        "level": 1,
                    }
                    for component, quantity in components.items()
                ],
                "operations": [],
                "statistics": {},
            }

        apack = "APACK-EU-C-CAB01-BAS001-A"
        hrd_a = "HRD-EU-C-CAB01-BAS001-A"
        dataset = {
            "schema_version": "1.0",
            "dataset_id": "old",
            "batch_reference": "REFORM",
            "environment": "production",
            "created_at_utc": "2026-08-20T00:00:00+00:00",
            "source": {"file_name": "Reform BOM vXX.xlsx", "file_hash": "x"},
            "statistics": {},
            "products": [
                product(apack, {"DETAIL": 1}),
                product(hrd_a, {"HINGE": 4, "HANDLE": 1}),
            ],
        }
        analysis = {
            "status": "PASS",
            "statistics": {"apack_total": 1},
            "results": [{
                "status": "TRANSFERRED",
                "apack_sku": apack,
                "hrd_a_sku": hrd_a,
                "analog_match_method": "PROFILE_CONSENSUS",
                "transfer_plan": [{
                    "component_sku": "HINGE",
                    "quantity": 4,
                    "from_hrd_a": hrd_a,
                    "to_apack": apack,
                }],
            }],
        }
        with patch(
            "generate_full_validated_dataset.analyze_all",
            return_value=analysis,
        ):
            transformed, _, audit = apply_apack_hrd_target_rules(
                dataset, object()
            )
        products = {row["sku"]: row for row in transformed["products"]}
        apack_parts = {row["sku"] for row in products[apack]["components"]}
        hrd_parts = {row["sku"] for row in products[hrd_a]["components"]}
        self.assertEqual(apack_parts, {"DETAIL", "HINGE"})
        self.assertEqual(hrd_parts, {"HANDLE"})
        self.assertEqual(audit["statistics"]["component_transfers"], 1)


if __name__ == "__main__":
    unittest.main()
