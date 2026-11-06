from datetime import timedelta
from decimal import Decimal

from odoo import api, fields, models
from odoo.exceptions import UserError
from ..engine import DataError, formula
from .imports import accepts_performance, audit


class Formula(models.Model):
    _name = 'hrm.payroll.formula'
    _description = 'Excel formula version'
    _rec_name = 'expression'
    tenant_id = fields.Many2one('hrm.tenant', required=True)
    component_id = fields.Many2one('hrm.salary.component', required=True, ondelete='restrict')
    effective_from = fields.Date(required=True)
    effective_to = fields.Date()
    expression = fields.Char(required=True, help='Example: =ROUND(BASE_SALARY * PAID_DAYS / STANDARD_DAYS, 0)')
    test_context = fields.Json(default=lambda self: {'BASE_SALARY': 13000000, 'PAID_DAYS': 24,
                                                    'STANDARD_DAYS': 26, 'PERFORMANCE_AMOUNT': 1600000})
    test_result = fields.Text(readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved')], default='draft', readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('state', 'draft') != 'draft' or v.get('approved_by') for v in vals_list):
            raise UserError('Tạo công thức nháp rồi duyệt.')
        return super().create(vals_list)

    def action_test(self):
        self.check_access('write')
        for rec in self:
            try: result = str(formula(rec.expression, rec.test_context or {}))
            except (DataError, ValueError) as exc: result = 'Lỗi: ' + str(exc)
            super(Formula, rec).write({'test_result': result})

    def action_approve(self):
        self.check_access('write')
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise UserError('Cần quyền duyệt công thức.')
        for rec in self:
            rec._lock_formula()
            if rec.state != 'draft': raise UserError('Công thức đã được duyệt.')
            self.env.cr.execute('SELECT id FROM hrm_salary_component WHERE id=%s FOR UPDATE', (rec.component_id.id,))
            if rec.tenant_id != rec.component_id.tenant_id: raise UserError('Sai tenant của khoản lương.')
            if rec.effective_to and rec.effective_to < rec.effective_from: raise UserError('Khoảng ngày không hợp lệ.')
            affected = self.env['hrm.payroll'].search([
                ('company_id', '=', rec.component_id.structure_id.company_id.id),
                ('period_id.period_end', '>=', rec.effective_from),
                ('period_id.period_start', '<=', rec.effective_to or '9999-12-31'),
                ('status', 'not in', ['draft', 'processing'])], limit=1)
            if affected: raise UserError('Công thức ảnh hưởng kỳ đã tính/duyệt. Hãy chọn kỳ hiệu lực mới.')
            overlaps = self.search([('component_id', '=', rec.component_id.id), ('id', '!=', rec.id),
                                   ('state', '=', 'approved'), ('effective_from', '<=', rec.effective_to or '9999-12-31')])
            overlaps = overlaps.filtered(lambda r: not r.effective_to or r.effective_to >= rec.effective_from)
            if any(r.effective_from >= rec.effective_from for r in overlaps):
                raise UserError('Trùng hoặc lùi ngày hiệu lực với phiên bản đã duyệt.')
            formula(rec.expression, rec.test_context or {})
            for old in overlaps:
                end = rec.effective_from - timedelta(days=1)
                super(Formula, old).write({'effective_to': end})
                audit(old, 'CLOSE', {'effective_to': str(end), 'superseded_by': rec.id})
            super(Formula, rec).write({'state': 'approved', 'approved_by': self.env.uid})
            audit(rec, 'APPROVE', {'expression': rec.expression, 'from': str(rec.effective_from)})

    def write(self, vals):
        self._lock_formula()
        if any(r.state == 'approved' for r in self): raise UserError('Công thức đã duyệt bất biến; tạo phiên bản mới.')
        if 'state' in vals or 'approved_by' in vals: raise UserError('Dùng nút duyệt.')
        return super().write(vals)

    def _lock_formula(self):
        if self.ids:
            self.env.cr.execute('SELECT id FROM hrm_payroll_formula WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()

    def copy(self, default=None):
        return super().copy(dict(default or {}, state='draft', approved_by=False, test_result=False))

    def unlink(self):
        self._lock_formula()
        if any(r.state == 'approved' for r in self): raise UserError('Không xóa công thức đã duyệt.')
        return super().unlink()


class Component(models.Model):
    _inherit = 'hrm.salary.component'

    def compute_amount(self, ctx):
        self.ensure_one()
        if '_period_end' not in ctx: return super().compute_amount(ctx)
        approved = self.env['hrm.payroll.formula'].search([
            ('component_id', '=', self.id), ('state', '=', 'approved'),
            ('effective_from', '<=', ctx['_period_end']),
            '|', ('effective_to', '=', False), ('effective_to', '>=', ctx['_period_end'])])
        imported = ctx.get('_imported', {})
        if self.code in imported and not (approved and self.env.context.get('salary_grid_calculation')):
            # Explicit amount is already calculated. Never multiply KPI twice.
            return float(imported[self.code])
        if approved:
            try: return float(formula(approved.expression, {k: v for k, v in ctx.items() if not k.startswith('_')}))
            except DataError as exc: raise UserError(f'{self.code}: {exc}') from exc
        return super().compute_amount(ctx)


class Period(models.Model):
    _inherit = 'hrm.payroll.period'
    standard_days = fields.Float(string='Standard paid days')
    hours_per_day = fields.Float(string='Hours per day', default=8)
    require_imported_attendance = fields.Boolean(string='Attendance required')
    require_imported_performance = fields.Boolean(string='Performance required')


class Payroll(models.Model):
    _inherit = 'hrm.payroll'

    def _eligible_employees(self):
        candidates = super()._eligible_employees()
        assignments = self.env['hrm.employee.assignment'].search([
            ('tenant_id', '=', self.tenant_id.id), ('company_id', '=', self.company_id.id),
            ('start_date', '<=', self.period_id.period_end),
            '|', ('end_date', '=', False), ('end_date', '>=', self.period_id.period_start)])
        salaries = self.env['hrm.employee.salary'].search([
            ('tenant_id', '=', self.tenant_id.id), ('structure_id.company_id', '=', self.company_id.id),
            ('effective_from', '<=', self.period_id.period_end),
            '|', ('effective_to', '=', False), ('effective_to', '>=', self.period_id.period_start)])
        ids = set(assignments.employee_id.ids) | set(salaries.employee_id.ids)
        return candidates.filtered(lambda e: e.id in ids)

    def _active_salary(self, employee):
        salaries = self.env['hrm.employee.salary'].search([
            ('tenant_id', '=', self.tenant_id.id), ('employee_id', '=', employee.id),
            ('structure_id.company_id', '=', self.company_id.id),
            ('effective_from', '<=', self.period_id.period_end),
            '|', ('effective_to', '=', False), ('effective_to', '>=', self.period_id.period_start)])
        if len(salaries) != 1:
            raise UserError(f'{employee.employee_code}: SALARY_MISSING_OR_OVERLAPPING')
        if salaries.effective_from > self.period_id.period_start or (salaries.effective_to and salaries.effective_to < self.period_id.period_end):
            raise UserError('SALARY_CHANGES_WITHIN_PERIOD: cần tách kỳ/segment')
        return salaries

    def _calculation_context(self, employee, salary, context):
        ctx = super()._calculation_context(employee, salary, context)
        inputs = self.env['hrm.import.input'].search([
            ('period_id', '=', self.period_id.id), ('employee_id', '=', employee.id),
            ('company_id', '=', self.company_id.id), ('tenant_id', '=', self.tenant_id.id),
            ('dataset', 'in', ['attendance', 'performance'])])
        attendance = inputs.filtered(lambda r: r.dataset == 'attendance')
        components = salary.structure_id.component_ids.filtered(lambda c: c.status == 'active')
        excluded_codes = {c.code for c in components if not accepts_performance(c)}
        performance = inputs.filtered(lambda r: r.dataset == 'performance'
                                      and r.payload['component_code'] not in excluded_codes)
        if self.period_id.require_imported_attendance and not attendance:
            raise UserError(f'{employee.employee_code}: ATTENDANCE_MISSING')
        if self.period_id.require_imported_performance and not performance:
            raise UserError(f'{employee.employee_code}: PERFORMANCE_MISSING')
        if attendance:
            # A single paid-hour provider per date/shift/project prevents double counting.
            keys = [(r.payload['work_date'], r.payload.get('shift_code', ''), r.payload.get('project_code', '')) for r in attendance]
            if len(keys) != len(set(keys)): raise UserError('ATTENDANCE_SOURCE_CONFLICT')
            totals = {}
            for row in attendance:
                day = row.payload['work_date']
                totals[day] = totals.get(day, 0) + float(row.payload['regular_hours']) + float(row.payload.get('overtime_hours', 0))
            if any(v > 24 for v in totals.values()): raise UserError('DAILY_HOURS_EXCEED_24')
            ctx['worked_hours'] = sum(float(r.payload['regular_hours']) for r in attendance)
            # Imported overtime owns its day. Keep approved work entries for other dates.
            overtime_rows = attendance.filtered(lambda r: 'overtime_hours' in r.payload)
            if overtime_rows:
                dates = {r.payload['work_date'] for r in overtime_rows}
                work_entries = self.env['hrm.work.entry'].search([
                    ('tenant_id', '=', self.tenant_id.id), ('employee_id', '=', employee.id),
                    ('entry_type', '=', 'overtime'), ('status', 'in', ('approved', 'locked')),
                    ('work_date', '>=', self.period_id.period_start), ('work_date', '<=', self.period_id.period_end),
                ])
                ctx['overtime_hours'] = (
                    sum(float(r.payload['overtime_hours']) for r in overtime_rows)
                    + sum(entry.quantity for entry in work_entries if entry.work_date.isoformat() not in dates)
                )
        imported, sources = {}, {}
        for row in performance:
            code = row.payload['component_code']
            if code in sources and sources[code] != (row.source, row.dataset):
                raise UserError(f'COMPONENT_SOURCE_CONFLICT: {code}')
            sources[code] = (row.source, row.dataset)
            imported[code] = imported.get(code, Decimal(0)) + Decimal(row.payload['amount'])
        if salary.currency_code != self.tenant_id.default_currency:
            raise UserError('CURRENCY_MISMATCH')
        if self.period_id.hours_per_day <= 0: raise UserError('HOURS_PER_DAY_ZERO')
        ctx.update(BASE_SALARY=salary.base_salary, STANDARD_DAYS=self.period_id.standard_days,
                   OVERTIME_HOURS=ctx['overtime_hours'],
                   PAID_HOURS=ctx['worked_hours'], PAID_DAYS=ctx['worked_hours'] / self.period_id.hours_per_day,
                   PERFORMANCE_AMOUNT=sum(float(r.payload['amount']) for r in performance),
                   _imported=imported, _period_end=str(self.period_id.period_end))
        if set(imported) - set(components.mapped('code')):
            raise UserError('IMPORTED_COMPONENT_NOT_IN_EMPLOYEE_STRUCTURE')
        policies = self.env['hrm.payroll.formula'].search([('component_id', 'in', components.ids), ('state', '=', 'approved'),
            ('effective_from', '<=', self.period_id.period_end), '|', ('effective_to', '=', False),
            ('effective_to', '>=', self.period_id.period_end)])
        if policies.filtered(lambda p: p.effective_from > self.period_id.period_start):
            raise UserError('FORMULA_CHANGES_WITHIN_PERIOD: cần tách kỳ/segment')
        if 'STANDARD_DAYS' in ' '.join(policies.mapped('expression')) and self.period_id.standard_days <= 0:
            raise UserError('STANDARD_TIME_ZERO')
        audit(self, 'UPDATE', {'step': 'calculation_snapshot', 'employee_id': employee.id,
              'salary_id': salary.id, 'base_salary': salary.base_salary, 'inputs': [
                  {'id': r.id, 'revision': r.revision, 'payload': r.payload} for r in attendance | performance],
              'components': [{'id': c.id, 'code': c.code, 'type': c.component_type,
                              'configuration': c.configuration, 'sequence': c.sequence_no} for c in components],
              'formulas': [{'id': p.id, 'expression': p.expression} for p in policies],
              'context': {k: v for k, v in ctx.items() if not k.startswith('_')}})
        return ctx

    def action_calculate(self):
        self.check_access('write')
        for rec in self:
            self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (rec.period_id.id,))
            try:
                with self.env.cr.savepoint():
                    # Core used to keep old component lines after recalculation.
                    rec.env['hrm.payslip.item'].search([('payroll_id', '=', rec.id), ('status', '=', 'calculated')]).unlink()
                    super(Payroll, rec).action_calculate()
                    audit(rec, 'UPDATE', {'step': 'calculated', 'version': rec.calculation_version})
            except (UserError, DataError) as exc:
                audit(rec, 'UPDATE', {'step': 'calculation_failed', 'error': str(exc)})
                return {'type': 'ir.actions.client', 'tag': 'display_notification',
                        'params': {'title': 'Tính lương thất bại', 'message': str(exc), 'type': 'danger', 'sticky': True}}
        return True
