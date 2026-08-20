from __future__ import annotations

import unittest

from shelf_pp import (
    ShelfPpError,
    ShelfPpTemplate,
    add_generated_shelf_pp_boms,
    build_shelf_pp_templates,
    choose_shelf_pp_operation_template,
)


class ShelfPpTests(unittest.TestCase):
    def setUp(self):
        self.part = "EU-SREW-SHELF-563x564-NO"
        self.pp = f"{self.part}-PP"
        self.packaging = "N9565A"
        self.sticker = "TERMO 90X48"
        self.templates = build_shelf_pp_templates({
            "EU-SREW-SHELF-563x564-WW-PP": [
                {"component": "EU-SREW-SHELF-563x564-WW", "quantity": 1},
                {"component": self.packaging, "quantity": 0.4},
                {"component": self.sticker, "quantity": 2},
            ],
        })

    def test_reform_shelf_is_replaced_by_generated_pp(self):
        shelf = "EUB-C-CAB01-SLF001"
        pins = "SLF-PINS-HRD-4"
        parents = {shelf}
        lines = {shelf: [
            {"component": self.part, "quantity": 1},
            {"component": pins, "quantity": 1},
        ]}
        levels = {shelf: 1}
        bom_types = {shelf: "OLD"}
        products = {
            shelf: {"category": "CABINET SHELF"},
            self.part: {"part_group": "SHELF PART"},
        }

        generated = add_generated_shelf_pp_boms(
            parents,
            lines,
            levels,
            bom_types,
            products,
            self.templates,
            kit_type="KIT",
            manufacture_type="MANUFACTURE",
        )

        canonical_part = self.part.upper()
        canonical_pp = self.pp.upper()
        self.assertEqual(generated, {canonical_pp: canonical_part})
        self.assertEqual(bom_types[shelf], "KIT")
        self.assertEqual(bom_types[canonical_pp], "MANUFACTURE")
        self.assertEqual(
            lines[shelf],
            [
                {"component": canonical_pp, "quantity": 1},
                {"component": pins, "quantity": 1},
            ],
        )
        self.assertEqual(
            lines[canonical_pp],
            [
                {"component": canonical_part, "quantity": 1},
                {"component": self.packaging, "quantity": 0.4},
                {"component": self.sticker, "quantity": 2.0},
            ],
        )

    def test_missing_shelf_part_is_blocked(self):
        with self.assertRaisesRegex(ShelfPpError, "tikėtasi vieno SHELF PART"):
            add_generated_shelf_pp_boms(
                {"SHELF-1"},
                {"SHELF-1": [{"component": "PINS", "quantity": 1}]},
                {"SHELF-1": 1},
                {"SHELF-1": "KIT"},
                {"SHELF-1": {"category": "CABINET SHELF"}},
                self.templates,
                kit_type="KIT",
                manufacture_type="MANUFACTURE",
            )

    def test_existing_prepack_component_is_not_generated_again(self):
        shelf = "EUB-C-CAB01-SLF301"
        prepack = "EUB-PACK-CAB01-SLF301-PP"
        parents = {shelf}
        lines = {shelf: [
            {"component": prepack, "quantity": 1},
            {"component": "SLF-LED-HRD-4", "quantity": 1},
        ]}
        bom_types = {shelf: "OLD"}

        generated = add_generated_shelf_pp_boms(
            parents,
            lines,
            {shelf: 1},
            bom_types,
            {
                shelf: {"category": "CABINET SHELF"},
                prepack: {"part_group": "CABINET SHELF"},
            },
            self.templates,
            kit_type="KIT",
            manufacture_type="MANUFACTURE",
        )

        self.assertEqual(generated, {})
        self.assertEqual(bom_types[shelf], "KIT")
        self.assertEqual(lines[shelf][0]["component"], prepack)

    def test_existing_prepack_parent_is_not_transformed(self):
        prepack = "EUB-PACK-CAB01-SLF301-PP"
        parents = {prepack}
        lines = {prepack: [
            {"component": "EU-SREW-SHELF-ROD-1163X340-WW", "quantity": 1},
            {"component": "EU-PROSLEEVE-D37", "quantity": 1},
        ]}
        bom_types = {prepack: "MANUFACTURE"}

        generated = add_generated_shelf_pp_boms(
            parents,
            lines,
            {prepack: 1},
            bom_types,
            {
                prepack: {"category": "CABINET SHELF"},
                "EU-SREW-SHELF-ROD-1163X340-WW": {
                    "part_group": "SHELF PART"
                },
                "EU-PROSLEEVE-D37": {"part_group": "SHELF PART"},
            },
            self.templates,
            kit_type="KIT",
            manufacture_type="MANUFACTURE",
        )

        self.assertEqual(generated, {})
        self.assertEqual(bom_types[prepack], "MANUFACTURE")

    def test_reform_v10_new_corner_uses_approved_packaging_class(self):
        from shelf_pp import choose_shelf_pp_template

        templates = build_shelf_pp_templates({
            "EU-SREW-SHELF-CORNER-R_LEFT-1238x564-WW-PP": [
                {
                    "component":
                        "EU-SREW-SHELF-CORNER-R_LEFT-1238x564-WW",
                    "quantity": 1,
                },
                {"component": "N9570A", "quantity": 0.4},
                {"component": "TERMO 90X48", "quantity": 2},
            ],
        })

        selected = choose_shelf_pp_template(
            "EU-SREW-SHELF-CORNER-R_LEFT-963x564-NO-PP",
            templates,
        )

        self.assertEqual(selected.source_pp_sku,
            "EU-SREW-SHELF-CORNER-R_LEFT-1238X564-WW-PP")
        self.assertEqual(selected.extra_components[0], ("N9570A", 0.4))

    def test_reform_v10_fallback_is_used_for_packing_operation(self):
        templates = {
            1: {
                "sku": "US-SREW-SHELF-FIX-726x574-WW-PP",
                "operations": [{
                    "name": "Lentynų pakavimas",
                    "workcenter": "Pakuotojai",
                    "time_mode": "manual",
                    "time": 1,
                    "sequence": 0,
                }],
            }
        }

        selected = choose_shelf_pp_operation_template(
            "US-SREW-SHELF-FIX-878x574-NO-PP",
            templates,
        )

        self.assertEqual(selected["sku"],
            "US-SREW-SHELF-FIX-726x574-WW-PP")

    def test_ambiguous_packaging_profile_is_blocked(self):
        target = "EU-SREW-SHELF-563x564-NO-PP"
        ambiguous = {
            "EU-SREW-SHELF-563x564-WW-PP": ShelfPpTemplate(
                "EU-SREW-SHELF-563x564-WW-PP",
                "EU-SREW-SHELF-563x564-WW",
                (("PACK-A", 1), ("LABEL", 1)),
            ),
            "EU-SREW-SHELF-563x564-BB-PP": ShelfPpTemplate(
                "EU-SREW-SHELF-563x564-BB-PP",
                "EU-SREW-SHELF-563x564-BB",
                (("PACK-B", 1), ("LABEL", 1)),
            ),
        }
        from shelf_pp import choose_shelf_pp_template

        with self.assertRaisesRegex(ShelfPpError, "skirtingas pakuotes"):
            choose_shelf_pp_template(target, ambiguous)

    def test_exactly_one_packing_operation_is_required(self):
        templates = {
            1: {
                "sku": "EU-SREW-SHELF-563x564-WW-PP",
                "operations": [{
                    "name": "Lentynų pakavimas",
                    "workcenter": "Pakuotojai",
                    "time_mode": "manual",
                    "time": 1,
                    "sequence": 0,
                }],
            }
        }
        selected = choose_shelf_pp_operation_template(self.pp, templates)
        self.assertEqual(selected["sku"], "EU-SREW-SHELF-563x564-WW-PP")


if __name__ == "__main__":
    unittest.main()
