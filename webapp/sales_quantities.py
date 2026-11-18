from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Blueprint, current_app, render_template, request
from sales_quantity_report import SO_TAGS, build_report, period, whole_quantity

sales_quantities = Blueprint('sales_quantities', __name__)
sales_quantities.add_app_template_filter(whole_quantity, 'whole_quantity')


def report_client():
    from config import load_settings
    from odoo_client import OdooClient
    return OdooClient(load_settings())


@sales_quantities.get('/sales-quantities')
def index():
    today = datetime.now(ZoneInfo('Europe/Vilnius')).date()
    start = request.args.get('start', today.replace(day=1).isoformat())
    end = request.args.get('end', today.isoformat())
    requested_tags = request.args.getlist('so_tag')
    selected_tags = tuple(tag for tag in SO_TAGS if tag in requested_tags)
    report, error, status = None, None, 200
    if request.args.get('run'):
        try:
            period(start, end)
            if set(requested_tags) - set(SO_TAGS):
                raise ValueError('Pasirinkite galiojančią SO žymą.')
            report = build_report(report_client(), start, end, selected_tags)
        except ValueError as exc:
            error, status = str(exc), 400
        except Exception:
            current_app.logger.exception('Sales quantity report failed')
            error, status = 'Nepavyko nuskaityti Odoo duomenų. Patikrinkite ryšį ir prieigos teises, tada bandykite dar kartą.', 502
    return render_template('sales_quantities.html', report=report, error=error, start=start, end=end,
                           so_tags=SO_TAGS, selected_tags=selected_tags), status
