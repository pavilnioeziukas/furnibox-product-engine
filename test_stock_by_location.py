from run_stock_by_location import StockByLocationReport


class FakeClient:
    def __init__(self, lines, uoms):
        self.lines = lines
        self.uoms = uoms
        self.search_calls = []

    def search(self, model, domain, **kwargs):
        self.search_calls.append((model, domain))
        return [line["id"] for line in self.lines]

    def read(self, model, record_ids, fields=None):
        records = self.lines if model == "purchase.order.line" else self.uoms
        wanted = set(record_ids)
        return [record for record in records if record["id"] in wanted]


def test_active_po_remaining_filters_received_and_converts_to_product_uom():
    client = FakeClient(
        lines=[
            {
                "id": 1,
                "product_id": [10, "A"],
                "product_qty": 3,
                "qty_received": 1,
                "product_uom": [2, "Dozen"],
            },
            {
                "id": 2,
                "product_id": [10, "A"],
                "product_qty": 5,
                "qty_received": 5,
                "product_uom": [1, "Units"],
            },
        ],
        uoms=[
            {"id": 1, "category_id": [7, "Unit"], "factor": 1, "rounding": 1},
            {"id": 2, "category_id": [7, "Unit"], "factor": 1 / 12, "rounding": 1},
        ],
    )
    report = StockByLocationReport(client)
    products = [{"id": 10, "default_code": "SKU-A", "uom_id": [1, "Units"]}]

    result = report.load_active_po_remaining(products)

    assert result == {"SKU-A": 24.0}
    assert client.search_calls == [
        (
            "purchase.order.line",
            [
                ("state", "in", ["purchase", "done"]),
            ],
        )
    ]


def test_active_po_remaining_sums_lines_and_ignores_over_received_quantity():
    client = FakeClient(
        lines=[
            {"id": 1, "product_id": [10, "A"], "product_qty": 10, "qty_received": 4, "product_uom": [1, "Units"]},
            {"id": 2, "product_id": [10, "A"], "product_qty": 8, "qty_received": 3, "product_uom": [1, "Units"]},
            {"id": 3, "product_id": [10, "A"], "product_qty": 2, "qty_received": 3, "product_uom": [1, "Units"]},
        ],
        uoms=[{"id": 1, "category_id": [7, "Unit"], "factor": 1, "rounding": 0.01}],
    )
    report = StockByLocationReport(client)
    products = [{"id": 10, "default_code": "SKU-A", "uom_id": [1, "Units"]}]

    assert report.load_active_po_remaining(products) == {"SKU-A": 11.0}


def test_report_adds_lithuanian_column_without_changing_existing_columns(monkeypatch):
    report = StockByLocationReport(FakeClient([], []))
    products = [{"id": 10, "default_code": "SKU-A", "uom_id": [1, "Units"]}]
    monkeypatch.setattr(report, "load_products", lambda: products)
    monkeypatch.setattr(report, "load_categories", lambda products: {})
    monkeypatch.setattr(report, "find_buy_product_ids", lambda **kwargs: set())
    monkeypatch.setattr(report, "load_location_balances", lambda location_id: {})
    monkeypatch.setattr(report, "load_last_purchases", lambda product_ids: {})
    monkeypatch.setattr(report, "load_active_po_remaining", lambda products: {"SKU-A": 7.5})
    monkeypatch.setattr(
        report,
        "build_rows",
        lambda **kwargs: [{"SKU": "SKU-A", "WH On Hand": 2.0}],
    )
    captured = {}
    monkeypatch.setattr(report, "export_to_excel", lambda rows: captured.setdefault("rows", rows) or "unused")

    report.run()

    assert captured["rows"] == [
        {"SKU": "SKU-A", "WH On Hand": 2.0, "Aktyviuose PO dar negauta": 7.5}
    ]
