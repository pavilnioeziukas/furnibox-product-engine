from mo_component_consumption_audit import detect_gaps


PRODUCTS = {
    10: {"default_code": "FIN", "display_name": "Finished"},
    20: {"default_code": "COMP-A", "display_name": "Component A"},
    21: {"default_code": "COMP-B", "display_name": "Component B"},
}


def production(move_ids=(100, 101)):
    return {
        "id": 1, "name": "WH/MO/34218", "state": "done",
        "product_id": [10, "Finished"], "qty_produced": 5,
        "bom_id": [30, "BOM"], "date_finished": "2025-07-18 11:20:17",
        "company_id": [1, "Company"], "move_raw_ids": list(move_ids),
    }


def test_detects_zero_and_partial_consumption_but_not_fully_consumed():
    moves = [
        {"id": 100, "product_id": [20, "Component A"], "product_uom_qty": 10, "quantity": 0, "state": "cancel", "product_uom": [1, "Units"]},
        {"id": 101, "product_id": [21, "Component B"], "product_uom_qty": 5, "quantity": 3, "state": "done", "product_uom": [1, "Units"]},
        {"id": 102, "product_id": [20, "Component A"], "product_uom_qty": 7, "quantity": 7, "state": "done", "product_uom": [1, "Units"]},
    ]
    rows = detect_gaps([production((100, 101, 102))], moves, PRODUCTS)
    assert [(row.component_sku, row.missing_qty) for row in rows] == [("COMP-A", 10), ("COMP-B", 2)]
    assert all(row.mo == "WH/MO/34218" for row in rows)


def test_ignores_fully_consumed_and_zero_plan_moves():
    moves = [
        {"id": 100, "product_id": [20, "Component A"], "product_uom_qty": 10, "quantity": 10, "state": "done"},
        {"id": 101, "product_id": [21, "Component B"], "product_uom_qty": 0, "quantity": 0, "state": "cancel"},
    ]
    assert detect_gaps([production()], moves, PRODUCTS) == []
