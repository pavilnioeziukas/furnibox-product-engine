"""Independent, immutable Pivot-to-Pivot comparisons. No Odoo or proposal writes."""
import hashlib
import json
import io
import math
import secrets
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, send_file, url_for, has_request_context
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from webapp.reform_workspace import reform, db, owner, now, pack, unpack, baseline
from webapp.reform_excel import LIMIT, read_book
from webapp.reform_pivot import ALIASES, NAME, HEADERS


class PivotError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('Pivot validation failed.')


def code(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse(content, allow_empty=False):
    try:
        wb = read_book(content)
    except ValueError as exc:
        raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Choose a readable Excel workbook smaller than 5 MB containing the Pivot sheet.'}]) from exc
    try:
        candidates, issues = [], []
        for name in ALIASES:
            if name not in wb:
                continue
            ws = wb[name]
            if ws.max_row > 20032 or ws.max_column > 20:
                raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Pivot sheet exceeds the 20,000-row / 20-column limit.'}])
            rows = list(ws.iter_rows())
            header = next((i for i, r in enumerate(rows[:30]) if [code(c.value) for c in r[:3]] == HEADERS), None)
            if header is None:
                issues.append({'row': '', 'sku': '', 'material': '', 'reason': f'{name}: SKU / MATERIAL_SKU / Total headers are required in columns A:C.'})
                continue
            data, seen = [], set()
            for n, cells in enumerate(rows[header + 1:], header + 2):
                values = [c.value for c in cells]
                if not any(code(v) for v in values):
                    continue
                parent, material = code(values[0]), code(values[1])
                reason = ''
                if any(c.data_type == 'f' for c in cells):
                    reason = 'Paste values instead of formulas.'
                elif not parent or not material:
                    reason = 'SKU and MATERIAL_SKU must be present on every data row. Remove subtotals and grand totals.'
                elif any(code(v) for v in values[3:]):
                    reason = 'Only three data columns are supported: SKU / MATERIAL_SKU / Total.'
                elif (parent, material) in seen:
                    reason = 'Duplicate SKU / MATERIAL_SKU pair. Supply one quantity per pair.'
                try:
                    quantity = Decimal(code(values[2]).replace(',', '.'))
                    if (isinstance(values[2], bool) or not quantity.is_finite() or quantity < 0 or
                            not math.isfinite(float(quantity)) or (quantity != 0 and float(quantity) == 0)):
                        raise InvalidOperation()
                except (InvalidOperation, ValueError):
                    quantity = None
                    if not reason:
                        reason = 'Total must be a finite number greater than or equal to zero.'
                if reason:
                    issues.append({'row': n, 'sku': parent, 'material': material, 'reason': reason})
                else:
                    seen.add((parent, material))
                    data.append({'sku': parent, 'material': material, 'quantity': str(quantity), 'row': n})
            if data:
                candidates.append(data)
        if issues:
            raise PivotError(issues)
        if not candidates and allow_empty:
            return []
        if len(candidates) != 1:
            raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Supply exactly one populated Product MBOM Pivot or Product MBOMs - Pivot sheet.'}])
        return candidates[0]
    finally:
        wb.close()


NON_BOM_HEADERS = ['Product code', 'Name', 'Category', 'Unit', 'Supplier Code']


def parse_non_bom(content):
    """Read optional non-BOM product cards without interpreting them as BOM rows."""
    wb = read_book(content)
    try:
        if 'Non-BOM' not in wb:
            return []
        ws = wb['Non-BOM']
        if ws.max_row > 20001 or ws.max_column > 5:
            raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Non-BOM: maximum 20,000 rows and five columns.'}])
        rows = list(ws.iter_rows(min_col=1, max_col=5))
        if [code(c.value) for c in rows[0]] != NON_BOM_HEADERS:
            raise PivotError([{'row': 1, 'sku': '', 'material': '', 'reason': 'Non-BOM: keep headers Product code / Name / Category / Unit / Supplier Code.'}])
        cards, issues, seen = [], [], set()
        for number, cells in enumerate(rows[1:], 2):
            values = [code(c.value) for c in cells]
            if not any(values):
                continue
            sku, name, category, unit, supplier = values
            reason = ''
            if any(c.data_type == 'f' for c in cells):
                reason = 'Non-BOM: paste values instead of formulas.'
            elif not sku:
                reason = 'Non-BOM: Product code is required.'
            elif sku.casefold() in seen:
                reason = 'Non-BOM: duplicate Product code (including differences in letter case).'
            if reason:
                issues.append({'row': number, 'sku': sku, 'material': '', 'reason': reason})
            seen.add(sku.casefold())
            cards.append(dict(sku=sku, name=name, category=category, unit=unit, supplier=supplier, row=number))
        if issues:
            raise PivotError(issues)
        return cards
    finally:
        wb.close()


def check_non_bom(cards, catalogue, pivot_rows):
    """Freeze newness and validation against the catalogue captured at upload time."""
    if not cards:
        return {'new': [], 'existing': 0, 'checked': 0}
    if not catalogue:
        raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Non-BOM: load a catalogue before checking whether product codes are new.'}])
    products = catalogue['products']
    folded = {}
    for sku in products:
        folded.setdefault(sku.casefold(), []).append(sku)
    parents = {r['sku'].casefold() for r in pivot_rows}
    parents.update(b['sku'].casefold() for b in catalogue['boms'].values())
    units = {p['uom'] for p in products.values()}
    new, issues, existing = [], [], 0
    for card in cards:
        sku = card['sku']
        reason = ''
        if sku.casefold() in parents:
            reason = 'Non-BOM: this product is a BOM parent. Supply its card in Products, not Non-BOM.'
        elif sku in products:
            existing += 1
            continue
        elif sku.casefold() in folded:
            reason = 'Non-BOM: code differs only in letter case from existing code(s): ' + ', '.join(folded[sku.casefold()])
        elif not all(card[k] for k in ('name', 'category', 'unit')):
            reason = 'Non-BOM: new items require Name, Category and Unit.'
        elif card['unit'] not in units:
            reason = 'Non-BOM: unknown Unit. Use a unit from the current catalogue.'
        if reason:
            issues.append({'row': card['row'], 'sku': sku, 'material': '', 'reason': reason})
        else:
            new.append(card)
    if issues:
        raise PivotError(issues)
    return {'new': new, 'existing': existing, 'checked': len(cards),
            'source': catalogue.get('source', ''), 'captured_at': catalogue.get('captured_at', '')}


def compare(before, after, scope='uploaded'):
    if not after:
        scope = 'uploaded'  # A non-BOM-only upload cannot remove BOMs.
    new = {(r['sku'], r['material']): r for r in after}
    uploaded_skus = {r['sku'] for r in after}
    old = {(r['sku'], r['material']): r for r in before
           if scope == 'all' or r['sku'] in uploaded_skus}
    result, unchanged = [], 0
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        x, y = (Decimal(a['quantity']) if a else None), (Decimal(b['quantity']) if b else None)
        if a and b and x == y:
            unchanged += 1
            continue
        result.append({'sku': key[0], 'material': key[1], 'old': str(x) if a else None,
                       'new': str(y) if b else None, 'difference': str((y or Decimal(0)) - (x or Decimal(0))),
                       'status': 'Added' if not a else 'Removed' if not b else 'Quantity changed',
                       'old_row': a['row'] if a else None, 'new_row': b['row'] if b else None})
    return {'changes': result, 'unchanged': unchanged, 'old_count': len(old), 'new_count': len(after),
            'scope': scope, 'ignored': len(before) - len(old),
            'added': sum(r['status'] == 'Added' for r in result),
            'removed': sum(r['status'] == 'Removed' for r in result),
            'changed': sum(r['status'] == 'Quantity changed' for r in result)}


def displayed_report(before, saved, scope=None):
    """Reconstruct legacy full comparisons without changing their stored evidence."""
    after = saved.get('uploaded_rows')
    if after is None:
        changed = {(r['sku'], r['material']): r for r in saved['changes']}
        after = [r for r in before if (r['sku'], r['material']) not in changed]
        after += [{'sku': r['sku'], 'material': r['material'], 'quantity': r['new'], 'row': r['new_row']}
                  for r in saved['changes'] if r['new'] is not None]
    selected = scope if scope in ('uploaded', 'all') else saved.get('scope', 'uploaded')
    report = compare(before, after, selected)
    report['non_bom'] = saved.get('non_bom')
    return report


def schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS pivot_confirmations (result_id TEXT PRIMARY KEY, actor TEXT NOT NULL, created TEXT NOT NULL, package_digest TEXT NOT NULL, payload BLOB NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS pivot_references (id TEXT PRIMARY KEY, label TEXT, filename TEXT, actor TEXT, created TEXT, sha256 TEXT, payload BLOB)')
    conn.execute('CREATE TABLE IF NOT EXISTS pivot_comparisons (id TEXT PRIMARY KEY, reference_id TEXT, filename TEXT, actor TEXT, created TEXT, sha256 TEXT, payload BLOB)')


def save_reference(conn, rows, label, filename, sha256, reference_id=None):
    schema(conn)
    key = reference_id or secrets.token_hex(16)
    existing = conn.execute('SELECT * FROM pivot_references WHERE id=?', (key,)).fetchone()
    if existing:
        if existing['sha256'] != sha256:
            raise ValueError('An immutable reference with this identifier already exists.')
        return key
    conn.execute('INSERT INTO pivot_references VALUES (?,?,?,?,?,?,?)',
                 (key, label, filename, owner() if has_request_context() else 'Furnibox import', now(), sha256, pack(rows)))
    return key


def reference(conn, key=None):
    schema(conn)
    return (conn.execute('SELECT * FROM pivot_references WHERE id=?', (key,)).fetchone() if key else
            conn.execute('SELECT * FROM pivot_references ORDER BY created DESC LIMIT 1').fetchone())


def upload(candidate=False):
    file = request.files.get('file')
    if not file or not file.filename.lower().endswith(('.xlsx', '.xlsm')):
        raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Select an .xlsx or .xlsm workbook containing the Pivot sheet.'}])
    raw = file.stream.read(LIMIT + 1)
    return file.filename[:200], raw, parse(raw, allow_empty=candidate)


def page(result_id=None, issues=None, status=200):
    with db() as conn:
        schema(conn)
        item = conn.execute('SELECT * FROM pivot_comparisons WHERE id=?', (result_id,)).fetchone() if result_id else None
        if result_id and not item:
            abort(404)
        ref = reference(conn, item['reference_id'] if item else None)
        confirmation = conn.execute('SELECT * FROM pivot_confirmations WHERE result_id=?', (result_id,)).fetchone() if item else None
        summary = (unpack(confirmation['payload']) if confirmation else displayed_report(unpack(ref['payload']), unpack(item['payload']), request.args.get('scope'))) if item else None
        package_digest = confirmation_digest(ref, item, summary) if item else ''
        query = request.args.get('q', '').strip()[:200]
        changed = summary['changes'] if summary else []
        if query:
            changed = [r for r in changed if query.casefold() in (r['sku'] + ' ' + r['material']).casefold()]
        try:
            number = max(1, int(request.args.get('page', 1)))
        except ValueError:
            number = 1
        pages = max(1, (len(changed) + 99) // 100)
        number = min(number, pages)
        visible = changed[(number - 1) * 100:number * 100]
        base_count = len(unpack(ref['payload'])) if ref else 0
        recent = conn.execute('SELECT p.id,p.filename,p.actor,p.created,c.actor AS confirmed_by,c.created AS confirmed_at FROM pivot_comparisons p LEFT JOIN pivot_confirmations c ON c.result_id=p.id ORDER BY p.created DESC LIMIT 20').fetchall()
    return render_template('reform_pivot_compare.html', reference=ref, base_count=base_count,
                           result=item, summary=summary, rows=visible, issues=(issues or [])[:200],
                           issue_count=len(issues or []), query=query, page=number, pages=pages,
                           confirmation=confirmation, package_digest=package_digest, recent=recent), status


@reform.get('/pivot-compare')
def pivot_compare():
    return page()


@reform.post('/pivot-compare/reference')
def pivot_reference_upload():
    try:
        filename, raw, rows = upload()
        label = request.form.get('label', '').strip()[:100]
        if not label:
            raise ValueError('Enter a reference version name, for example BOM v10.')
        with db() as conn:
            save_reference(conn, rows, label, filename, hashlib.sha256(raw).hexdigest())
        flash('Reference Pivot saved. Earlier references and reports are preserved.')
        return redirect(url_for('reform.pivot_compare'))
    except PivotError as exc:
        return page(issues=exc.issues, status=400)
    except ValueError as exc:
        return page(issues=[{'row': '', 'sku': '', 'material': '', 'reason': str(exc)}], status=400)


@reform.post('/pivot-compare')
def pivot_compare_upload():
    try:
        filename, raw, rows = upload(candidate=True)
        cards = parse_non_bom(raw)
        if not rows and not cards:
            raise PivotError([{'row': '', 'sku': '', 'material': '', 'reason': 'Supply BOM Pivot rows or Non-BOM items.'}])
        with db() as conn:
            ref = reference(conn, request.form.get('reference_id', ''))
            if not ref:
                abort(409, 'Choose an existing reference Pivot before uploading the new version.')
            selected = 'all' if request.form.get('scope') == 'all' else 'uploaded'
            report = compare(unpack(ref['payload']), rows, selected)
            report['uploaded_rows'] = rows
            report['non_bom'] = check_non_bom(cards, baseline(conn), rows)
            key = secrets.token_hex(16)
            conn.execute('INSERT INTO pivot_comparisons VALUES (?,?,?,?,?,?,?)',
                         (key, ref['id'], filename, owner(), now(), hashlib.sha256(raw).hexdigest(), pack(report)))
        return redirect(url_for('reform.pivot_compare_result', result_id=key))
    except PivotError as exc:
        return page(issues=exc.issues, status=400)
    except ValueError as exc:
        return page(issues=[{'row': '', 'sku': '', 'material': '', 'reason': str(exc)}], status=400)


@reform.get('/pivot-compare/results/<result_id>')
def pivot_compare_result(result_id):
    return page(result_id)


def confirmation_digest(ref, item, report):
    package = {'reference_id': ref['id'], 'reference_sha256': ref['sha256'],
               'result_id': item['id'], 'upload_sha256': item['sha256'], 'report': report}
    return hashlib.sha256(json.dumps(package, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


@reform.post('/pivot-compare/results/<result_id>/confirm')
def pivot_compare_confirm(result_id):
    if not request.form.get('confirm') == 'yes':
        abort(400, 'Confirm that you have reviewed all changes.')
    with db() as conn:
        schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        item = conn.execute('SELECT * FROM pivot_comparisons WHERE id=?', (result_id,)).fetchone()
        if not item:
            abort(404)
        ref = reference(conn, item['reference_id'])
        existing = conn.execute('SELECT * FROM pivot_confirmations WHERE result_id=?', (result_id,)).fetchone()
        if existing:
            if request.form.get('package_digest') != existing['package_digest']:
                abort(409, 'This report was already confirmed with a different scope. Refresh the result.')
        else:
            scope = request.form.get('scope')
            if scope not in ('uploaded', 'all'):
                abort(400, 'Choose a comparison scope.')
            report = displayed_report(unpack(ref['payload']), unpack(item['payload']), scope)
            expected = confirmation_digest(ref, item, report)
            if request.form.get('package_digest') != expected:
                abort(409, 'The reviewed package does not match. Refresh and review the result.')
            if not report['changes'] and not (report.get('non_bom') or {}).get('new'):
                abort(400, 'There are no changes to confirm.')
            conn.execute('INSERT INTO pivot_confirmations VALUES (?,?,?,?,?)',
                         (result_id, owner(), now(), expected, pack(report)))
    flash('Changes confirmed and submitted to Furnibox. The reviewed package is locked.')
    return redirect(url_for('reform.pivot_compare_result', result_id=result_id))


def workbook(headers, rows, title):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    for values in rows:
        ws.append(values)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = PatternFill('solid', fgColor='24496B')
        cell.font = Font(bold=True, color='FFFFFF')
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 38 if col[0].column in (2, 3) else 22
        for cell in col[1:]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
            elif isinstance(cell.value, (int, float)):
                cell.number_format = '0.########'
    return wb


@reform.get('/pivot-compare/template')
def pivot_compare_template():
    wb = workbook(HEADERS, [], NAME)
    ws = wb.create_sheet('Non-BOM')
    ws.append(NON_BOM_HEADERS)
    ws.freeze_panes = 'A2'
    for col in 'ABCDE':
        ws.column_dimensions[col].width = 32
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    return send_file(data, as_attachment=True, download_name='Reform-Pivot-Comparison-Template.xlsx')


@reform.get('/pivot-compare/results/<result_id>/download')
def pivot_compare_download(result_id):
    with db() as conn:
        schema(conn)
        item = conn.execute('SELECT * FROM pivot_comparisons WHERE id=?', (result_id,)).fetchone()
        if not item:
            abort(404)
        ref = reference(conn, item['reference_id'])
        confirmation = conn.execute('SELECT * FROM pivot_confirmations WHERE result_id=?', (result_id,)).fetchone()
        report = unpack(confirmation['payload']) if confirmation else displayed_report(unpack(ref['payload']), unpack(item['payload']), request.args.get('scope'))
    numeric = lambda q: None if q is None else float(Decimal(q))
    wb = workbook(['Change', 'SKU', 'MATERIAL_SKU', 'Reference quantity', 'New quantity', 'Difference', 'Reference row', 'New row'],
                  [[r['status'], r['sku'], r['material'], numeric(r['old']), numeric(r['new']), numeric(r['difference']), r['old_row'], r['new_row']] for r in report['changes']], 'Changes')
    non_bom = report.get('non_bom')
    if non_bom is not None:
        cards = wb.create_sheet('New Non-BOM items')
        cards.append(NON_BOM_HEADERS + ['Source row'])
        for card in non_bom['new']:
            cards.append([card[k] for k in ('sku', 'name', 'category', 'unit', 'supplier', 'row')])
        cards.freeze_panes = 'A2'
        cards.auto_filter.ref = cards.dimensions
        for col in cards.columns:
            cards.column_dimensions[col[0].column_letter].width = 32
            for cell in col:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    info = wb.create_sheet('Sources')
    for row in [['Reference version', ref['label']], ['Reference file', ref['filename']], ['Reference SHA256', ref['sha256']],
                ['New version file', item['filename']], ['New version SHA256', item['sha256']], ['Uploaded by', item['actor']],
                ['Compared at (UTC)', item['created']], ['Added', report['added']], ['Removed', report['removed']],
                ['Quantity changed', report['changed']], ['Unchanged', report['unchanged']],
                ['Comparison scope', 'Complete version: absent rows are removals' if report['scope'] == 'all' else 'Uploaded SKUs: missing components are removals; absent SKUs are unchanged'],
                ['Reference rows outside scope', report['ignored']],
                ['Comparison', 'No Odoo data used. Codes are compared exactly after trimming surrounding spaces.']]:
        info.append(row)
        for cell in info[info.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
    if confirmation:
        for values in [['Status', 'Submitted to Furnibox'], ['Confirmed by', confirmation['actor']],
                       ['Confirmed at (UTC)', confirmation['created']], ['Confirmed package SHA256', confirmation['package_digest']]]:
            info.append(values)
            for cell in info[info.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    if non_bom is not None:
        for values in [['New Non-BOM items', len(non_bom['new'])], ['Existing Non-BOM items ignored', non_bom['existing']],
                       ['Non-BOM catalogue source', non_bom.get('source', '')], ['Non-BOM catalogue captured (UTC)', non_bom.get('captured_at', '')]]:
            info.append(values)
            for cell in info[info.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
    info.column_dimensions['A'].width, info.column_dimensions['B'].width = 28, 110
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    return send_file(data, as_attachment=True, download_name='Reform-Pivot-Changes.xlsx')
