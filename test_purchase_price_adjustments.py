import json
import tempfile
import unittest
from pathlib import Path

from purchase_price_adjustments import load_adjustments


class PurchasePriceAdjustmentDefaultsTest(unittest.TestCase):
    def test_approved_packaging_prices_are_loaded_as_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            adjustments = load_adjustments(Path(directory) / "missing.json")

        expected = {
            "EU FP PACK": 2.09,
            "US FP PACK": 2.09,
            "N PACK EU": 4.89,
            "N PACK US": 4.89,
            "SHELF PACK": 1.29,
            "L0377": 0.15,
            "STICKER UP": 0.18,
            "TERMO 90X48": 0.02,
        }
        self.assertEqual(
            {
                sku: adjustments[sku]["adjusted_purchase_price"]
                for sku in expected
            },
            expected,
        )

    def test_persisted_adjustment_overrides_approved_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adjustments.json"
            path.write_text(
                json.dumps(
                    {
                        "adjustments": {
                            "EU FP PACK": {
                                "adjusted_purchase_price": 2.25,
                                "comment": "Newer correction",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            adjustments = load_adjustments(path)

        self.assertEqual(
            adjustments["EU FP PACK"]["adjusted_purchase_price"],
            2.25,
        )


if __name__ == "__main__":
    unittest.main()
