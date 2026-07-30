from __future__ import annotations

import sys
from types import ModuleType
import unittest

if "dotenv" not in sys.modules:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from analyze_apack_hrd_transfer import (
    ApackHrdTransferError,
    active_sequence_zero_boms,
    apack_signature,
    analyze_all,
    build_transfer_plan,
    choose_production_analog,
    dataset_apack_skus,
    one_bom,
    select_dataset_pair,
    transfer_profile,
)


def product(sku, components):
    return {
        "sku": sku,
        "components": [
            {"sku": component, "quantity": quantity}
            for component, quantity in components.items()
        ],
    }


class ApackHrdTransferTests(unittest.TestCase):
    def setUp(self):
        self.apack = product("APACK-X-A", {"DETAIL-1": 2})
        self.hrd_a = product(
            "HRD-X-A",
            {"HINGE": 4, "SCREW": 8, "HANDLE": 1},
        )

    def test_selects_dataset_pair_without_changing_hrd_quantity(self):
        dataset = {
            "products": [
                self.apack,
                self.hrd_a,
                product(
                    "CABINET-X-A",
                    {"APACK-X-A": 1, "HRD-X-A": 1},
                ),
            ]
        }
        apack, hrd_a, hrd_sku = select_dataset_pair(dataset, "apack-x-a")
        self.assertIs(apack, self.apack)
        self.assertIs(hrd_a, self.hrd_a)
        self.assertEqual(hrd_sku, "HRD-X-A")

    def test_builds_verified_transfer_plan(self):
        plan = build_transfer_plan(
            new_apack=self.apack,
            new_hrd_a=self.hrd_a,
            old_apack_components={
                "DETAIL-1": 2,
                "HINGE": 4,
                "SCREW": 8,
            },
            old_hrd_a_components={"HANDLE": 1},
        )
        self.assertEqual(
            plan,
            [
                {
                    "component_sku": "HINGE",
                    "quantity": 4,
                    "from_hrd_a": "HRD-X-A",
                    "to_apack": "APACK-X-A",
                    "production_apack_quantity": 4,
                    "new_hrd_a_quantity": 4,
                },
                {
                    "component_sku": "SCREW",
                    "quantity": 8,
                    "from_hrd_a": "HRD-X-A",
                    "to_apack": "APACK-X-A",
                    "production_apack_quantity": 8,
                    "new_hrd_a_quantity": 8,
                },
            ],
        )

    def test_rejects_unconfirmed_transfer(self):
        with self.assertRaisesRegex(
            ApackHrdTransferError,
            "Production pora dviprasmiška",
        ):
            build_transfer_plan(
                new_apack=self.apack,
                new_hrd_a=self.hrd_a,
                old_apack_components={"DETAIL-1": 2, "HINGE": 4},
                old_hrd_a_components={"HINGE": 4, "HANDLE": 1},
            )

    def test_uses_new_hrd_quantity_when_reform_quantity_changed(self):
        plan = build_transfer_plan(
            new_apack=self.apack,
            new_hrd_a=self.hrd_a,
            old_apack_components={"DETAIL-1": 2, "HINGE": 3},
            old_hrd_a_components={},
        )
        self.assertEqual(plan[0]["quantity"], 4)
        self.assertEqual(plan[0]["production_apack_quantity"], 3)

    def test_no_transfer_is_valid(self):
        plan = build_transfer_plan(
            new_apack=self.apack,
            new_hrd_a=self.hrd_a,
            old_apack_components={"DETAIL-1": 2},
            old_hrd_a_components={"HINGE": 4},
        )
        self.assertEqual(plan, [])

    def test_lists_only_apack_assembled_skus(self):
        dataset = {
            "products": [
                product("APACK-X-A", {"D": 1}),
                product("APACK-X", {"D": 1}),
                product("FPACK-X-A", {"D": 1}),
            ]
        }
        self.assertEqual(dataset_apack_skus(dataset), ["APACK-X-A"])

    def test_extracts_market_cabinet_type_and_group(self):
        self.assertEqual(
            apack_signature("APACK-EU-C-CAB01-BAS001-A"),
            ("EU", "CAB01", "BAS"),
        )
        self.assertEqual(
            apack_signature("APACK-US-C-CAB03-UPP042-A"),
            ("US", "CAB03", "UPP"),
        )

    def test_selects_structural_analog_with_same_signature(self):
        bom_parent = {
            1: "APACK-EU-C-CAB01-BAS001-A",
            2: "HRD-OLD-A",
            3: "CABINET-EU-C-CAB01-BAS001-A",
            4: "APACK-EU-C-CAB01-TOP001-A",
            5: "HRD-TOP-A",
            6: "CABINET-EU-C-CAB01-TOP001-A",
        }
        by_parent = {
            sku: [bom_id] for bom_id, sku in bom_parent.items()
        }
        components = {
            1: {"DETAIL-1": 1, "HINGE": 2},
            2: {"HANDLE": 1},
            3: {
                "APACK-EU-C-CAB01-BAS001-A": 1,
                "HRD-OLD-A": 1,
            },
            4: {"DETAIL-X": 1},
            5: {"HANDLE-X": 1},
            6: {
                "APACK-EU-C-CAB01-TOP001-A": 1,
                "HRD-TOP-A": 1,
            },
        }
        analog = choose_production_analog(
            apack_sku="APACK-EU-C-CAB01-BAS999-A",
            new_apack_components={"DETAIL-1": 1},
            new_hrd_a_components={"HINGE": 2, "HANDLE": 1},
            bom_parent=bom_parent,
            by_parent=by_parent,
            components=components,
        )
        self.assertEqual(
            analog["apack_sku"],
            "APACK-EU-C-CAB01-BAS001-A",
        )
        self.assertEqual(analog["match_method"], "STRUCTURAL_ANALOG")

    def test_blocks_tied_structural_analogs_with_different_profiles(self):
        bom_parent = {
            1: "APACK-EU-C-CAB01-BAS001-A",
            2: "HRD-1-A",
            3: "CABINET-1-A",
            4: "APACK-EU-C-CAB01-BAS002-A",
            5: "HRD-2-A",
            6: "CABINET-2-A",
        }
        by_parent = {
            sku: [bom_id] for bom_id, sku in bom_parent.items()
        }
        components = {
            1: {"DETAIL-1": 1, "HINGE-A": 1},
            2: {"HANDLE-1": 1},
            3: {
                "APACK-EU-C-CAB01-BAS001-A": 1,
                "HRD-1-A": 1,
            },
            4: {"DETAIL-1": 1, "HINGE-B": 1},
            5: {"HANDLE-2": 1},
            6: {
                "APACK-EU-C-CAB01-BAS002-A": 1,
                "HRD-2-A": 1,
            },
        }
        with self.assertRaisesRegex(
            ApackHrdTransferError,
            "Keli nesutampantys Production perkėlimo profiliai",
        ):
            choose_production_analog(
                apack_sku="APACK-EU-C-CAB01-BAS999-A",
                new_apack_components={"DETAIL-1": 1},
                new_hrd_a_components={"HINGE-A": 1, "HINGE-B": 1},
                bom_parent=bom_parent,
                by_parent=by_parent,
                components=components,
            )

    def test_accepts_tied_analogs_with_same_transfer_profile(self):
        bom_parent = {
            1: "APACK-EU-C-CAB01-BAS001-A",
            2: "HRD-1-A",
            3: "CABINET-1-A",
            4: "APACK-EU-C-CAB01-BAS002-A",
            5: "HRD-2-A",
            6: "CABINET-2-A",
        }
        by_parent = {
            sku: [bom_id] for bom_id, sku in bom_parent.items()
        }
        components = {
            1: {"DETAIL-1": 1, "HINGE": 1},
            2: {"HANDLE-1": 1},
            3: {
                "APACK-EU-C-CAB01-BAS001-A": 1,
                "HRD-1-A": 1,
            },
            4: {"DETAIL-1": 1, "HINGE": 2},
            5: {"HANDLE-2": 1},
            6: {
                "APACK-EU-C-CAB01-BAS002-A": 1,
                "HRD-2-A": 1,
            },
        }
        analog = choose_production_analog(
            apack_sku="APACK-EU-C-CAB01-BAS999-A",
            new_apack_components={"DETAIL-1": 1},
            new_hrd_a_components={"HINGE": 4},
            bom_parent=bom_parent,
            by_parent=by_parent,
            components=components,
        )
        self.assertEqual(analog["match_method"], "PROFILE_CONSENSUS")
        self.assertEqual(analog["transfer_profile"], ["HINGE"])
        self.assertEqual(analog["profile_consensus_candidates"], 2)

    def test_uses_cross_cab_profile_only_when_all_candidates_agree(self):
        bom_parent = {
            1: "APACK-EU-C-CAB01-BAS001-A",
            2: "HRD-1-A",
            3: "CABINET-1-A",
            4: "APACK-EU-C-CAB03-BAS002-A",
            5: "HRD-2-A",
            6: "CABINET-2-A",
        }
        by_parent = {
            sku: [bom_id] for bom_id, sku in bom_parent.items()
        }
        components = {
            1: {"DETAIL-1": 1, "HINGE": 1},
            2: {"HANDLE-1": 1},
            3: {
                "APACK-EU-C-CAB01-BAS001-A": 1,
                "HRD-1-A": 1,
            },
            4: {"DETAIL-2": 1, "HINGE": 2},
            5: {"HANDLE-2": 1},
            6: {
                "APACK-EU-C-CAB03-BAS002-A": 1,
                "HRD-2-A": 1,
            },
        }
        analog = choose_production_analog(
            apack_sku="APACK-EU-C-CAB02-BAS999-A",
            new_apack_components={"DETAIL-X": 1},
            new_hrd_a_components={"HINGE": 4},
            bom_parent=bom_parent,
            by_parent=by_parent,
            components=components,
        )
        self.assertEqual(
            analog["match_method"],
            "CROSS_CAB_PROFILE_CONSENSUS",
        )
        self.assertEqual(analog["transfer_profile"], ["HINGE"])
        self.assertEqual(analog["profile_consensus_candidates"], 2)

    def test_blocks_cross_cab_profiles_when_one_candidate_disagrees(self):
        bom_parent = {
            1: "APACK-EU-C-CAB01-BAS001-A",
            2: "HRD-1-A",
            3: "CABINET-1-A",
            4: "APACK-EU-C-CAB03-BAS002-A",
            5: "HRD-2-A",
            6: "CABINET-2-A",
        }
        by_parent = {
            sku: [bom_id] for bom_id, sku in bom_parent.items()
        }
        components = {
            1: {"DETAIL-1": 1, "HINGE": 1},
            2: {},
            3: {
                "APACK-EU-C-CAB01-BAS001-A": 1,
                "HRD-1-A": 1,
            },
            4: {"DETAIL-2": 1, "SCREW": 2},
            5: {},
            6: {
                "APACK-EU-C-CAB03-BAS002-A": 1,
                "HRD-2-A": 1,
            },
        }
        with self.assertRaisesRegex(
            ApackHrdTransferError,
            "Keli nesutampantys Production perkėlimo profiliai",
        ):
            choose_production_analog(
                apack_sku="APACK-EU-C-CAB02-BAS999-A",
                new_apack_components={"DETAIL-X": 1},
                new_hrd_a_components={"HINGE": 4, "SCREW": 4},
                bom_parent=bom_parent,
                by_parent=by_parent,
                components=components,
            )

    def test_cab_spacer_remains_blocked_in_profile(self):
        with self.assertRaisesRegex(
            ApackHrdTransferError,
            "CAB_SPACER.*Production pora dviprasmiška",
        ):
            transfer_profile(
                new_apack_components={},
                new_hrd_a_components={"CAB_SPACER": 1},
                old_apack_components={"CAB_SPACER": 1},
                old_hrd_a_components={"CAB_SPACER": 1},
            )

    def test_equal_priority_identical_boms_are_equivalent(self):
        self.assertEqual(
            one_bom(
                {"HRD-X-A": [12, 11]},
                "HRD-X-A",
                {
                    11: {"HINGE": 4, "SCREW": 8},
                    12: {"SCREW": 8, "HINGE": 4},
                },
            ),
            11,
        )

    def test_odoo_bom_query_uses_only_real_required_fields(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def search_read_all(
                self,
                model,
                domain,
                fields,
                context=None,
            ):
                self.calls.append((model, domain, fields, context))
                return []

        client = FakeClient()
        active_sequence_zero_boms(client)

        bom_call = next(
            call for call in client.calls if call[0] == "mrp.bom"
        )
        self.assertEqual(
            bom_call[2],
            [
                "id",
                "product_tmpl_id",
                "product_id",
                "sequence",
                "create_date",
                "write_date",
            ],
        )
        self.assertNotIn("reference", bom_call[2])
        self.assertEqual(
            bom_call[1],
            [
                ["active", "=", True],
                ["create_date", "<", "2026-07-26 00:00:00"],
            ],
        )

    def test_cutoff_is_applied_before_sequence_selection(self):
        class FakeClient:
            def search_read_all(
                self,
                model,
                domain,
                fields,
                context=None,
            ):
                if model == "product.product":
                    return [
                        {
                            "id": 11,
                            "default_code": "APACK-X-A",
                            "product_tmpl_id": [101, "APACK-X-A"],
                        }
                    ]
                if model == "mrp.bom":
                    self.assertEqual(
                        domain,
                        [
                            ["active", "=", True],
                            ["create_date", "<", "2026-07-26 00:00:00"],
                        ],
                    )
                    return [
                        {
                            "id": 201,
                            "product_tmpl_id": [101, "APACK-X-A"],
                            "product_id": False,
                            "sequence": 10,
                            "create_date": "2026-07-25 23:59:59",
                            "write_date": "2026-07-25 23:59:59",
                        }
                    ]
                if model == "mrp.bom.line":
                    return []
                raise AssertionError(model)

        client = FakeClient()
        client.assertEqual = self.assertEqual
        bom_parent, by_parent, _ = active_sequence_zero_boms(client)

        self.assertEqual(bom_parent, {201: "APACK-X-A"})
        self.assertEqual(by_parent, {"APACK-X-A": [201]})

    def test_selects_lowest_active_sequence_then_newest_write_date(self):
        class FakeClient:
            def search_read_all(
                self,
                model,
                domain,
                fields,
                context=None,
            ):
                if model == "product.product":
                    return [
                        {
                            "id": 11,
                            "default_code": "APACK-X-A",
                            "product_tmpl_id": [101, "APACK-X-A"],
                        }
                    ]
                if model == "mrp.bom":
                    return [
                        {
                            "id": 201,
                            "product_tmpl_id": [101, "APACK-X-A"],
                            "product_id": False,
                            "sequence": 10,
                            "write_date": "2026-07-30 08:00:00",
                        },
                        {
                            "id": 202,
                            "product_tmpl_id": [101, "APACK-X-A"],
                            "product_id": False,
                            "sequence": 5,
                            "write_date": "2026-07-29 08:00:00",
                        },
                        {
                            "id": 203,
                            "product_tmpl_id": [101, "APACK-X-A"],
                            "product_id": False,
                            "sequence": 5,
                            "write_date": "2026-07-30 08:00:00",
                        },
                    ]
                if model == "mrp.bom.line":
                    if domain != [["bom_id", "in", [203]]]:
                        raise AssertionError(domain)
                    return []
                raise AssertionError(model)

        bom_parent, by_parent, _ = active_sequence_zero_boms(FakeClient())

        self.assertEqual(bom_parent, {203: "APACK-X-A"})
        self.assertEqual(by_parent, {"APACK-X-A": [203]})

    def test_keeps_equal_priority_boms_ambiguous(self):
        class FakeClient:
            def search_read_all(
                self,
                model,
                domain,
                fields,
                context=None,
            ):
                if model == "product.product":
                    return [
                        {
                            "id": 11,
                            "default_code": "APACK-X-A",
                            "product_tmpl_id": [101, "APACK-X-A"],
                        }
                    ]
                if model == "mrp.bom":
                    return [
                        {
                            "id": bom_id,
                            "product_tmpl_id": [101, "APACK-X-A"],
                            "product_id": False,
                            "sequence": 5,
                            "write_date": "2026-07-30 08:00:00",
                        }
                        for bom_id in (201, 202)
                    ]
                if model == "mrp.bom.line":
                    return []
                raise AssertionError(model)

        _, by_parent, _ = active_sequence_zero_boms(FakeClient())

        with self.assertRaisesRegex(
            ApackHrdTransferError,
            "2 vienodai prioritetinių",
        ):
            from analyze_apack_hrd_transfer import one_bom

            one_bom(by_parent, "APACK-X-A")


if __name__ == "__main__":
    unittest.main()
