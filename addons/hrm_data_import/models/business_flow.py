import csv
import io
import math
from datetime import date
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
from .imports import audit


class Contract(models.Model):
    _inherit = 'hrm.employee.contract'
    _rec_name = 'contract_no'

    parent_id = fields.Many2one('hrm.employee.contract', string='Parent contract', ondelete='restrict')
    appendix_ids = fields.One2many('hrm.employee.contract', 'parent_id', string='Addenda')
    structure_id = fields.Many2one('hrm.salary.structure', string='Salary structure',
        domain="[('company_id', '=', company_id), ('tenant_id', '=', tenant_id)]")
    terms = fields.Html(string='Agreed terms', sanitize=True)
    job_description = fields.Text(string='Duties and responsibilities')
    workplace = fields.Char(string='Workplace')
    attachment_filename = fields.Char(string='Signed document filename')
    signed_document = fields.Binary(string='Signed contract/addendum', attachment=True)
    changes_salary = fields.Boolean(string='Salary adjustment addendum')
    employee_birth_date = fields.Date(related='employee_id.hrm_birth_date', string='Date of birth', readonly=True)
    employee_identity = fields.Char(related='employee_id.hrm_identity_number', string='CCCD/CMND', readonly=True,
        groups='hrm_data_import.group_import_operator')

    @api.constrains('employee_id', 'company_id', 'tenant_id', 'parent_id', 'start_date', 'end_date', 'base_salary', 'structure_id')
    def _check_contract_scope(self):
        for rec in self:
            if rec.employee_id.hrm_company_id != rec.company_id or rec.company_id.tenant_id != rec.tenant_id:
                raise UserError('Nhân viên và hợp đồng phải cùng công ty.')
            if rec.structure_id and rec.structure_id.company_id != rec.company_id:
                raise UserError('Cơ cấu lương phải thuộc công ty hợp đồng.')
            if not math.isfinite(rec.base_salary) or rec.base_salary < 0:
                raise UserError('Lương hợp đồng không được âm hoặc vô hạn.')
            if rec.end_date and rec.end_date < rec.start_date:
                raise UserError('Ngày kết thúc phải sau ngày bắt đầu.')
            if rec.parent_id and (rec.parent_id == rec or rec.parent_id.parent_id or
                rec.parent_id.employee_id != rec.employee_id or rec.parent_id.company_id != rec.company_id):
                raise UserError('Phụ lục phải gắn hợp đồng gốc của cùng nhân viên/công ty.')

    def action_approve(self):
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise UserError('Cần quyền duyệt hợp đồng.')
        for rec in self:
            if not rec.parent_id or rec.changes_salary:
                if rec.base_salary <= 0 or not rec.structure_id:
                    raise UserError('Nhập lương cơ bản thật lớn hơn 0 và chọn cơ cấu lương trước khi duyệt.')
        result = super().action_approve()
        for rec in self: audit(rec, 'APPROVE', {'contract_no': rec.contract_no})
        return result

    def write(self, vals):
        if vals.get('status') == 'active' and self:
            if not self.env.user.has_group('hrm_data_import.group_import_approver'):
                raise UserError('Cần quyền duyệt để kích hoạt hợp đồng.')
            self.check_access('write')
            self.env.cr.execute('SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR UPDATE',
                                (tuple(self.employee_id.ids),))
        if self.ids:
            self.env.cr.execute('SELECT id FROM hrm_employee_contract WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()
        if 'status' in vals:
            for rec in self:
                if vals['status'] != rec.status and vals['status'] not in rec._TRANSITIONS.get(rec.status, ()):
                    raise UserError('Trạng thái hợp đồng phải đi đúng bước gửi duyệt → duyệt → hiệu lực → hết hạn.')
            if vals['status'] in ('approved', 'active') and not self.env.user.has_group('hrm_data_import.group_import_approver'):
                raise UserError('Cần quyền duyệt để duyệt/kích hoạt hợp đồng.')
        protected = {'base_salary', 'currency_code', 'start_date', 'end_date', 'terms', 'employee_id',
                     'company_id', 'tenant_id', 'parent_id', 'structure_id', 'changes_salary', 'contract_no',
                     'contract_type_id', 'probation_start', 'probation_end', 'job_description', 'workplace', 'working_hours_per_week',
                     'full_renewal'}
        if protected & vals.keys() and any(r.status in ('approved', 'active', 'expired') for r in self):
            raise UserError('Hợp đồng đã duyệt không sửa nội dung. Tạo phụ lục hoặc hợp đồng mới.')
        if vals.get('status') == 'active':
            if len(self.mapped('employee_id')) != len(self):
                raise UserError('Chỉ kích hoạt một hợp đồng cho mỗi nhân viên trong một lần.')
            for rec in self.filtered(lambda contract: contract.status != 'active'):
                if rec.base_salary <= 0 or not rec.structure_id:
                    raise UserError('Cần lương cơ bản và cơ cấu lương trước khi kích hoạt.')
                previous = self.search([('employee_id', '=', rec.employee_id.id), ('company_id', '=', rec.company_id.id),
                                        ('status', '=', 'active'), ('id', '!=', rec.id)])
                previous.write({'status': 'expired'})
                rec.employee_id.write({'current_contract_id': rec.id})
        result = super().write(vals)
        if 'status' in vals:
            for rec in self: audit(rec, 'UPDATE', {'step': 'contract_status', 'status': rec.status})
        return result

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('status', 'draft') != 'draft' for v in vals_list):
            raise UserError('Hợp đồng mới phải bắt đầu từ bản nháp.')
        return super().create(vals_list)


class ContractPayroll(models.Model):
    _inherit = 'hrm.payroll'
    selected_employee_ids = fields.Many2many('hr.employee', string='Selected employees')

    def _eligible_employees(self):
        self.ensure_one()
        employees = self.env['hr.employee'].search([('hrm_company_id', '=', self.company_id.id),
            ('tenant_id', '=', self.tenant_id.id), ('current_status', 'in', ['active', 'onboarding'])])
        if self.selected_employee_ids:
            if self.selected_employee_ids - employees:
                raise UserError('Nhân viên tính lương không thuộc công ty hoặc không đang làm việc.')
            employees = self.selected_employee_ids
        return employees

    def _active_salary(self, employee):
        self.ensure_one()
        start, end = self.period_id.period_start, self.period_id.period_end
        contracts = self.env['hrm.employee.contract'].search([
            ('company_id', '=', self.company_id.id), ('employee_id', '=', employee.id),
            ('tenant_id', '=', self.tenant_id.id),
            ('status', '=', 'active'), ('start_date', '<=', end),
            '|', ('end_date', '=', False), ('end_date', '>=', start)])
        if len(contracts) != 1:
            raise UserError(f'{employee.employee_code}: cần đúng một hợp đồng lao động đang hiệu lực trong tháng.')
        contract = contracts
        if contract.start_date > start or (contract.end_date and contract.end_date < end):
            raise UserError('Hợp đồng thay đổi giữa tháng: cần tách kỳ trước khi tính.')
        if not contract.structure_id:
            raise UserError('Hợp đồng/phụ lục thiếu cơ cấu tính lương.')
        return contract

    def _calculation_context(self, employee, salary, context):
        result = super()._calculation_context(employee, salary, context)
        audit(self, 'UPDATE', {'step': 'contract_salary_source', 'employee_id': employee.id,
            'contract_id': salary.id, 'contract_no': salary.contract_no, 'base_salary': salary.base_salary})
        return result

    def action_calculate(self):
        result = super().action_calculate()
        if isinstance(result, dict): return result
        for rec in self.filtered(lambda r: r.status == 'calculated'):
            for item in rec.item_ids:
                bonus, deduction = rec._period_extras(item.employee_id)
                for code, name, amount in [('EXTRA_BONUS', 'Thưởng bổ sung đã duyệt', bonus),
                                           ('EXTRA_DEDUCTION', 'Khấu trừ bổ sung', deduction)]:
                    if amount:
                        self.env['hrm.payslip.item'].create(dict(tenant_id=rec.tenant_id.id,
                            payroll_id=rec.id, employee_id=item.employee_id.id, code=code, name=name,
                            amount=amount, currency_code=item.currency_code, sequence_no=999,
                            status='calculated'))
        return result


class ManualInput(models.Model):
    _name = 'hrm.manual.input'
    _description = 'Manual attendance and performance'
    _rec_name = 'employee_id'
    company_id = fields.Many2one('hrm.company', required=True)
    tenant_id = fields.Many2one(related='company_id.tenant_id', store=True)
    period_id = fields.Many2one('hrm.payroll.period', required=True, domain="[('company_id', '=', company_id)]")
    employee_id = fields.Many2one('hr.employee', required=True, domain="[('hrm_company_id', '=', company_id)]")
    dataset = fields.Selection([('attendance', 'Attendance'), ('performance', 'Performance'), ('salary', 'Salary component')], required=True, default='attendance')
    work_date = fields.Date(string='Paid days')
    regular_hours = fields.Float(string='Worked hours')
    component_id = fields.Many2one('hrm.salary.component', string='Salary component', domain="[('structure_id.company_id', '=', company_id), ('status', '=', 'active')]")
    amount = fields.Float(string='Amount')
    source_record_id = fields.Char(string='Source record ID', required=True)
    revision = fields.Integer(string='Version', default=1, required=True)
    approval_reference = fields.Char(string='Approval reference / correction reason', required=True)
    batch_id = fields.Many2one('hrm.import.batch', readonly=True)

    def action_publish(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM hrm_manual_input WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.batch_id:
            raise UserError('Dòng đã gửi. Tạo dòng mới, giữ mã nguồn và tăng phiên bản để sửa.')
        if self.employee_id.hrm_company_id != self.company_id or self.period_id.company_id != self.company_id:
            raise UserError('Nhân viên/kỳ phải thuộc công ty đã chọn.')
        if self.revision < 1 or not self.approval_reference.strip():
            raise UserError('Cần phiên bản dương và tham chiếu xác nhận.')
        columns = ['employee_code', 'source_record_id', 'revision', 'approval_reference']
        values = [self.employee_id.employee_code, self.source_record_id, self.revision, self.approval_reference]
        if self.dataset == 'attendance':
            if not self.work_date: raise UserError('Chọn ngày công.')
            columns += ['work_date', 'regular_hours']
            values += [str(self.work_date), self.regular_hours]
        else:
            if not self.component_id or self.component_id.structure_id.company_id != self.company_id:
                raise UserError('Chọn khoản lương của công ty.')
            columns += ['component_code', 'amount', 'currency']
            values += [self.component_id.code, self.amount, self.tenant_id.default_currency]
        profile = self.env['hrm.import.profile'].search([('company_id', '=', self.company_id.id),
            ('source', '=', 'WEB-DIRECT-' + self.dataset), ('state', '=', 'approved')], limit=1)
        if not profile:
            if not self.env.user.has_group('hrm_data_import.group_import_approver'):
                raise UserError('Người duyệt cần tạo mapping WEB-DIRECT cho lần nhập trực tiếp đầu tiên.')
            profile = self.env['hrm.import.profile'].create(dict(name='Nhập trực tiếp ' + self.dataset,
                company_id=self.company_id.id, tenant_id=self.tenant_id.id, dataset=self.dataset,
                source='WEB-DIRECT-' + self.dataset, locale='en', headers=columns,
                mapping_ids=[(0, 0, dict(column=i, target=key, required=True,
                    data_type='number' if key in ('revision', 'regular_hours', 'amount') else 'date' if key == 'work_date' else 'text'))
                    for i, key in enumerate(columns, 1)]))
            profile.action_approve()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerow(values)
        batch = self.env['hrm.import.batch'].create(dict(profile_id=profile.id, period_id=self.period_id.id,
            filename='web-input.csv', file_data=BinaryBytes(output.getvalue().encode('utf-8'))))
        batch.action_preview()
        if batch.state == 'ready': batch.action_commit()
        self.batch_id = batch
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.import.batch', 'view_mode': 'form', 'res_id': batch.id}

    def write(self, vals):
        if any(r.batch_id for r in self): raise UserError('Dòng đã gửi không sửa; nhập phiên bản mới để đối chiếu.')
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any('batch_id' in v for v in vals_list): raise UserError('Không tự gán lần nhập.')
        return super().create(vals_list)


class PayslipDetails(models.Model):
    _inherit = 'hrm.payroll.item'
    period_id = fields.Many2one(related='payroll_id.period_id', store=True, string='Payroll month')
    company_id = fields.Many2one(related='payroll_id.company_id', store=True, string='Company')
    detail_ids = fields.Many2many('hrm.payslip.item', compute='_compute_detail_ids', string='Payroll component details')

    def _compute_detail_ids(self):
        for rec in self:
            rec.detail_ids = self.env['hrm.payslip.item'].search([
                ('payroll_id', '=', rec.payroll_id.id), ('employee_id', '=', rec.employee_id.id)])
