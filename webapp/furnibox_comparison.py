import csv
import io
import math
import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, Response, session, url_for
import furnibox_comparison as model

comparison = Blueprint('furnibox_comparison', __name__)
COLUMNS = [
 ('sku','Detalės kodas'), ('group','Grupė'), ('furnibox_coefficient','Realus Furnibox koef.'),
 ('reform','Reform pardavimo kaina, €/vnt.'), ('purchase','Furnibox pirkimo kaina, €/vnt.'),
 ('calculated_purchase','Reali pirkimo kaina iš Furnix, €/vnt.'), ('coefficient','Furnix koef. (įvedamas ranka)'),
 ('furnibox_coefficient','Realus Furnibox koef.'), ('material','Plokštė + briaunavimas, €/vnt.'),
 ('difference','Skirtumas: pirkimas − plokštė ir briauna, €/vnt.'),
 ('difference_pct','Skirtumo dalis Furnix pardavimo kainoje, %'),
 ('reform_difference','Skirtumas Reform − pirkimas, €/vnt.'), ('reform_markup','Reform antkainis nuo pirkimo, %'),
 ('basis','Pirkimo kainos pagrindas'), ('note','Duomenų pastaba'), ('po','Pirkimo užsakymas'),
 ('date','Patvirtinimo data'), ('status','Katalogo būsena'), ('name','Detalės pavadinimas')]


@comparison.route('/detail-comparison', methods=['GET','POST'])
def index():
    directory = Path(current_app.config['DETAIL_CALCULATOR_PATHS']['copy']).parent / 'furnibox_comparison'
    token = session.setdefault('comparison_csrf', secrets.token_urlsafe(32))
    error = None
    if request.method == 'POST':
        if not secrets.compare_digest(request.form.get('csrf_token',''), token):
            abort(400)
        try:
            action = request.form.get('action')
            if action == 'coefficient':
                model.save_coefficient(directory, request.form.get('sku'), request.form.get('coefficient'))
            elif action == 'rates':
                model.save_rates(directory, request.form)
            else:
                abort(400)
            return redirect(url_for('.index', q=request.args.get('q',''), group=request.args.get('group',''),
                                    status=request.args.get('status',''), page=request.args.get('page',1), saved='1'))
        except ValueError as exc:
            error = str(exc)
    rates, all_rows = model.results(directory)
    q = request.args.get('q','').strip().casefold()
    group, status = request.args.get('group',''), request.args.get('status','')
    rows = [r for r in all_rows if (not q or q in (r['sku']+' '+r['name']).casefold())
            and (not group or r['group']==group) and (not status or r['status']==status)]
    if request.args.get('export') == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=';')
        writer.writerow([label for key,label in COLUMNS])
        for row in rows:
            values = []
            for key, _ in COLUMNS:
                value = row[key]
                if isinstance(value, (int,float)):
                    value = f'{value*100 if key in ("difference_pct","reform_markup") else value:.6f}'.replace('.',',')
                elif value is None:
                    value = 'Netaikoma' if key=='material' else ''
                elif str(value).startswith(('=','+','-','@','\t','\r')):
                    value = "'"+str(value)
                values.append(value)
            writer.writerow(values)
        return Response('\ufeff'+output.getvalue(), mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="Furnibox_kainu_palyginimas.csv"'})
    try:
        page = max(1, int(request.args.get('page',1)))
    except ValueError:
        abort(400)
    pages = max(1, math.ceil(len(rows)/100)); page = min(page,pages)
    return render_template('furnibox_comparison.html', rows=rows[(page-1)*100:page*100], total=len(all_rows),
        matched=len(rows), groups=sorted({r['group'] for r in all_rows}), q=request.args.get('q',''), group=group,
        status=status, page=page, pages=pages, rates=rates, labels=model.RATE_LABELS, columns=COLUMNS,
        csrf_token=token, error=error, saved=request.args.get('saved')=='1', source=model.source())
