from __future__ import annotations

import sys
import types
import unittest


if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from bom_import_manufacture_v5 import (  # noqa: E402
    choose_apack_operation_template,
)


def operation(name: str) -> dict:
    return {
        "name": name,
        "workcenter": "TEST",
        "time_mode": "manual",
        "time": 1,
        "sequence": 0,
    }


class ApackOperationTemplateTests(unittest.TestCase):
    def test_invalid_exact_sku_does_not_hide_valid_family_template(self):
        templates = {
            1: {
                "sku": "APACK-US-C-CAB01-WAL024-A",
                "operations": [
                    operation("Surinkimas"),
                    operation("Pakavimas"),
                    operation("Papildomas pakavimas"),
                ],
            },
            2: {
                "sku": "APACK-US-C-CAB01-WAL023-A",
                "operations": [
                    operation("Surinkimas"),
                    operation("Pakavimas"),
                ],
            },
        }

        selected = choose_apack_operation_template(
            "APACK-US-C-CAB01-WAL024-A",
            "PREPACK CABINETS",
            templates,
        )

        self.assertEqual(selected["sku"], "APACK-US-C-CAB01-WAL023-A")
        self.assertEqual(
            [item["sequence"] for item in selected["operations"]],
            [100, 101],
        )

    def test_family_without_valid_operation_pair_is_blocked(self):
        templates = {
            1: {
                "sku": "APACK-US-C-CAB01-WAL024-A",
                "operations": [operation("Surinkimas")],
            },
        }

        with self.assertRaisesRegex(ValueError, "WAL/CAB01.*1 kandidatų"):
            choose_apack_operation_template(
                "APACK-US-C-CAB01-WAL024-A",
                "PREPACK CABINETS",
                templates,
            )


if __name__ == "__main__":
    unittest.main()
