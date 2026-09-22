import copy
import csv
import io
import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, request, Response, session
import detail_calculator as model
from cabinet_parts_price_v1 import load_target_cabinet_parts, parse_dimensions, parse_color
from price_calculators import source, number

detail_calculators = Blueprint('detail_calculators', __name__)
KINDS = {'shelf': 'Lentynos', 'panel': 'Panelės', 'cabinet': 'Cabinet Parts'}
LABELS = {
    'WW': 'WW medžiaga, €/m²', 'BB': 'BB medžiaga, €/m²', 'NO': 'NO medžiaga, €/m²',
    'work': 'Bazinis darbas, €/m²', 'fixed': 'Fiksuota dalis, €/vnt.',
    'packaging': 'Pakuotė, €/m²', 'extra_work': 'Papildomas darbas, €/m²',
    'small_limit': 'Mažo ploto riba, m²', 'medium_limit': 'Vidutinio ploto riba, m²',
    'small': 'Mažo ploto koeficientas', 'medium': 'Vidutinio ploto koeficientas',
    'large': 'Didelio ploto koeficientas', 'back_rate_per_m2': 'BACK tarifas, €/m²',
    'processing_rate_per_m2': 'Apdirbimo tarifas, €/m²',
    'ww_material_rate_per_m2': 'WW medžiaga, €/m²', 'bb_material_rate_per_m2': 'BB medžiaga, €/m²',
    'no_material_rate_per_m2': 'NO medžiaga, €/m²',
    'small_part_threshold_m2': 'Mažos detalės ploto riba, m²',
    'small_part_surcharge': 'Mažos detalės priedas, €',
    'furnix_markup_percent': 'Furnix perdavimo antkainis, %',
    'output_decimals': 'Apvalinimo skaitmenų skaičius',
}


def cabinet_rows(dataset_path):
    rows = []
    if Path(dataset_path).exists():
        for sku in sorted(load_target_cabinet_parts(Path(dataset_path)).values()):
            length, width = parse_dimensions(sku)
            rows.append(dict(sku=sku, length=length, width=width, color=parse_color(sku),
                             part_type='BACK' if 'BACK' in sku.upper() else 'STANDARD'))
    return rows


@detail_calculators.route('/detail-calculator', methods=['GET', 'POST'])
@detail_calculators.route('/detail-calculator/<kind>', methods=['GET', 'POST'])
def calculator(kind='shelf'):
    if kind not in KINDS:
        abort(404)
    paths = current_app.config['DETAIL_CALCULATOR_PATHS']
    stored = model.load(paths['copy'], paths['cabinet'])
    config = copy.deepcopy(stored)
    rows = cabinet_rows(paths['dataset']) if kind == 'cabinet' else source(kind)['rows']
    source_label = 'Patvirtintas detalių katalogas'
    if kind == 'cabinet' and not rows:
        from webapp.app import _latest_job_for, _job_file
        latest = _latest_job_for('refresh_reform_pricing')
        dataset = _job_file(latest, 'Furnibox_Target_Dataset.json')
        if dataset:
            rows = cabinet_rows(dataset)
            source_label = 'Paskutinio kainodaros perskaičiavimo detalių katalogas'
    values = request.form if request.method == 'POST' else request.args
    try:
        selected = int(values.get('row', -1 if kind == 'cabinet' else 0))
    except ValueError:
        abort(400)
    if selected < -1 or selected >= len(rows) or (selected == -1 and kind != 'cabinet'):
        abort(400)
    row = dict(rows[selected]) if selected >= 0 else dict(
        sku='Rankinė detalė', length=600, width=400, color='WW', part_type='STANDARD')
    token = session.setdefault('detail_calculator_csrf', secrets.token_urlsafe(32))
    error = None
    saved = False
    result = None
    results = []
    groups = [kind] + (['area'] if kind == 'shelf' else [])
    action = values.get('action', 'calculate')
    try:
        if request.method == 'POST':
            if not secrets.compare_digest(values.get('csrf_token', ''), token):
                abort(400)
            if action not in ('calculate', 'save', 'export'):
                abort(400)
            for group in groups:
                config[group] = {key: values.get(group+'_'+key) for key in stored[group]}
            config = model.validate(config)
            if action == 'save':
                model.save(paths['copy'], config)
                saved = True
            elif action != 'export':
                row['length'] = number(values.get('length'), 'Ilgis', True)
                row['width'] = number(values.get('width'), 'Plotis', True)
                if kind == 'shelf':
                    row['kind'] = values.get('shelf_kind')
                    for key in ('packaging', 'cardboard'):
                        row[key] = number(values[key], key) if values.get(key) else None
                    row['source_multiplier'] = number(values.get('source_multiplier'), 'Šaltinio daugiklis')
                else:
                    row['color'] = values.get('color')
                    if row['color'] not in ('WW', 'BB', 'NO'):
                        raise ValueError('Pasirinkite WW, BB arba NO spalvą.')
                    if kind == 'cabinet':
                        row['part_type'] = values.get('part_type')
                        if row['part_type'] not in ('BACK', 'STANDARD'):
                            raise ValueError('Nežinomas detalės tipas.')
        result = model.compute(kind, row, config)
        for item in rows:
            try:
                calculated = model.compute(kind, item, config)
            except ValueError as exc:
                calculated = dict(total=None, area=None, message=str(exc))
            results.append((item, calculated))
        if request.method == 'POST' and action == 'export':
            if not rows:
                raise ValueError('Nėra katalogo eilučių eksportui. Rankinės detalės rezultatą žiūrėkite apačioje.')
            output = io.StringIO(newline='')
            writer = csv.writer(output, delimiter=';')
            writer.writerow(['SKU', 'Šaltinio eilutė', 'Plotas m²', 'Viso EUR', 'Pastabos'])
            for item, calculated in results:
                total = calculated['total']
                if total is not None and kind == 'cabinet':
                    total = round(total, config['cabinet']['output_decimals'])
                writer.writerow([item['sku'], item.get('source_row', ''), calculated['area'],
                                 total if total is not None else '',
                                 '; '.join(item.get('issues', []) + [calculated['message']]).strip('; ')])
            return Response('\ufeff'+output.getvalue(), mimetype='text/csv; charset=utf-8',
                            headers={'Content-Disposition': f'attachment; filename="detail_{kind}.csv"'})
    except (ValueError, KeyError) as exc:
        error = str(exc)
        result = None
        config = stored
    return render_template('detail_calculator.html', kind=kind, kinds=KINDS, config=config,
                           groups=groups, labels=LABELS, rows=rows, row=row, selected=selected,
                           result=result, results=results, error=error, saved=saved, csrf_token=token,
                           source_label=source_label,
                           has_copy=Path(paths['copy']).exists(),
                           decimals=config['cabinet']['output_decimals'] if kind == 'cabinet' else 4)
