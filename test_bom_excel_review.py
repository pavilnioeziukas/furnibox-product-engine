import copy
import unittest
from decimal import Decimal
from io import BytesIO
from openpyxl import Workbook

from bom_excel_review import (REQUIRED, minutes, operation_mapping, read_rows,
                              require_stage, review_rows, unique_mapping)


def row(oid=10, **values):
    r = dict.fromkeys(REQUIRED, '')
    r.update({'Produkto kodas': 'APACK-X', 'Produkto pavadinimas': 'X',
              'Kategorija': 'All / APACK', 'BOM reference': 'BOM_for Furnibox_v10_APACK',
              'BOM tipas': 'Manufacture this product', 'TECH BOM ID': 1,
              'TECH BOM write_date': '2026-10-29', 'TECH operacijos ID': oid,
              'TECH operacijos write_date': '2026-10-06' if oid else '',
              '_row': 2})
    if oid:
        r.update({'Eiliškumas': 10, 'Operacija': 'Assemble',
                  'Darbo centras': 'Assembly', 'Laikas (min:sek)': '01:30'})
    r.update(values)
    return r


class ReviewTests(unittest.TestCase):
    def test_times(self):
        for value, expected in [('00:30', '.5'), ('01:30', '1.5'),
                                ('30:00', '30'), ('120:01', str(Decimal(120)+Decimal(1)/60))]:
            self.assertEqual(minutes(value), Decimal(expected))
        self.assertEqual(minutes(0.5, baseline=True), minutes('00:30'))
        for invalid in ['1:60', '1:3', '-1:00', '1.5', 0.5, True, '01:30:00', 'NaN', None]:
            with self.assertRaises(ValueError):
                minutes(invalid)

    def test_unchanged_no_eco(self):
        b = [row(), row(None)]
        result = review_rows(b, copy.deepcopy(b))
        self.assertEqual(result['proposed_eco_count'], 0)
        self.assertEqual(result['changes'], [])
        self.assertFalse(result['ready_to_write'])
        numeric = row(**{'Laikas (min:sek)': 30.0})
        textual = row(**{'Laikas (min:sek)': '30:00'})
        self.assertEqual(review_rows([numeric], [textual])['changes'], [])

    def test_update_all_operation_fields(self):
        changed = row(**{'Eiliškumas': 20, 'Operacija': 'Pack',
                         'Darbo centras': 'Packing', 'Laikas (min:sek)': '00:30'})
        result = review_rows([row()], [changed])
        self.assertEqual(len(result['changes']), 1)
        self.assertEqual(result['changes'][0]['after']['minutes'], '0.5')

    def test_new_with_and_without_old_operations(self):
        new = row(None, **{'Eiliškumas': 30, 'Operacija': 'Pack',
                           'Darbo centras': 'Packing', 'Laikas (min:sek)': '120:00'})
        for baseline, returned in [([row(), row(None)], [row(), new]),
                                   ([row(None)], [new])]:
            result = review_rows(baseline, returned)
            self.assertEqual(result['changes'][0]['kind'], 'create')
            self.assertEqual(result['errors'], [])

    def test_routing_and_conflict(self):
        result = review_rows([row()], [row(Routing='Manufacturing')])
        self.assertEqual(result['changes'][0]['kind'], 'routing')
        result = review_rows([row(), row(None)], [row(Routing='M'), row(None, Routing='A')])
        self.assertTrue(result['errors'])

    def test_blank_missing_note_and_kit(self):
        self.assertTrue(review_rows([row()], [row(Operacija='')])['errors'])
        missing = review_rows([row()], [])
        self.assertFalse(missing['changes'])
        self.assertTrue(missing['warnings'])
        note = review_rows([row()], [row(Pastaba='Pašalinti operaciją')])
        self.assertFalse(note['changes'])
        self.assertTrue(note['human_review'])
        kit = row(**{'BOM tipas': 'Kit'})
        changed = copy.deepcopy(kit)
        changed['Operacija'] = 'Changed'
        self.assertTrue(review_rows([kit], [changed])['errors'])

    def test_metadata_unknown_and_duplicate_block(self):
        for field in ['Produkto kodas', 'BOM tipas', 'BOM reference', 'TECH BOM write_date']:
            changed = row()
            changed[field] = 'Changed'
            self.assertTrue(review_rows([row()], [changed])['errors'])
        self.assertTrue(review_rows([row()], [row(oid=99)])['errors'])
        self.assertTrue(review_rows([row()], [row(), row()])['errors'])

    def test_reordered_changes_have_same_hash(self):
        a = row(Operacija='Pack')
        b = row(None, **{'Operacija': 'Check', 'Eiliškumas': 30,
                         'Darbo centras': 'QA', 'Laikas (min:sek)': '00:30'})
        self.assertEqual(review_rows([row()], [a, b])['change_hash'],
                         review_rows([row()], [b, a])['change_hash'])

    def test_stage_guard(self):
        require_stage('https://stageodoo.furnibox.lt')
        for url in ['https://odoo.furnibox.lt', 'http://stageodoo.furnibox.lt',
                    'https://stageodoo.furnibox.lt.evil.test',
                    'https://u:p@stageodoo.furnibox.lt', 'https://stageodoo.furnibox.lt:444']:
            with self.assertRaises(ValueError):
                require_stage(url)

    def test_mapping_requires_full_unique_identity(self):
        identity = dict(sku='X', company='Furnibox', variant='', type='normal',
                        quantity='1', uom='Units', reference='BOM_for Furnibox_v10_X',
                        component_fingerprint='abc')
        candidate = dict(identity, id=999, active=True)
        self.assertEqual(unique_mapping(identity, [candidate])['id'], 999)
        for candidates in [[], [candidate, candidate], [dict(candidate, reference='old')]]:
            with self.assertRaises(ValueError):
                unique_mapping(identity, candidates)
        op = dict(id=1, name='A', sequence=10, workcenter='W', minutes='1')
        self.assertEqual(operation_mapping([op], [dict(op, id=500)]), {1: 500})
        with self.assertRaises(ValueError):
            operation_mapping([op], [dict(op, minutes='2')])

    def test_real_xlsx_and_formula_rejection(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Korekcijos'
        ws.append(list(REQUIRED))
        ws.append([row()[k] for k in REQUIRED])
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        self.assertEqual(read_rows(stream)[0]['TECH BOM ID'], 1)
        ws.cell(2, 1, '=1+1')
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        with self.assertRaises(ValueError):
            read_rows(stream)


if __name__ == '__main__':
    unittest.main()
