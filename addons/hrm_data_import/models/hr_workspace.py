import hashlib
import io
from html import escape
from datetime import date, datetime

from openpyxl import load_workbook
from odoo import api, fields, models
from odoo.exceptions import UserError
from .imports import audit

EMPLOYEE_COLUMNS = [
    ('code', 'employee_code'), ('full_name', 'name'), ('working_status_id', 'current_status'),
    ('birthday', 'hrm_birth_date'), ('phone_number', 'work_phone'), ('mobile_phone', 'mobile_phone'),
    ('email', 'work_email'), ('identity_card_number', 'hrm_identity_number'),
    ('identity_card_issue_date', 'hrm_identity_date'), ('identity_card_issue_by', 'hrm_identity_place'),
    ('bank_number', 'hrm_bank_number'), ('bank_name', 'hrm_bank_name'), ('bank_address', 'hrm_bank_branch'),
    ('start_date', 'hire_date'), ('end_date', 'termination_date'), ('note', 'additional_note')]


class EmployeeImport(models.Model):
    _name = 'hrm.employee.import'
    _description = 'Import employee records'
    _rec_name = 'filename'

    company_id = fields.Many2one('hrm.company', required=True)
    tenant_id = fields.Many2one(related='company_id.tenant_id', store=True)
    filename = fields.Char(required=True)
    file_data = fields.Binary(required=True, attachment=True)
    sheet = fields.Char(default='VP', required=True)
    result = fields.Text(readonly=True)
    state = fields.Selection([('draft', 'Not imported'), ('done', 'Imported')], default='draft', readonly=True)
    update_existing = fields.Boolean(string='Update existing employees (blank cells keep current values)')
    mapping_ids = fields.One2many('hrm.employee.import.column', 'import_id', string='Excel column mapping',
        default=lambda s: [(0, 0, {'source': source, 'target': target}) for source, target in EMPLOYEE_COLUMNS])
    mapping = fields.Json(compute='_compute_mapping')
    preview = fields.Json(string='Data preview', readonly=True)

    @api.depends('mapping_ids.source', 'mapping_ids.target')
    def _compute_mapping(self):
        for rec in self:
            rec.mapping = {m.source: m.target for m in rec.mapping_ids}

    def _rows(self):
        self.ensure_one()
        payload = self.file_data.content
        if len(payload) > 5 * 1024 * 1024:
            raise UserError('File tối đa 5 MB.')
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024:
                    raise UserError('File giải nén quá lớn.')
                if any('vbaProject' in n for n in archive.namelist()):
                    raise UserError('Không hỗ trợ macro.')
            # Read literal source columns only; never execute or trust cached formulas.
            book = load_workbook(io.BytesIO(payload), read_only=True, data_only=False, keep_links=False)
            if self.sheet not in book.sheetnames:
                raise UserError('Không tìm thấy sheet: ' + self.sheet)
            rows = book[self.sheet].iter_rows(values_only=True)
            headers = list(next(rows))
            mapping = self.mapping or {}
            if len(mapping) != len(self.mapping_ids):
                raise UserError('Tên cột nguồn không được trùng.')
            if set(mapping.values()) - {target for source, target in EMPLOYEE_COLUMNS} or len(mapping.values()) != len(set(mapping.values())):
                raise UserError('Mapping chứa trường không hỗ trợ hoặc đích bị trùng.')
            reverse = {target: source for source, target in mapping.items()}
            if any(target not in reverse for target in ('employee_code', 'name', 'current_status')):
                raise UserError('Mapping cần mã nhân viên, họ tên, trạng thái.')
            required = tuple(reverse[t] for t in ('employee_code', 'name', 'current_status'))
            if any(headers.count(key) != 1 for key in required):
                raise UserError('Cần cột duy nhất: code, full_name, working_status_id.')
            records, seen = [], set()
            for no, cells in enumerate(rows, 2):
                if no > 10001:
                    raise UserError('Tối đa 10.000 dòng.')
                raw = dict(zip(headers, cells))
                row = {source: raw.get(reverse.get(target)) for source, target in EMPLOYEE_COLUMNS}
                code = row.get('code')
                if not code and not row.get('full_name'):
                    continue
                if not isinstance(code, str) or not code.strip() or code.startswith('='):
                    raise UserError(f'Dòng {no}: mã nhân viên phải là chữ, không dùng công thức.')
                code = code.strip()
                if code in seen:
                    raise UserError(f'Dòng {no}: trùng mã {code}.')
                seen.add(code)
                name = row.get('full_name')
                status = {'Đang làm việc': 'active', 'Nghỉ việc': 'terminated'}.get(row.get('working_status_id'))
                if not isinstance(name, str) or not name.strip() or name.startswith('=') or not status:
                    raise UserError(f'Dòng {no}: thiếu tên hoặc trạng thái không hợp lệ.')
                values = {'name': name.strip(), 'hrm_source_profile': {str(key): str(value)
                    for key, value in raw.items() if key and value is not None and
                    not (isinstance(value, str) and value.startswith('='))}}
                for source, target in [('phone_number', 'work_phone'), ('mobile_phone', 'mobile_phone'),
                                       ('email', 'work_email'), ('bank_number', 'hrm_bank_number'),
                                       ('bank_name', 'hrm_bank_name'), ('bank_address', 'hrm_bank_branch'),
                                       ('note', 'additional_note'),
                                       ('identity_card_number', 'hrm_identity_number'),
                                       ('identity_card_issue_by', 'hrm_identity_place')]:
                    value = row.get(source)
                    if value is not None and str(value).strip():
                        if isinstance(value, str) and value.startswith('='):
                            raise UserError(f'Dòng {no}: {source} không nhận công thức.')
                        values[target] = str(value).strip()
                for source, target in [('birthday', 'hrm_birth_date'), ('identity_card_issue_date', 'hrm_identity_date'),
                                       ('start_date', 'hire_date'), ('end_date', 'termination_date')]:
                    value = row.get(source)
                    if value:
                        if not isinstance(value, (date, datetime)):
                            raise UserError(f'Dòng {no}: {source} phải là ngày Excel.')
                        values[target] = value.date() if isinstance(value, datetime) else value
                records.append((code, status, values))
            book.close()
            return records
        except (ValueError, zipfile.BadZipFile, KeyError, StopIteration) as exc:
            raise UserError('File XLSX không hợp lệ: ' + str(exc)) from exc

    def action_preview(self):
        self.check_access('write')
        for rec in self:
            rows = rec._rows()
            rec.preview = [{'code': code, 'status': status, **{k: str(v) for k, v in values.items()}} for code, status, values in rows]
            rec.result = f'{len(rows)} hồ sơ hợp lệ. Ô trống giữ nguyên. Không nhập cột thuế/BHXH đang cần đối chiếu. Bấm Ghi hồ sơ để lưu.'

    def action_import(self):
        self.check_access('write')
        for rec in self:
            self.env.cr.execute('SELECT id FROM hrm_company WHERE id=%s FOR UPDATE', (rec.company_id.id,))
            self.env.cr.execute('SELECT id FROM hrm_employee_import WHERE id=%s FOR UPDATE', (rec.id,))
            rec.invalidate_recordset()
            if rec.state != 'draft':
                raise UserError('File đã nhập; tạo lần nhập mới để cập nhật.')
            created = updated = skipped = 0
            for code, status, values in rec._rows():
                employee = self.env['hr.employee'].with_context(active_test=False).search([
                    ('tenant_id', '=', rec.tenant_id.id), ('employee_code', '=', code)])
                if employee and employee.hrm_company_id != rec.company_id:
                    raise UserError('Mã đã tồn tại ngoài phạm vi công ty được chọn.')
                if employee:
                    if rec.update_existing:
                        old = {k: str(v) for k, v in employee.read(list(values))[0].items()}
                        employee.write(values)
                        audit(rec, 'UPDATE', {'employee_id': employee.id, 'before': old,
                                             'after': {k: str(v) for k, v in values.items()}})
                        updated += 1
                    else:
                        skipped += 1
                else:
                    employee = self.env['hr.employee'].create(dict(values, tenant_id=rec.tenant_id.id,
                        hrm_company_id=rec.company_id.id, employee_code=code,
                        current_status=status, active=status != 'terminated'))
                    created += 1
            super(EmployeeImport, rec).write({'state': 'done', 'result': f'Tạo {created}; cập nhật {updated}; bỏ qua {skipped}.'})
            audit(rec, 'IMPORT', {'sha256': hashlib.sha256(rec.file_data.content).hexdigest(),
                                 'created': created, 'updated': updated, 'skipped': skipped})

    @api.model_create_multi
    def create(self, vals_list):
        if any('state' in v or 'result' in v for v in vals_list):
            raise UserError('Trạng thái do hệ thống quản lý.')
        return super().create(vals_list)

    def write(self, vals):
        if 'state' in vals or any(r.state == 'done' for r in self):
            raise UserError('Lần nhập đã ghi không được sửa.')
        return super().write(vals)

    def unlink(self):
        raise UserError('Giữ lịch sử nhập để đối chiếu.')


class EmployeeImportColumn(models.Model):
    _name = 'hrm.employee.import.column'
    _description = 'Employee import column mapping'
    import_id = fields.Many2one('hrm.employee.import', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='import_id.company_id', store=True)
    source = fields.Char(string='Excel column name', required=True)
    target = fields.Selection([(target, source + ' → ' + target) for source, target in EMPLOYEE_COLUMNS],
        string='Employee information', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        parents = self.env['hrm.employee.import'].browse([v.get('import_id') for v in vals_list if v.get('import_id')])
        if parents.filtered(lambda p: p.state != 'draft'): raise UserError('Mapping đã nhập không sửa.')
        return super().create(vals_list)

    def write(self, vals):
        if 'import_id' in vals or self.import_id.filtered(lambda p: p.state != 'draft'):
            raise UserError('Mapping đã nhập không sửa hoặc chuyển lần nhập.')
        return super().write(vals)

    def unlink(self):
        if self.import_id.filtered(lambda p: p.state != 'draft'): raise UserError('Mapping đã nhập không xóa.')
        return super().unlink()


class EmployeeDetails(models.Model):
    _inherit = 'hr.employee'
    hrm_birth_date = fields.Date(string='Date of birth (HR source)')
    hrm_identity_number = fields.Char(string='National ID number', groups='hrm_data_import.group_import_operator')
    hrm_identity_date = fields.Date(string='Issue date', groups='hrm_data_import.group_import_operator')
    hrm_identity_place = fields.Char(string='Issuing authority', groups='hrm_data_import.group_import_operator')
    hrm_bank_number = fields.Char(string='Bank account number', groups='hrm_data_import.group_import_operator')
    hrm_bank_name = fields.Char(string='Bank', groups='hrm_data_import.group_import_operator')
    hrm_bank_branch = fields.Char(string='Bank branch', groups='hrm_data_import.group_import_operator')
    hrm_salary_ids = fields.One2many('hrm.employee.salary', 'employee_id', string='Payroll settings')
    hrm_contract_ids = fields.One2many('hrm.employee.contract', 'employee_id', string='Contracts and addenda')
    hrm_source_profile = fields.Json(string='Original Excel information (unprocessed)', readonly=True,
        groups='hrm_data_import.group_import_operator', help='Keep original column names for reconciliation. Do not calculate payroll from unverified values.')
    hrm_source_table = fields.Html(compute='_compute_source_table', string='Excel information', sanitize=True,
        groups='hrm_data_import.group_import_operator')

    @api.depends('hrm_source_profile')
    def _compute_source_table(self):
        labels = {'code':'Mã nhân viên', 'full_name':'Họ và tên', 'birthday':'Ngày sinh',
            'working_status_id':'Trạng thái nguồn', 'marital_status_id':'Hôn nhân', 'people_id':'Dân tộc',
            'religion_id':'Tôn giáo', 'nationality_id':'Quốc tịch', 'identity_card_number':'CCCD/CMND',
            'identity_card_issue_date':'Ngày cấp CCCD/CMND', 'identity_card_issue_by':'Nơi cấp',
            'passport':'Hộ chiếu', 'passport_issue_date':'Ngày cấp hộ chiếu', 'passport_expired_date':'Hết hạn hộ chiếu',
            'phone_number':'Điện thoại', 'mobile_phone':'Di động', 'email':'Email',
            'start_date':'Ngày vào làm (mô phỏng trong bộ demo)', 'end_date':'Ngày nghỉ (mô phỏng trong bộ demo)',
            'bank_number':'Số tài khoản', 'bank_name':'Ngân hàng', 'bank_address':'Chi nhánh',
            'social_insurance_number':'BHXH từ nguồn — cần đối chiếu', 'bhxh':'BHXH cột phụ — cần đối chiếu',
            'personal_tax_number':'Mã số thuế từ nguồn', 'personal_tax_issue_date':'Cột personal_tax_issue_date — cần đối chiếu',
            'note':'Ghi chú'}
        for rec in self:
            rows = ''.join('<tr><th style="width:35%">'+escape(labels.get(key,key))+'</th><td>'+escape(str(value))+'</td></tr>'
                for key,value in (rec.hrm_source_profile or {}).items())
            rec.hrm_source_table = '<table class="table table-sm table-striped">'+rows+'</table>' if rows else '<p>Chưa có thông tin nguồn.</p>'

    def action_monthly_overview(self):
        self.ensure_one()
        self.check_access('read')
        if not self.hrm_company_id: raise UserError('Chọn công ty của nhân viên trước.')
        period = self.env['hrm.payroll.period'].search([('company_id', '=', self.hrm_company_id.id)], order='period_start desc', limit=1)
        ref = period.period_start if period else fields.Date.today()
        screen = self.env['hrm.monthly.workspace'].search([('company_id', '=', self.hrm_company_id.id),
            ('employee_id', '=', self.id), ('year', '=', ref.year), ('month', '=', str(ref.month))], limit=1)
        if not screen:
            screen = self.env['hrm.monthly.workspace'].create(dict(company_id=self.hrm_company_id.id,
                employee_id=self.id, year=ref.year, month=str(ref.month)))
        screen.action_refresh()
        return {'type': 'ir.actions.act_window', 'name': 'Công và lương nhân viên theo tháng',
                'res_model': 'hrm.monthly.workspace', 'res_id': screen.id, 'view_mode': 'form'}


class PeriodWorkspace(models.Model):
    _inherit = 'hrm.payroll.period'
    _rec_name = 'period_code'
    correction_reason = fields.Text(string='Reason for reopening')
    readiness = fields.Text(string='Validation results', readonly=True)
    selected_employee_ids = fields.Many2many('hr.employee', string='Payroll employees (blank = all)',
        domain="[('hrm_company_id', '=', company_id), ('current_status', 'in', ['active', 'onboarding'])]")
    require_imported_attendance = fields.Boolean(string='Attendance required', default=True)
    require_imported_performance = fields.Boolean(string='Performance required', default=True)

    @api.constrains('company_id', 'tenant_id', 'selected_employee_ids')
    def _check_workspace_company(self):
        for rec in self:
            if rec.company_id.tenant_id != rec.tenant_id or rec.selected_employee_ids.filtered(lambda e: e.hrm_company_id != rec.company_id):
                raise UserError('Kỳ và nhân viên phải thuộc cùng công ty.')

    def _open_import(self, dataset):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': 'Nhập file theo kỳ',
                'res_model': 'hrm.import.batch', 'view_mode': 'list,form',
                'domain': [('period_id', '=', self.id), ('profile_id.dataset', '=', dataset)],
                'context': {'default_period_id': self.id, 'search_default_group_by_profile': 1,
                            'hrm_dataset': dataset, 'hrm_company_id': self.company_id.id}}

    def action_import_attendance(self): return self._open_import('attendance')
    def action_import_performance(self): return self._open_import('performance')
    def action_import_salary(self):
        raise UserError('Chỉ nhập file công và hiệu quả. Lương và phụ cấp lấy từ hợp đồng đang hiệu lực.')

    def _readiness_errors(self):
        self.ensure_one()
        employees = self.env['hr.employee'].search([('hrm_company_id', '=', self.company_id.id),
                                                   ('current_status', 'in', ['active', 'onboarding'])])
        errors = []
        if self.selected_employee_ids:
            if self.selected_employee_ids - employees:
                raise UserError('Danh sách chọn có nhân viên ngoài công ty hoặc không đang làm việc.')
            employees = self.selected_employee_ids
        if not employees: errors.append('Không có nhân viên đang làm việc trong công ty.')
        probe = self.env['hrm.payroll'].new(dict(tenant_id=self.tenant_id.id, company_id=self.company_id.id, period_id=self.id))
        for employee in employees:
            try:
                salary = probe._active_salary(employee)
                if not salary.structure_id.component_ids.filtered(lambda c: c.status == 'active'):
                    raise UserError('Chưa có khoản lương trong cơ cấu.')
                inputs = self.env['hrm.import.input'].search([('period_id', '=', self.id),
                    ('company_id', '=', self.company_id.id), ('employee_id', '=', employee.id)])
                if self.require_imported_attendance and not inputs.filtered(lambda i: i.dataset == 'attendance'):
                    raise UserError('Thiếu công tháng.')
                if self.require_imported_performance and not inputs.filtered(lambda i: i.dataset == 'performance'):
                    raise UserError('Thiếu hiệu quả tháng.')
            except UserError as exc:
                errors.append(f'{employee.employee_code} — {exc}')
        return errors

    def action_check_ready(self):
        self.check_access('write')
        for rec in self:
            errors = rec._readiness_errors()
            rec.readiness = '\n'.join(errors) if errors else 'Đủ hồ sơ cơ bản. Tính lương sẽ kiểm tra chi tiết công thức, công và khoản tiền.'

    def action_quick_payroll(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.status not in ('open', 'processing'):
            raise UserError('Mở lại kỳ chưa duyệt trước khi tính lại.')
        errors = self._readiness_errors()
        if errors:
            self.readiness = '\n'.join(errors)
            return False
        runs = self.env['hrm.payroll'].search([('period_id', '=', self.id)])
        if len(runs) > 1 or runs.filtered(lambda r: r.status not in ('draft', 'processing')):
            raise UserError('Kỳ có bảng lương cần xử lý; mở bảng lương hiện có để kiểm tra.')
        run = runs or self.env['hrm.payroll'].create(dict(tenant_id=self.tenant_id.id,
            company_id=self.company_id.id, period_id=self.id, run_no=1))
        if self.status == 'open': self.action_start_processing()
        if run.status == 'draft': run.action_start()
        run.selected_employee_ids = self.selected_employee_ids
        result = run.action_calculate()
        if isinstance(result, dict): return result
        if run.status == 'calculated': self.action_mark_calculated()
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.payroll',
                'res_id': run.id, 'view_mode': 'form', 'target': 'current'}

    def action_reopen_inputs(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise UserError('Cần quyền duyệt để mở lại kỳ.')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        runs = self.env['hrm.payroll'].search([('period_id', '=', self.id)])
        if self.status in ('approved', 'finalized', 'paid') or runs.filtered(lambda r: r.status in ('approved', 'finalized', 'paid')):
            raise UserError('Bảng lương đã duyệt/chốt không được mở lại.')
        if not self.correction_reason or not self.correction_reason.strip():
            raise UserError('Nhập lý do mở lại để sửa dữ liệu.')
        for run in runs:
            audit(run, 'UPDATE', {'step': 'reopen', 'reason': self.correction_reason,
                'version': run.calculation_version, 'previous_results': run.item_ids.read([
                    'employee_id', 'gross_amount', 'deduction_amount', 'tax_amount', 'net_amount'])})
            self.env['hrm.payslip.item'].search([('payroll_id', '=', run.id), ('status', '=', 'calculated')]).unlink()
            run.item_ids.unlink()
            run.write({'status': 'processing', 'completed_at': False})
        audit(self, 'UPDATE', {'step': 'reopen_inputs', 'reason': self.correction_reason})
        self.write({'status': 'processing', 'readiness': 'Đã mở lại. Nhập bản sửa với revision lớn hơn; sau đó Tính lương tháng.'})
