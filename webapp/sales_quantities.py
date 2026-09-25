from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Blueprint, current_app, render_template, request
from sales_quantity_report import build_report, period

sales_quantities = Blueprint('sales_quantities', __name__)


def report_client():
    from config import load_settings
    from odoo_client import OdooClient
    return OdooClient(load_settings())


@sales_quantities.get('/sales-quantities')
def index():
    today = datetime.now(ZoneInfo('Europe/Vilnius')).date()
    start = request.args.get('start', today.replace(day=1).isoformat())
    end = request.args.get('end', today.isoformat())
    report, error, status = None, None, 200
    if request.args.get('run'):
        try:
            period(start, end)
            report = build_report(report_client(), start, end)
        except ValueError as exc:
            error, status = str(exc), 400
        except Exception:
            current_app.logger.exception('Sales quantity report failed')
            error, status = 'Nepavyko nuskaityti Odoo duomenų. Patikrinkite ryšį ir prieigos teises, tada bandykite dar kartą.', 502
    return render_template('sales_quantities.html', report=report, error=error, start=start, end=end), status
