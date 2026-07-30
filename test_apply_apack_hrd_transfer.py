from __future__ import annotations

import unittest

from apply_apack_hrd_transfer import (
    DatasetTransferError,
    component_map,
    transform_dataset,
)


def product(sku, components, content_hash="old"):
    return {
        "sku": sku,
        "product_type": "TEST",
        "bom_type": "MANUFACTURE",
        "level": 1,
        "source_sku": sku,
        "generated_from": "",
        "reform_category": "TEST",
        "content_hash": content_hash,
        "content_signature": "old-signature",
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
        "statistics": {
            "component_count": len(components),
            "operation_count": 0,
        },
    }


class ApplyApackHrdTransferTests(unittest.TestCase):
    def dataset(self):
        return {
            "schema_version": "1.0",
            "dataset_id": "old-id",
            "batch_reference": "REFORM_v08",
            "environment": "production",
            "created_at_utc": "2026-07-29T00:00:00+00:00",
            "source": {"file_name": "source.xlsx", "file_hash": "x"},
            "statistics": {},
            "products": [
                product("APACK-EU-C-CAB01-BAS001-A", {"DETAIL": 2}),
                product(
                    "HRD-EU-C-CAB01-BAS001-A",
                    {"HINGE": 4, "HANDLE": 1},
                ),
            ],
        }

    def analysis(self, status="TRANSFERRED"):
        row = {
            "status": status,
            "apack_sku": "APACK-EU-C-CAB01-BAS001-A",
            "hrd_a_sku": "HRD-EU-C-CAB01-BAS001-A",
            "analog_match_method": "PROFILE_CONSENSUS",
            "transfer_plan": [],
        }
        if status == "TRANSFERRED":
            row["transfer_plan"] = [
                {
                    "component_sku": "HINGE",
                    "quantity": 4,
                    "from_hrd_a": "HRD-EU-C-CAB01-BAS001-A",
                    "to_apack": "APACK-EU-C-CAB01-BAS001-A",
                }
            ]
        if status == "BLOCKED":
            row["reason"] = "Nėra patikimo analogo."
        return {"statistics": {}, "results": [row]}

    def test_moves_component_exactly_once_and_refreshes_hashes(self):
        source = self.dataset()
        old_hashes = {
            row["sku"]: row["content_hash"] for row in source["products"]
        }
        transformed, audit = transform_dataset(source, self.analysis())
        products = {row["sku"]: row for row in transformed["products"]}
        apack = products["APACK-EU-C-CAB01-BAS001-A"]
        hrd = products["HRD-EU-C-CAB01-BAS001-A"]
        self.assertEqual(component_map(apack), {"DETAIL": 2, "HINGE": 4})
        self.assertEqual(component_map(hrd), {"HANDLE": 1})
        self.assertNotEqual(apack["content_hash"], old_hashes[apack["sku"]])
        self.assertNotEqual(hrd["content_hash"], old_hashes[hrd["sku"]])
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["statistics"]["component_transfers"], 1)

    def test_blocked_case_remains_in_hrd_a(self):
        transformed, audit = transform_dataset(
            self.dataset(), self.analysis("BLOCKED")
        )
        products = {row["sku"]: row for row in transformed["products"]}
        self.assertEqual(
            component_map(products["APACK-EU-C-CAB01-BAS001-A"]),
            {"DETAIL": 2},
        )
        self.assertEqual(
            component_map(products["HRD-EU-C-CAB01-BAS001-A"]),
            {"HANDLE": 1, "HINGE": 4},
        )
        self.assertEqual(audit["statistics"]["default_hrd_review"], 1)
        self.assertEqual(
            audit["rows"][0]["decision"], "DEFAULT_HRD_REVIEW"
        )

    def test_rejects_quantity_mismatch(self):
        analysis = self.analysis()
        analysis["results"][0]["transfer_plan"][0]["quantity"] = 3
        with self.assertRaisesRegex(
            DatasetTransferError, "nesutampa su HRD-A kiekiu"
        ):
            transform_dataset(self.dataset(), analysis)

    def test_rejects_component_already_in_both_boms(self):
        dataset = self.dataset()
        dataset["products"][0]["components"].append(
            {
                "sku": "HINGE",
                "quantity": 4,
                "parent_sku": "APACK-EU-C-CAB01-BAS001-A",
                "level": 1,
            }
        )
        with self.assertRaisesRegex(
            DatasetTransferError, "jau yra ir APACK, ir HRD-A"
        ):
            transform_dataset(dataset, self.analysis())

    def test_shared_hrd_component_is_moved_to_each_apack_and_removed_once(self):
        dataset = self.dataset()
        dataset["products"].append(
            product("APACK-EU-C-CAB01-BAS002-A", {"DETAIL-2": 1})
        )
        analysis = self.analysis()
        second = {
            **analysis["results"][0],
            "apack_sku": "APACK-EU-C-CAB01-BAS002-A",
            "transfer_plan": [
                {
                    "component_sku": "HINGE",
                    "quantity": 4,
                    "from_hrd_a": "HRD-EU-C-CAB01-BAS001-A",
                    "to_apack": "APACK-EU-C-CAB01-BAS002-A",
                }
            ],
        }
        analysis["results"].append(second)

        transformed, audit = transform_dataset(dataset, analysis)
        products = {row["sku"]: row for row in transformed["products"]}
        self.assertEqual(
            component_map(products["APACK-EU-C-CAB01-BAS001-A"]),
            {"DETAIL": 2, "HINGE": 4},
        )
        self.assertEqual(
            component_map(products["APACK-EU-C-CAB01-BAS002-A"]),
            {"DETAIL-2": 1, "HINGE": 4},
        )
        self.assertEqual(
            component_map(products["HRD-EU-C-CAB01-BAS001-A"]),
            {"HANDLE": 1},
        )
        self.assertEqual(audit["statistics"]["component_transfers"], 2)

    def test_requires_analysis_coverage_for_every_apack(self):
        dataset = self.dataset()
        dataset["products"].append(
            product("APACK-EU-C-CAB01-TOP001-A", {"DETAIL-2": 1})
        )
        with self.assertRaisesRegex(
            DatasetTransferError, "neapima visų Dataset APACK"
        ):
            transform_dataset(dataset, self.analysis())


if __name__ == "__main__":
    unittest.main()
