"""Localize presentation without changing source keys or payroll amounts."""
from odoo import api, fields, models


class MonthlyLanguage(models.Model):
    _inherit = 'hrm.monthly.workspace'

    @api.depends_context('lang')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = self.env._('Monthly attendance and payroll')

    def action_refresh(self):
        result = super().action_refresh()
        self.ensure_one()
        period = self.period_id
        domain = [('company_id', '=', self.company_id.id), ('period_id', '=', period.id)]
        if self.employee_id: domain.append(('employee_id', '=', self.employee_id.id))
        results = self.env['hrm.payroll.item'].search_count(domain) if period else 0
        self.notice = self.env._(
            'Month %(month)s/%(year)s: %(employees)s employees; %(attendance)s attendance rows; %(performance)s performance items; %(results)s payroll results.',
            month=f'{int(self.month):02}', year=self.year, employees=len(self.line_ids),
            attendance=sum(self.line_ids.mapped('attendance_count')),
            performance=sum(self.line_ids.mapped('performance_count')), results=results)
        self.notice += ' ' + self.env._('Zero without a source is not confirmed zero data.')
        self.notice += ' ' + (self.env._('Period: %(period)s.', period=period.period_code)
            if period else self.env._('No payroll period exists for this month.'))
        return result


class MonthlyLineLanguage(models.Model):
    _inherit = 'hrm.monthly.line'
    state = fields.Selection([
        ('Đã tính', 'Calculated'),
        ('Nhiều bảng lương — cần đối chiếu', 'Multiple payroll runs — reconciliation required'),
        ('Đã nghỉ — chỉ xem hồ sơ', 'Former employee — profile only'),
        ('Thiếu hợp đồng', 'Missing contract'), ('Thiếu công', 'Missing attendance'),
        ('Thiếu hiệu quả', 'Missing performance'), ('Sẵn sàng tính', 'Ready to calculate')], string='Status')


class AttendanceLanguage(models.Model):
    _inherit = 'hrm.attendance.month'
    data_state = fields.Selection([('Chưa có công', 'No attendance data'),
        ('Đã có công', 'Attendance recorded')], string='Attendance data', readonly=True)


class PayrollLanguage(models.Model):
    _inherit = 'hrm.payroll'

    @api.depends('period_id', 'run_no')
    @api.depends_context('lang')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = self.env._('Payroll %(period)s / Run %(run)s',
                period=rec.period_id.period_code or '', run=rec.run_no)


class PayrollItemLanguage(models.Model):
    _inherit = 'hrm.payroll.item'

    @api.depends('employee_id', 'period_id')
    @api.depends_context('lang')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = self.env._('Payslip: %(employee)s — %(period)s',
                employee=rec.employee_id.name or '', period=rec.period_id.period_code or '')

    @api.depends('insurance_snapshot')
    @api.depends_context('lang')
    def _compute_insurance_state(self):
        for rec in self:
            rec.insurance_state = self.env._('Insurance calculated') if rec.insurance_snapshot else self.env._('Insurance missing — export blocked')
