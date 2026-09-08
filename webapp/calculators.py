import csv
import io
from flask import Blueprint, abort, render_template, request, Response
from price_calculators import calculate, defaults, number, source
import shelf_workbook

calculators = Blueprint('calculators', __name__)


@calculators.route('/shelf-workbook', methods=['GET', 'POST'])
def shelf_file():
    data=shelf_workbook.load()
    view=request.args.get('view','bom')
    if view not in ('bom','led','legacy','purchase','rates','source','related'):abort(404)
    query=request.args.get('q','').strip()
    selected=request.args.get('item','')
    rows=[];detail=None;error=None
    if view=='bom':rows=shelf_workbook.bom_results(data)
    elif view=='legacy':rows=shelf_workbook.legacy_results(data)
    elif view=='led':rows=shelf_workbook.led_results(data)
    elif view=='purchase':rows=data['purchase']
    if query:rows=[r for r in rows if query.casefold() in str(r).casefold()]
    if view in ('bom','led') and rows:
        detail=next((r for r in rows if r['sku']==selected),rows[0] if not selected else None)
    if request.method=='POST':
        if detail is None or view not in ('bom','led'):abort(400)
        try:
            if view=='bom':
                for line in detail['lines']:
                    suffix=str(line['row'])
                    line['qty']=number(request.form.get('qty_'+suffix),'Kiekis')
                    unit=request.form.get('unit_'+suffix,'')
                    line['unit']=number(unit,'Vieneto kaina') if unit!='' else None
                    line['cost']=line['qty']*line['unit'] if line['unit'] is not None else None
                detail['total']=sum(r['cost']for r in detail['lines'])if all(r['cost']is not None for r in detail['lines'])else None
                detail['unweighted']=sum(r['unit']for r in detail['lines'])if all(r['unit']is not None for r in detail['lines'])else None
                detail['difference']=detail['total']-detail['unweighted']if detail['total']is not None else None
            else:
                detail['parts']=[(label,number(request.form.get('cost_'+str(i)),'Kainos dalis'))for i,label in enumerate(shelf_workbook.LED_LABELS)]
                detail['total']=sum(value for label,value in detail['parts'])
        except ValueError as exc:
            error=str(exc)
            detail['total']=None
    sheet=None;page=1;pages=1
    if view=='source':
        try:
            index=int(request.args.get('sheet',0));page=max(1,int(request.args.get('page',1)))
            if index<0 or index>=len(data['sheets']):abort(400)
        except ValueError:abort(400)
        sheet=data['sheets'][index]
        rows=sheet['rows']
        if query:rows=[r for r in rows if query.casefold() in str(r).casefold()]
        pages=max(1,(len(rows)+49)//50);page=min(page,pages);rows=rows[(page-1)*50:page*50]
    related=shelf_workbook.evidence(query) if view=='related' and query else None
    return render_template('shelf_workbook.html',data=data,view=view,query=query,rows=rows,detail=detail,error=error,
                           sheet=sheet,page=page,pages=pages,related=related,logical_rates=defaults('shelf'))


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
