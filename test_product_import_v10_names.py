import unittest

from product_import_v10 import product_name


class ProductImportV10NameTests(unittest.TestCase):
    def test_cabinet_shelf_uses_name_2_and_sku_suffix(self):
        product = {
            "sku": "EUB-C-CAB01-SLF001",
            "category": "CABINET SHELF",
            "name_1": "REFORM BOX - White",
            "name_2": "Shelf - W20 D60 - standard",
        }
        self.assertEqual(
            product_name(product["sku"], product),
            "Shelf - W20 D60 - standard - SLF001",
        )

    def test_cabinet_uses_name_2_and_logical_suffix(self):
        product = {
            "sku": "EUB-C-CAB01-BAS001-A",
            "category": "CABINETS",
            "name_1": "REFORM BOX - White",
            "name_2": "BASE Cabinet - W20 H80 D60",
        }
        self.assertEqual(
            product_name(product["sku"], product),
            "BASE Cabinet - W20 H80 D60 - BAS001",
        )

    def test_interior_storage_uses_name_2(self):
        product = {
            "sku": "UNI-P-ACC02-MIS009",
            "category": "INTERIOR STORAGE",
            "name_1": "ACCESSORIES - Interior",
            "name_2": "Interior storage basket",
        }
        self.assertEqual(
            product_name(product["sku"], product),
            "Interior storage basket",
        )

    def test_approved_name_overrides_broken_name_2(self):
        product = {
            "sku": "EUB-P-ACC02-MIS012",
            "category": "INTERIOR STORAGE",
            "name_1": "REFORM BOX - White",
            "name_2": "#N/A",
        }
        self.assertEqual(product_name(product["sku"], product), "Rename")

    def test_other_categories_keep_existing_name_priority(self):
        product = {
            "sku": "FPACK-EU-CAB01-BAS001",
            "category": "PREPACK CABINETS",
            "name_1": "REFORM BOX - White",
            "name_2": "BASE Cabinet - W20 H80 D60",
        }
        self.assertEqual(product_name(product["sku"], product), "REFORM BOX - White")


if __name__ == "__main__":
    unittest.main()
