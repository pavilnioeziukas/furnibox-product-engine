from __future__ import annotations

import unittest
import sys
from types import ModuleType


if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from bom_import_manufacture_v5 import (
    KIT,
    MANUFACTURE,
    add_generated_apack_boms,
    add_generated_cabinet_assembled_kits,
    prepare_manufacture_boms,
)
from shelf_pp import add_generated_shelf_pp_boms, build_shelf_pp_templates


class LegacyApackGenerationTests(unittest.TestCase):
    def test_legacy_gui_generator_exports_shelf_pp_with_packing_operation(self):
        shelf = "EUB-C-CAB01-SLF001"
        part = "EU-SREW-SHELF-163X564-WW"
        pp = f"{part}-PP"
        parents = {shelf}
        lines = {shelf: [
            {"component": part, "quantity": 1},
            {"component": "SLF-PINS-HRD-6", "quantity": 1},
        ]}
        levels = {shelf: 1}
        bom_types = {shelf: KIT}
        reform_products = {
            shelf: {"category": "CABINET SHELF", "is_parent": True},
            part: {"part_group": "SHELF PART", "is_component": True},
        }
        templates = build_shelf_pp_templates({
            pp: [
                {"component": part, "quantity": 1},
                {"component": "N9569A", "quantity": 0.4},
                {"component": "TERMO 90X48", "quantity": 2},
            ]
        })
        generated = add_generated_shelf_pp_boms(
            parents,
            lines,
            levels,
            bom_types,
            reform_products,
            templates,
            kit_type=KIT,
            manufacture_type=MANUFACTURE,
        )
        product_skus = {pp, part, "N9569A", "TERMO 90X48"}
        products = {
            sku: {
                "template_xmlid": f"tmpl.{index}",
                "product_xmlid": f"product.{index}",
                "display_sku": sku,
            }
            for index, sku in enumerate(sorted(product_skus), start=1)
        }
        operation_templates = {
            1: {
                "sku": pp,
                "subcategory": "SHELF PREPACK",
                "reference": "20260421_Shelf_prepack(reduced_packaging)",
                "operations": [{
                    "name": "Lentynų pakavimas",
                    "workcenter": "Pakuotojai",
                    "time_mode": "manual",
                    "time": 1,
                    "sequence": 0,
                }],
            }
        }

        ready, review, diagnostics = prepare_manufacture_boms(
            parents,
            lines,
            levels,
            bom_types,
            products,
            {pp: "SHELF PREPACK"},
            operation_templates,
            {"Pakuotojai"},
            set(),
            set(),
            generated,
            {},
            generated,
        )

        self.assertEqual(diagnostics, [])
        self.assertEqual(len(ready), 1)
        self.assertEqual(review[0]["sku"], pp)
        self.assertEqual(
            [(line["component"], line["quantity"]) for line in ready[0]["lines"]],
            [(part, 1), ("N9569A", 0.4), ("TERMO 90X48", 2.0)],
        )
        self.assertEqual(
            [operation["name"] for operation in ready[0]["operations"]],
            ["Lentynų pakavimas"],
        )

    def test_legacy_apack_parent_matches_assembled_cabinet_component(self):
        cabinet = "USB-C-CAB01-WAL045"
        fpack = "FPACK-US-C-CAB01-WAL045"
        apack = "APACK-USB-C-CAB01-WAL045-A"
        hrd = "USB-C-CAB01-WAL045-HRD001"

        parents = {cabinet, fpack}
        lines = {
            cabinet: [
                {"component": fpack, "quantity": 1},
                {"component": hrd, "quantity": 1},
            ],
            fpack: [
                {"component": "USB-C-CAB01-WAL045-BOT", "quantity": 1},
            ],
        }
        levels = {cabinet: 1, fpack: 2}
        bom_types = {cabinet: KIT, fpack: MANUFACTURE}
        reform_products = {
            cabinet: {
                "is_parent": True,
                "category": "CABINETS",
            },
        }

        generated_apacks = add_generated_apack_boms(
            parents,
            lines,
            levels,
            bom_types,
        )
        add_generated_cabinet_assembled_kits(
            parents,
            lines,
            levels,
            bom_types,
            reform_products,
            lines,
        )

        self.assertIn(apack, generated_apacks)
        self.assertIn(apack, parents)
        self.assertEqual(lines[apack], lines[fpack])
        self.assertEqual(
            lines[f"{cabinet}-A"][0]["component"],
            apack,
        )
        self.assertNotIn("APACK-US-C-CAB01-WAL045-A", parents)


if __name__ == "__main__":
    unittest.main()
