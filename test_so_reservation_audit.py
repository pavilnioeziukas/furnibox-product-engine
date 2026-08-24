from so_reservation_audit import audit_so_reservations, reservation_status


class FakeClient:
    def __init__(self):
        self.records = {
            "sale.order": [{"id": 7, "name": "US1", "state": "sale"}],
            "mrp.production": [
                {
                    "id": 10,
                    "name": "WH/MO/10",
                    "state": "confirmed",
                    "product_id": [100, "Finished"],
                    "product_qty": 1,
                    "qty_produced": 0,
                    "move_raw_ids": [20, 21],
                },
                {
                    "id": 11,
                    "name": "WH/MO/11",
                    "state": "done",
                    "product_id": [101, "Done product"],
                    "product_qty": 1,
                    "qty_produced": 1,
                    "move_raw_ids": [22],
                },
            ],
            "stock.move": [
                {
                    "id": 20,
                    "product_id": [200, "Missing"],
                    "raw_material_production_id": [10, "WH/MO/10"],
                    "product_uom_qty": 4,
                    "quantity": 0,
                    "state": "confirmed",
                },
                {
                    "id": 21,
                    "product_id": [201, "Partial"],
                    "raw_material_production_id": [10, "WH/MO/10"],
                    "product_uom_qty": 3,
                    "quantity": 1,
                    "state": "assigned",
                },
                {
                    "id": 22,
                    "product_id": [202, "Consumed"],
                    "raw_material_production_id": [11, "WH/MO/11"],
                    "product_uom_qty": 2,
                    "quantity": 2,
                    "state": "done",
                },
            ],
        }

    def search_read_all(self, model, domain, fields, order="id asc", **_kwargs):
        rows = self.records[model]
        if model == "sale.order":
            return [row for row in rows if row["name"] == domain[0][2]]
        if model == "mrp.production":
            return rows if domain[0][2] == 7 else []
        if model == "stock.move":
            ids = set(domain[0][2])
            return [row for row in rows if row["id"] in ids]
        return []


def test_reservation_statuses():
    assert reservation_status("confirmed", 2, 2) == "RESERVED"
    assert reservation_status("confirmed", 2, 1) == "PARTIALLY_RESERVED"
    assert reservation_status("confirmed", 2, 0) == "NOT_RESERVED"
    assert reservation_status("done", 2, 0) == "MO_CLOSED"


def test_audit_is_scoped_to_so_and_summarizes_active_shortages():
    report = audit_so_reservations(FakeClient(), " us1 ")

    assert report["so_number"] == "US1"
    assert report["mo_count"] == 2
    assert report["active_mo_count"] == 1
    assert report["not_reserved_count"] == 1
    assert report["partially_reserved_count"] == 1
    assert report["missing_qty_total"] == 6
    assert [row["status"] for row in report["rows"]] == [
        "NOT_RESERVED",
        "PARTIALLY_RESERVED",
        "MO_CLOSED",
    ]
