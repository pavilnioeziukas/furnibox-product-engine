from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path


if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from product_import_v10 import (  # noqa: E402
    build_rows,
    load_reference_from_odoo,
    shelf_pp_reference_profile,
    validate_dataset_source,
    validated_synthetic_shelf_pp,
)
from manifest.manifest_writer import calculate_file_hash  # noqa: E402


class ProductImportShelfPpTests(unittest.TestCase):
    def test_reference_is_loaded_directly_from_odoo(self):
        class FakeClient:
            def search_read_all(
                self, model, domain, fields, batch_size=1000, **kwargs
            ):
                if model == "product.product":
                    self.assert_context(kwargs)
                    return [{
                        "id": 1,
                        "default_code": "SHELF-PP",
                        "product_tmpl_id": [101, "Shelf PP"],
                        "active": True,
                    }]
                if model == "product.template":
                    self.assert_context(kwargs)
                    return [{
                        "id": 101,
                        "categ_id": [201, "Shelf PP"],
                        "route_ids": [301, 302],
                        "seller_ids": [401],
                    }]
                if model == "product.supplierinfo":
                    return [{
                        "id": 401,
                        "partner_id": [501, "Vendor"],
                        "sequence": 1,
                    }]
                if model == "ir.model.data":
                    wanted = domain[0][2]
                    values = {
                        "product.category": (201, "category_shelf_pp"),
                        "stock.route": [
                            (301, "route_mto"),
                            (302, "route_manufacture"),
                        ],
                        "res.partner": (501, "vendor"),
                    }[wanted]
                    if isinstance(values, tuple):
                        values = [values]
                    return [
                        {
                            "module": "test",
                            "name": name,
                            "res_id": record_id,
                        }
                        for record_id, name in values
                    ]
                return []

            @staticmethod
            def assert_context(kwargs):
                if kwargs.get("context") != {"active_test": False}:
                    raise AssertionError("Trūksta active_test=False")

        self.assertEqual(
            load_reference_from_odoo(FakeClient()),
            {
                "SHELF-PP": {
                    "category": "test.category_shelf_pp",
                    "routes": "test.route_mto,test.route_manufacture",
                    "vendor": "test.vendor",
                }
            },
        )

    def test_product_import_contains_generated_shelf_pp_card(self):
        part = "EU-SREW-SHELF-163X564-WW"
        pp = f"{part}-PP"
        ready, review, diagnostics, *counts = build_rows(
            set(),
            set(),
            {part: {
                "sku": part,
                "is_parent": False,
                "is_component": True,
                "part_group": "SHELF PART",
            }},
            {},
            None,
            None,
            {},
            {},
            {},
            {},
            {},
            {pp: {
                "sku": pp,
                "generated_from": part,
                "product_type": "SHELF PREPACK",
            }},
            {
                pp: {
                    "category": "category.shelf_pp",
                    "routes": "stock.mto,mrp.manufacture",
                    "vendor": "",
                }
            },
        )
        self.assertEqual(review, [])
        self.assertEqual(diagnostics, [])
        self.assertEqual(counts[-1], 1)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["Internal reference"], pp)
        self.assertEqual(ready[0]["categ_id"], "category.shelf_pp")
        self.assertEqual(
            ready[0]["route_ids/id"],
            "stock.mto,mrp.manufacture",
        )

    def test_stale_dataset_is_blocked_before_product_export(self):
        with tempfile.TemporaryDirectory() as directory:
            reform = Path(directory) / "Reform BOM v12.xlsx"
            reform.write_bytes(b"current")
            valid = {
                "source": {
                    "file_name": reform.name,
                    "file_hash": calculate_file_hash(reform),
                }
            }
            validate_dataset_source(valid, reform)
            stale = {
                "source": {
                    "file_name": "Reform BOM v11.xlsx",
                    "file_hash": "old",
                }
            }
            with self.assertRaisesRegex(ValueError, "žingsnį 6A"):
                validate_dataset_source(stale, reform)

    def test_only_validated_generated_shelf_prepack_is_selected(self):
        record = {"products": [
            {
                "sku": "EU-SREW-SHELF-563X564-NO-PP",
                "generated_from": "EU-SREW-SHELF-563X564-NO",
                "product_type": "SHELF PREPACK",
            },
            {
                "sku": "OTHER-PP",
                "generated_from": "OTHER",
                "product_type": "OTHER",
            },
        ]}
        self.assertEqual(
            set(validated_synthetic_shelf_pp(record)),
            {"EU-SREW-SHELF-563X564-NO-PP"},
        )

    def test_product_profile_is_inherited_only_when_unambiguous(self):
        target = "EU-SREW-SHELF-563X564-NO-PP"
        reference = {
            "EU-SREW-SHELF-563X564-WW-PP": {
                "category": "category.shelf_pp",
                "routes": "stock.mto,mrp.manufacture",
                "vendor": "",
            },
            "EU-SREW-SHELF-563X564-BB-PP": {
                "category": "category.shelf_pp",
                "routes": "stock.mto,mrp.manufacture",
                "vendor": "",
            },
        }
        self.assertEqual(
            shelf_pp_reference_profile(target, reference),
            {
                "category": "category.shelf_pp",
                "routes": "stock.mto,mrp.manufacture",
                "vendor": "",
            },
        )
        reference["EU-SREW-SHELF-563X564-BB-PP"]["routes"] = "purchase"
        self.assertIsNone(shelf_pp_reference_profile(target, reference))


if __name__ == "__main__":
    unittest.main()
