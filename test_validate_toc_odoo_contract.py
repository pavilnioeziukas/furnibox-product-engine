import unittest

from validate_toc_odoo_contract import ReadOnlyOdoo, is_populated, numeric_summary, ratio


class ReadOnlyGuardTests(unittest.TestCase):
    def test_mutating_method_is_denied_before_network_access(self):
        client = object.__new__(ReadOnlyOdoo)
        with self.assertRaises(PermissionError):
            client.call("sale.order", "write", [[1], {"name": "forbidden"}])


class AggregateHelperTests(unittest.TestCase):
    def test_zero_is_a_populated_numeric_value(self):
        self.assertTrue(is_populated(0))
        self.assertEqual(ratio([{"value": 0}, {"value": False}], "value")["populated_count"], 1)

    def test_numeric_summary_includes_zero(self):
        summary = numeric_summary([{"value": 0}, {"value": 10}, {"value": 20}], "value")
        self.assertEqual(summary, {"count": 3, "min": 0.0, "median": 10.0, "max": 20.0})


if __name__ == "__main__":
    unittest.main()
