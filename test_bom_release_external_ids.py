from __future__ import annotations

import unittest

from bom_release.external_ids import (
    apply_external_id_preparation,
    build_external_id_preparation,
)


class FakeClient:
    def __init__(self):
        self.external_ids = {
            "product.template": set(),
            "product.product": set(),
        }
        self.ensure_calls = []

    def search_read_all(self, model, domain, fields, context=None):
        if model == "product.product":
            return [
                {
                    "id": 1,
                    "default_code": "PARENT",
                    "product_tmpl_id": [11, "PARENT"],
                    "active": True,
                },
                {
                    "id": 2,
                    "default_code": "PART",
                    "product_tmpl_id": [12, "PART"],
                    "active": True,
                },
            ]
        if model == "ir.model.data":
            source_model = domain[0][2]
            wanted = set(domain[1][2])
            return [
                {"res_id": record_id}
                for record_id in self.external_ids[source_model]
                if record_id in wanted
            ]
        raise AssertionError(model)

    def ensure_external_ids(self, model, record_ids):
        ids = set(record_ids)
        self.ensure_calls.append((model, ids))
        self.external_ids[model].update(ids)
        return len(ids)


def dataset():
    return {
        "products": [
            {
                "sku": "PARENT",
                "components": [{"sku": "PART", "quantity": 1}],
            }
        ]
    }


class ExternalIdPreparationTests(unittest.TestCase):
    def test_preview_does_not_write_and_apply_targets_existing_records(self):
        client = FakeClient()
        preparation = build_external_id_preparation(client, dataset())
        self.assertEqual(preparation.template_ids, (11,))
        self.assertEqual(preparation.product_ids, (2,))
        self.assertEqual(client.ensure_calls, [])

        result = apply_external_id_preparation(client, preparation)
        self.assertEqual(result, (1, 1))
        self.assertEqual(
            client.ensure_calls,
            [
                ("product.template", {11}),
                ("product.product", {2}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
