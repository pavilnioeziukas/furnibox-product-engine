from resolve_bom_archive_blockers import parse_queries, resolve


class FakeClient:
    def __init__(self, fail_archive=False):
        self.writes = []
        self.bom_active = True
        self.qty = 2.0
        self.fail_archive = fail_archive

    def search_read_all(self, model, domain, fields, **kwargs):
        if model == "mrp.bom":
            if fields == ["id", "active"]:
                return [{"id": 42, "active": self.bom_active}]
            return [{"id": 42, "code": "BOM", "active": True, "type": "phantom", "product_id": False, "product_tmpl_id": [10, "[SKU-1] Product"]}]
        if model == "product.product":
            return [{"id": 11, "default_code": "SKU-1", "display_name": "[SKU-1] Product", "product_tmpl_id": [10, "Product"]}]
        if model == "sale.order.line":
            if fields == ["id", "product_uom_qty"]:
                return [{"id": 99, "product_uom_qty": self.qty}]
            return [{"id": 99, "order_id": [7, "SO7"], "product_id": [11, "Product"], "product_uom_qty": 2, "qty_delivered": 0, "qty_invoiced": 0, "display_type": False}]
        if model == "sale.order":
            return [{"id": 7, "name": "SO7", "state": "sale"}]
        return []

    def execute(self, model, method, args=None, kwargs=None):
        self.writes.append((model, method, args))
        values = args[1]
        if model == "sale.order.line":
            self.qty = float(values["product_uom_qty"])
        if model == "mrp.bom":
            if self.fail_archive:
                raise RuntimeError("archive failed")
            self.bom_active = bool(values["active"])
        return True


def test_parse_queries_accepts_multiple_separators_and_deduplicates():
    assert parse_queries("sku-1, SKU-2\nsku-1") == ["SKU-1", "SKU-2"]


def test_resolution_archives_bom_and_restores_quantity():
    client = FakeClient()
    result = resolve(client, ["SKU-1"])
    assert result["status"] == "COMPLETED"
    assert result["archived_bom_ids"] == [42]
    assert result["restored_lines"][0]["quantity"] == 2.0
    assert client.qty == 2.0
    assert client.bom_active is False
    assert client.writes == [
        ("sale.order.line", "write", [[99], {"product_uom_qty": 0.0}]),
        ("mrp.bom", "write", [[42], {"active": False}]),
        ("sale.order.line", "write", [[99], {"product_uom_qty": 2.0}]),
    ]


def test_quantity_is_restored_when_archive_fails():
    client = FakeClient(fail_archive=True)
    try:
        resolve(client, ["SKU-1"])
    except RuntimeError as exc:
        assert str(exc) == "archive failed"
    else:
        raise AssertionError("Expected archive failure")
    assert client.qty == 2.0
