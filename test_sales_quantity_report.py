from decimal import Decimal
import pytest
from sales_quantity_report import build_report, classify, period, whole_quantity


@pytest.mark.parametrize('value,expected', [('12.49', '12'), ('12.5', '13'),
    ('-2.5', '-3'), ('-0.1', '0'), ('0', '0'), ('24.00000000000000096', '24')])
def test_whole_quantity_rounding(value, expected):
    assert whole_quantity(Decimal(value)) == expected


@pytest.mark.parametrize('code,expected', [
    ('USB-C-CAB03-BSK005-A', 'assembled'), (' EUB-C-CAB01-BAS001 ', 'flatpack'),
    ('USB-C-CAB03-SLF010', 'shelf'), ('EUB-C-CAB03-SLF001 CUSTOM', 'shelf'),
    ('USB-C-CAB03-TOP009-A', 'assembled'), ('FPACK-EUB-C-CAB01-BAS001', None),
    ('APACK-USB-C-CAB01-BAS001-A', None), ('UNI-P-ACC01-HRD102-A', None),
    ('EUB-C-CAB01-PNL001', None), ('EUB-C-CAB01-SLF001-PP', None),
    ('EU-SREW-SHELF-1163x564-WW', None), ('EUB-D-CAB99-DOC001', None),
    ('EUB-C-CAB01-UNKNOWN001', None), ('', None)])
def test_classification(code, expected):
    assert classify(code) == expected


def test_inclusive_local_dates_and_dst():
    assert period('2026-09-01', '2026-09-30') == ('2026-08-31 21:00:00', '2026-09-30 21:00:00')
    assert period('2026-10-25', '2026-10-25') == ('2026-10-24 21:00:00', '2026-10-25 22:00:00')
    with pytest.raises(ValueError):
        period('2026-10-01', '2026-09-01')
    with pytest.raises(ValueError):
        period('', '2026-09-01')


class FakeClient:
    uid = 7
    def __init__(self, dedicated=False):
        self.calls = []
        self.field = 'confirmation_date' if dedicated else 'date_order'
    def authenticate(self):
        return self.uid
    def execute(self, model, method, args, kwargs):
        if model == 'res.users':
            return [{'company_id': [1, 'Furnibox']}]
        assert (model, method) == ('sale.order', 'fields_get')
        return {self.field: {'type': 'datetime'}}
    def search_read_all(self, model, domain, fields, context):
        self.calls.append((model, domain, context))
        return {
            'sale.order': [{'id': 10, 'name': 'SO10', self.field: '2026-09-01 10:00:00'}],
            'account.move': [{'id': 20, 'name': 'INV20', 'invoice_date': '2026-09-01', 'move_type': 'out_invoice'},
                             {'id': 21, 'name': 'CN21', 'invoice_date': '2026-09-15', 'move_type': 'out_refund'}],
            'sale.order.line': [{'id': 1, 'order_id': [10, 'SO10'], 'product_id': [100, 'Cabinet'], 'product_uom_qty': 10, 'product_uom': [1, 'Units']},
                                {'id': 2, 'order_id': [10, 'SO10'], 'product_id': [101, 'FPACK'], 'product_uom_qty': 99, 'product_uom': [1, 'Units']}],
            'account.move.line': [{'id': 3, 'move_id': [20, 'INV20'], 'product_id': [100, 'Cabinet'], 'quantity': 2, 'product_uom_id': [2, 'Dozens']},
                                  {'id': 4, 'move_id': [21, 'CN21'], 'product_id': [100, 'Cabinet'], 'quantity': 3, 'product_uom_id': [1, 'Units']}],
            'product.product': [{'id': 100, 'default_code': 'EUB-C-CAB01-BAS001-A', 'name': 'Cabinet', 'uom_id': [1, 'Units']},
                                {'id': 101, 'default_code': 'FPACK-EUB-C-CAB01-BAS001', 'name': 'FPACK', 'uom_id': [1, 'Units']}],
            'uom.uom': [{'id': 1, 'name': 'Units', 'factor': 1, 'category_id': [1, 'Units'], 'uom_type': 'reference'},
                        {'id': 2, 'name': 'Dozens', 'factor': 1/12, 'category_id': [1, 'Units'], 'uom_type': 'bigger'}]
        }[model]


@pytest.mark.parametrize('dedicated', [False, True])
def test_independent_documents_credit_sign_units_company_and_filters(dedicated):
    client = FakeClient(dedicated)
    result = build_report(client, '2026-09-01', '2026-09-30')
    row = result['summary'][0]
    assert row['so'] == 10
    assert abs(row['net'] - Decimal(21)) < Decimal('0.000001')
    assert result['details'][-1]['quantity'] == -3
    assert len(result['details']) == 3
    assert 'FPACK-EUB-C-CAB01-BAS001' in result['excluded']
    domains = {model: domain for model, domain, context in client.calls}
    assert ['state', 'in', ['sale', 'done']] in domains['sale.order']
    assert [client.field, '>=', '2026-08-31 21:00:00'] in domains['sale.order']
    assert [client.field, '<', '2026-09-30 21:00:00'] in domains['sale.order']
    assert ['state', '=', 'posted'] in domains['account.move']
    assert ['invoice_date', '<=', '2026-09-30'] in domains['account.move']
    assert all(context['allowed_company_ids'] == [1] for _, _, context in client.calls)


def test_empty_period_returns_zeroes():
    class Empty(FakeClient):
        def search_read_all(self, *args, **kwargs):
            return []
    result = build_report(Empty(), '2026-09-01', '2026-09-30')
    assert all(row['net'] == row['so'] == 0 for row in result['summary'])
    assert result['details'] == []


def test_cabinet_types_are_separate_and_totals_stay_unrounded():
    class Mixed(FakeClient):
        def search_read_all(self, model, domain, fields, context):
            rows = super().search_read_all(model, domain, fields, context)
            if model == 'product.product':
                for pid, code in [(102, 'USB-C-CAB03-TOP009-A'), (103, 'EUB-C-CAB01-UPP001')]:
                    rows.append({'id': pid, 'default_code': code, 'name': code, 'uom_id': [1, 'Units']})
            if model == 'sale.order.line':
                for pid, qty in [(102, 0.4), (102, 0.4), (103, 7)]:
                    rows.append({'order_id': [10, 'SO10'], 'product_id': [pid, 'Cabinet'],
                                 'product_uom_qty': qty, 'product_uom': [1, 'Units']})
            if model == 'account.move.line':
                rows.append({'move_id': [21, 'CN21'], 'product_id': [103, 'Cabinet'],
                             'quantity': 2, 'product_uom_id': [1, 'Units']})
            return rows
    report = build_report(Mixed(), '2026-09-01', '2026-09-30')
    assembled, flatpack, shelf = report['summary']
    assert [row['label'] for row in assembled['types']] == ['BAS', 'TOP']
    assert assembled['types'][1]['so'] == Decimal('0.8')
    assert whole_quantity(assembled['types'][1]['so']) == '1'
    assert assembled['so'] == Decimal('10.8')
    assert flatpack['types'][0]['label'] == 'UPP'
    assert flatpack['types'][0]['so'] == 7
    assert flatpack['types'][0]['net'] == -2
    assert shelf['types'] == []
    for group in (assembled, flatpack):
        for key in ('so', 'invoice', 'credit', 'net'):
            assert sum(row[key] for row in group['types']) == group[key]


def test_route_validation_does_not_query_odoo(monkeypatch):
    from flask import Flask
    import webapp.sales_quantities as route
    app = Flask(__name__)
    app.register_blueprint(route.sales_quantities)
    monkeypatch.setattr(route, 'render_template', lambda template, **values: values['error'] or 'ok')
    monkeypatch.setattr(route, 'report_client', lambda: pytest.fail('invalid dates must not contact Odoo'))
    assert app.test_client().get('/sales-quantities').status_code == 200
    assert app.test_client().get('/sales-quantities?run=1&start=bad&end=bad').status_code == 400


def test_page_in_real_app_and_auth(monkeypatch, tmp_path):
    from test_webapp import load_webapp
    import webapp.sales_quantities as route
    webapp = load_webapp(monkeypatch, tmp_path)
    monkeypatch.setattr(route, 'report_client', lambda: FakeClient())
    client = webapp.app.test_client()
    page = client.get('/sales-quantities?run=1&start=2026-09-01&end=2026-09-30')
    assert page.status_code == 200
    assert 'CN21' in page.text and 'Surenkami cabinet' in page.text
    assert '· iš viso' in page.text and '>BAS</th>' in page.text
    assert '24.000' not in page.text
    assert '<td>24</td>' in page.text and '<td>-3</td>' in page.text
    monkeypatch.setenv('FURNIBOX_WEB_PASSWORD', 'test-password')
    webapp.SETTINGS = webapp.ProductEngineSettings.from_env(webapp.BASE_DIR)
    assert client.get('/sales-quantities?run=1').status_code == 302
