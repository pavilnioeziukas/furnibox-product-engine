import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from pricing_bom_scope import supplement_pricing_graph


class PricingScopeTests(unittest.TestCase):
    def apply(self, edges, graph=None, skus=None, configured=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scope = root / "scope.json"
            scope.write_text(json.dumps({"schema_version": 1, "purpose": "pricing_only", "skus": skus or ["LEGACY"]}), encoding="utf-8")
            book = Workbook()
            book.active.title = "ODOO EDGES"
            book.active.append(["Parent SKU", "Component SKU", "Quantity", "BOM ID"])
            for edge in edges:
                book.active.append(edge)
            book.save(root / "map.xlsx")
            return supplement_pricing_graph(graph or {}, configured or ["LEGACY"], scope, root / "map.xlsx")

    def test_explicit_nested_scope_preserves_target_and_ignores_unselected_boms(self):
        graph = {"target": [("PART", 2)]}
        result, added = self.apply([
            ["LEGACY", "NESTED", 2, 1], ["NESTED", "TARGET", 3, 2],
            ["TARGET", "WRONG", 99, 3], ["UNSELECTED", "PART", 5, 4],
        ], graph)
        self.assertEqual(graph, {"target": [("PART", 2)]})
        self.assertEqual(result["target"], graph["target"])
        self.assertEqual(added, {"legacy", "nested"})
        self.assertNotIn("unselected", result)

    def test_unknown_root_and_missing_bom_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unconfigured"):
            self.apply([], configured=["OTHER"])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.apply([])

    def test_bad_quantities_duplicates_and_ambiguous_boms_are_rejected(self):
        for edges, message in [
            ([["LEGACY", "PART", 0, 1]], "quantity"),
            ([["LEGACY", "PART", -1, 1]], "quantity"),
            ([["LEGACY", "PART", 1, 1], ["LEGACY", "PART", 2, 1]], "Duplicate"),
            ([["LEGACY", "PART", 1, 1], ["LEGACY", "OTHER", 2, 2]], "Ambiguous"),
            ([["LEGACY", "PART", 1, 1], ["PART", "LEGACY", 1, 2]], "Cycle"),
        ]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.apply(edges)

    def test_case_insensitive_duplicate_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate SKU"):
            self.apply([], skus=["LEGACY", "legacy"])


if __name__ == "__main__":
    unittest.main()
