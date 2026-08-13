from odoo_supply_chain_audit import classify_receipts, run_audit


class FakeClient:
    def search_read_all(self, model, domain, fields, order="id asc", context=None, batch_size=1000):
        data = {
            "stock.picking": [
                {"id": 10, "name": "WH/INT/1", "state": "waiting", "origin": "WH/MO/1", "sale_primary_id": [20, "SO1"], "move_ids": [100]},
                {"id": 30, "name": "WH/INPC/1", "state": "done"},
            ],
            "stock.move": [
                {"id": 100, "state": "waiting", "product_uom_qty": 2, "quantity": 0, "picking_id": [10, "WH/INT/1"], "move_orig_ids": [101]},
                {"id": 101, "picking_id": [30, "WH/INPC/1"]},
            ],
            "sale.order": [{"id": 20, "name": "SO1", "state": "sale", "invoice_status": "invoiced", "delivery_status": "full"}],
            "mrp.production": [{"id": 40, "name": "WH/MO/1", "state": "confirmed", "product_id": [50, "Product"], "product_qty": 1, "qty_produced": 0, "sale_primary_id": [20, "SO1"], "write_date": "2026-01-01"}],
            "stock.location": [{"id": 629, "complete_name": "WH/Input-Custom"}],
            "stock.quant": [{"id": 60, "product_id": [50, "Product"], "quantity": 3, "reserved_quantity": 1, "write_date": "2026-01-01"}],
        }
        rows = data.get(model, [])
        ids = next((set(item[2]) for item in domain if item[0] == "id" and item[1] == "in"), None)
        if ids is not None:
            return [row for row in rows if row["id"] in ids]
        if model == "stock.picking" and any(item[:2] == ["picking_type_id", "="] for item in domain):
            return [rows[0]]
        return rows


def test_receipt_classification():
    assert classify_receipts([]) == "NO_WH_INPC_LINK"
    assert classify_receipts([{"state": "assigned"}]) == "WH_INPC_NOT_DONE"
    assert classify_receipts([{"state": "done"}]) == "WH_INPC_DONE"
    assert classify_receipts([{"state": "cancel"}]) == "WH_INPC_CANCELLED"


def test_run_audit_writes_readable_outputs(tmp_path):
    summary = run_audit(FakeClient(), tmp_path)
    assert summary["sorting_by_receipt_state"] == {"WH_INPC_DONE": 1}
    assert summary["active_mo_with_invoiced_so"] == 1
    assert summary["input_custom_on_hand"] == 3
    assert (tmp_path / "supply_chain_audit.md").exists()
    assert (tmp_path / "sorting_by_receipt.csv").exists()
