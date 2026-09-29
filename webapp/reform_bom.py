"""Two-level Excel exchange: each assembly and its immediate components, once."""
from collections import defaultdict
from math import ceil

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HEADERS = ['Parent BOM SKU', 'Component SKU', 'Quantity', 'Unit', 'Supplier Code',
           'Action', 'Note', 'BOM key', 'Line ID']
MAX_ROWS = 20000


def supplier_codes(record, sku):
    product = record['scope']['products'].get(sku, {})
    return '; '.join(record.get('supplier_codes', {}).get(sku, product.get('supplier_codes', [])))


def component_rows(record):
    for key, bom in sorted(record['scope']['boms'].items(), key=lambda item: (item[1]['sku'], item[0])):
        for line in bom['components']:
            yield [bom['sku'], line['sku'], line['quantity'], line['uom'],
                   supplier_codes(record, line['sku']), 'KEEP',
                   bom.get('read_only', ''), key, line['id']]


def add_vertical_bom(wb, record):
    sheet = wb.create_sheet('BOM', 0)
    sheet.append(HEADERS)
    for row in component_rows(record):
        sheet.append(row)
    if sheet.max_row > MAX_ROWS + 1:
        raise ValueError('The BOM exceeds 20,000 component rows. Export a smaller product selection.')
    sheet.column_dimensions['H'].hidden = True
    sheet.column_dimensions['I'].hidden = True
    wb['Components'].sheet_state = 'veryHidden'
    non = wb.create_sheet('Non-BOM', 1)
    cards = wb['Products']
    card_headers = ['Product code', 'Name', 'Category', 'Unit', 'Supplier Code']
    non.append(card_headers)
    # Split cards once rather than repeatedly shifting thousands of worksheet rows.
    values = list(cards.values)[1:]
    cards.delete_rows(1, cards.max_row)
    cards.append(card_headers)
    parents = {b['sku'] for b in record['scope']['boms'].values()}
    for row in values:
        target = cards if row[0] in parents else non
        target.append(list(row) + [supplier_codes(record, row[0])])
    for name, col in [('Categories', 'C'), ('Units', 'D')]:
        if name in wb.defined_names:
            rule = DataValidation(type='list', formula1=name, allow_blank=False)
            rule.showErrorMessage = True
            non.add_data_validation(rule)
            rule.add(f'{col}2:{col}10001')
    action = DataValidation(type='list', formula1='"KEEP,REMOVE"', allow_blank=False)
    action.showErrorMessage = True
    sheet.add_data_validation(action)
    action.add(f'F2:F{MAX_ROWS + 1}')

    body = Font(name='Calibri', size=9, color='243746')
    bold = Font(name='Calibri', size=9, bold=True, color='24496B')
    header = Font(name='Calibri', size=9, bold=True, color='FFFFFF')
    fills = [PatternFill('solid', fgColor=color) for color in ('E4EDF7', 'FCECDD')]
    group_fills = [PatternFill('solid', fgColor=color) for color in ('B8CCE4', 'FCE9D9')]
    top = Border(top=Side(style='medium', color='344F6A'))
    empty = Border()
    for ws in wb:
        if ws.sheet_state != 'visible':
            continue
        ws.sheet_view.showGridLines = False
        for row in ws:
            for cell in row:
                cell.font = header if cell.row == 1 else body
            if row[0].row > 1 and ws.title != 'Instructions':
                ws.row_dimensions[row[0].row].height = 20
    for ws in (sheet, cards, non):
        ws.freeze_panes = 'B2' if ws == sheet else 'A2'
        ws.auto_filter.ref = ws.dimensions
        ws.print_title_rows = '1:1'
        ws.row_dimensions[1].height = 30
        widths = [34, 38, 12, 12, 28, 12, 48, 16, 16] if ws == sheet else [34, 52, 38, 12, 28]
        for col, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = width
        for cell in ws[1]:
            color = '24496B' if ws != sheet or cell.column == 1 else '276B66' if cell.column in (2, 3) else '80613E' if cell.column == 6 else '586779'
            cell.fill = PatternFill('solid', fgColor=color)
            cell.font = header
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        previous = None
        stripe = 0
        for row in ws.iter_rows(min_row=2):
            key = row[7].value if ws == sheet else None
            start = ws == sheet and key != previous
            if start:
                stripe += 1
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                cell.font = bold if ws == sheet and cell.column == 1 else body
                cell.fill = (group_fills if ws == sheet else fills)[stripe % 2]
                cell.border = top if start else empty
                cell.alignment = Alignment(vertical='center', horizontal='right' if isinstance(cell.value, (int, float)) else 'left')
                cell.number_format = 'General'
            # Keep long names, supplier codes and reference notes inside their cells.
            wrap_columns = (2, 5, 7) if ws == sheet else (2, 3, 5)
            line_count = 1
            for col in wrap_columns:
                cell = row[col - 1]
                cell.alignment = Alignment(vertical='center', wrap_text=True)
                line_count = max(line_count, ceil(len(str(cell.value or '')) / widths[col - 1]))
            ws.row_dimensions[row[0].row].height = max(20, line_count * 12)
            previous = key
            if ws != sheet:
                stripe += 1
    sheet.sheet_properties.tabColor = '24496B'
    guide = wb['Instructions']
    guide['B5'] = 'Products / Non-BOM: edit names and categories, or add product cards. Supplier Code is an Odoo reference.'
    guide['B7'] = 'BOM: each parent lists only its direct components. Edit Component SKU or Quantity. Use REMOVE to remove an existing component.'
    guide['B9'] = 'Two levels per block: cabinet → FPACK and HRD. Each FPACK or HRD has its own block of direct components. Shared sub-BOMs are listed once.'
    guide['B10'] = 'Choose categories and units from the lists on Products / Non-BOM. New components need a product card or an existing code from Catalogue.'
    guide.append(['Add a component', 'Append a BOM row: Parent BOM SKU, Component SKU, Quantity and KEEP. Leave Unit, Supplier Code, Note and hidden IDs blank.'])
    guide.append(['New BOM', 'Add its product card, define a NEW- key in BOMs, then add its direct component rows in BOM. Each parent must identify one BOM.'])
    guide.append(['Quantity', 'Quantity is per parent BOM output, as defined in BOMs. It is not a multiplied total across hierarchy levels.'])
    guide.append(['References', 'Unit and Supplier Code describe the exported component. Keep them unchanged when replacing its SKU; the next download refreshes them.'])
    guide.append(['Shared assemblies', 'Changing an HRD or FPACK BOM affects every parent that uses it. Do not copy its component rows under the cabinet.'])
    guide.append(['Reading', 'Each BOM block has one fill colour. Peach and blue alternate between BOMs, with dark lines separating the blocks. Font size: 9 pt.'])
    for row in guide.iter_rows(min_row=16):
        for cell in row:
            cell.font = body
            cell.alignment = Alignment(vertical='center', wrap_text=True)
        guide.row_dimensions[row[0].row].height = 34


def translate(wb, record):
    """Validate visible references and adapt to the established atomic importer."""
    from webapp.reform_excel import HEADERS as LEGACY, text, rows_from
    if 'BOM' not in wb or wb['BOM'].max_row > MAX_ROWS + 1 or wb['BOM'].max_column != len(HEADERS):
        raise ValueError('BOM is missing or exceeds the row/column limit.')
    iterator = wb['BOM'].iter_rows()
    if [c.value for c in next(iterator)] != HEADERS:
        raise ValueError('BOM: keep the original column headers.')
    out = Workbook()
    out.remove(out.active)
    for name in ('Products', 'BOMs', 'Components'):
        out.create_sheet(name).append(LEGACY[name])
    for name in ('Products', 'Non-BOM'):
        if name not in wb or wb[name].max_row > 20001 or wb[name].max_column != 5:
            raise ValueError(f'{name}: sheet is missing or too large.')
        rows = wb[name].iter_rows()
        if [c.value for c in next(rows)] != LEGACY['Products'] + ['Supplier Code']:
            raise ValueError(f'{name}: keep the original column headers.')
        for row in rows:
            if not any(c.value is not None for c in row):
                continue
            if any(c.data_type == 'f' for c in row):
                raise ValueError(f'{name}: replace formulas with values.')
            if text(row[4].value) != supplier_codes(record, row[0].value):
                raise ValueError('Supplier Code is a reference field and must remain unchanged.')
            out['Products'].append([c.value for c in row[:4]])
    parents = defaultdict(list)
    for _, values in rows_from(wb, 'BOMs'):
        out['BOMs'].append(values)
        parents[text(values[1])].append(text(values[0]))
    original = {(str(row[7]), str(row[8])): row for row in component_rows(record)}
    seen = set()
    for number, cells in enumerate(iterator, 2):
        values = [c.value for c in cells]
        if not any(v is not None for v in values):
            continue
        if any(c.data_type == 'f' for c in cells):
            raise ValueError(f'BOM, row {number}: replace formulas with values.')
        parent, code, quantity, unit, supplier, action, note, key, lid = values
        key, lid, action = text(key), text(lid), text(action)
        if action not in ('KEEP', 'REMOVE'):
            raise ValueError('BOM: use Action KEEP or REMOVE.')
        if lid:
            identity = (key, lid)
            before = original.get(identity)
            if before is None or identity in seen:
                raise ValueError('BOM: Line ID is invalid or duplicated. Keep hidden IDs unchanged.')
            seen.add(identity)
            for col in (0, 3, 4, 6):
                if text(values[col]) != text(before[col]):
                    raise ValueError(f'BOM: {HEADERS[col]} is a reference field and must remain unchanged.')
        else:
            if action != 'KEEP':
                raise ValueError('BOM: a new component row must use KEEP.')
            candidates = parents.get(text(parent), [])
            if len(candidates) != 1 or (key and key != candidates[0]):
                raise ValueError('BOM: Parent BOM SKU must identify exactly one BOM in BOMs.')
            key = candidates[0]
            if any(text(v) for v in (unit, supplier, note)):
                raise ValueError('BOM: leave Unit, Supplier Code and Note blank for new component rows.')
        out['Components'].append([key, lid, action, code, quantity])
    if seen != set(original):
        raise ValueError('BOM: exported rows are missing. Keep existing rows and use REMOVE.')
    return out
