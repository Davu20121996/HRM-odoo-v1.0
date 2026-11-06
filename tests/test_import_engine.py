"""Run without an Odoo server: python -m unittest discover -s tests -v."""
import importlib.util
import io
import unittest
from decimal import Decimal
from pathlib import Path

spec = importlib.util.spec_from_file_location('import_engine', Path(__file__).parents[1] / 'addons/hrm_data_import/engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class TestImportEngine(unittest.TestCase):
    def test_document_golden_payroll(self):
        ctx = dict(BASE_SALARY=13000000, PAID_DAYS=24, STANDARD_DAYS=26)
        base = engine.formula('=BASE_SALARY * PAID_DAYS / STANDARD_DAYS', ctx)
        performance = engine.formula('2000000 * 0.8', {})
        meal = engine.formula('30000 * PAID_DAYS', ctx)
        self.assertEqual(base + performance + meal, Decimal('14320000'))
        self.assertEqual(base + performance + meal - 1000000 - 500000, Decimal('12820000'))

    def test_lazy_if_and_iferror(self):
        self.assertEqual(engine.formula('=IF(STANDARD_DAYS=0; 0; 10/STANDARD_DAYS)', {'STANDARD_DAYS': 0}), 0)
        self.assertEqual(engine.formula('IFERROR(1/0, 9)', {}), 9)
        with self.assertRaises(engine.DataError): engine.formula('1/0', {})

    def test_functions_and_rounding(self):
        self.assertEqual(engine.formula('ROUND(2.5,0)', {}), 3)
        self.assertEqual(engine.formula('SUM(1, MAX(2,3), MIN(5,6))', {}), 9)
        self.assertEqual(engine.formula('IF(AND(3>2, 4<>5), 8, 0)', {}), 8)
        self.assertEqual(engine.formula('1 < 2', {}), 1)

    def test_forbidden_expressions(self):
        for expression in ['__import__(1)', '(1).__class__', '[1][0]', '10**100000',
                           '"x" * 100', 'UNKNOWN + 1', 'round(1, foo=2)', '1' * 2001]:
            with self.subTest(expression=expression), self.assertRaises(engine.DataError):
                engine.formula(expression, {})

    def test_number_locales_and_zero(self):
        self.assertEqual(engine.number('1.234.567,89', 'vi'), Decimal('1234567.89'))
        self.assertEqual(engine.number('1,234,567.89'), Decimal('1234567.89'))
        self.assertEqual(engine.number(0), 0)
        for value in ['1,23,4', 'NaN', 'Infinity', '1.2.3', '=1+1']:
            with self.assertRaises(engine.DataError): engine.number(value)

    def test_mapping_blank_zero_and_identifier(self):
        mapping = [dict(column=1, target='employee_code'), dict(column=2, target='amount', type='number'),
                   dict(column=3, target='optional')]
        self.assertEqual(engine.normalize(['00012', 0, ''], mapping, 'en'), {'employee_code': '00012', 'amount': '0'})
        with self.assertRaises(engine.DataError):
            engine.normalize([''], [dict(column=1, target='employee_code', required=True)], 'vi')
        with self.assertRaisesRegex(engine.DataError, 'IDENTIFIER_MUST_BE_TEXT'):
            engine.normalize([12], [dict(column=1, target='employee_code')], 'vi')

    def test_csv_preserves_duplicate_headers(self):
        headers, rows = engine.read_table(b'code,amount,amount\n001,0,12\n', 'a.csv', None, 1)
        self.assertEqual(headers, ['code', 'amount', 'amount'])
        self.assertEqual(rows[0], (2, ['001', '0', '12']))

    def test_header_size_and_type_limits(self):
        for content, name, header in [(b'a\n', 'a.xls', 1), (b'a\n', 'a.csv', 3), (b'x' * (5*1024*1024+1), 'a.csv', 1)]:
            with self.assertRaises(engine.DataError): engine.read_table(content, name, None, header)

    def test_xlsx_and_formula_cell_rejection(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(['employee_code', 'amount'])
        book.active.append(['0001', 0])
        out = io.BytesIO()
        book.save(out)
        self.assertEqual(engine.read_table(out.getvalue(), 'a.xlsx', None, 1)[1][0][1], ['0001', 0])
        book.active['B2'] = '=2+3'
        out = io.BytesIO()
        book.save(out)
        with self.assertRaisesRegex(engine.DataError, 'FORMULA_CELL'):
            engine.read_table(out.getvalue(), 'a.xlsx', None, 1)
        book.close()

    def test_monthly_unpivot_and_invalid_date(self):
        data = {'employee_code': '001', 'source_record_id': 'R1'}
        values = ['X', 0, ''] + [None] * 28
        rows = engine.unpivot(data, values, 2026, 2, 1, {'X': 8}, 'vi')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['regular_hours'], '8')
        self.assertEqual(rows[1]['regular_hours'], '0')
        self.assertEqual(rows[1]['source_record_id'], 'R1:2026-02-02')
        values[28] = 'X'
        with self.assertRaisesRegex(engine.DataError, 'INVALID_CALENDAR_DATE'):
            engine.unpivot(data, values, 2026, 2, 1, {'X': 8}, 'vi')

    def test_variable_performance_columns_zero_blank_and_stable_keys(self):
        data = {'employee_code': '001', 'source_record_id': 'PERF-001', 'revision': '1'}
        specs = [dict(column=2, component_code='KPI', required=False),
                 dict(column=3, component_code='SALES', required=False),
                 dict(column=4, component_code='EXTRA', required=False)]
        rows = engine.expand_amount_columns(data, ['001', '1.200.000', 0, ''], specs, 'vi', 'VND')
        self.assertEqual([(r['component_code'], r['amount']) for r in rows], [('KPI', '1200000'), ('SALES', '0')])
        self.assertEqual(rows[0]['source_record_id'], 'PERF-001:KPI')
        self.assertEqual(rows[0]['currency'], 'VND')
        reordered = engine.expand_amount_columns(data, [0, '1.200.000'],
            [dict(column=1, component_code='SALES'), dict(column=2, component_code='KPI')], 'vi', 'VND')
        self.assertEqual(reordered[1]['source_record_id'], rows[0]['source_record_id'])

    def test_more_than_100_columns_csv_and_xlsx(self):
        count = 180
        csv_file = (','.join(f'KPI_{i}' for i in range(count)) + '\n' + ','.join('0' for _ in range(count))).encode()
        self.assertEqual(len(engine.read_table(csv_file, 'wide.csv', None, 1)[0]), count)
        from openpyxl import Workbook
        book = Workbook()
        book.active.append([f'KPI_{i}' for i in range(count)])
        book.active.append([0] * count)
        output = io.BytesIO()
        book.save(output)
        book.close()
        self.assertEqual(len(engine.read_table(output.getvalue(), 'wide.xlsx', None, 1)[0]), count)

    def test_required_performance_amount_column(self):
        with self.assertRaisesRegex(engine.DataError, 'REQUIRED'):
            engine.expand_amount_columns({'source_record_id': 'A'}, [''],
                [dict(column=1, component_code='KPI', required=True)], 'vi', 'VND')


    def test_multirow_header_and_cached_header_only(self):
        from openpyxl import Workbook
        from zipfile import ZipFile
        book = Workbook()
        sheet = book.active
        sheet.append(['Report', '=100+200'])
        sheet.append(['code', '="amount"'])
        sheet.append(['secondary header', None])
        sheet.append(['001', 0])
        output = io.BytesIO()
        book.save(output)
        rewritten = io.BytesIO()
        with ZipFile(io.BytesIO(output.getvalue())) as source, ZipFile(rewritten, 'w') as target:
            for name in source.namelist():
                data = source.read(name)
                if name == 'xl/worksheets/sheet1.xml':
                    data = data.replace(b'<c r="B2"><f>"amount"</f><v></v></c>',
                        b'<c r="B2" t="str"><f>"amount"</f><v>amount</v></c>')
                target.writestr(name, data)
        headers, rows = engine.read_table(rewritten.getvalue(), 'a.xlsx', None, 2, 4, True)
        self.assertEqual(headers, ['code', 'amount'])
        self.assertEqual(rows, [(4, ['001', 0])])
        with self.assertRaisesRegex(engine.DataError, 'HEADER_CACHE_MISSING'):
            engine.read_table(output.getvalue(), 'a.xlsx', None, 2, 4, True)
        sheet['B4'] = '=1+1'
        output = io.BytesIO()
        book.save(output)
        with self.assertRaises(engine.DataError):
            engine.read_table(output.getvalue(), 'a.xlsx', None, 1, 4, True)
        book.close()

if __name__ == '__main__':
    unittest.main()
