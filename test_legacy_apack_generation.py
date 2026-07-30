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
)


class LegacyApackGenerationTests(unittest.TestCase):
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
