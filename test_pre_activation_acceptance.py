from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


# The production module imports project infrastructure at module-import time.
# Acceptance domain tests do not need a real Odoo connection.
config = types.ModuleType("config")
config.load_settings = lambda: None
sys.modules.setdefault("config", config)

odoo_client = types.ModuleType("odoo_client")
odoo_client.OdooClient = object
sys.modules.setdefault("odoo_client", odoo_client)

output_paths = types.ModuleType("output_paths")
output_paths.environment_output_dir = lambda base: Path(base) / "output"
sys.modules.setdefault("output_paths", output_paths)

bom_release = types.ModuleType("bom_release")
bom_release.load_latest_dataset_record = lambda path=None: ({}, Path(path or "."))
sys.modules.setdefault("bom_release", bom_release)

from pre_activation_acceptance import Acceptance  # noqa: E402


def product(
    sku: str,
    category: str,
    bom_type: str = "",
    components=None,
    operations=None,
):
    row = {
        "sku": sku,
        "category": category,
        "bom_type": bom_type,
        "components": components or [],
    }
    if operations is not None:
        row["operations"] = operations
    elif bom_type == "MANUFACTURE":
        if sku.startswith("APACK-") or category == "APACK":
            names = ["Surinkimas", "Pakavimas"]
        elif sku.endswith("-A") and "HRD" in sku:
            names = ["Komplektavimas"]
        else:
            names = ["Pakavimas"]
        row["operations"] = [{"name": name} for name in names]
    return row


def component(sku: str, quantity: float = 1):
    return {"sku": sku, "quantity": quantity}


class AcceptanceTests(unittest.TestCase):
    def test_hardware_picking_is_recognized_as_kitting(self):
        dataset = {
            "products": [
                product(
                    "UNI-P-ACC01-HRD201D",
                    "CABINET HARDWARE",
                    "MANUFACTURE",
                    [component("PART-1")],
                    operations=[
                        {
                            "name": "Furnitūros atrinkimas",
                            "workcenter": "Furnitūros komplektų gamyba",
                        }
                    ],
                ),
            ]
        }

        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())

        missing = [
            issue
            for issue in acceptance.issues
            if issue.test_code == "MISSING_REQUIRED_OPERATION"
        ]
        self.assertEqual([], missing)

    def test_cabinet_hardware_uses_kitting_despite_fpack_prefix(self):
        dataset = {
            "products": [
                product(
                    "FPACK-WTP92-HRD001",
                    "CABINET HARDWARE",
                    "MANUFACTURE",
                    [component("PART-1")],
                    operations=[{"name": "HRD(F) komplektavimas"}],
                ),
                product(
                    "FPACK-WTP92-HRD001-A",
                    "CABINET HARDWARE",
                    "MANUFACTURE",
                    [component("PART-1")],
                    operations=[{"name": "Komplektavimas"}],
                ),
            ]
        }

        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())

        missing = [
            issue
            for issue in acceptance.issues
            if issue.test_code == "MISSING_REQUIRED_OPERATION"
        ]
        self.assertEqual([], missing)

    def test_manufacture_without_operations_fails(self):
        dataset = {
            "products": [
                product(
                    "FPACK-01",
                    "FPACK",
                    "MANUFACTURE",
                    [component("PART-01")],
                    operations=[],
                ),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        codes = {issue.test_code for issue in acceptance.issues}
        self.assertIn("MISSING_OPERATIONS", codes)
        self.assertIn("MISSING_REQUIRED_OPERATION", codes)

    def test_cabinet_shelf_manufacture_without_operations_passes(self):
        dataset = {
            "products": [
                product(
                    "EUB-C-CAB03-SLF901",
                    "CABINET SHELF",
                    "MANUFACTURE",
                    [component("PART-01")],
                    operations=[],
                ),
                product("PART-01", "CABINET PART"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        operation_codes = {
            issue.test_code
            for issue in acceptance.issues
            if "OPERATION" in issue.test_code
        }
        self.assertEqual(operation_codes, set())

    def test_full_production_operation_names_are_recognized(self):
        dataset = {
            "products": [
                product(
                    "APACK-EU-C-CAB01-BAS001-A",
                    "APACK",
                    "MANUFACTURE",
                    [component("PART-01")],
                    operations=[
                        {"name": "Spintelės surinkimas"},
                        {"name": "Spintelės pakavimas"},
                    ],
                ),
                product("PART-01", "CABINET PART"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        operation_issues = [
            issue
            for issue in acceptance.issues
            if issue.test_code == "MISSING_REQUIRED_OPERATION"
        ]
        self.assertEqual(operation_issues, [])

    def test_valid_cabinet_release_passes(self):
        dataset = {
            "products": [
                product("CAB01", "CABINETS", "KIT", [
                    component("FPACK-01"), component("HRD-01"),
                ]),
                product("CAB01-A", "CABINETS", "KIT", [
                    component("APACK-01"), component("HRD-01-A"),
                ]),
                product("FPACK-01", "FPACK", "MANUFACTURE", [
                    component("PART-01", 2),
                ]),
                product("APACK-01", "APACK", "MANUFACTURE", [
                    component("PART-01", 2),
                ]),
                product("HRD-01", "HRD", "MANUFACTURE", [
                    component("SCREW-01", 4),
                ]),
                product("HRD-01-A", "HRD-A", "MANUFACTURE", [
                    component("SCREW-01", 2),
                ]),
                product("PART-01", "CABINET PART"),
                product("SCREW-01", "HARDWARE"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        self.assertEqual(acceptance.issues, [])

    def test_reverse_cabinet_pair_is_required(self):
        dataset = {"products": [product("CAB01-A", "CABINETS", "KIT")]}
        acceptance = Acceptance(dataset)
        structures = acceptance.dataset_structures()
        acceptance.run(structures)
        codes = {issue.test_code for issue in acceptance.issues}
        self.assertIn("CABINET_PAIR", codes)

    def test_duplicate_components_are_not_hidden_by_aggregation(self):
        dataset = {
            "products": [
                product(
                    "FPACK-01",
                    "FPACK",
                    "MANUFACTURE",
                    [component("PART-01"), component("PART-01"), component("UNKNOWN")],
                ),
                product("PART-01", "CABINET PART"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        codes = {issue.test_code for issue in acceptance.issues}
        self.assertIn("DUPLICATE_COMPONENT", codes)
        self.assertNotIn("MISSING_COMPONENT", codes)
        self.assertEqual(acceptance.metrics["missing_components"], 0)

    def test_leaf_components_need_not_be_bom_parents(self):
        dataset = {
            "products": [
                product(
                    "FPACK-01",
                    "FPACK",
                    "MANUFACTURE",
                    [component("RAW-BOARD"), component("EDGE-BAND")],
                ),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        self.assertNotIn(
            "MISSING_COMPONENT",
            {issue.test_code for issue in acceptance.issues},
        )

    def test_invalid_quantity_and_empty_bom_fail(self):
        dataset = {
            "products": [
                product("EMPTY", "FPACK", "MANUFACTURE"),
                product("INVALID", "FPACK", "MANUFACTURE", [
                    component("PART-01", 0),
                ]),
                product("PART-01", "CABINET PART"),
                product("PART-02", "CABINET PART"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        codes = {issue.test_code for issue in acceptance.issues}
        self.assertIn("EMPTY_BOM", codes)
        self.assertIn("INVALID_QTY", codes)
        self.assertIn("ORPHAN_CABINET_PART", codes)

    def test_hrd_a_must_be_subset_of_hrd(self):
        dataset = {
            "products": [
                product("CAB01", "CABINETS", "KIT", [
                    component("FPACK-01"), component("HRD-01"),
                ]),
                product("CAB01-A", "CABINETS", "KIT", [
                    component("APACK-01"), component("HRD-01-A"),
                ]),
                product("FPACK-01", "FPACK", "MANUFACTURE", [
                    component("PART-01"),
                ]),
                product("APACK-01", "APACK", "MANUFACTURE", [
                    component("PART-01"),
                ]),
                product("HRD-01", "HRD", "MANUFACTURE", [
                    component("SCREW-01", 1),
                ]),
                product("HRD-01-A", "HRD-A", "MANUFACTURE", [
                    component("SCREW-01", 2),
                ]),
                product("PART-01", "CABINET PART"),
                product("SCREW-01", "HARDWARE"),
            ]
        }
        acceptance = Acceptance(dataset)
        acceptance.run(acceptance.dataset_structures())
        codes = {issue.test_code for issue in acceptance.issues}
        self.assertIn("HRD_A_SUBSET", codes)

    def test_dataset_odoo_comparison_detects_all_contract_dimensions(self):
        dataset = {
            "products": [
                product("PARENT-1", "FPACK", "MANUFACTURE", [component("PART-1", 2)]),
                product("PARENT-2", "FPACK", "MANUFACTURE", [component("PART-1", 1)]),
                product("PART-1", "CABINET PART"),
            ]
        }
        acceptance = Acceptance(dataset)
        actual = {
            "PARENT-1": {
                "bom_type": "phantom",
                "components": {"PART-1": 3},
                "component_rows": [component("PART-1", 3)],
                "reference": "WRONG",
                "sequence": 7,
            },
            "EXTRA": {
                "bom_type": "normal",
                "components": {},
                "component_rows": [],
                "reference": "REL",
                "sequence": 10,
            },
        }
        acceptance.compare_dataset_to_odoo(actual, "REL", 10)
        self.assertEqual(acceptance.metrics["dataset_odoo_missing"], 1)
        self.assertEqual(acceptance.metrics["dataset_odoo_extra"], 1)
        self.assertEqual(acceptance.metrics["dataset_odoo_qty_or_component_mismatch"], 1)
        self.assertEqual(acceptance.metrics["dataset_odoo_type_mismatch"], 1)
        self.assertEqual(acceptance.metrics["dataset_odoo_reference_or_sequence_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
