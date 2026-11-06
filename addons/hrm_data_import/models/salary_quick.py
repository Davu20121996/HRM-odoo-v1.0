"""Monthly payroll grid matching the customer's A:AZ salary template."""
import io
import json
import math
import re
from pathlib import Path

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
from .imports import audit
from .timesheet_report import MONTHS, available_years

DISPLAY_HEADERS = ['Employee code', 'No.', 'FULL NAME', 'JOB TITLE', 'DEPARTMENT', 'EMPLOYMENT STATUS', 'BASE SALARY', 'LUNCH', 'FUEL SUPPORT', 'PHONE SUPPORT', 'TRAVEL SUPPORT', 'HOUSING SUPPORT', 'PERFORMANCE', 'STANDARD DAYS IN MONTH', 'PROBATION DAYS', 'EMPLOYMENT CONTRACT DAYS', 'ACTUAL WORKED DAYS', 'ANNUAL LEAVE', 'PAID PERSONAL LEAVE', 'PUBLIC HOLIDAYS', 'PAYROLL DAYS', 'MONTHLY BASE PAY', 'x 150', 'x 200', 'x 300', 'OVERTIME PAY', 'SOCIAL (17%), HEALTH (3%), UNEMPLOYMENT (1%)', 'BONUS', 'GROSS TOTAL', 'DIRECT DEDUCTIONS', 'DEPENDANT RELIEF', 'EMPLOYEE INSURANCE', 'TAX EXEMPT AMOUNTS', 'TAX EXEMPT AMOUNTS (AH)', 'TAX EXEMPT AMOUNTS (AI)', 'DEDUCTION TOTAL', 'TAXABLE INCOME', 'PERSONAL INCOME TAX', 'NET MONTHLY PAY', 'Notes', 'EMPLOYER SOCIAL 17%', 'OCCUPATIONAL ACCIDENT 0.5%', 'EMPLOYER HEALTH 3%', 'EMPLOYER UNEMPLOYMENT 1%', 'EMPLOYER UNION 2%', 'EMPLOYER TOTAL', 'EMPLOYEE SOCIAL 8%', 'EMPLOYEE HEALTH 1.5%', 'EMPLOYEE UNEMPLOYMENT 1%', 'EMPLOYEE UNION 1%', 'EMPLOYEE TOTAL', 'COMBINED TOTAL']
HEADERS = json.loads(Path(__file__).with_name('salary_columns.json').read_text(encoding='utf-8'))
LETTERS = [chr(65+i) if i < 26 else 'A'+chr(65+i-26) for i in range(52)]
# Only explicit source meanings are mapped. No old tax/insurance rates are assumed.
COMPONENT_COLUMNS = {'H': 'LUNCH', 'I': 'PETROL', 'J': 'PHONE', 'K': 'TRAVEL',
    'L': 'HOUSING', 'V': 'BASE', 'Z': 'OVERTIME', 'AA': 'INSURANCE_SUPPORT',
    'AB': 'EXTRA_BONUS', 'AD': 'DEDUCT', 'AE': 'DEPENDENT_RELIEF',
    'AF': 'EMPLOYEE_INSURANCE', 'AG': 'TAX_EXEMPT', 'AH': 'TAX_EXEMPT_2',
    'AI': 'TAX_EXEMPT_3', 'AO': 'EMPLOYER_SOCIAL', 'AP': 'EMPLOYER_ACCIDENT',
    'AQ': 'EMPLOYER_HEALTH', 'AR': 'EMPLOYER_UNEMPLOYMENT', 'AS': 'EMPLOYER_UNION',
    'AU': 'EMPLOYEE_SOCIAL', 'AV': 'EMPLOYEE_HEALTH', 'AW': 'EMPLOYEE_UNEMPLOYMENT',
    'AX': 'EMPLOYEE_UNION'}
ALIASES = dict(COMPONENT_COLUMNS, G='BASE_SALARY', M='PERFORMANCE_AMOUNT',
    N='STANDARD_DAYS', Q='PAID_DAYS', U='PAID_DAYS')


def excel_expression(expression):
    """Translate same-row Excel cell references; reject ranges across employees."""
    expression = (expression or '').strip()
    rows = {int(n) for n in re.findall(r'\$?[A-Z]{1,2}\$?(\d+)\b', expression)}
    if len(rows) > 1:
        raise UserError('Công thức chỉ được tham chiếu các cột của cùng một nhân viên.')
    def cell(match):
        column = match.group(1)
        if column not in ALIASES:
            raise UserError(f'Cột {column} chưa có biến tính lương. Dùng mã khoản lương hoặc biến được hỗ trợ.')
        return ALIASES[column]
    def span(match):
        start, end = LETTERS.index(match.group(1)), LETTERS.index(match.group(3))
        if end < start: raise UserError('Vùng tham chiếu bị đảo chiều.')
        return ','.join(cell(re.match(r'([A-Z]+)', c)) for c in LETTERS[start:end+1])
    expression = re.sub(r'\$?([A-Z]{1,2})\$?(\d+):\$?([A-Z]{1,2})\$?(\d+)', span, expression)
    return re.sub(r'\$?([A-Z]{1,2})\$?\d+\b', cell, expression)


class FormulaExcel(models.Model):
    _inherit = 'hrm.payroll.formula'
    excel_expression = fields.Char(string='Excel column formula',
        help='Example: =ROUND(G12*U12/N12,0). Same-row references only; external workbook links are not supported.')

    @api.onchange('excel_expression')
    def _onchange_excel_expression(self):
        if self.excel_expression: self.expression = excel_expression(self.excel_expression)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('excel_expression'): vals['expression'] = excel_expression(vals['excel_expression'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('excel_expression'): vals = dict(vals, expression=excel_expression(vals['excel_expression']))
        elif 'expression' in vals and 'excel_expression' not in vals: vals = dict(vals, excel_expression=False)
        return super().write(vals)

    def action_new_version(self):
        self.ensure_one()
        self.check_access('read')
        draft = self.copy({'effective_from': fields.Date.today(), 'effective_to': False})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form', 'res_id': draft.id}


class SalaryAdjustment(models.Model):
    _name = 'hrm.salary.adjustment'
    _description = 'Monthly salary adjustments with reasons and history'
    _order = 'id desc'
    _rec_name = 'reason'
    company_id = fields.Many2one('hrm.company', required=True, string='Company')
    tenant_id = fields.Many2one(related='company_id.tenant_id', store=True)
    period_id = fields.Many2one('hrm.payroll.period', required=True, string='Payroll month', domain="[('company_id','=',company_id)]")
    employee_id = fields.Many2one('hr.employee', required=True, string='Employees', domain="[('hrm_company_id','=',company_id)]")
    component_id = fields.Many2one('hrm.salary.component', required=True, string='Component to adjust', domain="[('structure_id.company_id','=',company_id),('status','=','active')]")
    amount = fields.Float(required=True, digits=(19, 4), string='Replacement amount')
    restore_formula = fields.Boolean(string='Trả về công thức')
    reason = fields.Text(required=True, string='Reason / approval reference')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved')], default='draft', readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True, string='Approved By')
    approved_at = fields.Datetime(readonly=True, string='Approved At')

    @api.constrains('company_id', 'period_id', 'employee_id', 'component_id', 'amount')
    def _scope(self):
        for rec in self:
            if (rec.period_id.company_id != rec.company_id or rec.employee_id.hrm_company_id != rec.company_id
                or rec.component_id.structure_id.company_id != rec.company_id):
                raise UserError('Công ty, nhân viên, kỳ và khoản lương phải đồng bộ.')
            if not math.isfinite(rec.amount) or abs(rec.amount) > 1e15:
                raise UserError('Số tiền vượt giới hạn.')

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('state', 'draft') != 'draft' or v.get('approved_by') or v.get('approved_at') for v in vals_list):
            raise UserError('Tạo bản nháp rồi duyệt điều chỉnh.')
        return super().create(vals_list)

    def action_approve(self):
        self.check_access('write')
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise UserError('Cần quyền duyệt điều chỉnh lương.')
        for rec in self:
            self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (rec.period_id.id,))
            self.env.cr.execute('SELECT id FROM hrm_salary_adjustment WHERE id=%s FOR UPDATE', (rec.id,))
            rec.invalidate_recordset(); rec.period_id.invalidate_recordset()
            if rec.state != 'draft': raise UserError('Bản điều chỉnh đã duyệt không duyệt lại.')
            if rec.period_id.status not in ('open', 'processing'):
                raise UserError('Mở lại kỳ chưa chốt và nhập lý do trước khi điều chỉnh; sau đó tính lại lương.')
            if self.env['hrm.payroll'].search_count([('period_id', '=', rec.period_id.id),
                ('status', 'not in', ['draft', 'processing'])]):
                raise UserError('Bảng lương đang khóa. Mở lại kỳ trước khi duyệt điều chỉnh.')
            if not (rec.reason or '').strip(): raise UserError('Cần lý do điều chỉnh.')
            probe = self.env['hrm.payroll'].new(dict(company_id=rec.company_id.id,
                tenant_id=rec.tenant_id.id, period_id=rec.period_id.id))
            if probe._active_salary(rec.employee_id).structure_id != rec.component_id.structure_id:
                raise UserError('Khoản lương không thuộc cơ cấu trong hợp đồng của nhân viên.')
            super(SalaryAdjustment, rec).write({'state': 'approved', 'approved_by': self.env.uid,
                'approved_at': fields.Datetime.now()})
            audit(rec, 'APPROVE', {'component': rec.component_id.code,
                'replacement': None if rec.restore_formula else rec.amount,
                'restore_formula': rec.restore_formula, 'reason': rec.reason})

    def write(self, vals):
        if self.ids:
            self.env.cr.execute('SELECT id FROM hrm_salary_adjustment WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()
        if any(r.state == 'approved' for r in self): raise UserError('Điều chỉnh đã duyệt không sửa. Tạo bản điều chỉnh mới để giữ lịch sử.')
        if {'state', 'approved_by', 'approved_at'} & vals.keys(): raise UserError('Dùng nút duyệt điều chỉnh.')
        return super().write(vals)

    def unlink(self):
        if any(r.state == 'approved' for r in self): raise UserError('Không xóa điều chỉnh đã duyệt.')
        return super().unlink()


class AdjustedComponent(models.Model):
    _inherit = 'hrm.salary.component'
    def compute_amount(self, ctx):
        self.ensure_one()
        if self.id in ctx.get('_adjustments', {}): return ctx['_adjustments'][self.id]
        return super().compute_amount(ctx)


class PayrollQuick(models.Model):
    _inherit = 'hrm.payroll'
    def _calculation_context(self, employee, salary, context):
        ctx = super()._calculation_context(employee, salary, context)
        adjustments = self.env['hrm.salary.adjustment'].search([('company_id', '=', self.company_id.id),
            ('period_id', '=', self.period_id.id), ('employee_id', '=', employee.id), ('state', '=', 'approved')], order='approved_at, id')
        latest = {r.component_id.id: r for r in adjustments}
        ctx['_adjustments'] = {key: row.amount for key, row in latest.items() if not row.restore_formula}
        if adjustments: audit(self, 'UPDATE', {'step': 'salary_adjustments', 'employee_id': employee.id,
            'adjustments': [{'id': r.id, 'component': r.component_id.code, 'replacement': r.amount} for r in adjustments]})
        return ctx


class SalaryQuickItem(models.Model):
    _inherit = 'hrm.payroll.item'
    assignment_department = fields.Char(string='Phòng ban', compute='_compute_assignment_labels')
    assignment_projects = fields.Char(string='Dự án', compute='_compute_assignment_labels')
    assignment_position = fields.Char(string='Chức vụ', compute='_compute_assignment_labels')
    salary_year = fields.Selection(available_years, compute='_compute_period_labels', store=True, string='Year')
    salary_month = fields.Selection(MONTHS, compute='_compute_period_labels', store=True, string='Month')
    salary_period = fields.Char(compute='_compute_period_labels', store=True, string='Period')
    for _letter, _header in zip(LETTERS, DISPLAY_HEADERS):
        locals()['xl_'+_letter.lower()] = fields.Char(string=f'{_letter} · {_header or "(cột gộp)"}', compute='_compute_excel_columns')
    del _letter, _header

    def _compute_assignment_labels(self):
        for period, rows in self.grouped('period_id').items():
            assignments = rows.employee_id._primary_assignments(period.period_end)
            for row in rows:
                assignment = assignments.get(row.employee_id.id, self.env['hrm.employee.assignment'])
                row.assignment_department = assignment.department_id.name
                row.assignment_position = assignment.position_id.title
                row.assignment_projects = ', '.join(assignment.project_ids.mapped('name'))

    @api.depends('period_id.period_start')
    def _compute_period_labels(self):
        for rec in self:
            start = rec.period_id.period_start
            rec.salary_year = str(start.year) if start else False
            rec.salary_month = str(start.month) if start else False
            rec.salary_period = start.strftime('%m/%Y') if start else False

    def _excel_values(self, ordinal=1):
        self.ensure_one(); self.check_access('read')
        lines = {r.code: r.amount for r in self.detail_ids}
        log = self.env['hrm.audit.log'].search([('company_id', '=', self.company_id.id),
            ('entity_type', '=', 'hrm.payroll'), ('entity_id', '=', self.payroll_id.id)], order='id desc')
        snapshot = next((r.metadata for r in log if (r.metadata or {}).get('step') == 'calculation_snapshot'
            and r.metadata.get('employee_id') == self.employee_id.id), {})
        ctx = snapshot.get('context', {})
        source = self.employee_id.hrm_source_profile or {}
        values = {'A': self.employee_id.employee_code, 'B': ordinal, 'C': self.employee_id.name,
            'D': self.assignment_position or self.employee_id.job_title or '',
            'E': self.assignment_department or self.employee_id.department_id.name or '',
            'F': source.get('working_status_id', self.employee_id.current_status),
            'G': ctx.get('BASE_SALARY'), 'M': ctx.get('PERFORMANCE_AMOUNT'),
            'N': ctx.get('STANDARD_DAYS'), 'Q': ctx.get('PAID_DAYS'),
            'U': ctx.get('PAID_DAYS'), 'AC': self.gross_amount,
            'AJ': self.deduction_amount, 'AL': self.tax_amount, 'AM': self.net_amount,
            'AN': 'MÔ PHỎNG' if 'MO_PHONG' in str(snapshot) or 'MÔ PHỎNG' in str(snapshot) else ''}
        for col, code in COMPONENT_COLUMNS.items():
            if code in lines: values[col] = lines[code]
        allowances = self.detail_ids.filtered('contract_allowance')
        if allowances:
            exemption_columns = {'LUNCH': 'AG', 'MEAL': 'AG', 'PHONE': 'AH'}
            for line in allowances:
                if line.tax_exempt_amount:
                    code = line.code.removeprefix('CONTRACT_ALLOWANCE_')
                    col = exemption_columns.get(code, 'AI')
                    values[col] = (values.get(col) or 0) + line.tax_exempt_amount
            for col, codes in {'H': ('LUNCH', 'MEAL'), 'I': ('PETROL',), 'J': ('PHONE',),
                               'K': ('TRAVEL',), 'L': ('HOUSING',)}.items():
                matched = allowances.filtered(lambda line: line.code.removeprefix('CONTRACT_ALLOWANCE_') in codes)
                if matched:
                    values[col] = (values.get(col) or 0) + sum(matched.mapped('amount'))
        values['AK'] = max(0, self.gross_amount - sum(values.get(col) or 0 for col in ('AG', 'AH', 'AI')))
        if 'components' in snapshot and not any(c['type'] == 'tax' for c in snapshot['components']):
            values['AN'] = ' · '.join(filter(None, (values['AN'], 'Chưa cấu hình thuế TNCN')))
        return values

    def _compute_excel_columns(self):
        for index, rec in enumerate(self, 1):
            values = rec._excel_values(index)
            for col in LETTERS:
                value = values.get(col)
                rec['xl_'+col.lower()] = (f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value, (int, float))
                    else str(value)) if value is not None and value is not False else False

    def action_adjust_salary(self):
        self.ensure_one(); self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.salary.adjustment', 'view_mode': 'form',
            'context': {'default_company_id': self.company_id.id, 'default_period_id': self.period_id.id,
                        'default_employee_id': self.employee_id.id}}

    def action_salary_period(self):
        self.ensure_one(); self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.payroll.period', 'view_mode': 'form',
            'views': [(self.env.ref('hrm_data_import.view_period_input_form').id, 'form')], 'res_id': self.period_id.id}

    def action_salary_formulas(self):
        self.ensure_one(); self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.payroll.formula', 'view_mode': 'list,form',
            'domain': [('component_id.structure_id.company_id', '=', self.company_id.id)],
            'context': {'default_tenant_id': self.company_id.tenant_id.id}}

    def action_salary_slip(self):
        self.ensure_one(); self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form',
            'views': [(self.env.ref('hrm_data_import.payroll_item_details').id, 'form')], 'res_id': self.id}

    def action_export_salary_month(self):
        self.check_access('read')
        if not self or len(self.company_id) != 1 or len(self.period_id) != 1:
            raise UserError('Chọn ít nhất một dòng và chỉ một công ty/tháng để xuất toàn bộ bảng lương tháng đó.')
        period = self.period_id
        workspace = self.env['hrm.monthly.workspace'].create(dict(company_id=self.company_id.id,
            year=period.period_start.year, month=str(period.period_start.month)))
        return workspace.action_export_salary()


class SalaryMonthlyWorkspace(models.Model):
    _inherit = 'hrm.monthly.workspace'
    tenant_id = fields.Many2one(related='company_id.tenant_id', readonly=True)
    salary_export = fields.Binary(readonly=True, attachment=False)
    salary_filename = fields.Char(readonly=True)

    def action_salary_grid(self):
        period = self._period()
        domain = [('company_id', '=', self.company_id.id), ('period_id', '=', period.id)]
        if self.employee_id: domain.append(('employee_id', '=', self.employee_id.id))
        return {'type': 'ir.actions.act_window', 'name': 'Bảng lương theo mẫu Excel',
            'res_model': 'hrm.payroll.item', 'view_mode': 'list', 'domain': domain,
            'views': [(self.env.ref('hrm_data_import.salary_excel_list').id, 'list')],
            'search_view_id': self.env.ref('hrm_data_import.salary_excel_search').id}

    def _salary_xlsx(self):
        # Runtime export feature: native typed XLSX, not a server-side Excel engine.
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        period = self._period()
        domain = [('company_id', '=', self.company_id.id), ('period_id', '=', period.id)]
        if self.employee_id: domain.append(('employee_id', '=', self.employee_id.id))
        items = self.env['hrm.payroll.item'].search(domain, order='employee_id, payroll_id')
        if not items: raise UserError('Chưa có kết quả lương tháng này. Tính lương trước khi xuất.')
        if len(items.employee_id) != len(items): raise UserError('Có nhiều lần tính lương cùng nhân viên. Chọn lại kỳ/bảng lương để tránh cộng trùng.')
        book = Workbook(); sheet = book.active; sheet.title = 'Luong'
        sheet['B1'] = self.company_id.name
        sheet['C6'] = f'BẢNG LƯƠNG THÁNG {int(self.month):02} NĂM {self.year}'
        sheet['C7'] = 'Kết quả đã tính; cột trống = chưa có nguồn. Không áp dụng tỷ lệ bảo hiểm/thuế trong mẫu cũ.'
        groups = [('B9:B11', 'STT'), ('H9:M9', 'PHỤ CẤP/HỖ TRỢ'), ('O9:T9', 'NGÀY'),
            ('O10:P10', 'CÔNG'), ('W9:Y9', 'GIỜ CÔNG LÀM THÊM'), ('Z9:AC9', 'CÁC KHOẢN CỘNG THÊM'),
            ('AD9:AJ9', 'CÁC KHOẢN KHẤU TRỪ'), ('AG10:AI10', 'CÁC KHOẢN MIỄN THUẾ'),
            ('AO9:AZ9', 'CÔNG TY CÓ NGHĨA VỤ THANH TOÁN CHO NLĐ'),
            ('AO11:AT11', 'CÔNG TY'), ('AU11:AY11', 'NGƯỜI LAO ĐỘNG')]
        for i, title in enumerate(HEADERS, 1): sheet.cell(10, i, title)
        sheet['B10'] = None
        for span, title in groups:
            sheet.merge_cells(span); sheet[span.split(':')[0]] = title
        sheet['O11'] = 'THỬ VIỆC'
        sheet['P11'] = 'HĐLĐ'
        sheet['AG11'] = 'ĂN TRƯA'
        sheet['AH11'] = 'HỖ TRỢ ĐIỆN THOẠI'
        for n, item in enumerate(items, 1):
            values = item._excel_values(n)
            for i, col in enumerate(LETTERS, 1):
                value = values.get(col)
                # Force source strings to text, even names beginning with '='.
                cell = sheet.cell(n+11, i, value)
                if isinstance(value, str): cell.data_type = 's'
                elif isinstance(value, (int, float)): cell.number_format = '#,##0.00' if col in ('N', 'O', 'P', 'Q', 'U') else '#,##0'
        sheet.freeze_panes = 'G12'; sheet.auto_filter.ref = f'A10:AZ{len(items)+11}'
        for i in range(1, 53):
            sheet.column_dimensions[get_column_letter(i)].width = 22 if i != 3 else 30
        for row in sheet.iter_rows(min_row=9, max_row=11, max_col=52):
            for cell in row:
                cell.fill = PatternFill('solid', fgColor='E7EEF7'); cell.font = Font(bold=True, color='17365D')
                cell.alignment = Alignment(wrap_text=True, vertical='center')
        sheet.row_dimensions[10].height = 72
        trace = book.create_sheet('CongThuc_Log')
        trace.append(['Tháng', 'Mã NV', 'Khoản', 'Số tiền', 'Lần tính', 'Phiên bản',
                      'Phụ cấp miễn thuế', 'Phụ cấp tính thuế'])
        for item in items:
            for line in item.detail_ids:
                trace.append([item.salary_period, item.employee_id.employee_code, line.code, line.amount,
                              item.payroll_id.id, item.payroll_id.calculation_version,
                              line.tax_exempt_amount if line.contract_allowance else None,
                              line.taxable_amount if line.contract_allowance else None])
        trace.append([]); trace.append(['Công thức có hiệu lực', 'Khoản', 'Công thức Excel', 'Công thức hệ thống', 'Từ ngày', 'Đến ngày'])
        policies = self.env['hrm.payroll.formula'].search([('component_id.structure_id.company_id', '=', self.company_id.id),
            ('state', '=', 'approved'), ('effective_from', '<=', period.period_end),
            '|', ('effective_to', '=', False), ('effective_to', '>=', period.period_start)])
        for p in policies:
            trace.append(['Đã duyệt', p.component_id.code, p.excel_expression or '', p.expression, p.effective_from, p.effective_to or None])
        for row in trace:
            for cell in row:
                if isinstance(cell.value, str): cell.data_type = 's'
        for col in 'ABCDEFGH': trace.column_dimensions[col].width = 30 if col not in 'CD' else 55
        trace.freeze_panes = 'C2'
        output = io.BytesIO(); book.save(output)
        return output.getvalue()

    def action_export_salary(self):
        self.ensure_one(); self.check_access('write')
        content = self._salary_xlsx()
        self.write({'salary_export': BinaryBytes(content), 'salary_filename': f'BangLuong_{self.year}_{int(self.month):02}.xlsx'})
        audit(self, 'UPDATE', {'step': 'export_salary_excel', 'period_id': self.period_id.id, 'employee_id': self.employee_id.id})
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/hrm.monthly.workspace/{self.id}/salary_export/{self.salary_filename}?download=true', 'target': 'self'}
