from uuid import uuid4

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class EmployeeProject(models.Model):
    _name = 'hrm.employee.project'
    _description = 'Dự án nhân sự'
    _order = 'name, id'

    name = fields.Char(required=True, string='Tên dự án')
    company_id = fields.Many2one('hrm.company', required=True, ondelete='restrict', string='Công ty')
    active = fields.Boolean(default=True)

    _unique_name = models.Constraint('UNIQUE(company_id, name)', 'Tên dự án đã tồn tại trong công ty.')


class Assignment(models.Model):
    _inherit = 'hrm.employee.assignment'

    project_ids = fields.Many2many('hrm.employee.project', string='Dự án')

    @api.constrains('company_id', 'project_ids')
    def _check_project_company(self):
        for row in self:
            if row.project_ids.filtered(lambda project: project.company_id != row.company_id):
                raise ValidationError('Dự án phải thuộc công ty của phân công.')

    @api.constrains('employee_id', 'status', 'department_id', 'position_id', 'project_ids',
                    'company_id', 'start_date', 'end_date', 'job_id')
    def _check_active_assignment_employee(self):
        today = fields.Date.context_today(self)
        current = self.filtered(lambda row: row.status == 'active' and (not row.end_date or row.end_date >= today))
        current.employee_id._check_can_assign()

class Position(models.Model):
    _inherit = 'hrm.position'
    _rec_name = 'title'


class AssignmentLog(models.Model):
    _name = 'hrm.employee.assignment.log'
    _description = 'Lịch sử phân công nhân viên'
    _order = 'id desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('hrm.company', required=True, ondelete='restrict')
    assignment_id = fields.Many2one('hrm.employee.assignment', required=True, ondelete='restrict', index=True)
    actor_id = fields.Many2one('res.users', required=True, ondelete='restrict', string='Người thao tác')
    previous_actor_id = fields.Many2one('res.users', ondelete='restrict', string='Người nhập trước')
    reason = fields.Text(string='Lý do điều chỉnh')
    before = fields.Text(string='Thông tin trước')
    after = fields.Text(required=True, string='Thông tin sau')


class Employee(models.Model):
    _inherit = 'hr.employee'

    hrm_assignment_log_ids = fields.One2many('hrm.employee.assignment.log', 'employee_id', string='Lịch sử phân công')
    hrm_assignment_department = fields.Many2one('hrm.department', compute='_compute_assignment_summary', string='Phòng ban')
    hrm_assignment_position = fields.Many2one('hrm.position', compute='_compute_assignment_summary', string='Chức vụ')
    hrm_assignment_projects = fields.Many2many('hrm.employee.project', compute='_compute_assignment_summary', string='Dự án')

    def _primary_assignments(self, as_of=None):
        date = as_of or fields.Date.context_today(self)
        statuses = ['active', 'closed'] if as_of else ['active']
        records = self.env['hrm.employee.assignment'].search([
            ('employee_id', 'in', self.ids), ('company_id', 'in', self.hrm_company_id.ids),
            ('assignment_type', '=', 'primary'), ('status', 'in', statuses), ('start_date', '<=', date),
            '|', ('end_date', '=', False), ('end_date', '>=', date),
        ], order='start_date desc, id desc')
        assignments = {}
        for record in records:
            if record.company_id == record.employee_id.hrm_company_id and (record.status == 'active' or record.end_date):
                assignments.setdefault(record.employee_id.id, record)
        return assignments

    def _compute_assignment_summary(self):
        assignments = self._primary_assignments()
        for employee in self:
            row = assignments.get(employee.id)
            employee.hrm_assignment_department = row.department_id if row else False
            employee.hrm_assignment_position = row.position_id if row else False
            employee.hrm_assignment_projects = row.project_ids if row else False

    def action_assignment_popup(self):
        self.ensure_one()
        self.check_access('write')
        self._check_can_assign()
        if not self.hrm_company_id or self.hrm_company_id not in self.env.user.hrm_company_ids:
            raise UserError('Chọn công ty của nhân viên trước khi phân công.')
        row = self._primary_assignments().get(self.id)
        wizard = self.env['hrm.employee.assignment.wizard'].create({
            'employee_id': self.id, 'assignment_id': row.id if row else False,
            'assignment_stamp': row.write_date if row else False,
            'department_id': row.department_id.id if row else False,
            'position_id': row.position_id.id if row else False,
            'project_ids': [Command.set(row.project_ids.ids)] if row else [],
        })
        return {
            'type': 'ir.actions.act_window', 'name': 'Phân công nhân viên',
            'res_model': wizard._name, 'res_id': wizard.id,
            'views': [(self.env.ref('hrm_data_import.employee_assignment_popup').id, 'form')],
            'target': 'new',
        }

    def _check_can_assign(self):
        if any(employee.current_status in ('terminated', 'alumni') for employee in self):
            raise UserError('Nhân viên đã nghỉ việc. Hãy kích hoạt lại trong hồ sơ trước khi phân công.')

    def action_reactivate_employee(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('hrm_data_import.group_import_operator') or self.hrm_company_id not in self.env.user.hrm_company_ids:
            raise UserError('Bạn không có quyền kích hoạt lại nhân viên của công ty này.')
        self.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.current_status not in ('terminated', 'alumni'):
            raise UserError('Chỉ kích hoạt lại nhân viên đã nghỉ việc.')
        reason = 'Kích hoạt lại từ hồ sơ nhân viên'
        if self.termination_date:
            reason += f' (ngày nghỉ đã ghi: {self.termination_date:%d/%m/%Y})'
        self._move_status('active', reason)
        self.write({'active': True, 'termination_date': False})


class AssignmentWizard(models.TransientModel):
    _name = 'hrm.employee.assignment.wizard'
    _description = 'Phân công nhân viên nhanh'

    employee_id = fields.Many2one('hr.employee', required=True, readonly=True)
    company_id = fields.Many2one(related='employee_id.hrm_company_id')
    assignment_id = fields.Many2one('hrm.employee.assignment', readonly=True)
    assignment_stamp = fields.Datetime(readonly=True)
    department_id = fields.Many2one('hrm.department', string='Phòng ban')
    position_id = fields.Many2one('hrm.position', string='Chức vụ')
    new_position = fields.Boolean(string='Thêm chức vụ mới')
    position_title = fields.Char(string='Tên chức vụ mới')
    project_ids = fields.Many2many('hrm.employee.project', string='Dự án')
    reason = fields.Text(string='Lý do điều chỉnh')

    @api.onchange('department_id')
    def _reset_position(self):
        if self.position_id.department_id != self.department_id:
            self.position_id = False

    def _position(self, company):
        if not self.new_position:
            return self.position_id
        title = (self.position_title or '').strip()
        if not title:
            raise UserError('Nhập tên chức vụ mới.')
        positions = self.env['hrm.position']
        existing = positions.search([('company_id', '=', company.id), ('department_id', '=', self.department_id.id),
                                     ('title', '=ilike', title), ('status', '=', 'active')], limit=1)
        if existing:
            return existing
        common = {'company_id': company.id, 'tenant_id': company.tenant_id.id, 'title': title}
        jobs = self.env['hrm.job']
        job = jobs.search([('company_id', '=', company.id), ('title', '=ilike', title), ('status', '=', 'active')], limit=1)
        if not job:
            job = jobs.create(dict(common, code=uuid4().hex[:12].upper()))
        return positions.create(dict(common, department_id=self.department_id.id, job_id=job.id,
                                     code=uuid4().hex[:12].upper()))

    def _summary(self, row):
        return 'Phòng ban: %s\nChức vụ: %s\nDự án: %s' % (
            row.department_id.name or '—', row.position_id.title or '—',
            ', '.join(row.project_ids.mapped('name')) or '—')

    def action_apply(self):
        self.ensure_one()
        self.check_access('write')
        employee = self.employee_id
        employee.check_access('write')
        company = employee.hrm_company_id
        if not self.env.user.has_group('hrm_data_import.group_import_operator') or company not in self.env.user.hrm_company_ids:
            raise UserError('Bạn không có quyền phân công nhân viên của công ty này.')
        self.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE', (employee.id,))
        employee.invalidate_recordset()
        employee._check_can_assign()
        row = employee._primary_assignments().get(employee.id, self.env['hrm.employee.assignment'])
        row.invalidate_recordset()
        if row != self.assignment_id or (row and row.write_date != self.assignment_stamp):
            raise UserError('Phân công đã thay đổi. Mở lại popup trước khi lưu.')
        reason = (self.reason or '').strip()
        if row and not reason:
            raise UserError('Nhập lý do điều chỉnh phân công.')
        department = self.department_id
        if not department:
            raise UserError('Chọn phòng ban trước khi lưu phân công.')
        department.check_access('read')
        self.project_ids.check_access('read')
        if department.company_id != company or department.status != 'active' or self.project_ids.filtered(
                lambda project: project.company_id != company or not project.active):
            raise UserError('Chọn phòng ban và dự án đang hoạt động thuộc công ty nhân viên.')
        position = self._position(company)
        position.check_access('read')
        if not position or position.company_id != company or position.department_id != department or position.status != 'active':
            raise UserError('Chọn chức vụ đang hoạt động thuộc phòng ban đã chọn.')
        if row and row.department_id == department and row.position_id == position and row.project_ids == self.project_ids:
            return {'type': 'ir.actions.act_window_close'}
        log = self.env['hrm.employee.assignment.log'].sudo()
        previous = log.search([('assignment_id', '=', row.id)], limit=1) if row else log
        before = self._summary(row) if row else False
        previous_actor = previous.actor_id if previous else row.create_uid
        values = {'department_id': department.id, 'position_id': position.id, 'job_id': position.job_id.id,
                  'project_ids': [Command.set(self.project_ids.ids)]}
        if row:
            row.write(values)
        else:
            row = row.create(dict(values, employee_id=employee.id, company_id=company.id,
                                  tenant_id=company.tenant_id.id, start_date=fields.Date.context_today(self)))
        employee.write({'current_assignment_id': row.id, 'job_title': position.title})
        log.create({'employee_id': employee.id, 'company_id': company.id, 'assignment_id': row.id,
                    'actor_id': self.env.uid, 'previous_actor_id': previous_actor.id, 'reason': reason,
                    'before': before, 'after': self._summary(row)})
        return {'type': 'ir.actions.act_window_close'}
