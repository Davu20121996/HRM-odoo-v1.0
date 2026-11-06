"""Bounded expression interpreter and import adapters, independent of Odoo."""
import ast
import csv
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


class DataError(ValueError):
    pass


def number(value, locale='en'):
    text = str(value).strip()
    pattern = r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?'
    if locale == 'vi':
        pattern = r'[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?'
    if not re.fullmatch(pattern, text):
        raise DataError('INVALID_NUMBER: ' + text)
    text = text.replace('.', '').replace(',', '.') if locale == 'vi' else text.replace(',', '')
    result = Decimal(text)
    if not result.is_finite() or abs(result) > Decimal('1e15'):
        raise DataError('NUMBER_OUT_OF_RANGE')
    return result


def formula(expression, context):
    """Excel-style named variables; no eval, objects, imports, loops or powers."""
    expression = (expression or '').strip().lstrip('=').replace(';', ',').replace('<>', '!=')
    expression = re.sub(r'(?<![<>=!])=(?!=)', '==', expression)
    if len(expression) > 2000:
        raise DataError('FORMULA_TOO_LONG')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as exc:
        raise DataError('INVALID_FORMULA') from exc
    if len(list(ast.walk(tree))) > 200:
        raise DataError('FORMULA_TOO_COMPLEX')
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            return Decimal(str(int(node.value) if isinstance(node.value, bool) else node.value))
        if isinstance(node, ast.Name) and node.id in context:
            return Decimal(str(context[node.id]))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return a / b
            if isinstance(node.op, ast.Mod): return a % b
        if isinstance(node, ast.Compare):
            a = visit(node.left)
            for op, right in zip(node.ops, node.comparators):
                b = visit(right)
                if isinstance(op, ast.Eq): ok = a == b
                elif isinstance(op, ast.NotEq): ok = a != b
                elif isinstance(op, ast.Lt): ok = a < b
                elif isinstance(op, ast.LtE): ok = a <= b
                elif isinstance(op, ast.Gt): ok = a > b
                elif isinstance(op, ast.GtE): ok = a >= b
                else: raise DataError('FORBIDDEN_OPERATOR')
                if not ok: return False
                a = b
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = node.func.id.upper()
            if fn == 'IF' and len(node.args) == 3:
                return visit(node.args[1] if visit(node.args[0]) else node.args[2])
            if fn == 'IFERROR' and len(node.args) == 2:
                try: return visit(node.args[0])
                except (ArithmeticError, DataError): return visit(node.args[1])
            args = [visit(x) for x in node.args]
            if fn in ('SUM', 'MIN', 'MAX', 'AND', 'OR') and args:
                return {'SUM': lambda: sum(args), 'MIN': lambda: min(args),
                        'MAX': lambda: max(args), 'AND': lambda: all(args),
                        'OR': lambda: any(args)}[fn]()
            if fn == 'ROUND' and len(args) in (1, 2):
                digits = args[1] if len(args) == 2 else Decimal(0)
                if digits != int(digits) or abs(digits) > 8: raise DataError('INVALID_PRECISION')
                return args[0].quantize(Decimal(1).scaleb(-int(digits)), rounding=ROUND_HALF_UP)
        raise DataError('UNKNOWN_VARIABLE_OR_FORBIDDEN_EXPRESSION')
    try:
        value = visit(tree)
        result = Decimal(int(value)) if isinstance(value, bool) else Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal('1e18'):
            raise DataError('RESULT_OUT_OF_RANGE')
        return result
    except ArithmeticError as exc:
        raise DataError('ARITHMETIC_ERROR: ' + str(exc)) from exc


def read_table(payload, filename, sheet, header_row, data_start_row=None, cached_header=False):
    if len(payload) > 5 * 1024 * 1024:
        raise DataError('FILE_TOO_LARGE: tối đa 5 MB')
    if filename.lower().endswith('.csv'):
        rows = list(csv.reader(io.StringIO(payload.decode('utf-8-sig'))))
    elif filename.lower().endswith('.xlsx'):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024:
                raise DataError('ZIP_TOO_LARGE')
            if any('vbaProject' in n or ('externalLinks/' in n and not cached_header) for n in archive.namelist()):
                raise DataError('EXTERNAL_LINK_OR_MACRO')
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(payload), read_only=True, data_only=False, keep_links=False)
        cache = load_workbook(io.BytesIO(payload), read_only=True, data_only=True, keep_links=False) if cached_header else None
        try:
            ws = book[sheet] if sheet else book.worksheets[0]
            rows = []
            for row_no, row in enumerate(ws.iter_rows(), 1):
                values = []
                for cell in row:
                    value = cell.value
                    if cell.data_type == 'f':
                        if cached_header and row_no < header_row:
                            value = None
                        elif cached_header and row_no == header_row:
                            value = cache[ws.title].cell(row_no, cell.column).value
                            if not isinstance(value, str) or not value.strip():
                                raise DataError('HEADER_CACHE_MISSING: lưu lại file bằng Excel trước khi nhập')
                        else:
                            raise DataError('FORMULA_CELL: hãy xuất file chỉ chứa giá trị')
                    values.append(value)
                rows.append(values)
                if len(rows) > 10001:
                    raise DataError('TABLE_TOO_LARGE')
        finally:
            book.close()
            if cache: cache.close()
    else:
        raise DataError('FILE_TYPE: chỉ hỗ trợ CSV UTF-8 và XLSX')
    if not 1 <= header_row <= len(rows) or len(rows) > 10001:
        raise DataError('INVALID_TABLE_SIZE_OR_HEADER')
    headers = [str(v or '').strip() for v in rows[header_row - 1]]
    first = data_start_row or header_row + 1
    if first <= header_row: raise DataError('DATA_ROW_MUST_FOLLOW_HEADER')
    return headers, list(enumerate(rows[first - 1:], start=first))


def normalize(raw, mapping, locale):
    result = {}
    for item in mapping:
        index = item['column'] - 1
        value = raw[index] if index < len(raw) else None
        if value is None or str(value).strip() == '':
            if item.get('required'): raise DataError('REQUIRED: ' + item['target'])
            continue
        kind = item.get('type', 'text')
        if item['target'] in ('employee_code', 'source_record_id') and not isinstance(value, str):
            raise DataError('IDENTIFIER_MUST_BE_TEXT: ' + item['target'])
        if kind == 'number': value = str(number(value, locale))
        elif kind == 'date':
            value = value.date().isoformat() if isinstance(value, datetime) else (
                value.isoformat() if isinstance(value, date) else datetime.strptime(str(value), item.get('format', '%Y-%m-%d')).date().isoformat())
        else: value = str(value).strip()
        result[item['target']] = value
    return result


def unpivot(data, raw, year, month, first_column, symbols, locale):
    """A monthly row becomes daily source records; blanks do not erase values."""
    records = []
    for day in range(1, 32):
        column = first_column + day - 1
        value = raw[column - 1] if column <= len(raw) else None
        if value is None or str(value).strip() == '': continue
        try: work_date = date(year, month, day)
        except ValueError as exc: raise DataError(f'INVALID_CALENDAR_DATE: cột {column}, ngày {day}') from exc
        text = str(value).strip()
        symbol = symbols.get(text)
        hours = number(symbol.get('regular_hours', 0), 'en') if isinstance(symbol, dict) else (
            number(str(symbol), 'en') if symbol is not None else number(value, locale))
        item = dict(data, work_date=work_date.isoformat(), regular_hours=str(hours),
                    source_record_id=f"{data['source_record_id']}:{work_date.isoformat()}", source_column=column)
        if symbol is not None:
            item['attendance_symbol'] = text
        if isinstance(symbol, dict) and 'overtime_hours' in symbol:
            item['overtime_hours'] = str(number(symbol['overtime_hours'], 'en'))
        records.append(item)
    return records


def expand_amount_columns(data, raw, columns, locale, default_currency):
    """Map an arbitrary set of source columns to stable salary component codes.

    Blank cells do not supply a value; zero explicitly replaces the previous
    amount. The component code, not its position/header, forms the source key.
    """
    records = []
    for mapping in columns:
        index = mapping['column'] - 1
        value = raw[index] if index < len(raw) else None
        if value is None or str(value).strip() == '':
            if mapping.get('required'):
                raise DataError(f"REQUIRED: cột {index + 1}, {mapping['component_code']}")
            continue
        try:
            amount = number(value, locale)
        except DataError as exc:
            raise DataError(f"COLUMN_{index + 1}: {exc}") from exc
        records.append(dict(data, component_code=mapping['component_code'], amount=str(amount),
                            currency=data.get('currency') or default_currency,
                            source_record_id=f"{data['source_record_id']}:{mapping['component_code']}",
                            source_column=index + 1))
    return records
