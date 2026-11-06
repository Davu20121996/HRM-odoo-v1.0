import hashlib
import csv
import hmac
import io
import json
import re
import secrets
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.binary import BinaryBytes
from odoo.addons.hrm_data_import.models.attendance_grid import GRID_COLUMNS, GRID_SOURCE
from odoo.tools.mimetypes import guess_mimetype

MANAGER = 'hrm_data_import.group_import_approver'
REQUEST_KINDS = [
    ('am', 'Nghỉ nửa ngày sáng'), ('pm', 'Nghỉ nửa ngày chiều'),
    ('day', 'Nghỉ một ngày'), ('days', 'Nghỉ nhiều ngày'), ('ot', 'Đăng ký tăng ca'),
    ('late', 'Xin đi trễ'), ('early', 'Xin về sớm'), ('outside', 'Xin ra ngoài'),
]
DURATIONS = {'late': (30, 60, 120, 180, 240), 'early': (30, 60, 120, 180, 240),
             'outside': (15, 30, 60), 'ot': tuple(range(30, 721, 30))}


class Employee(models.Model):
    _inherit = 'hr.employee'

    zalo_user_id = fields.Char(copy=False, readonly=True, groups=MANAGER)
    zalo_code_digest = fields.Char(copy=False, groups='base.group_system')
    zalo_code_expires = fields.Datetime(copy=False, readonly=True, groups=MANAGER)
    zalo_code_configured = fields.Boolean(compute='_compute_zalo_code_configured', compute_sudo=True, groups=MANAGER)
    zalo_session_digest = fields.Char(copy=False, index=True, groups='base.group_system')
    zalo_session_expires = fields.Datetime(copy=False, readonly=True, groups=MANAGER)

    _zalo_user_unique = models.Constraint('UNIQUE(zalo_user_id)', 'Tài khoản Zalo đã liên kết.')
    _zalo_code_unique = models.Constraint('UNIQUE(zalo_code_digest)', 'Mã liên kết đã được cấp.')

    @api.depends('zalo_code_digest')
    def _compute_zalo_code_configured(self):
        for employee in self:
            employee.zalo_code_configured = bool(employee.zalo_code_digest)

    @api.model
    def _zalo_digest(self, code):
        secret = self.env['ir.config_parameter'].sudo().get_str('database.secret')
        if not secret:
            raise UserError('Thiếu khóa bảo mật của cơ sở dữ liệu.')
        return hmac.new(secret.encode(), ('zalo-link:' + code).encode(), hashlib.sha256).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        self._check_zalo_fields(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_zalo_fields([vals])
        return super().write(vals)

    def _check_zalo_fields(self, vals_list):
        protected = {'zalo_user_id', 'zalo_code_digest', 'zalo_code_expires',
                     'zalo_session_digest', 'zalo_session_expires'}
        if not self.env.su and any(protected.intersection(vals) for vals in vals_list):
            raise AccessError('Sử dụng chức năng cấp mã hoặc hủy liên kết.')

    def _check_zalo_manager(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group(MANAGER) or self.hrm_company_id not in self.env.user.hrm_company_ids:
            raise AccessError('Bạn không có quyền quản lý liên kết của nhân viên này.')

    def action_zalo_code(self):
        self._check_zalo_manager()
        return {'type': 'ir.actions.act_window', 'name': 'Cấp mã liên kết Zalo',
                'res_model': 'hrm.zalo.code', 'views': [[False, 'form']], 'target': 'new',
                'context': {'default_employee_id': self.id}}

    def action_zalo_unlink(self):
        self._check_zalo_manager()
        self.sudo().write({'zalo_user_id': False, 'zalo_code_digest': False, 'zalo_code_expires': False,
                           'zalo_session_digest': False, 'zalo_session_expires': False})
        self._log_zalo_event('zalo_unlinked', actor=self.env.uid)

    def _log_zalo_event(self, step, actor, **details):
        self.ensure_one()
        self.env['hrm.audit.log'].sudo().create({
            'tenant_id': self.tenant_id.id, 'company_id': self.hrm_company_id.id,
            'actor_user_id': actor, 'actor_employee_ref': self.employee_code,
            'entity_type': self._name, 'entity_id': self.id,
            'action': 'UPDATE', 'metadata': {'step': step, **details},
        })

    @api.model
    def _zalo_eligible(self):
        return [('active', '=', True), ('current_status', 'in', ['active', 'onboarding']),
                ('hrm_company_id', '!=', False)]

    @api.autovacuum
    def _gc_zalo_codes(self):
        self.sudo().search([('zalo_code_expires', '<', fields.Datetime.now()),
                            ('zalo_code_digest', '!=', False)]).write({'zalo_code_digest': False})


class LinkCode(models.TransientModel):
    _name = 'hrm.zalo.code'
    _description = 'Cấp mã liên kết Zalo'
    _transient_max_hours = 0.25

    employee_id = fields.Many2one('hr.employee', required=True, readonly=True)
    code = fields.Char(string='Mã 6 số')
    issued = fields.Boolean(readonly=True)

    def action_issue(self):
        self.ensure_one()
        employee = self.employee_id
        employee._check_zalo_manager()
        self.env.cr.execute("SELECT id FROM hr_employee WHERE id=%s FOR UPDATE", (employee.id,))
        employee.invalidate_recordset()
        if not employee.filtered_domain(employee._zalo_eligible()) or not employee.employee_code:
            raise UserError('Chỉ cấp mã cho nhân viên đang làm việc và đã có mã nhân viên.')
        if self.issued:
            raise UserError('Mã đã cấp. Mở lại cửa sổ để cấp mã mới.')
        code = (self.code or '').strip()
        if code and not re.fullmatch(r'[0-9]{6}', code):
            raise UserError('Mã phải gồm đúng 6 chữ số.')
        employee = employee.sudo()
        for _ in range(10):
            candidate = code or f'{secrets.randbelow(1_000_000):06d}'
            digest = employee._zalo_digest(candidate)
            try:
                with self.env.cr.savepoint():
                    employee.write({'zalo_code_digest': digest,
                                    'zalo_code_expires': False,
                                    'zalo_session_digest': False, 'zalo_session_expires': False})
                break
            except IntegrityError:
                if code:
                    raise UserError('Mã đang được cấp cho hồ sơ khác. Chọn mã khác.')
        else:
            raise UserError('Chưa cấp được mã, vui lòng thử lại.')
        self.write({'code': candidate, 'issued': True})
        employee._log_zalo_event('zalo_code_issued', actor=self.env.uid)
        return {'type': 'ir.actions.act_window', 'name': 'Mã liên kết đã cấp',
                'res_model': self._name, 'res_id': self.id, 'views': [[False, 'form']], 'target': 'new'}


class Announcement(models.Model):
    _name = 'hrm.zalo.notice'
    _description = 'Thông báo nhân sự trên Zalo'
    _order = 'important desc, published_at desc, id desc'

    company_id = fields.Many2one('hrm.company', required=True, ondelete='restrict', string='Công ty',
                                 default=lambda self: self.env.user.hrm_company_ids[:1])
    title = fields.Char(required=True, size=160, string='Tiêu đề')
    body = fields.Text(required=True, string='Nội dung')
    image = fields.Image(max_width=1000, max_height=1000, string='Hình ảnh')
    important = fields.Boolean(string='Sự kiện quan trọng')
    published_at = fields.Datetime(readonly=True, copy=False, string='Đăng lúc')
    active = fields.Boolean(default=True)

    @api.constrains('body', 'image')
    def _validate_content(self):
        for notice in self:
            if len(notice.body or '') > 4000:
                raise UserError('Nội dung tối đa 4.000 ký tự.')
            if notice.image:
                content = notice.image.content
                if len(content) > 600_000 or guess_mimetype(content) not in ('image/png', 'image/jpeg', 'image/webp'):
                    raise UserError('Chọn ảnh JPG, PNG hoặc WebP tối đa 600 KB sau khi thu nhỏ.')

    def action_publish(self):
        self.write({'published_at': fields.Datetime.now(), 'active': True})

    def action_unpublish(self):
        self.write({'published_at': False})


class Attempt(models.Model):
    _name = 'hrm.zalo.attempt'
    _description = 'Giới hạn thử mã Zalo'
    _log_access = False

    identity = fields.Char(required=True)
    bucket = fields.Datetime(required=True)
    attempts = fields.Integer(required=True)
    _bucket_unique = models.Constraint('UNIQUE(identity,bucket)', 'Duplicate rate-limit bucket.')

    @api.model
    def _take(self, identity, limit, bucket):
        key = hashlib.sha256(identity.encode()).hexdigest()
        self.env.cr.execute("""
            INSERT INTO hrm_zalo_attempt (identity,bucket,attempts) VALUES (%s,%s,1)
            ON CONFLICT (identity,bucket) DO UPDATE SET attempts=hrm_zalo_attempt.attempts+1
            WHERE hrm_zalo_attempt.attempts < %s RETURNING id
        """, (key, bucket, limit))
        return bool(self.env.cr.fetchone())

    @api.model
    def _release(self, identities, bucket):
        keys = [hashlib.sha256(identity.encode()).hexdigest() for identity in identities]
        self.env.cr.execute("""
            UPDATE hrm_zalo_attempt SET attempts = attempts - 1
            WHERE bucket = %s AND identity = ANY(%s) AND attempts > 0
        """, (bucket, keys))

    @api.autovacuum
    def _gc_attempts(self):
        self.sudo().search([('bucket', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()


class LeaveType(models.Model):
    _inherit = 'hrm.leave.type'

    dashboard_maternity = fields.Boolean(string='Nghỉ thai sản')

    @api.model
    def _miniapp_type(self, tenant, kind):
        code = 'ZMP_' + kind.upper()
        self.env.cr.execute('SELECT id FROM hrm_tenant WHERE id=%s FOR UPDATE', (tenant.id,))
        domain = [('tenant_id', '=', tenant.id), ('code', '=', code)]
        record = self.search(domain, limit=1)
        return record or self.create({'tenant_id': tenant.id, 'code': code,
                                      'name': dict(REQUEST_KINDS)[kind], 'paid': False,
                                      'unit': 'hour' if kind in DURATIONS else 'day',
                                      'allow_negative_balance': True})


class MiniAppLeaveRequest(models.Model):
    _inherit = 'hrm.leave.request'

    miniapp_kind = fields.Selection(REQUEST_KINDS, string='Yêu cầu Mini App', readonly=True, copy=False)
    miniapp_minutes = fields.Integer(string='Số phút', readonly=True, copy=False)
    miniapp_attendance_state = fields.Selection(
        [('waiting', 'Chờ ghi công'), ('applied', 'Đã ghi công')], string='Ghi công', readonly=True, copy=False)
    miniapp_attendance_message = fields.Text(string='Lý do chưa ghi công', readonly=True, copy=False)
    miniapp_applied_at = fields.Datetime(string='Ghi công lúc', readonly=True, copy=False)
    miniapp_applied_by = fields.Many2one('res.users', string='Người ghi công', readonly=True, copy=False)

    _miniapp_managed_fields = {'miniapp_kind', 'miniapp_minutes', 'miniapp_attendance_state',
                               'miniapp_attendance_message', 'miniapp_applied_at', 'miniapp_applied_by'}

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(self._miniapp_managed_fields & vals.keys() for vals in vals_list):
            raise AccessError('Yêu cầu này được tạo từ Mini App.')
        return super().create(vals_list)

    def write(self, vals):
        if self._miniapp_managed_fields & vals.keys():
            raise AccessError('Thông tin ghi công do hệ thống quản lý.')
        protected = {'employee_id', 'tenant_id', 'leave_type_id', 'start_at', 'end_at', 'requested_quantity', 'reason'}
        requests = self.filtered('miniapp_kind') if protected & vals.keys() or 'status' in vals else self.browse()
        if requests and protected & vals.keys():
            raise UserError('Thông tin đơn Mini App đã gửi. Hãy tạo đơn mới nếu cần điều chỉnh.')
        if requests and (vals.get('status') in ('approved', 'taken') or
                         ('status' in vals and any(row.status in ('approved', 'taken') for row in requests))):
            raise UserError('Dùng nút Duyệt để xử lý đơn. Đơn đã duyệt được giữ trong lịch sử.')
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _protect_miniapp_request_history(self):
        if self.filtered('miniapp_kind'):
            raise UserError('Đơn Mini App được giữ trong lịch sử. Hãy hủy hoặc từ chối đơn đang chờ nếu cần.')

    def _lock_miniapp_requests(self):
        self.check_access('write')
        if not self.env.user.has_group(MANAGER) or any(
                row.employee_id.hrm_company_id not in self.env.user.hrm_company_ids for row in self):
            raise AccessError('Bạn chỉ được xử lý đơn của công ty được cấp quyền.')
        self.env.cr.execute('SELECT id FROM hrm_leave_request WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
        self.invalidate_recordset()

    def action_approve(self):
        manual = self.filtered(lambda row: not row.miniapp_kind)
        miniapp = self - manual
        if manual:
            super(MiniAppLeaveRequest, manual).action_approve()
        if not miniapp:
            return True
        miniapp._lock_miniapp_requests()
        for row in miniapp:
            if row.status != 'pending_approval':
                raise UserError('Chỉ duyệt đơn đang chờ xử lý.')
            # Time adjustments and unpaid requests have no leave quota to post.
            approver = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
            self.env['hrm.leave.approval'].create({
                'tenant_id': row.tenant_id.id, 'request_id': row.id, 'decision': 'approved',
                'sequence_no': 1, 'decided_at': fields.Datetime.now(), 'approver_employee_id': approver.id,
            })
            super(MiniAppLeaveRequest, row).write({'status': 'approved'})
            row._record_miniapp_attendance()
        return True

    def _record_miniapp_attendance(self):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self._apply_miniapp_attendance()
        except UserError as error:
            super().write({'miniapp_attendance_state': 'waiting', 'miniapp_attendance_message': str(error)})
            return False
        super().write({'miniapp_attendance_state': 'applied', 'miniapp_attendance_message': False,
                       'miniapp_applied_at': fields.Datetime.now(), 'miniapp_applied_by': self.env.uid})
        return True

    def action_apply_miniapp_attendance(self):
        self.ensure_one()
        self._lock_miniapp_requests()
        if self.status == 'approved' and self.miniapp_attendance_state == 'waiting':
            applied = self._record_miniapp_attendance()
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'message': 'Đã ghi công từ đơn.' if applied else self.miniapp_attendance_message,
                'type': 'success' if applied else 'warning', 'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }}
        return False

    @api.model
    def _miniapp_history_action(self, period=None):
        action = self.env['ir.actions.actions']._for_xml_id('hrm_zalo.action_miniapp_leave_history')
        companies = self.env.user.hrm_company_ids
        domain = [('miniapp_kind', '!=', False), ('employee_id.hrm_company_id', 'in', companies.ids)]
        if period:
            company = period.company_id & companies
            zone = ZoneInfo(company.timezone or 'Asia/Ho_Chi_Minh') if company else ZoneInfo('Asia/Ho_Chi_Minh')
            start = datetime.combine(period.period_start, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
            end = datetime.combine(period.period_end + timedelta(days=1), time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
            domain += [('employee_id.hrm_company_id', 'in', company.ids), ('start_at', '<', end), ('end_at', '>=', start)]
        action['domain'] = domain
        return action

    def _apply_miniapp_attendance(self):
        self.ensure_one()
        employee = self.employee_id
        company = employee.hrm_company_id
        zone = ZoneInfo(company.timezone or 'Asia/Ho_Chi_Minh')
        first, last = [value.replace(tzinfo=timezone.utc).astimezone(zone).date()
                       for value in (self.start_at, self.end_at)]
        periods = self.env['hrm.payroll.period'].sudo().search([
            ('company_id', '=', company.id), ('tenant_id', '=', self.tenant_id.id),
            ('period_start', '<=', last), ('period_end', '>=', first),
        ])
        if not periods:
            raise UserError('Chưa có kỳ chấm công cho ngày xin nghỉ hoặc điều chỉnh.')
        self.env.cr.execute('SELECT id FROM hrm_payroll_period WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(periods.ids),))
        periods.invalidate_recordset()
        grid = self.env['hrm.attendance.month'].sudo()
        inputs = self.env['hrm.import.input'].sudo().search([
            ('company_id', '=', company.id), ('period_id', 'in', periods.ids),
            ('employee_id', '=', employee.id), ('dataset', '=', 'attendance'),
        ], order='id')
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            period = periods.filtered(lambda item: item.period_start <= day <= item.period_end)
            if len(period) != 1:
                raise UserError(f'{day:%d/%m/%Y} cần thuộc đúng một kỳ chấm công.')
            if period.status not in ('open', 'processing') or grid._grid_lock_mode(period) != 'open':
                raise UserError(f'Kỳ công {day:%m/%Y} đã khóa. Hãy mở kỳ theo quy trình trước khi ghi công.')
            rows = inputs.filtered(lambda item: item.period_id == period and item.payload['work_date'] == day.isoformat())
            self._adjust_miniapp_day(grid, period, day, rows)

    def _adjust_miniapp_day(self, grid, period, day, rows):
        kind = self.miniapp_kind
        full_day = kind in ('day', 'days')
        half_day = kind in ('am', 'pm')
        markers = {'am': '1/2RO', 'pm': '1/2RO', 'day': 'RO', 'days': 'RO',
                   'ot': 'W', 'late': 'DT', 'early': 'VS', 'outside': 'RN'}
        marker = markers[kind]
        quantity = period.hours_per_day / 2 if half_day else self.miniapp_minutes / 60
        before = [item.payload for item in rows]
        if not rows and not (full_day or kind == 'ot'):
            raise UserError(
                f'Chưa lưu công cho nhân viên {self.employee_id.employee_code} ngày {day:%d/%m/%Y} '
                f'trong kỳ {period.period_code}. Hãy lưu ô của ngày này tại Bảng nhập công theo tháng rồi ghi công từ đơn.'
            )
        if not rows:
            csv_file = io.StringIO()
            writer = csv.writer(csv_file)
            writer.writerow(GRID_COLUMNS)
            writer.writerow([self.employee_id.employee_code, f'{self.employee_id.id}:{day}', 1,
                             f'Đơn Mini App #{self.id}', day, 0, quantity if kind == 'ot' else 0, marker])
            batch = self.env['hrm.import.batch'].create({
                'profile_id': grid._grid_profile(period).id, 'period_id': period.id,
                'filename': f'miniapp-{self.id}-{day}.csv',
                'file_data': BinaryBytes(csv_file.getvalue().encode('utf-8')),
            })
            batch.action_preview()
            if batch.state == 'ready':
                batch.action_commit()
            if batch.state != 'committed':
                raise UserError(batch.line_ids.filtered('error')[:1].error or batch.message)
        else:
            total = sum(float(item.get('regular_hours', 0)) + float(item.get('overtime_hours', 0)) for item in before)
            if kind == 'ot' and total + quantity > 24:
                raise UserError(f'Tổng giờ công và tăng ca ngày {day:%d/%m/%Y} vượt 24 giờ.')
            deduction = quantity
            for index, item in enumerate(rows):
                payload = dict(item.payload)
                regular = float(payload['regular_hours'])
                overtime = float(payload.get('overtime_hours', 0))
                removed = min(regular, deduction) if kind != 'ot' else 0
                deduction -= removed
                payload['regular_hours'] = str(round(0 if full_day else regular - removed, 8))
                payload['overtime_hours'] = str(0 if full_day else overtime + (quantity if kind == 'ot' and not index else 0))
                if not index or full_day:
                    current = payload.get('attendance_symbol') or ''
                    codes = current.split('+') if current else []
                    if full_day:
                        codes = [marker]
                    elif half_day:
                        codes = [marker, 'W'] if 'W' in codes else [marker]
                    elif marker not in codes:
                        codes.append(marker)
                    payload['attendance_symbol'] = '+'.join(codes)
                payload['approval_reference'] = f'Đơn Mini App #{self.id}'
                values = {'payload': payload}
                if item.source == GRID_SOURCE:
                    values['revision'] = item.revision + 1
                    payload['revision'] = str(values['revision'])
                item.write(values)
        self.employee_id._log_zalo_event('zalo_attendance_adjusted', actor=self.env.uid, request_id=self.id,
                                         date=day.isoformat(), symbol=marker, before=before,
                                         after=[item.payload for item in rows] if rows else
                                         [{'regular_hours': 0, 'overtime_hours': quantity if kind == 'ot' else 0}])


class AttendanceGrid(models.Model):
    _inherit = 'hrm.attendance.month'

    @api.model
    def load_attendance_grid(self, period_id=False):
        result = super().load_attendance_grid(period_id)
        if result.get('period_id') and self.env.user.has_group(MANAGER):
            period = self.env['hrm.payroll.period'].browse(result['period_id'])
            result['leave_history_action'] = self.env['hrm.leave.request']._miniapp_history_action(period)
        return result


class ContractType(models.Model):
    _inherit = 'hrm.contract.type'

    dashboard_internship = fields.Boolean(string='Hợp đồng thực tập')


class Dashboard(models.TransientModel):
    _name = 'hrm.zalo.dashboard'
    _description = 'Tổng quan nhân sự Mini App'

    company_id = fields.Many2one('hrm.company', required=True, default=lambda self: self.env.user.hrm_company_ids[:1])
    employee_count = fields.Integer(compute='_compute_totals', string='Nhân viên đang làm')
    linked_count = fields.Integer(compute='_compute_totals', string='Đã liên kết Zalo')
    leave_count = fields.Integer(compute='_compute_totals', string='Đơn nghỉ chờ duyệt')
    notice_count = fields.Integer(compute='_compute_totals', string='Thông báo đang đăng')
    notice_ids = fields.Many2many('hrm.zalo.notice', compute='_compute_totals', string='Sự kiện quan trọng')
    dashboard_payload = fields.Char(compute='_compute_totals')

    def _pending_leave_domain(self):
        self.ensure_one()
        company = self.company_id & self.env.user.hrm_company_ids
        return [('employee_id.hrm_company_id', 'in', company.ids), ('status', '=', 'pending_approval')]

    def action_pending_leave(self):
        action = self.env['ir.actions.actions']._for_xml_id('hrm_leave.action_hrm_leave_request')
        action.update(name='Đơn nghỉ chờ duyệt', domain=self._pending_leave_domain(), context={'create': False})
        return action

    @api.depends('company_id')
    def _compute_totals(self):
        for row in self:
            company = row.company_id & self.env.user.hrm_company_ids
            employees = self.env['hr.employee'].sudo().search(
                [('hrm_company_id', 'in', company.ids)] + self.env['hr.employee']._zalo_eligible())
            row.employee_count = len(employees)
            row.linked_count = len(employees.filtered('zalo_user_id'))
            now = fields.Datetime.now()
            code_sessions = employees.filtered(
                lambda person: not person.zalo_user_id and person.zalo_session_digest
                and person.zalo_session_expires and person.zalo_session_expires > now)
            leave = self.env['hrm.leave.request']
            pending_domain = row._pending_leave_domain()
            row.leave_count = leave.search_count(pending_domain)
            pending = leave.search(pending_domain, order='create_date desc, id desc', limit=5)
            notices = self.env['hrm.zalo.notice'].search([('company_id', 'in', company.ids), ('published_at', '!=', False)])
            row.notice_count = len(notices)
            row.notice_ids = notices.filtered('important')[:10]
            zone = ZoneInfo(company.timezone or 'Asia/Ho_Chi_Minh') if company else ZoneInfo('Asia/Ho_Chi_Minh')
            today = fields.Date.context_today(row.with_context(tz=zone.key))
            start = datetime.combine(today, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
            end = start + timedelta(days=1)
            maternity = self.env['hrm.leave.request'].sudo().search([
                ('employee_id', 'in', employees.ids), ('leave_type_id.dashboard_maternity', '=', True),
                ('status', 'in', ['approved', 'taken']), ('start_at', '<', end), ('end_at', '>=', start),
            ]).employee_id
            interns = self.env['hrm.employee.contract'].sudo().search([
                ('company_id', 'in', company.ids), ('employee_id', 'in', employees.ids),
                ('contract_type_id.dashboard_internship', '=', True), ('status', '=', 'active'),
                ('start_date', '<=', today), '|', ('end_date', '=', False), ('end_date', '>=', today),
            ]).employee_id
            joined = employees.filtered(lambda person: person.hire_date and today.replace(day=1) <= person.hire_date <= today)
            birthdays = []
            for person in employees:
                birthday = person.hrm_birth_date or person.birthday
                if birthday and birthday.month == today.month:
                    birthdays.append({'id': person.id, 'name': person.name, 'day': birthday.day,
                                      'date': f'{birthday:%d/%m}'})
            row.dashboard_payload = json.dumps({
                'month': today.strftime('%m/%Y'), 'working': len(employees - maternity),
                'maternity': len(maternity), 'new': len(joined), 'interns': len(interns),
                'linked': row.linked_count, 'code_sessions': len(code_sessions),
                'leave': row.leave_count, 'notices': row.notice_count,
                'pending_leave': [{'id': request.id, 'employee': request.employee_id.name,
                                   'type': request.leave_type_id.name,
                                   'start': fields.Datetime.context_timestamp(row.with_context(tz=zone.key),
                                                                              request.start_at).strftime('%d/%m/%Y')}
                                  for request in pending],
                'birthdays': sorted(birthdays, key=lambda item: (item['day'], item['name'])),
                'events': [{'id': notice.id, 'title': notice.title} for notice in row.notice_ids],
            }, ensure_ascii=False)
