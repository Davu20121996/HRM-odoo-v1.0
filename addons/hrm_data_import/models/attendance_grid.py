import csv
import io
import math
import re
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.binary import BinaryBytes

from .imports import GRID_SOURCE, audit
GRID_COLUMNS = {
    'employee_code': 'text', 'source_record_id': 'text', 'revision': 'number',
    'approval_reference': 'text', 'work_date': 'date', 'regular_hours': 'number',
    'overtime_hours': 'number', 'attendance_symbol': 'text',
}
DEFAULT_SYMBOLS = {'X': (8, 0), 'X4': (4, 0), 'TC2': (0, 2), 'X+TC2': (8, 2),
                   'RO': (0, 0), '1/2RO': (4, 0), '0': (0, 0)}


class AttendanceSymbol(models.Model):
    _name = 'hrm.attendance.symbol'
    _description = 'Ký hiệu chấm công'
    _rec_name = 'code'
    _order = 'code'

    company_id = fields.Many2one('hrm.company', required=True, default=lambda self: self.env.user.hrm_company_ids[:1])
    code = fields.Char(required=True, string='Ký hiệu')
    regular_hours = fields.Float(string='Giờ thường')
    overtime_hours = fields.Float(string='Giờ tăng ca')
    enabled = fields.Boolean(default=True, string='Cho phép nhập')
    _code_unique = models.Constraint('UNIQUE(company_id, code)', 'Ký hiệu đã tồn tại trong công ty.')

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals, code=(vals.get('code') or '').strip().upper()) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if 'code' in vals:
            vals = dict(vals, code=(vals['code'] or '').strip().upper())
        return super().write(vals)

    @api.constrains('code', 'regular_hours', 'overtime_hours')
    def _check_symbol(self):
        for record in self:
            if not re.fullmatch(r'[A-Z0-9+_/-]{1,16}', record.code or '') or record.code == '0':
                raise UserError('Ký hiệu gồm tối đa 16 chữ, số hoặc dấu + _ / -. Mã 0 dành cho ngày không có giờ.')
            regular, overtime = record.regular_hours, record.overtime_hours
            if not all(math.isfinite(hours) and hours >= 0 for hours in (regular, overtime)) or regular + overtime > 24:
                raise UserError('Tổng giờ thường và giờ tăng ca phải từ 0 đến 24.')


class AttendancePeriod(models.Model):
    _inherit = 'hrm.payroll.period'

    attendance_locked = fields.Boolean(string='Khóa nhập công', readonly=True,
                                       groups='hrm_data_import.group_import_operator')

    def write(self, vals):
        if 'attendance_locked' in vals and not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise AccessError('Cần quyền duyệt để khóa hoặc mở khóa nhập công.')
        return super().write(vals)


class AttendanceGrid(models.Model):
    _inherit = 'hrm.attendance.month'

    @api.model
    def _grid_periods(self):
        if not self.env.user.has_group('hrm_data_import.group_import_operator'):
            raise AccessError('Cần quyền nhập công.')
        return self.env['hrm.payroll.period'].search([
            ('company_id', 'in', self.env.user.hrm_company_ids.ids),
        ], order='period_start desc, id desc')

    @api.model
    def _grid_period(self, period_id):
        period = self._grid_periods().filtered(lambda period: period.id == period_id)
        if not period:
            raise UserError('Kỳ chấm công không tồn tại hoặc nằm ngoài công ty được cấp quyền.')
        return period

    @api.model
    def _grid_symbols(self, company):
        symbols = dict(DEFAULT_SYMBOLS)
        for line in self.env['hrm.attendance.symbol'].search([('company_id', '=', company.id)]):
            if line.enabled:
                symbols[line.code] = (line.regular_hours, line.overtime_hours)
            else:
                symbols.pop(line.code, None)
        return symbols

    @api.model
    def update_grid_symbol(self, period_id, operation, code, regular=0, overtime=0):
        period = self._grid_period(period_id)
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise AccessError('Cần quyền duyệt để quản lý ký hiệu chấm công.')
        company = period.company_id
        code = (code or '').strip().upper()
        if code == '0' or operation not in ('add', 'edit', 'delete'):
            raise UserError('Không thể thay đổi ký hiệu này.')
        self.env.cr.execute('SELECT id FROM hrm_company WHERE id=%s FOR UPDATE', (company.id,))
        model = self.env['hrm.attendance.symbol']
        record = model.search([('company_id', '=', company.id), ('code', '=', code)], limit=1)
        exists = code in self._grid_symbols(company)
        if operation == 'add' and exists:
            raise UserError('Ký hiệu đã tồn tại. Chọn Sửa để cập nhật.')
        if operation != 'add' and not exists:
            raise UserError('Ký hiệu không còn hiệu lực. Tải lại bảng.')
        if operation == 'delete' and code not in DEFAULT_SYMBOLS:
            record.unlink()
        else:
            values = {'enabled': operation != 'delete'}
            if operation != 'delete':
                values.update(regular_hours=regular, overtime_hours=overtime)
            if record:
                record.write(values)
            else:
                model.create(dict(values, company_id=company.id, code=code))
        return self._grid_symbols(company)

    @api.model
    def _grid_inputs(self, period):
        return self.env['hrm.import.input'].search([
            ('company_id', '=', period.company_id.id), ('period_id', '=', period.id), ('dataset', '=', 'attendance'),
        ])

    @api.model
    def _grid_lock_mode(self, period):
        runs = self.env['hrm.payroll'].search([('period_id', '=', period.id)])
        statuses = set(runs.mapped('status')) | {period.status}
        if statuses & {'approved', 'finalized', 'paid'}:
            return 'final'
        if statuses & {'calculated', 'review'}:
            return 'payroll'
        return 'manual' if period.attendance_locked else 'open'

    @api.model
    def set_grid_lock(self, period_id, locked, reason=''):
        period = self._grid_period(period_id)
        if not self.env.user.has_group('hrm_data_import.group_import_approver'):
            raise AccessError('Cần quyền duyệt để khóa hoặc mở khóa nhập công.')
        period.check_access('write')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (period.id,))
        period.invalidate_recordset()
        mode = self._grid_lock_mode(period)
        if mode == 'final':
            raise UserError('Kỳ lương đã duyệt, chốt hoặc thanh toán. Không thể mở khóa công.')
        if locked and mode != 'open':
            return
        if not locked and mode == 'payroll':
            raise UserError('Hãy mở khóa tại Bảng nhập lương theo tháng trước khi sửa công.')
        if period.attendance_locked != locked:
            period.write({'attendance_locked': locked})
            audit(period, 'UPDATE', {'step': 'attendance_grid_lock', 'locked': locked})

    @api.model
    def load_attendance_grid(self, period_id=False):
        periods = self._grid_periods()
        choices = [{'id': p.id, 'label': f'{p.period_start:%m/%Y} · {p.company_id.name} · {p.period_code}'} for p in periods]
        if not periods:
            return {'periods': [], 'rows': []}
        period = self._grid_period(period_id) if period_id else periods[0]
        employees = self.env['hr.employee'].with_context(active_test=False).search([
            ('hrm_company_id', '=', period.company_id.id), ('tenant_id', '=', period.tenant_id.id),
        ], order='employee_code, id')
        assignments = employees._primary_assignments(period.period_end)
        empty_assignment = self.env['hrm.employee.assignment']
        dates = [period.period_start + timedelta(days=i) for i in range((period.period_end - period.period_start).days + 1)]
        cells = defaultdict(dict)
        for entry in self._grid_inputs(period):
            payload = entry.payload
            cell = cells[entry.employee_id.id].setdefault(payload['work_date'], {
                'regular': 0, 'overtime': 0, 'revision': 0, 'code': '', 'imported': False,
            })
            cell['regular'] += float(payload['regular_hours'])
            cell['overtime'] += float(payload.get('overtime_hours', 0))
            if entry.source == GRID_SOURCE:
                cell.update(code=payload['attendance_symbol'], revision=entry.revision)
            else:
                cell['code'] = payload.get('attendance_symbol', '') if not cell['imported'] else ''
                cell['imported'] = True
        lock_mode = self._grid_lock_mode(period)
        return {'periods': choices, 'period_id': period.id, 'locked': lock_mode != 'open',
                'lock_mode': lock_mode,
                'dates': [{'key': day.isoformat(), 'label': day.strftime('%d/%m')} for day in dates],
                'hours_per_day': period.hours_per_day,
                'symbols': self._grid_symbols(period.company_id),
                'manage_symbols': self.env.user.has_group('hrm_data_import.group_import_approver'),
                'rows': [{'id': emp.id, 'code': emp.employee_code, 'name': emp.name,
                          'department': assignments.get(emp.id, empty_assignment).department_id.name or '',
                          'projects': ', '.join(assignments.get(emp.id, empty_assignment).project_ids.mapped('name')),
                          'start': emp.hire_date.isoformat() if emp.hire_date else '',
                          'end': emp.termination_date.isoformat() if emp.termination_date else '',
                          'cells': cells[emp.id]} for emp in employees]}

    @api.model
    def _grid_profile(self, period):
        company = period.company_id
        profiles = self.env['hrm.import.profile']
        domain = [('company_id', '=', company.id), ('dataset', '=', 'attendance'),
                  ('source', '=', GRID_SOURCE), ('state', '=', 'approved')]
        profile = profiles.search(domain, limit=1)
        if not profile:
            self.env.cr.execute('SELECT id FROM hrm_company WHERE id=%s FOR UPDATE', (company.id,))
            profile = profiles.search(domain, limit=1)
        if not profile:
            profile = profiles.create({
                'name': 'Bảng chấm công theo ô', 'company_id': company.id, 'tenant_id': period.tenant_id.id,
                'dataset': 'attendance', 'source': GRID_SOURCE, 'locale': 'en', 'headers': list(GRID_COLUMNS),
                'mapping_ids': [(0, 0, {'column': index, 'target': key, 'data_type': kind, 'required': True})
                                for index, (key, kind) in enumerate(GRID_COLUMNS.items(), 1)],
            })
            profile.sudo().action_approve()
        return profile

    @api.model
    def save_attendance_grid(self, period_id, changes):
        period = self._grid_period(period_id)
        if not isinstance(changes, list) or not 0 < len(changes) <= 5000:
            raise UserError('Mỗi lần lưu tối đa 5.000 ô đã thay đổi.')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id=%s FOR UPDATE', (period.id,))
        period.invalidate_recordset()
        if self._grid_lock_mode(period) != 'open':
            raise UserError('Kỳ đã tính lương hoặc đã khóa. Mở lại kỳ trước khi sửa công.')
        grid = self.load_attendance_grid(period.id)
        rows = {row['id']: row for row in grid['rows']}
        days = {day['key'] for day in grid['dates']}
        symbols = grid['symbols']
        seen = set()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(GRID_COLUMNS)
        for change in changes:
            employee_id, day = change['employee_id'], change['date']
            row = rows.get(employee_id)
            key = (employee_id, day)
            if not row or day not in days or key in seen:
                raise UserError('Ô chấm công trùng hoặc nằm ngoài kỳ/công ty.')
            seen.add(key)
            cell = row['cells'].get(day, {})
            if cell.get('imported') or cell.get('revision', 0) != change['revision']:
                raise UserError('Ô công đã thay đổi hoặc lấy từ nguồn khác. Tải lại bảng trước khi sửa.')
            code = change['code'].strip().upper() or '0'
            if code not in symbols:
                raise UserError(f'Ký hiệu {code} chưa được cấu hình.')
            regular, overtime = symbols[code]
            writer.writerow([row['code'], f'{employee_id}:{day}', change['revision'] + 1,
                             'Lưu từ bảng chấm công theo ô', day, regular, overtime, code])
        batch = self.env['hrm.import.batch'].create({
            'profile_id': self._grid_profile(period).id, 'period_id': period.id,
            'filename': 'bang-cham-cong.csv', 'file_data': BinaryBytes(output.getvalue().encode('utf-8')),
        })
        batch.action_preview()
        if batch.state == 'ready':
            batch.action_commit()
        if batch.state != 'committed':
            return {'ok': False, 'batch_id': batch.id, 'message': batch.line_ids.filtered('error')[:1].error or batch.message}
        return {'ok': True, 'batch_id': batch.id}
