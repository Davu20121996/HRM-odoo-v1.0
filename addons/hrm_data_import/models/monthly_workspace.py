import calendar
from datetime import date
from odoo import api, fields, models
from odoo.exceptions import UserError


class MonthlyWorkspace(models.Model):
    _name = 'hrm.monthly.workspace'
    _description = 'Monthly attendance and payroll'
    _rec_name = 'name'

    name = fields.Char(default='Công • Hiệu quả • Lương', readonly=True)
    company_id = fields.Many2one('hrm.company', required=True, string='Company')
    year = fields.Integer(default=lambda s: fields.Date.today().year, required=True, string='Year')
    month = fields.Selection([(str(n), f'Month {n:02}') for n in range(1, 13)],
        default=lambda s: str(fields.Date.today().month), required=True, string='Month')
    employee_id = fields.Many2one('hr.employee', string='Employee (blank = all)',
        domain="[('hrm_company_id', '=', company_id)]")
    period_id = fields.Many2one('hrm.payroll.period', compute='_compute_period', string='Payroll period')
    line_ids = fields.One2many('hrm.monthly.line', 'workspace_id', readonly=True, string='Employee summary')
    notice = fields.Text(readonly=True, string='Data status')

    @api.depends('company_id', 'year', 'month')
    def _compute_period(self):
        for rec in self:
            rec.period_id = False
            if rec.company_id and rec.month and 1900 <= rec.year <= 2200:
                start, end = rec._bounds()
                periods = self.env['hrm.payroll.period'].search([
                    ('company_id', '=', rec.company_id.id), ('period_start', '=', start), ('period_end', '=', end)])
                if len(periods) == 1: rec.period_id = periods

    def _bounds(self):
        self.ensure_one()
        if not 1900 <= self.year <= 2200 or self.month not in dict(self._fields['month'].selection):
            raise UserError('Chọn năm 1900–2200 và tháng hợp lệ.')
        return date(self.year, int(self.month), 1), date(self.year, int(self.month), calendar.monthrange(self.year, int(self.month))[1])

    @api.constrains('company_id', 'employee_id', 'year', 'month')
    def _check_scope(self):
        for rec in self:
            rec._bounds()
            if rec.employee_id and rec.employee_id.hrm_company_id != rec.company_id:
                raise UserError('Nhân viên phải thuộc công ty đã chọn.')

    def write(self, vals):
        result = super().write(vals)
        if {'company_id', 'employee_id', 'year', 'month'} & vals.keys():
            self.line_ids.sudo().unlink()
            super().write({'notice': 'Bộ lọc đã đổi. Bấm Xem dữ liệu tháng để cập nhật.'})
        return result

    def action_refresh(self):
        self.ensure_one()
        self.check_access('write')
        self.company_id.check_access('read')
        self.env.cr.execute('SELECT id FROM hrm_monthly_workspace WHERE id=%s FOR UPDATE', (self.id,))
        self.line_ids.sudo().unlink()
        period = self.period_id
        start, end = self._bounds()
        employees = self.env['hr.employee'].with_context(active_test=False).search([('hrm_company_id', '=', self.company_id.id)])
        if self.employee_id: employees &= self.employee_id
        inputs = self.env['hrm.import.input'].search([('company_id', '=', self.company_id.id), ('period_id', '=', period.id)]) if period else self.env['hrm.import.input']
        items = self.env['hrm.payroll.item'].search([('payroll_id.company_id', '=', self.company_id.id), ('payroll_id.period_id', '=', period.id)]) if period else self.env['hrm.payroll.item']
        if self.employee_id:
            inputs = inputs.filtered(lambda r: r.employee_id == self.employee_id)
            items = items.filtered(lambda r: r.employee_id == self.employee_id)
        vals = []
        for employee in employees:
            rows = inputs.filtered(lambda r: r.employee_id == employee)
            attendance = rows.filtered(lambda r: r.dataset == 'attendance')
            performance = rows.filtered(lambda r: r.dataset == 'performance')
            results = items.filtered(lambda r: r.employee_id == employee)
            contracts = self.env['hrm.employee.contract'].search([
                ('employee_id', '=', employee.id), ('company_id', '=', self.company_id.id),
                ('status', '=', 'active'),
                ('start_date', '<=', start), '|', ('end_date', '=', False), ('end_date', '>=', end)])
            hours = sum(float(r.payload.get('regular_hours', 0)) for r in attendance)
            vals.append(dict(workspace_id=self.id, employee_id=employee.id, period_id=period.id,
                hours=hours, paid_days=hours / period.hours_per_day if period and period.hours_per_day else 0,
                performance=sum(float(r.payload.get('amount', 0)) for r in performance),
                base_salary=contracts.base_salary if len(contracts) == 1 else 0,
                attendance_count=len(attendance), performance_count=len(performance),
                result_id=results.id if len(results) == 1 else False,
                state='Đã tính' if len(results) == 1 else 'Nhiều bảng lương — cần đối chiếu' if len(results) > 1 else
                    'Đã nghỉ — chỉ xem hồ sơ' if employee.current_status in ('terminated', 'alumni') else
                    'Thiếu hợp đồng' if len(contracts) != 1 else 'Thiếu công' if not attendance else
                    'Thiếu hiệu quả' if not performance else 'Sẵn sàng tính'))
        self.env['hrm.monthly.line'].sudo().create(vals)
        self.notice = (f'Tháng {int(self.month):02}/{self.year}: {len(employees)} hồ sơ; '
            f'{len(inputs.filtered(lambda r: r.dataset == "attendance"))} dòng công; '
            f'{len(inputs.filtered(lambda r: r.dataset == "performance"))} dòng hiệu quả; {len(items)} kết quả lương. '
            'Số 0 khi thiếu nguồn không phải xác nhận dữ liệu bằng 0. ' +
            ('Chưa có kỳ lương cho tháng này.' if not period else f'Kỳ: {period.period_code}.'))

    def action_all_employees(self):
        self.ensure_one()
        self.check_access('write')
        self.employee_id = False
        self.action_refresh()

    def action_timesheet(self):
        self.ensure_one()
        self.check_access('read')
        domain = [('company_id', '=', self.company_id.id), ('year', '=', str(self.year)), ('month', '=', self.month)]
        if self.employee_id: domain.append(('employee_id', '=', self.employee_id.id))
        return {'type': 'ir.actions.act_window', 'name': 'Bảng công tháng đang chọn',
            'res_model': 'hrm.attendance.month', 'view_mode': 'list,pivot', 'domain': domain,
            'search_view_id': self.env.ref('hrm_data_import.attendance_month_search').id}

    def action_period(self):
        self.ensure_one()
        self.check_access('read')
        start, end = self._bounds()
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.payroll.period', 'view_mode': 'form',
            'views': [(self.env.ref('hrm_data_import.view_period_input_form').id, 'form')],
            'res_id': self.period_id.id or False, 'context': {'default_company_id': self.company_id.id,
                'default_tenant_id': self.company_id.tenant_id.id, 'default_period_start': str(start),
                'default_period_end': str(end), 'default_period_code': f'{self.year}-{int(self.month):02}'}}

    def _period(self):
        self.ensure_one()
        self.check_access('read')
        if not self.period_id: raise UserError('Chưa có đúng một kỳ cho tháng này. Mở Thiết lập kỳ lương trước.')
        return self.period_id

    def action_import_attendance(self): return self._period().action_import_attendance()
    def action_import_performance(self): return self._period().action_import_performance()

    def action_manual(self):
        period = self._period()
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.manual.input', 'view_mode': 'form',
            'context': {'default_company_id': self.company_id.id, 'default_period_id': period.id,
                        'default_employee_id': self.employee_id.id}}

    def action_calculate(self):
        period = self._period()
        period.selected_employee_ids = self.employee_id
        result = period.action_quick_payroll()
        self.action_refresh()
        return result


class MonthlyLine(models.Model):
    _name = 'hrm.monthly.line'
    _description = 'Employee monthly attendance and payroll summary'
    workspace_id = fields.Many2one('hrm.monthly.workspace', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='workspace_id.company_id', store=True)
    employee_id = fields.Many2one('hr.employee', required=True, string='Employees')
    employee_code = fields.Char(related='employee_id.employee_code', string='Employee code')
    period_id = fields.Many2one('hrm.payroll.period', string='Period')
    hours = fields.Float(string='Worked hours')
    paid_days = fields.Float(string='Paid days')
    performance = fields.Float(string='Performance (VND)', digits=(19, 0))
    base_salary = fields.Float(string='Contract salary (VND)', digits=(19, 0))
    attendance_count = fields.Integer(string='Attendance rows')
    performance_count = fields.Integer(string='Performance items')
    result_id = fields.Many2one('hrm.payroll.item')
    gross = fields.Float(related='result_id.gross_amount', string='Gross pay', digits=(19, 0))
    deduction = fields.Float(related='result_id.deduction_amount', string='Deductions', digits=(19, 0))
    net = fields.Float(related='result_id.net_amount', string='Net pay', digits=(19, 0))
    state = fields.Char(string='Status')

    def action_inputs(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.import.input', 'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id), ('period_id', '=', self.period_id.id), ('employee_id', '=', self.employee_id.id)]}

    def action_salary(self):
        self.ensure_one()
        self.check_access('read')
        if not self.result_id: raise UserError('Chưa có kết quả lương. Kiểm tra dữ liệu và tính lương trước.')
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.payroll.item', 'view_mode': 'form',
            'views': [(self.env.ref('hrm_data_import.payroll_item_details').id, 'form')], 'res_id': self.result_id.id}
