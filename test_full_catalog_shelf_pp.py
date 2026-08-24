from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from shelf_pp import build_shelf_pp_templates  # noqa: E402
from validated_dataset.full_catalog_builder import (  # noqa: E402
    build_full_validated_dataset,
)


class Assignment:
    bom_type = "MANUFACTURE"


class TypeCatalog:
    unresolved_count = 0

    def get(self, _sku):
        return Assignment()


class FullCatalogShelfPpTests(unittest.TestCase):
    def test_dataset_contains_furnibox_shelf_and_prepack_contract(self):
        shelf = "EUB-C-CAB01-SLF001"
        part = "EU-SREW-SHELF-563X564-NO"
        pp = f"{part}-PP"
        templates = build_shelf_pp_templates({
            "EU-SREW-SHELF-563X564-WW-PP": [
                {"component": "EU-SREW-SHELF-563X564-WW", "quantity": 1},
                {"component": "N9565A", "quantity": 0.4},
                {"component": "TERMO 90X48", "quantity": 1},
            ]
        })
        operations = {
            1: {
                "sku": "EU-SREW-SHELF-563X564-WW-PP",
                "category_path": "All / SHELF PREPACK",
                "subcategory": "SHELF PREPACK",
                "operations": [{
                    "name": "Lentynų pakavimas",
                    "workcenter": "Pakuotojai",
                    "time_mode": "manual",
                    "time": 1,
                    "sequence": 0,
                }],
            }
        }
        reform_products = {
            shelf: {"category": "CABINET SHELF", "is_parent": True},
            part: {"part_group": "SHELF PART", "is_component": True},
            "SLF-PINS-HRD-4": {"part_group": "ACCESSORIES", "is_component": True},
        }
        reform_lines = {shelf: [
            {"component": part, "quantity": 1},
            {"component": "SLF-PINS-HRD-4", "quantity": 1},
        ]}

        dataset = build_full_validated_dataset(
            environment="stage",
            batch_reference="TEST",
            source_file=Path("Reform BOM vXX.xlsx"),
            source_file_hash="hash",
            reform_products=reform_products,
            reform_lines=reform_lines,
            type_catalog=TypeCatalog(),
            operation_templates=operations,
            shelf_pp_templates=templates,
        )
        products = {product.sku: product for product in dataset.products}

        self.assertEqual(products[shelf].bom_type, "KIT")
        self.assertEqual(
            [component.sku for component in products[shelf].components],
            [pp, "SLF-PINS-HRD-4"],
        )
        self.assertEqual(products[pp].bom_type, "MANUFACTURE")
        self.assertEqual(products[pp].product_type, "SHELF PREPACK")
        self.assertEqual(
            [component.sku for component in products[pp].components],
            [part, "N9565A", "TERMO 90X48"],
        )
        self.assertEqual(
            [component.quantity for component in products[pp].components],
            [1, 0.4, 1],
        )
        self.assertEqual(
            [operation.name for operation in products[pp].operations],
            ["Lentynų pakavimas"],
        )


if __name__ == "__main__":
    unittest.main()
