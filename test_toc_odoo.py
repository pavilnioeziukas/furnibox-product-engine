from datetime import date

import pytest

from webapp.toc_odoo import ReadOnlyOdooReader, load_assembly_candidates


class FakeReader:
    def search_read(self, model, domain, fields, *, order="id asc", limit=5000):
        return {
            "mrp.workcenter": [{"id": 9, "name": "Assembly"}],
            "mrp.workorder": [
                {"id": 1, "production_id": [101, "MO1"], "state": "ready", "duration_expected": 60},
                {"id": 2, "production_id": [102, "MO2"], "state": "waiting", "duration_expected": 30},
                {"id": 3, "production_id": [103, "MO3"], "state": "ready", "duration_expected": 90},
            ],
            "mrp.production": [
                {"id": 101, "name": "MO1", "origin": "S002", "state": "confirmed"},
                {"id": 102, "name": "MO2", "origin": "S002", "state": "confirmed"},
                {"id": 103, "name": "MO3", "origin": "UNKNOWN", "state": "confirmed"},
            ],
            "sale.order": [
                {"id": 201, "name": "S002", "commitment_date": "2026-08-22 10:00:00", "tag_ids": [7], "state": "sale"},
            ],
            "crm.tag": [{"id": 7, "name": "SKUBUS"}],
        }[model]


def test_candidates_aggregate_pending_assembly_hours_at_so_level():
    result = load_assembly_candidates(FakeReader())

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.so_reference == "S002"
    assert candidate.delivery_date == date(2026, 8, 22)
    assert candidate.urgent is True
    assert candidate.assembly_hours == 1.5
    assert candidate.manufacturing_order_count == 2
    assert result.excluded_without_exact_so == 1


def test_reader_denies_unapproved_odoo_methods():
    reader = ReadOnlyOdooReader(
        url="https://example.test", database="db", login="reader", api_key="secret"
    )

    with pytest.raises(PermissionError, match="uždraustas"):
        reader._call("sale.order", "write", [[1], {"name": "changed"}], {})
