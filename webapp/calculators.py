import csv
import io
from flask import Blueprint, abort, render_template, request, Response
from price_calculators import calculate, defaults, number, source
import shelf_workbook
import calculator_settings
from unified_calculator_pricing import led_results

calculators = Blueprint('calculators', __name__)


@calculators.route('/calculators/settings', methods=['GET', 'POST'])
def settings():
    data = calculator_settings.load()
    error = None
    saved = False
    if request.method == 'POST':
        try:
            data = calculator_settings.save({
                **data,
                'markup_percent': request.form.get('markup_percent'),
                **{kind: {k: request.form.get(kind+'_'+k) for k in defaults(kind)}
                   for kind in ('panel', 'shelf')}
            })
            saved = True
        except (ValueError, KeyError) as exc:
            error = str(exc)
    return render_template('calculator_settings.html', data=data, error=error, saved=saved)

FAMILIES = [('PAPR','Paprastos lentynos','Medinė dalis pagal plotą, tipo tarifą ir pakuotę.'),
            ('FIX','FIX','Fiksuotų lentynų medinės dalies skaičiavimas.'),
            ('FIXVEN','FIXVEN','FIXVEN lentynų medinės dalies skaičiavimas.'),
            ('OVEN','OVEN','OVEN lentynų medinės dalies skaičiavimas.'),
            ('CORNER','CORNER','Kampinių lentynų medinės dalies skaičiavimas.'),
            ('ROD','ROD','Gamyba, profilis, montavimas ir pakuotė.'),
            ('LED','LED','Gamyba, LED profilis, montavimas ir pakuotė.'),
            ('LEDROD','LED + ROD','Atskiras LED + ROD lentynų išskaidymas.')]


@calculators.get('/calculators/shelves')
def shelf_home():
    return render_template('shelf_home.html',families=FAMILIES)


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
    elif view=='led':rows=led_results(calculator_settings.load())
    elif view=='purchase':rows=data['purchase']
    family=request.args.get('family','')
    if family:
        if view!='led' or family not in ('LED','ROD','LEDROD'):abort(400)
        rows=[r for r in rows if r['kind']=={'LED':'tik LED','ROD':'ROD','LEDROD':'LED+ROD'}[family]]
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
                if request.form.get('action') == 'save':
                    config = calculator_settings.load()
                    config['led_costs'][detail['sku']] = [v for _,v in detail['parts']]
                    calculator_settings.save(config)
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
                           sheet=sheet,page=page,pages=pages,related=related,logical_rates=defaults('shelf'),family=family)


@calculators.route('/calculators/<kind>', methods=['GET', 'POST'])
def calculator(kind):
    if kind not in ('panel', 'shelf'):
        abort(404)
    data = source(kind)
    rates = calculator_settings.load()[kind]
    values = request.form if request.method == 'POST' else request.args
    family=values.get('family','')
    if family and (kind!='shelf' or family not in {r[0] for r in FAMILIES}):abort(400)
    available_rows=[(i,r)for i,r in enumerate(data['rows'])if not family or r['kind']=='SREW-SHELF-'+family]
    if not available_rows:abort(404)
    try:
        index = int(values.get('row', available_rows[0][0]))
        if index not in {i for i,r in available_rows}:
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
        for _,item in available_rows:
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
                           selected=index, result=result, results=results, error=error,available_rows=available_rows,family=family)
