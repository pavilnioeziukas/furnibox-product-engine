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
