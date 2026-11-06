import hashlib
import io
import json
import zipfile
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
from ..engine import DataError, expand_amount_columns, normalize, number, read_table, unpivot

DATASETS = [('attendance', 'Daily attendance'), ('performance', 'Performance amounts'),
            ('salary', 'Salary inputs'), ('history', 'Finalized payroll history')]
TARGETS = {'employee_code', 'source_record_id', 'revision', 'project_code', 'component_code',
           'work_date', 'shift_code', 'regular_hours', 'overtime_hours', 'attendance_symbol',
           'amount', 'currency', 'approval_reference'}
GRID_SOURCE = 'WEB-ATTENDANCE-GRID'
CONTRACT_COMPONENT_CODES = {'BASE', 'BASE_SALARY', 'LUNCH', 'MEAL', 'PETROL', 'PHONE',
                            'TRAVEL', 'HOUSING', 'TRAINING', 'RESP', 'PARK'}


def accepts_performance(component):
    return (component.component_type == 'earning' and component.code.upper() not in CONTRACT_COMPONENT_CODES
            and not component.code.upper().startswith('CONTRACT_ALLOWANCE_'))


def audit(rec, action, detail):
    company = rec.company_id if 'company_id' in rec._fields else (
        rec.profile_id.company_id if 'profile_id' in rec._fields else rec.component_id.structure_id.company_id)
    rec.env['hrm.audit.log'].sudo().create({
        'company_id': company.id,
        'tenant_id': rec.tenant_id.id, 'actor_user_id': rec.env.uid,
        'action': action, 'entity_type': rec._name, 'entity_id': rec.id,
        'metadata': detail,
    })


class Profile(models.Model):
    _name = 'hrm.import.profile'
    _description = 'HR import mapping version'
    _inherit = 'hrm.base.mixin'

    name = fields.Char(required=True)
    tenant_id = fields.Many2one('hrm.tenant', required=True)
    company_id = fields.Many2one('hrm.company', required=True)
    dataset = fields.Selection(DATASETS, required=True)
    source = fields.Char(required=True, help='Source system ID, stable across mapping versions')
    revision = fields.Integer(default=1, required=True)
    sheet = fields.Char()
    header_row = fields.Integer(default=1, required=True)
    data_start_row = fields.Integer(string='First data row (0 = after header)')
    cached_header = fields.Boolean(string='Use cached Excel header text')
    batch_identity = fields.Boolean(string='Use one revision and approval reference for the file',
        help='Generate a stable source ID from employee, date, shift and project when source control columns are missing.')
    locale = fields.Selection([('en', '1,234.56'), ('vi', '1.234,56')], default='vi', required=True)
    headers = fields.Json(help='Read template columns in order, including duplicate names')
    mapping_ids = fields.One2many('hrm.import.mapping', 'profile_id', copy=True)
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved')], default='draft', readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    monthly = fields.Boolean(string='Monthly attendance grid, days 1 to 31')
    first_day_column = fields.Integer(default=5, string='Day 1 column')
    symbols = fields.Json(default=dict, string='Convert symbols to paid hours', help='Example: {"X": 8, "KL": 0}. Does not create leave or overtime transactions.')
    sample_filename = fields.Char(string='Template filename')
    sample_data = fields.Binary(string='Template file', attachment=True)
    amount_columns = fields.Boolean(string='Each column is a performance / salary component',
        help='Map any number of company file columns. Select one salary component per amount column; no 100-column limit.')
    template_data = fields.Binary(compute='_compute_template', string='Mapped template file')
    template_filename = fields.Char(compute='_compute_template')

    def _default_headers(self):
        headers = ['employee_code', 'source_record_id', 'revision', 'approval_reference']
        if self.dataset == 'attendance':
            return headers + ([f'D{d:02}' for d in range(1, 32)] if self.monthly else ['work_date', 'regular_hours'])
        if self.amount_columns:
            codes = self.env['hrm.salary.component'].search([
                ('tenant_id', '=', self.tenant_id.id), ('structure_id.company_id', '=', self.company_id.id),
                ('status', '=', 'active')]).mapped('code')
            return headers + list(dict.fromkeys(codes))
        return headers + ['component_code', 'amount', 'currency']

    @api.depends('headers', 'name', 'dataset', 'amount_columns', 'monthly', 'mapping_ids.column',
                 'mapping_ids.target', 'mapping_ids.component_id', 'company_id', 'tenant_id')
    def _compute_template(self):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        for rec in self:
            book = Workbook()
            sheet = book.active
            sheet.title = rec.sheet or 'DuLieu'
            headers = rec.headers or rec._default_headers()
            for _ in range(max(0, rec.header_row - 1)): sheet.append([])
            sheet.append(headers)
            examples = {'employee_code': 'MA_NV', 'source_record_id': 'ID_NGUON_001',
                        'revision': 1, 'approval_reference': 'MA_PHE_DUYET', 'work_date': '2026-10-01',
                        'regular_hours': 8, 'component_code': 'MA_KHOAN', 'amount': 0,
                        'currency': rec.tenant_id.default_currency or 'VND'}
            row = [''] * len(headers)
            if rec.mapping_ids:
                for m in rec.mapping_ids:
                    if 1 <= m.column <= len(row): row[m.column - 1] = 0 if m.component_id else examples.get(m.target, '')
            else:
                row = [examples.get(h, 0 if rec.amount_columns else '') for h in headers]
            sheet.append(row)
            for cell in sheet[rec.header_row]:
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill('solid', fgColor='714B67')
                sheet.column_dimensions[cell.column_letter].width = 23
            sheet.freeze_panes = f'A{rec.header_row + 1}'
            instructions = book.create_sheet('HuongDan')
            for line in [
                'FILE MẪU IMPORT NHÂN SỰ', 'Thay dòng ví dụ MA_NV bằng mã nhân viên có trong hệ thống.',
                'Mã nhân viên và ID nguồn luôn lưu dạng Text; giữ số 0 đầu.',
                'Giữ ID nguồn khi nhập lại. Tăng revision khi thay giá trị.',
                'Ô trống không cung cấp dữ liệu. Số 0 thay khoản tiền cũ thành 0.',
                'File hiệu quả: thêm/bớt/đổi tên cột theo công ty; cập nhật mapping nháp rồi duyệt phiên bản mới.',
                'Mỗi cột tiền ánh xạ tới một khoản lương. Không có giới hạn nghiệp vụ 100 cột.',
                'Chỉ nhập giá trị, không dùng công thức hoặc liên kết ngoài trong file.',
                'Kỳ import được chọn trên giao diện. Không dùng file mẫu để tự động tạo nhân viên.',
            ]: instructions.append([line])
            instructions.column_dimensions['A'].width = 125
            stream = io.BytesIO()
            book.save(stream)
            book.close()
            rec.template_data = BinaryBytes(stream.getvalue())
            rec.template_filename = f'mau_{rec.dataset or "nhan_su"}_{rec.id}.xlsx'

    def action_download_template(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/web/content?model={self._name}&id={self.id}&field=template_data&filename_field=template_filename&download=true'}

    def action_add_amount_columns(self):
        self.ensure_one()
        self.check_access('write')
        self._lock_profile()
        if self.state != 'draft' or not self.amount_columns:
            raise UserError('Dùng mapping nháp với tùy chọn mỗi cột là một khoản tiền.')
        used = set(self.mapping_ids.mapped('column'))
        self.env['hrm.import.mapping'].create([
            {'profile_id': self.id, 'column': i, 'target': 'amount', 'data_type': 'number', 'required': False}
            for i in range(1, len(self.headers or []) + 1) if i not in used])
        return True

    def action_read_headers(self):
        self.check_access('write')
        for rec in self:
            if rec.state != 'draft' or not rec.sample_data or not rec.sample_filename:
                raise UserError('Chọn file mẫu cho mapping nháp trước.')
            try:
                headers, _rows = read_table(rec.sample_data.content, rec.sample_filename, rec.sheet, rec.header_row,
                                           rec.data_start_row, rec.cached_header)
            except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
                raise UserError(str(exc)) from exc
            rec.write({'headers': headers})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('state', 'draft') != 'draft' or v.get('approved_by') for v in vals_list):
            raise UserError('Tạo bản nháp rồi dùng nút duyệt.')
        return super().create(vals_list)

    def _spec(self):
        self.ensure_one()
        return [dict(column=m.column, target=m.target, type=m.data_type,
                     required=m.required, format=m.date_format) for m in self.mapping_ids if not m.component_id
                and not (self.batch_identity and m.target in ('source_record_id', 'revision', 'approval_reference'))]

    def _amount_spec(self):
        return [dict(column=m.column, component_code=m.component_id.code, required=m.required)
                for m in self.mapping_ids if m.component_id]

    def action_approve(self):
        self.check_access('write')
        if not self.env.su and not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise UserError('Cần quyền duyệt mapping và công thức.')
        for rec in self:
            rec._lock_profile()
            if rec.state != 'draft': raise UserError('Mapping đã duyệt.')
            targets = rec.mapping_ids.filtered(lambda m: not m.component_id).mapped('target')
            required = {'employee_code', 'source_record_id', 'revision', 'approval_reference'}
            if rec.batch_identity: required -= {'source_record_id', 'revision', 'approval_reference'}
            required |= {'work_date', 'regular_hours'} if rec.dataset == 'attendance' else {'component_code', 'amount', 'currency'}
            if rec.dataset == 'history' and rec.batch_identity:
                required -= {'component_code', 'currency'}
            if rec.amount_columns:
                if rec.dataset not in ('performance', 'salary') or rec.monthly:
                    raise UserError('Nhiều cột tiền chỉ áp dụng hiệu quả hoặc đầu vào lương.')
                required -= {'component_code', 'amount', 'currency'}
                money = rec.mapping_ids.filtered('component_id')
                if not money or any(m.target != 'amount' or m.data_type != 'number' for m in money):
                    raise UserError('Mỗi cột tiền phải có khoản lương, đích amount và kiểu Số.')
                if any(m.target == 'amount' and not m.component_id for m in rec.mapping_ids):
                    raise UserError('Chọn khoản lương cho tất cả cột tiền.')
                codes = money.mapped('component_id.code')
                if len(codes) != len(set(codes)):
                    raise UserError('Hai cột không được ánh xạ cùng mã khoản tiền.')
                if any(m.component_id.tenant_id != rec.tenant_id or m.component_id.structure_id.company_id != rec.company_id or m.component_id.status != 'active' for m in money):
                    raise UserError('Khoản lương phải đang hiệu lực và thuộc đúng công ty/tenant.')
                if rec.dataset == 'performance' and not all(accepts_performance(c) for c in money.component_id):
                    raise UserError('Chỉ ánh xạ khoản hiệu quả. Lương và phụ cấp lấy từ hợp đồng.')
                if set(targets) & {'component_code', 'amount'}:
                    raise UserError('Không trộn bộ trường khoản tiền dạng dòng với nhiều cột tiền.')
            elif any(m.component_id for m in rec.mapping_ids):
                raise UserError('Bật tùy chọn mỗi cột là một khoản tiền trước khi gán khoản lương.')
            if rec.monthly:
                if rec.dataset != 'attendance' or rec.first_day_column < 1 or rec.first_day_column + 30 > len(rec.headers or []):
                    raise UserError('Bảng ngang cần đủ 31 cột ngày và dataset công.')
                required -= {'work_date', 'regular_hours'}
                if rec.symbols and not isinstance(rec.symbols, dict): raise UserError('Bảng ký hiệu phải là object JSON.')
            if not required.issubset(targets) or len(targets) != len(set(targets)):
                raise UserError('Mapping thiếu trường bắt buộc hoặc trùng trường đích.')
            if not isinstance(rec.headers, list) or not rec.headers or rec.header_row < 1:
                raise UserError('Cần danh sách header và dòng header hợp lệ.')
            if rec.data_start_row and rec.data_start_row <= rec.header_row:
                raise UserError('Dòng dữ liệu phải sau dòng tiêu đề.')
            if rec.company_id.tenant_id != rec.tenant_id:
                raise UserError('Công ty không thuộc tenant.')
            if any(m.column < 1 or m.column > len(rec.headers) for m in rec.mapping_ids):
                raise UserError('Chỉ số cột ngoài header.')
            columns = rec.mapping_ids.mapped('column')
            if len(columns) != len(set(columns)): raise UserError('Một cột nguồn chỉ ánh xạ một lần.')
            super(Profile, rec).write({'state': 'approved', 'approved_by': self.env.uid})
            audit(rec, 'APPROVE', {'revision': rec.revision, 'mapping': rec._spec(), 'amount_columns': rec._amount_spec()})

    def write(self, vals):
        self._lock_profile()
        if any(r.state == 'approved' for r in self):
            raise UserError('Mapping đã duyệt bất biến. Sao chép để tạo phiên bản mới.')
        if 'state' in vals or 'approved_by' in vals:
            raise UserError('Dùng nút duyệt mapping.')
        return super().write(vals)

    def _lock_profile(self):
        if self.ids:
            self.env.cr.execute('SELECT id FROM hrm_import_profile WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()

    def copy(self, default=None):
        return super().copy(dict(default or {}, state='draft', approved_by=False, revision=self.revision + 1))

    def unlink(self):
        self._lock_profile()
        if any(r.state == 'approved' for r in self): raise UserError('Không xóa mapping đã duyệt.')
        return super().unlink()


class Mapping(models.Model):
    _name = 'hrm.import.mapping'
    _description = 'File column mapping'
    profile_id = fields.Many2one('hrm.import.profile', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(related='profile_id.tenant_id', store=True)
    column = fields.Integer(required=True, help='Column position starts at 1')
    target = fields.Selection([(x, x) for x in sorted(TARGETS)], required=True)
    data_type = fields.Selection([('text', 'Text'), ('number', 'Number'), ('date', 'Day')], default='text', required=True)
    required = fields.Boolean(default=True)
    date_format = fields.Char(default='%Y-%m-%d')
    source_header = fields.Char(string='Source column name', compute='_compute_source_header')
    component_id = fields.Many2one('hrm.salary.component', string='Performance / salary component', ondelete='restrict',
        help='Select the payroll component for this amount column.')

    @api.depends('column', 'profile_id.headers')
    def _compute_source_header(self):
        for rec in self:
            headers = rec.profile_id.headers or []
            rec.source_header = headers[rec.column - 1] if 1 <= rec.column <= len(headers) else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            profile = self.env['hrm.import.profile'].browse(vals['profile_id'])
            profile._lock_profile()
            if profile.state != 'draft':
                raise UserError('Không sửa mapping đã duyệt.')
        return super().create(vals_list)

    def write(self, vals):
        self.profile_id._lock_profile()
        if 'profile_id' in vals or any(r.profile_id.state != 'draft' for r in self):
            raise UserError('Không chuyển hoặc sửa mapping đã duyệt.')
        return super().write(vals)

    def unlink(self):
        self.profile_id._lock_profile()
        if any(r.profile_id.state != 'draft' for r in self): raise UserError('Không xóa mapping đã duyệt.')
        return super().unlink()


class Batch(models.Model):
    _name = 'hrm.import.batch'
    _description = 'Import batches and row logs'
    _order = 'id desc'
    _rec_name = 'filename'

    profile_id = fields.Many2one('hrm.import.profile', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='period_id.company_id', store=True)
    tenant_id = fields.Many2one(related='profile_id.tenant_id', store=True)
    period_id = fields.Many2one('hrm.payroll.period', required=True)
    filename = fields.Char(required=True)
    file_data = fields.Binary(required=True, attachment=True)
    file_hash = fields.Char(readonly=True)
    source_revision = fields.Integer(string='File revision', default=1)
    approval_reference = fields.Char(string='File approval reference')
    state = fields.Selection([('draft', 'Not checked'), ('ready', 'Ready to save'),
                              ('failed', 'Has errors'), ('committed', 'Saved')], default='draft', readonly=True)
    message = fields.Text(readonly=True)
    line_ids = fields.One2many('hrm.import.line', 'batch_id', readonly=True)
    committed_by = fields.Many2one('res.users', readonly=True)
    committed_at = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        managed = {'state', 'message', 'file_hash', 'line_ids', 'committed_by', 'committed_at'}
        if any(set(v) & managed for v in vals_list):
            raise UserError('Trạng thái và log do hệ thống quản lý.')
        return super().create(vals_list)

    def _lock_scope(self):
        self.ensure_one()
        if self.profile_id.dataset == 'salary':
            raise UserError('Chỉ nhập file công và hiệu quả cho kỳ lương. Lương và phụ cấp lấy từ hợp đồng đang hiệu lực.')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (self.period_id.id,))
        self.period_id.invalidate_recordset()
        if self.profile_id.dataset == 'attendance' and self.period_id.attendance_locked:
            raise UserError('Kỳ đang khóa nhập công. Mở khóa trên Bảng nhập công theo tháng.')
        if self.period_id.status not in ('open', 'processing'):
            raise UserError('Kỳ đã tính hoặc đã khóa. Không được thay đầu vào.')
        if self.period_id.company_id != self.profile_id.company_id or self.period_id.tenant_id != self.tenant_id:
            raise UserError('Kỳ và mapping không cùng công ty/tenant.')
        runs = self.env['hrm.payroll'].search([('period_id', '=', self.period_id.id), ('status', 'not in', ['draft', 'processing'])])
        if runs: raise UserError('Đã có bảng lương tính/duyệt. Cần xử lý lại kỳ trước khi import.')

    def _validate_row(self, data):
        employee = self.env['hr.employee'].search([('tenant_id', '=', self.tenant_id.id), ('employee_code', '=', data.get('employee_code'))])
        if len(employee) != 1: raise DataError('EMPLOYEE_NOT_FOUND_OR_AMBIGUOUS')
        assignment = self.env['hrm.employee.assignment'].search([
            ('employee_id', '=', employee.id), ('tenant_id', '=', self.tenant_id.id),
            ('company_id', '=', self.profile_id.company_id.id),
            ('start_date', '<=', self.period_id.period_start),
            '|', ('end_date', '=', False), ('end_date', '>=', self.period_id.period_end)])
        if not assignment and employee.hrm_company_id != self.profile_id.company_id:
            raise DataError('EMPLOYEE_COMPANY_MISMATCH')
        for key in ('source_record_id', 'revision', 'approval_reference'):
            if not data.get(key): raise DataError('REQUIRED: ' + key)
        revision = number(data['revision'], 'en')
        if revision < 1 or revision != int(revision): raise DataError('INVALID_REVISION')
        data['revision'] = str(int(revision))
        if self.profile_id.dataset == 'attendance':
            day = date.fromisoformat(data['work_date'])
            if not self.period_id.period_start <= day <= self.period_id.period_end:
                raise DataError('DATE_OUTSIDE_PERIOD')
            if (employee.hire_date and day < employee.hire_date) or (employee.termination_date and day > employee.termination_date):
                raise DataError('DATE_OUTSIDE_EMPLOYMENT')
            hours = number(data['regular_hours'], 'en')
            overtime = number(data.get('overtime_hours') or '0', 'en')
            if hours < 0 or overtime < 0 or hours + overtime > 24:
                raise DataError('INVALID_HOURS')
            source = self.profile_id.source
            other = self.env['hrm.import.input'].search([
                ('period_id', '=', self.period_id.id), ('employee_id', '=', employee.id),
                ('dataset', '=', 'attendance'),
                ('source', '!=' if source == GRID_SOURCE else '=', GRID_SOURCE),
            ])
            if any(row.payload.get('work_date') == data['work_date'] for row in other):
                raise DataError('Ngày công đã có ở bảng chấm công hoặc nguồn nhập khác. Hãy sửa tại nguồn đã nhập.')
        else:
            if self.profile_id.dataset == 'history' and self.profile_id.batch_identity:
                data.setdefault('currency', self.tenant_id.default_currency)
                data.setdefault('component_code', 'NET_HISTORY')
            number(data['amount'], 'en')
            if data.get('currency') != self.tenant_id.default_currency:
                raise DataError('CURRENCY_MISMATCH')
            if not data.get('component_code'): raise DataError('COMPONENT_REQUIRED')
            if self.profile_id.dataset != 'history':
                components = self.env['hrm.salary.component'].search([
                    ('tenant_id', '=', self.tenant_id.id), ('code', '=', data['component_code']),
                    ('structure_id.company_id', '=', self.profile_id.company_id.id), ('status', '=', 'active')])
                if not components: raise DataError('COMPONENT_NOT_FOUND')
                if self.profile_id.dataset == 'performance' and not all(accepts_performance(c) for c in components):
                    raise DataError('File hiệu quả không được nhập đè lương hợp đồng, phụ cấp hoặc khoản khấu trừ.')
        return employee

    def _existing(self, data):
        return self.env['hrm.import.input'].search([
            ('tenant_id', '=', self.tenant_id.id), ('company_id', '=', self.profile_id.company_id.id),
            ('period_id', '=', self.period_id.id), ('dataset', '=', self.profile_id.dataset),
            ('source', '=', self.profile_id.source), ('source_record_id', '=', data['source_record_id'])], limit=1)

    def _decision(self, data, old):
        if not old: return 'create'
        if int(data['revision']) < old.revision: raise DataError('STALE_REVISION')
        if data == old.payload: return 'unchanged'
        if int(data['revision']) == old.revision: raise DataError('REVISION_CONFLICT')
        if data['employee_code'] != old.payload['employee_code']:
            raise DataError('SOURCE_ID_EMPLOYEE_CHANGED')
        return 'update'

    def action_preview(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM hrm_import_batch WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.state == 'committed': raise UserError('Batch đã ghi bất biến.')
        self._lock_scope()
        if self.profile_id.state != 'approved': raise UserError('Mapping chưa được duyệt.')
        self.line_ids.sudo().unlink()
        try:
            payload = self.file_data.content
            headers, rows = read_table(payload, self.filename, self.profile_id.sheet, self.profile_id.header_row,
                                      self.profile_id.data_start_row, self.profile_id.cached_header)
            if headers != self.profile_id.headers: raise DataError('PROFILE_SCHEMA_CHANGED')
            seen, counts, errors = set(), {}, 0
            expanded = []
            for row_no, raw in rows:
                if all(v is None or str(v).strip() == '' for v in raw): continue
                try:
                    data = normalize(raw, self.profile_id._spec(), self.profile_id.locale)
                    if self.profile_id.batch_identity:
                        if self.source_revision < 1 or not (self.approval_reference or '').strip():
                            raise DataError('Cần phiên bản file dương và tham chiếu xác nhận file.')
                        data.update(source_record_id=json.dumps([data.get(k, '') for k in
                            ('employee_code', 'work_date', 'shift_code', 'project_code')], ensure_ascii=False),
                            revision=str(self.source_revision), approval_reference=self.approval_reference.strip())
                    if self.profile_id.monthly:
                        daily = unpivot(data, raw, self.period_id.period_start.year, self.period_id.period_start.month,
                                        self.profile_id.first_day_column, self.profile_id.symbols or {}, self.profile_id.locale)
                    elif self.profile_id.amount_columns:
                        daily = expand_amount_columns(data, raw, self.profile_id._amount_spec(),
                                                      self.profile_id.locale, self.tenant_id.default_currency)
                    else:
                        daily = [data]
                    expanded.extend((row_no, raw, d, None) for d in daily)
                except (ValueError, KeyError, TypeError) as exc:
                    expanded.append((row_no, raw, {}, str(exc)))
            if not expanded: raise DataError('File chưa có dòng dữ liệu để nhập.')
            if len(expanded) > 50000: raise DataError('EXPANDED_ROWS_LIMIT: tối đa 50000 dòng ngày')
            for row_no, raw, data, parse_error in expanded:
                vals = {'batch_id': self.id, 'row_no': row_no, 'raw': json.loads(json.dumps(raw, default=str))}
                try:
                    if parse_error: raise DataError(parse_error)
                    vals['normalized'] = data
                    self._validate_row(data)
                    key = data['source_record_id']
                    if key in seen: raise DataError('DUPLICATE_SOURCE_ID')
                    seen.add(key)
                    old = self._existing(data)
                    decision = self._decision(data, old)
                    vals.update(result=decision, previous=old.payload or {} if old else {})
                    counts[decision] = counts.get(decision, 0) + 1
                except (ValueError, KeyError, TypeError) as exc:
                    vals.update(result='reject', error=str(exc))
                    errors += 1
                self.env['hrm.import.line'].sudo().create(vals)
            if not self.line_ids: raise DataError('EMPTY_FILE')
            super(Batch, self).write({'file_hash': hashlib.sha256(payload).hexdigest(),
                'state': 'failed' if errors else 'ready', 'message': json.dumps(dict(counts, reject=errors))})
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
            super(Batch, self).write({'state': 'failed', 'message': str(exc)})
        audit(self, 'IMPORT', {'step': 'preview', 'state': self.state, 'summary': self.message})
        return True

    def action_commit(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM hrm_import_batch WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.state == 'committed': return True
        if self.state != 'ready': raise UserError('Cần xem trước và sửa hết lỗi trước khi ghi.')
        self._lock_scope()
        try:
            with self.env.cr.savepoint():
                for line in self.line_ids:
                    data = line.normalized
                    employee = self._validate_row(data)
                    old = self._existing(data)
                    if (old.payload if old else {}) != (line.previous or {}):
                        raise DataError('PREVIEW_CONFLICT: dữ liệu đã thay đổi, hãy xem trước lại')
                    decision = self._decision(data, old)
                    if decision == 'unchanged': continue
                    vals = dict(tenant_id=self.tenant_id.id, company_id=self.profile_id.company_id.id,
                                period_id=self.period_id.id, dataset=self.profile_id.dataset,
                                source=self.profile_id.source, source_record_id=data['source_record_id'],
                                revision=int(data['revision']), employee_id=employee.id, payload=data,
                                batch_id=self.id)
                    if old: old.sudo().write(vals)
                    else: self.env['hrm.import.input'].sudo().create(vals)
                super(Batch, self).write({'state': 'committed', 'committed_by': self.env.uid,
                                          'committed_at': fields.Datetime.now(), 'message': 'Đã ghi toàn bộ batch.'})
                audit(self, 'IMPORT', {'step': 'commit', 'sha256': self.file_hash, 'rows': len(self.line_ids)})
        except (DataError, UserError) as exc:
            super(Batch, self).write({'state': 'failed', 'message': str(exc)})
            audit(self, 'IMPORT', {'step': 'commit_failed', 'error': str(exc)})
        return True

    def write(self, vals):
        if self.ids:
            self.env.cr.execute('SELECT id FROM hrm_import_batch WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()
        if any(r.state == 'committed' for r in self): raise UserError('Batch đã ghi bất biến.')
        if set(vals) - {'profile_id', 'period_id', 'filename', 'file_data', 'source_revision', 'approval_reference'}:
            raise UserError('Trạng thái và log do hệ thống quản lý.')
        vals.update(state='draft', message=False, file_hash=False)
        return super().write(vals)

    def unlink(self):
        raise UserError('Giữ batch để truy vết. Không được xóa.')


class Line(models.Model):
    _name = 'hrm.import.line'
    _description = 'Import validation log'
    _order = 'row_no, id'
    batch_id = fields.Many2one('hrm.import.batch', required=True, ondelete='restrict')
    tenant_id = fields.Many2one(related='batch_id.tenant_id', store=True)
    row_no = fields.Integer()
    raw = fields.Json()
    normalized = fields.Json()
    previous = fields.Json()
    result = fields.Selection([(s, s) for s in ('create', 'update', 'unchanged', 'reject')])
    error = fields.Text()


class Input(models.Model):
    _name = 'hrm.import.input'
    _description = 'Imported inputs with source and revision'
    tenant_id = fields.Many2one('hrm.tenant', required=True)
    company_id = fields.Many2one('hrm.company', required=True)
    period_id = fields.Many2one('hrm.payroll.period', required=True)
    dataset = fields.Selection(DATASETS, required=True)
    source = fields.Char(required=True)
    source_record_id = fields.Char(required=True)
    revision = fields.Integer(required=True)
    employee_id = fields.Many2one('hr.employee', required=True)
    payload = fields.Json(required=True)
    batch_id = fields.Many2one('hrm.import.batch', required=True, ondelete='restrict')
    _source_unique = models.Constraint(
        'UNIQUE(tenant_id,company_id,period_id,dataset,source,source_record_id)',
        'Source key already exists.')
