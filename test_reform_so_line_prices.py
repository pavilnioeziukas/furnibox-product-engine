from pathlib import Path
import json
import sys
import tempfile
import types
import unittest

from openpyxl import Workbook, load_workbook

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

from reform_so_line_prices import (
    Item,
    add_generated_boms_to_graph,
    build_from_application_config,
    build_reform_so_line_prices,
    calculate_boms,
    component_cost_only_manufacture_products,
    exclude_bom_products_from_non_bom,
    inherit_generated_apack_rules,
    inherit_unambiguous_analog_rules,
    key,
    load_target_dataset_graph,
)
from manifest.manifest_writer import calculate_file_hash
from so_pricing_rules import PricingRule, load_config, migrate_legacy_workbook, save_config


class ReformSoLinePriceTests(unittest.TestCase):
    @staticmethod
    def pricing_rule(sku, assembly=0, storage=0, packaging=0):
        return PricingRule(
            sku,
            "CATEGORY",
            "Category",
            "Odoo / Category",
            assembly,
            storage,
            packaging,
            0,
            0,
            0,
        )

    def test_generated_manufacture_children_are_component_cost_only(self):
        apack = "APACK-EU-C-CAB01-BAS001-A"
        part = "CON7X50"
        rules = {
            key(apack): PricingRule(
                apack, "", "APACK", "", 5, 0, 0, 0, 0, 0
            ),
        }
        boms = {
            apack: ("APACK", [Item(part, 4)]),
        }
        prices = {
            key(part): ("Connector", 0.25, "DIRECT PRICE"),
        }

        rows, details = calculate_boms(
            boms,
            prices,
            rules,
            adjustment=0,
            graph={key(apack): [(part, 4)]},
            component_cost_only_tops={apack},
        )

        self.assertEqual(rows[0]["status"], "COMPLETE")
        self.assertEqual(rows[0]["issues"], "")
        self.assertAlmostEqual(rows[0]["cost"], 1.0)
        self.assertAlmostEqual(rows[0]["final"], 6.0)
        self.assertEqual([row["level"] for row in details], ["LEVEL I BOM"])

    def test_generated_cost_only_scope_does_not_hide_parent_rule_gap(self):
        cabinet = "EUB-C-CAB01-BAS001-A"
        apack = "APACK-EU-C-CAB01-BAS001-A"
        part = "PART"
        rules = {
            key(cabinet): PricingRule(
                cabinet, "", "CABINET-A", "", 1, 0, 0, 0, 0, 0
            ),
        }
        boms = {
            cabinet: ("CABINETS (Assembled)", [Item(apack, 1)]),
        }
        prices = {
            key(part): ("Part", 2.0, "DIRECT PRICE"),
        }

        rows, _ = calculate_boms(
            boms,
            prices,
            rules,
            adjustment=0,
            graph={
                key(cabinet): [(apack, 1)],
                key(apack): [(part, 1)],
            },
            component_cost_only_tops={apack},
        )

        self.assertEqual(rows[0]["status"], "BLOCKED")
        self.assertIn(
            f"Missing LEVEL II BOM pricing rule: {apack}",
            rows[0]["issues"],
        )

    def test_apack_rule_inherits_only_from_exact_generated_fpack(self):
        fpack = "FPACK-EU-CAB01-BNF002"
        apack = "APACK-EU-C-CAB01-BNF002-A"
        source = PricingRule(
            fpack, "8", "FPACK", "", 5, 0.2, 0, 0, 0, 0
        )
        shelf_pp = "EUB-PACK-CAB01-SLF301-PP"
        dataset = {
            "products": [{
                "sku": apack,
                "generated_from": fpack,
                "bom_type": "MANUFACTURE",
            }, {
                "sku": shelf_pp,
                "generated_from": "",
                "bom_type": "MANUFACTURE",
            }, {
                "sku": "FPACK-EU-CAB01-BNF002",
                "generated_from": "",
                "bom_type": "MANUFACTURE",
            }, {
                "sku": "EUB-C-CAB01-BNF002-A",
                "generated_from": "EUB-C-CAB01-BNF002",
                "bom_type": "KIT",
            }],
        }

        rules = inherit_generated_apack_rules(
            {key(fpack): source},
            dataset,
        )

        self.assertEqual(rules[key(apack)].sku, apack)
        self.assertEqual(rules[key(apack)].addons, source.addons)
        self.assertEqual(
            component_cost_only_manufacture_products(dataset),
            {key(apack), key(shelf_pp)},
        )

    def test_missing_rule_inherits_from_unanimous_exact_analogs(self):
        target = "FPACK-EU-CAB03-WAL015"
        analogs = [
            "FPACK-EU-CAB01-WAL015",
            "FPACK-EU-CAB02-WAL015",
            "FPACK-US-CAB03-WAL015",
        ]
        dataset = {
            "product_catalog": [
                {
                    "sku": sku,
                    "has_bom": True,
                    "product_type": "PREPACK CABINETS",
                    "name_2": "WALL Cabinet - W30 H80 D37",
                }
                for sku in [target, *analogs]
            ],
        }
        rules = {
            key(sku): self.pricing_rule(sku, assembly=4)
            for sku in analogs
        }

        result = inherit_unambiguous_analog_rules(rules, dataset)

        self.assertEqual(result[key(target)].sku, target)
        self.assertEqual(result[key(target)].addons, (4, 0, 0, 0, 0, 0))

    def test_shelf_pp_rule_may_inherit_across_width_only(self):
        target = "EUB-PACK-CAB03-SLF902-PP"
        analogs = [
            ("EUB-PACK-CAB03-SLF901-PP", "W20"),
            ("EUB-PACK-CAB03-SLF903-PP", "W60"),
            ("EUB-PACK-CAB03-SLF904-PP", "W80"),
        ]
        catalog = [{
            "sku": target,
            "has_bom": True,
            "product_type": "SHELF PREPACK",
            "name_2": "Shelf - W40 D60 - Shelf with integrated light (silver)",
        }]
        catalog.extend({
            "sku": sku,
            "has_bom": True,
            "product_type": "SHELF PREPACK",
            "name_2": f"Shelf - {width} D60 - Shelf with integrated light (silver)",
        } for sku, width in analogs)
        clothing_rod = "EUB-PACK-CAB03-SLF909-PP"
        catalog.append({
            "sku": clothing_rod,
            "has_bom": True,
            "product_type": "SHELF PREPACK",
            "name_2": "Shelf - W40 D60 - Shelf with integrated light (silver) & clothing rod",
        })
        rules = {
            key(sku): self.pricing_rule(
                sku,
                assembly=7.16,
                storage=0.5,
                packaging=1,
            )
            for sku, _ in analogs
        }
        rules[key(clothing_rod)] = self.pricing_rule(
            clothing_rod,
            assembly=7.16,
            storage=0.7,
            packaging=1,
        )

        result = inherit_unambiguous_analog_rules(
            rules,
            {"product_catalog": catalog},
        )

        self.assertEqual(result[key(target)].sku, target)
        self.assertEqual(
            result[key(target)].addons,
            (7.16, 0.5, 1, 0, 0, 0),
        )

    def test_ambiguous_analog_profiles_remain_without_rule(self):
        target = "TARGET-PP"
        dataset = {"product_catalog": [{
            "sku": sku,
            "has_bom": True,
            "product_type": "SHELF PREPACK",
            "name_2": name,
        } for sku, name in (
            (target, "Shelf - W40 D60 - Standard"),
            ("ANALOG-1-PP", "Shelf - W20 D60 - Standard"),
            ("ANALOG-2-PP", "Shelf - W60 D60 - Standard"),
        )]}
        rules = {
            key("ANALOG-1-PP"): self.pricing_rule("ANALOG-1-PP", storage=0.5),
            key("ANALOG-2-PP"): self.pricing_rule("ANALOG-2-PP", storage=0.7),
        }

        result = inherit_unambiguous_analog_rules(rules, dataset)

        self.assertNotIn(key(target), result)

    def test_bom_product_is_excluded_from_non_bom_pricing(self):
        bom_item = ("BOM", "BOM", "Category", "Pricing", 0, 0, 0, 0)
        non_bom_item = (
            "NON-BOM", "Non-BOM", "Category", "Pricing", 0, 0, 0, 0
        )

        result = exclude_bom_products_from_non_bom(
            [bom_item, non_bom_item],
            {key("BOM"): [("PART", 1)]},
        )

        self.assertEqual(result, [non_bom_item])

    def test_pricing_uses_full_target_dataset_for_shelf_pp(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bom = base / "Reform BOM.xlsx"
            bom.write_bytes(b"reform")
            dataset_path = base / "target.json"
            shelf = "SHELF"
            shelf_pp = "SHELF-PART-PP"
            dataset_path.write_text(json.dumps({
                "environment": "production",
                "source": {"file_hash": calculate_file_hash(bom)},
                "products": [
                    {
                        "sku": shelf,
                        "components": [
                            {"sku": shelf_pp, "quantity": 1},
                            {"sku": "PINS", "quantity": 1},
                        ],
                    },
                    {
                        "sku": shelf_pp,
                        "components": [
                            {"sku": "SHELF-PART", "quantity": 1},
                            {"sku": "PACKAGE", "quantity": 0.4},
                            {"sku": "STICKER", "quantity": 2},
                        ],
                    },
                ],
            }), encoding="utf-8")
            _, graph = load_target_dataset_graph(dataset_path, bom)
            prices = {
                key("SHELF-PART"): ("Part", 10.0, "DIRECT"),
                key("PACKAGE"): ("Package", 2.0, "DIRECT"),
                key("STICKER"): ("Sticker", 0.1, "DIRECT"),
                key("PINS"): ("Pins", 1.0, "DIRECT"),
            }
            from reform_so_line_prices import resolve_component_cost
            result = resolve_component_cost(shelf, prices, graph)
            self.assertAlmostEqual(result["cost"], 12.0)
            self.assertEqual(result["issues"], [])

    def test_stale_target_dataset_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bom = base / "Reform BOM.xlsx"
            bom.write_bytes(b"current")
            dataset = base / "target.json"
            dataset.write_text(json.dumps({
                "environment": "production",
                "source": {"file_hash": "old"},
                "products": [{
                    "sku": "TOP",
                    "components": [{"sku": "PART", "quantity": 1}],
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ne iš pateikto Reform"):
                load_target_dataset_graph(dataset, bom)

    def test_untransformed_apack_dataset_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bom = base / "Reform BOM.xlsx"
            bom.write_bytes(b"current")
            dataset = base / "target.json"
            dataset.write_text(json.dumps({
                "environment": "production",
                "source": {"file_hash": calculate_file_hash(bom)},
                "products": [{
                    "sku": "APACK-EU-C-CAB01-BAS001-A",
                    "components": [{"sku": "PART", "quantity": 1}],
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "seno Dataset"):
                load_target_dataset_graph(dataset, bom)

    def test_assembled_cabinet_uses_generated_apack_and_hrd_a_boms(self):
        cabinet = "EUB-C-CAB01-BAS001"
        assembled = f"{cabinet}-A"
        fpack = "FPACK-EU-CAB01-BAS001"
        apack = "APACK-EU-C-CAB01-BAS001-A"
        hrd = "UNI-P-ACC01-HRD206D"
        hrd_a = f"{hrd}-A"
        graph = {
            key(cabinet): [(hrd, 1), (fpack, 1)],
            key(hrd): [("HRD-PART", 2)],
            key(fpack): [("CABINET-PART", 3)],
        }
        products = [
            {"sku": cabinet, "product_category": "All / CABINETS"},
            {"sku": assembled, "product_category": "All / CABINETS (Assembled)"},
        ]

        generated = add_generated_boms_to_graph(graph, products)

        self.assertEqual(generated[key(assembled)], [(hrd_a, 1.0), (apack, 1.0)])
        self.assertEqual(generated[key(hrd_a)], [("HRD-PART", 2.0)])
        self.assertEqual(generated[key(apack)], [("CABINET-PART", 3.0)])

        def rule(sku, assembly=0):
            return PricingRule(sku, "", "", "", assembly, 0, 0, 0, 0, 0)

        rules = {
            key(sku): rule(sku, assembly=5.5 if sku == assembled else 0)
            for sku in (cabinet, assembled, fpack, apack, hrd, hrd_a)
        }
        boms = {
            cabinet: ("CABINETS", [Item(hrd, 1), Item(fpack, 1)]),
            assembled: ("CABINETS (Assembled)", [Item(hrd_a, 1), Item(apack, 1)]),
        }
        prices = {
            key("HRD-PART"): ("Hardware", 4.0, "DIRECT PRICE"),
            key("CABINET-PART"): ("Cabinet part", 10.0, "DIRECT PRICE"),
        }

        rows, _ = calculate_boms(boms, prices, rules, adjustment=0, graph=generated)
        by_sku = {row["sku"]: row for row in rows}
        self.assertEqual(by_sku[cabinet]["cost"], 38.0)
        self.assertEqual(by_sku[assembled]["cost"], 38.0)
        self.assertEqual(sum(by_sku[assembled]["addons"]), 5.5)

    def test_bom_category_breakdown_and_non_bom_logic(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            model = base / "model.xlsx"
            prices = base / "Reform_Final_Prices.xlsx"
            output = base / "Reform_SO_Line_Prices.xlsx"

            wb = Workbook()
            ws = wb.active
            ws.title = "bomai"
            ws.append([None] * 24)
            ws.append(["lv1", None, None, "lv2", None, "qty2", "lv3", "qty3"])
            ws.append(["TOP-1", "TOP-1", "CABINET", "SUB-1", "PACK", 2, "PART-1", 3])
            ws.append([None, "TOP-1", "CABINET", None, "PACK", None, "PART-2", 1])
            ws.append(["TOP-1", "TOP-1", "CABINET", "DIRECT-1", "HARDWARE", 4, None, None])
            rules = wb.create_sheet("Kainodaros kategorijos")
            rules.append(["SKU", "ID", "Name", "Odoo", "Assembly", "Storage", "Packaging", "Pallet", "Other", "Markup", "Total"])
            rules.append(["SUB-1", 8, "PACK", "", 1, 2, 3, 4, 5, 6, 21])
            rules.append(["DIRECT-1", 7, "HARDWARE", "", 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 2.1])
            rules.append(["TOP-1", 1, "CABINET", "", 10, 20, 30, 40, 50, 60, 210])
            non_bom = wb.create_sheet("Ne BOM pozicijos")
            non_bom.append(["SKU", "Description", "Group", "Category", "Cost", "New price", "Preparation", "Storage", "Bag", "Sticker", "Total"])
            non_bom.append(["ACC-1", "Accessory", "ACC", 11, 0, 0, 0.1, 0.2, 0.03, 0.02, 0])
            wb.save(model)

            wb = Workbook()
            ws = wb.active
            ws.title = "REFORM PRICE LIST"
            ws.append(["Internal Reference", "Name", "Adjusted Furnibox Purchase Price", "Reform Markup Factor", "Reform Purchase Price"])
            ws.append(["PART-1", "Part 1", 2, 1, 2])
            ws.append(["PART-2", "Part 2", 5, 1, 5])
            ws.append(["DIRECT-1", "Direct", 7, 1, 7])
            ws.append(["ACC-1", "Accessory", 10, 1, 10])
            wb.save(prices)

            counts = build_reform_so_line_prices(model, prices, output)
            self.assertEqual(counts, (1, 1, 0))
            result = load_workbook(output, data_only=True)
            self.assertEqual(result.sheetnames, [
                "SO LINE PRICES", "BOM COMPONENT COSTS", "BOM CATEGORY BREAKDOWN", "CATEGORY RULES",
                "NON-BOM RULES", "DIAGNOSTICS", "INFO",
            ])
            sheet = result["SO LINE PRICES"]
            headers = {cell.value: cell.column for cell in sheet[1]}
            rows = {sheet.cell(r, 1).value: r for r in range(2, sheet.max_row + 1)}
            bom = rows["TOP-1"]
            # Components: (2*3 + 5*1)*2 + 7*4 = 50
            self.assertAlmostEqual(sheet.cell(bom, headers["Component / Purchase Cost"]).value, 50)
            # Add-ons: SUB-1*2 + DIRECT-1 once + TOP-1 once = 254.1
            self.assertAlmostEqual(sheet.cell(bom, headers["Pricing Add-ons Total"]).value, 254.1)
            self.assertAlmostEqual(sheet.cell(bom, headers["Adjustment Amount"]).value, -17.787)
            self.assertAlmostEqual(sheet.cell(bom, headers["Final Reform SO Unit Price"]).value, 286.313)
            non = rows["ACC-1"]
            self.assertAlmostEqual(sheet.cell(non, headers["Final Reform SO Unit Price"]).value, 10.35)
            self.assertEqual(sheet.cell(non, headers["Status"]).value, "COMPLETE")

            components = result["BOM COMPONENT COSTS"]
            component_headers = {cell.value: cell.column for cell in components[1]}
            component_rows = {
                components.cell(row, component_headers["Purchased Component SKU"]).value: row
                for row in range(2, components.max_row + 1)
            }
            part_1 = component_rows["PART-1"]
            self.assertEqual(components.cell(part_1, component_headers["Level II SKU"]).value, "SUB-1")
            self.assertAlmostEqual(components.cell(part_1, component_headers["Total Qty in Top BOM"]).value, 6)
            self.assertAlmostEqual(components.cell(part_1, component_headers["Purchase Unit Price"]).value, 2)
            self.assertAlmostEqual(components.cell(part_1, component_headers["Component Cost"]).value, 12)
            direct = component_rows["DIRECT-1"]
            self.assertAlmostEqual(components.cell(direct, component_headers["Component Cost"]).value, 28)

    def test_application_config_replaces_legacy_workbook_at_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy = base / "legacy.xlsx"
            bom_input = base / "Reform_BOM_Input.xlsx"
            config = base / "so_pricing_rules.json"
            prices = base / "prices.xlsx"
            output = base / "result.xlsx"

            wb = Workbook()
            ws = wb.active; ws.title = "bomai"
            ws.append([]); ws.append([]); ws.append([None, "TOP", "CABINET", "SUB", None, 2, "PART", 3])
            ws = wb.create_sheet("Kainodaros kategorijos")
            ws.append(["SKU", "ID", "Name", "Odoo", "Assembly", "Storage", "Packaging", "Pallet", "Other", "Markup"])
            ws.append(["SUB", "2", "Pack", "", 1, 0, 0, 0, 0, 0])
            ws.append(["TOP", "1", "Cabinet", "", 10, 0, 0, 0, 0, 0])
            ws = wb.create_sheet("Ne BOM pozicijos")
            ws.append(["SKU", "Name", "Group", "Category", "", "", "Preparation", "Storage", "Bag", "Sticker"])
            wb.save(legacy)
            migrated = migrate_legacy_workbook(legacy)
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(len(migrated["bom_categories"]), 2)
            self.assertEqual(len(migrated["bom_skus"]), 2)
            self.assertEqual(migrated["bom_skus"][0]["category_id"], "BOM-001")
            save_config(config, migrated)
            self.assertEqual(load_config(config)["schema_version"], 2)
            legacy.unlink()

            wb = Workbook(); ws = wb.active; ws.title = "BOM - Input"
            ws.append(["BOM SKU Code", "Part 1 Code", "Part 1 Qty"])
            ws.append(["TOP", "SUB", 2]); ws.append(["SUB", "PART", 3]); wb.save(bom_input)
            wb = Workbook(); ws = wb.active; ws.title = "REFORM PRICE LIST"
            ws.append(["Internal Reference", "Name", "Adjusted Furnibox Purchase Price", "Reform Markup Factor", "Reform Purchase Price"])
            ws.append(["PART", "Part", 5, 1, 5]); wb.save(prices)

            self.assertEqual(build_from_application_config(bom_input, prices, config, output), (1, 0, 0))
            result = load_workbook(output, data_only=True)["SO LINE PRICES"]
            headers = {cell.value: cell.column for cell in result[1]}
            self.assertAlmostEqual(result.cell(2, headers["Final Reform SO Unit Price"]).value, 41.16)


if __name__ == "__main__":
    unittest.main()
