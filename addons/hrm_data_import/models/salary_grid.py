from odoo import api, models
from odoo.exceptions import AccessError, UserError

from .imports import audit


class SalaryMonthGrid(models.Model):
    _inherit = 'hrm.payroll.period'

    @api.model
    def load_salary_grid(self, period_id=False):
        attendance = self.env['hrm.attendance.month']
        periods = attendance._grid_periods()
        choices = [{'id': p.id, 'label': f'{p.period_start:%m/%Y} · {p.company_id.name} · {p.period_code}'} for p in periods]
        if not periods:
            return {'periods': [], 'rows': [], 'columns': []}
        period = attendance._grid_period(period_id) if period_id else periods[0]
        run_model = self.env['hrm.payroll']
        probe = run_model.new({'period_id': period.id, 'company_id': period.company_id.id,
                               'tenant_id': period.tenant_id.id})
        items = run_model.search([('period_id', '=', period.id)]).item_ids
        eligible = probe._eligible_employees()
        if period.selected_employee_ids:
            eligible &= period.selected_employee_ids
        employees = eligible | items.employee_id
        assignments = employees._primary_assignments(period.period_end)
        adjustments = self.env['hrm.salary.adjustment'].search([
            ('period_id', '=', period.id), ('state', '=', 'approved'),
        ], order='approved_at, id')
        latest = {(r.employee_id.id, r.component_id.id): r for r in adjustments}
        by_employee = {item.employee_id.id: item for item in items}
        columns, rows = {}, []
        for employee in employees.sorted('employee_code'):
            item = by_employee.get(employee.id, self.env['hrm.payroll.item'])
            lines = {line.salary_component_id.id: line.amount for line in item.detail_ids if line.salary_component_id}
            values, error = {}, ''
            try:
                components = probe._active_salary(employee).structure_id.component_ids.filtered(lambda c: c.status == 'active')
            except UserError as exc:
                components = self.env['hrm.salary.component']
                error = str(exc)
            for component in components:
                columns[component.id] = {'id': component.id, 'label': component.name, 'sequence': component.sequence_no}
                adjustment = latest.get((employee.id, component.id))
                manual = bool(adjustment and not adjustment.restore_formula)
                values[component.id] = {'value': lines.get(component.id), 'manual': manual,
                                        'revision': adjustment.id if adjustment else 0,
                                        'amount': adjustment.amount if manual else None}
            assignment = assignments.get(employee.id, self.env['hrm.employee.assignment'])
            rows.append({'id': employee.id, 'label': f'{employee.employee_code} · {employee.name}',
                         'department': assignment.department_id.name or '',
                         'projects': ', '.join(assignment.project_ids.mapped('name')),
                         'values': values, 'editable': employee in eligible, 'error': error,
                         'gross': item.gross_amount if item else None,
                         'allowances': sum(item.detail_ids.filtered('contract_allowance').mapped('amount')) if item else None,
                         'insurance': item.employee_insurance if item else None,
                         'deduction': item.deduction_amount if item else None, 'tax': item.tax_amount if item else None,
                         'net': item.net_amount if item else None})
        return {'periods': choices, 'period_id': period.id, 'rows': rows,
                'columns': sorted(columns.values(), key=lambda col: (col['sequence'], col['id'])),
                'mode': attendance._grid_lock_mode(period),
                'manage': self.env.user.has_group('hrm_data_import.group_import_approver')}

    @api.model
    def update_salary_grid(self, period_id, operation, changes=None, reason=''):
        attendance = self.env['hrm.attendance.month']
        period = attendance._grid_period(period_id)
        period.check_access('write')
        if operation not in ('calculate', 'save', 'lock', 'unlock'):
            raise UserError('Thao tác bảng lương không hợp lệ.')
        if operation != 'calculate' and not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise AccessError('Cần quyền duyệt để sửa, khóa hoặc mở khóa lương.')
        if operation != 'calculate' and (not isinstance(reason, str) or not reason.strip()):
            raise UserError('Nhập lý do trước khi thực hiện.')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (period.id,))
        period.invalidate_recordset()
        mode = attendance._grid_lock_mode(period)
        if mode == 'final':
            raise UserError('Kỳ đã duyệt, chốt hoặc thanh toán.')
        if operation == 'unlock':
            if mode != 'payroll':
                raise UserError('Kỳ chưa khóa lương.')
            period.correction_reason = reason.strip()
            period.action_reopen_inputs()
            return True
        if mode == 'payroll':
            raise UserError('Mở khóa lương trước khi sửa hoặc tính lại.')
        if operation == 'save':
            if not isinstance(changes, list) or not 0 < len(changes) <= 5000:
                raise UserError('Mỗi lần lưu tối đa 5.000 ô lương đã thay đổi.')
            grid = self.load_salary_grid(period.id)
            rows = {row['id']: row['values'] for row in grid['rows'] if row['editable']}
            adjustments = self.env['hrm.salary.adjustment']
            seen = set()
            for change in changes:
                employee, component = change['employee_id'], change['component_id']
                cell = rows.get(employee, {}).get(component)
                if (employee, component) in seen or cell is None or cell['revision'] != change['revision']:
                    raise UserError('Ô lương đã thay đổi hoặc không hợp lệ. Tải lại bảng.')
                seen.add((employee, component))
                reset = change['amount'] is None
                adjustment = adjustments.create({
                    'company_id': period.company_id.id, 'period_id': period.id, 'employee_id': employee,
                    'component_id': component, 'amount': 0 if reset else change['amount'],
                    'restore_formula': reset, 'reason': reason.strip(),
                })
                adjustment.action_approve()
        result = period.with_context(salary_grid_calculation=True).action_quick_payroll()
        if not result or result.get('res_model') != 'hrm.payroll':
            message = (result or {}).get('params', {}).get('message') or period.readiness
            raise UserError(message or 'Chưa thể tính lương kỳ này.')
        run = self.env['hrm.payroll'].browse(result['res_id'])
        if run.status != 'calculated':
            raise UserError('Chưa thể tính lương kỳ này.')
        if operation == 'lock':
            audit(period, 'UPDATE', {'step': 'salary_grid_lock', 'reason': reason.strip(), 'run_id': run.id})
        else:
            # Keep the calculated preview visible while both sets of inputs can still be edited.
            run.write({'status': 'processing', 'completed_at': False})
            period.status = 'processing'
        return True
