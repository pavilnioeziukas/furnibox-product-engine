import csv
import io
from flask import Blueprint, abort, render_template, request, Response
from price_calculators import calculate, defaults, number, source

calculators = Blueprint('calculators', __name__)


@calculators.route('/calculators/<kind>', methods=['GET', 'POST'])
def calculator(kind):
    if kind not in ('panel', 'shelf'):
        abort(404)
    data = source(kind)
    rates = defaults(kind)
    values = request.form if request.method == 'POST' else request.args
    try:
        index = int(values.get('row', 0))
        if index < 0 or index >= len(data['rows']):
            abort(400)
    except ValueError:
        abort(400)
    row = dict(data['rows'][index])
    error = None
    result = None
    results = []
    try:
        if request.method == 'POST':
            for key in rates:
                rates[key] = number(values.get('rate_'+key), key)
            if values.get('action') != 'export':
                for key in ('length', 'width'):
                    row[key] = number(values.get(key), key, True)
                if kind == 'panel':
                    row['color'] = values.get('color')
                else:
                    row['kind'] = values.get('kind')
                    for key in ('packaging', 'cardboard'):
                        row[key] = None if values.get(key, '') == '' else number(values[key], key)
        result = calculate(kind, row, rates)
        for item in data['rows']:
            results.append((item, calculate(kind, item, rates)))
        if values.get('action') == 'export' and request.method == 'POST':
            output = io.StringIO(newline='')
            writer = csv.writer(output, delimiter=';')
            writer.writerow(['SKU', 'Šaltinio eilutė', 'Plotas m²', 'Apskaičiuota suma EUR', 'Pastabos'])
            for item, calculated in results:
                writer.writerow([item['sku'], item.get('source_row',''), calculated['area'],
                                 calculated['total'] if calculated['total'] is not None else '',
                                 '; '.join(item.get('issues', [])) or calculated['message']])
            return Response('\ufeff'+output.getvalue(), mimetype='text/csv; charset=utf-8',
                            headers={'Content-Disposition':f'attachment; filename="{kind}_prices.csv"'})
    except ValueError as exc:
        error = str(exc)
    return render_template('calculators.html', kind=kind, data=data, rates=rates, row=row,
                           selected=index, result=result, results=results, error=error)
