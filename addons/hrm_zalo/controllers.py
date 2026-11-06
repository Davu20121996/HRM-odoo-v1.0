import base64
import hashlib
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype

from .models import DURATIONS, REQUEST_KINDS

PREFIX = '/hrm/zalo/v1'
ORIGIN = 'https://h5.zdn.vn'


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        super().__init__(message)


def cors_headers():
    origin = request.httprequest.headers.get('Origin', '')
    if origin == ORIGIN or re.fullmatch(r'https?://(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?', origin):
        return [('Vary', 'Origin'), ('Access-Control-Allow-Origin', origin)]
    return [('Vary', 'Origin')]


def response(data, status=200):
    return request.make_json_response(data, status=status, headers=cors_headers() + [
        ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
    ])


def preflight_response():
    return request.make_response('', status=204, headers=cors_headers() + [
        ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
        ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
        ('Access-Control-Max-Age', '600'),
    ])


class ZaloMiniApp(http.Controller):
    def _ensure_enabled(self):
        config = request.env['ir.config_parameter'].sudo()
        if config.get_str('hrm_zalo.enabled') != 'True':
            raise ApiError(503, 'not_configured', 'Mini App chưa được bật.')

    def _bearer(self):
        scheme, _, token = request.httprequest.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not token or len(token) > 4096 or not token.isascii():
            raise ApiError(401, 'unauthorized', 'Cần xác thực bằng Zalo.')
        return token

    def _session_domain(self, token):
        return [('zalo_session_digest', '=', hashlib.sha256(token.encode()).hexdigest()),
                ('zalo_session_expires', '>', fields.Datetime.now())]

    def _verify(self):
        return self._verify_token(self._bearer())

    def _verify_token(self, token):
        if not isinstance(token, str) or not token or len(token) > 4096 or not token.isascii():
            raise ApiError(401, 'invalid_token', 'Zalo chưa trả thông tin xác thực.')
        try:
            result = requests.get('https://graph.zalo.me/v2.0/me', params={'fields': 'id'},
                                  headers={'access_token': token}, timeout=(3, 5), allow_redirects=False)
            if result.status_code >= 500:
                raise ApiError(503, 'zalo_unavailable', 'Zalo tạm thời không phản hồi.')
            data = result.json() if result.ok else {}
        except (requests.RequestException, ValueError):
            raise ApiError(503, 'zalo_unavailable', 'Zalo tạm thời không phản hồi.') from None
        identity = str(data.get('id', '')) if isinstance(data, dict) else ''
        if not re.fullmatch(r'[0-9]{1,40}', identity) or data.get('error', 0) not in (0, '0', None):
            raise ApiError(401, 'invalid_token', 'Phiên Zalo hết hạn hoặc chưa được cấp quyền.')
        return identity

    def _body(self):
        if (request.httprequest.content_length or 0) > 8192:
            raise ApiError(413, 'too_large', 'Yêu cầu quá dài.')
        payload = request.httprequest.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ApiError(400, 'invalid_body', 'Yêu cầu phải là JSON.')
        return payload

    def _serve(self, endpoint, require_link=True):
        if request.httprequest.method == 'OPTIONS':
            return preflight_response()
        try:
            self._ensure_enabled()
            model = request.env['hr.employee'].sudo()
            token = self._bearer()
            if re.fullmatch(r'hrm_[A-Za-z0-9_-]{43}', token):
                identity = None
                domain = self._session_domain(token)
            else:
                identity = self._verify()
                domain = [('zalo_user_id', '=', identity)]
            employee = model.search(domain + model._zalo_eligible(), limit=1)
            if identity is None and not employee:
                raise ApiError(401, 'session_expired', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
            if require_link and not employee:
                raise ApiError(403, 'link_required', 'Nhập mã nhân viên và mã 6 số do nhân sự cấp.')
            return response(endpoint(identity, employee))
        except ApiError as exc:
            return response({'error': exc.code, 'message': str(exc)}, exc.status)

    @http.route(PREFIX + '/session', type='http', auth='public', methods=['GET'], save_session=False)
    def session(self):
        return self._serve(lambda identity, employee: {'linked': bool(employee)}, require_link=False)

    @http.route(PREFIX + '/link', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def link(self):
        def bind(identity, linked):
            if identity is None:
                raise ApiError(401, 'unauthorized', 'Cần xác thực bằng Zalo để liên kết.')
            if linked:
                return {'linked': True}
            return self._redeem_code(identity)
        return self._serve(bind, require_link=False)

    @http.route(PREFIX + '/link-session', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def link_session(self):
        def bind(identity, employee):
            if identity is not None:
                raise ApiError(400, 'invalid_session', 'Cần phiên đăng nhập bằng mã 6 số.')
            zalo_id = self._verify_token(self._body().get('zalo_token'))
            request.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE', (employee.id,))
            employee.invalidate_recordset()
            if not employee.filtered_domain(employee._zalo_eligible() + self._session_domain(self._bearer())):
                raise ApiError(401, 'session_expired', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
            if employee.zalo_user_id and employee.zalo_user_id != zalo_id:
                raise ApiError(409, 'already_linked', 'Hồ sơ đã liên kết với một tài khoản Zalo khác.')
            try:
                with request.env.cr.savepoint():
                    employee.write({'zalo_user_id': zalo_id, 'zalo_session_digest': False, 'zalo_session_expires': False})
                    employee._log_zalo_event('zalo_linked', actor=False)
            except IntegrityError:
                raise ApiError(409, 'already_linked', 'Tài khoản Zalo này đã liên kết với hồ sơ khác.') from None
            return {'linked': True}
        return self._serve(bind)

    @http.route(PREFIX + '/login', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def login(self):
        if request.httprequest.method == 'OPTIONS':
            return preflight_response()
        try:
            self._ensure_enabled()
            return response(self._redeem_code())
        except ApiError as exc:
            return response({'error': exc.code, 'message': str(exc)}, exc.status)

    def _redeem_code(self, identity=None):
        payload = self._body()
        employee_code = payload.get('employee_code')
        code = payload.get('code')
        if (not isinstance(employee_code, str) or not 0 < len(employee_code.strip()) <= 128
                or not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code)):
            raise ApiError(400, 'invalid_code', 'Nhập mã nhân viên và đúng 6 chữ số.')
        employee_code = employee_code.strip()
        limits = request.env['hrm.zalo.attempt'].sudo()
        address = request.httprequest.remote_addr or 'unknown'
        bucket = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        counters = [('failed:ip:' + address, 25), ('failed:employee:' + employee_code.casefold(), 5)]
        if identity:
            counters.append(('failed:user:' + identity, 5))
        with request.env.cr.savepoint():
            if not all(limits._take(key, maximum, bucket) for key, maximum in counters):
                raise ApiError(429, 'rate_limited', 'Đã nhập sai mã nhiều lần. Vui lòng thử lại sau.')

        model = request.env['hr.employee'].sudo()
        domain = [('employee_code', '=', employee_code),
                  ('zalo_code_digest', '=', model._zalo_digest(code))] + model._zalo_eligible()
        if identity:
            domain.append(('zalo_user_id', '=', False))
        def valid_code_domain():
            return domain + ['|', ('zalo_code_expires', '=', False), ('zalo_code_expires', '>', fields.Datetime.now())]

        target = model.search(valid_code_domain(), limit=1)
        invalid = ApiError(400, 'invalid_code', 'Mã nhân viên hoặc mã 6 số không hợp lệ hoặc đã hết hạn.')
        if not target:
            raise invalid
        request.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE', (target.id,))
        target.invalidate_recordset()
        if not target.filtered_domain(valid_code_domain()):
            raise invalid

        values = {'zalo_code_digest': False, 'zalo_code_expires': False} if target.zalo_code_expires else {}
        result = {'linked': True}
        if identity:
            values['zalo_user_id'] = identity
            event = 'zalo_linked'
        else:
            token = 'hrm_' + secrets.token_urlsafe(32)
            values.update(zalo_session_digest=hashlib.sha256(token.encode()).hexdigest(),
                          zalo_session_expires=fields.Datetime.now() + timedelta(hours=8))
            result = {'session_token': token}
            event = 'zalo_code_login'
        try:
            with request.env.cr.savepoint():
                target.write(values)
                target._log_zalo_event(event, actor=False)
                limits._release([key for key, _maximum in counters], bucket)
        except IntegrityError:
            raise ApiError(409, 'already_linked', 'Tài khoản đã được liên kết.') from None
        return result

    @http.route(PREFIX + '/profile', type='http', auth='public', methods=['GET'], save_session=False)
    def profile(self):
        def read(identity, employee):
            return {'name': employee.name, 'employee_code': employee.employee_code,
                    'company': employee.hrm_company_id.name, 'department': employee.hrm_assignment_department.name or '',
                    'position': employee.hrm_assignment_position.title or employee.job_title or '',
                    'avatar': self._image_data(base64.b64decode(employee.image_128)) if employee.image_128 else None,
                    'projects': employee.hrm_assignment_projects.mapped('name')}
        return self._serve(read)

    @http.route(PREFIX + '/periods', type='http', auth='public', methods=['GET'], save_session=False)
    def periods(self):
        def read(identity, employee):
            periods = request.env['hrm.payroll.period'].sudo().search([
                ('company_id', '=', employee.hrm_company_id.id)], order='period_start desc, id desc', limit=36)
            today = datetime.now(ZoneInfo(employee.hrm_company_id.timezone or 'Asia/Ho_Chi_Minh')).date()
            current = periods.filtered(lambda p: p.period_start <= today <= p.period_end)[:1]
            return {'current_id': current.id or None,
                    'items': [{'id': p.id, 'label': f'{p.period_start:%m/%Y} · {p.period_code}'} for p in periods]}
        return self._serve(read)

    @http.route(PREFIX + '/periods/<int:period_id>', type='http', auth='public', methods=['GET'], save_session=False)
    def period_detail(self, period_id):
        def read(identity, employee):
            period = request.env['hrm.payroll.period'].sudo().search([
                ('id', '=', period_id), ('company_id', '=', employee.hrm_company_id.id)], limit=1)
            if not period:
                raise ApiError(404, 'not_found', 'Không tìm thấy kỳ.')
            rows = request.env['hrm.attendance.day'].sudo().search([
                ('period_id', '=', period.id), ('company_id', '=', employee.hrm_company_id.id),
                ('employee_id', '=', employee.id)], order='work_date, id')
            payslip = request.env['hrm.payslip'].sudo().search([
                ('employee_id', '=', employee.id), ('payroll_id.period_id', '=', period.id),
                ('payroll_id.company_id', '=', employee.hrm_company_id.id),
                ('payroll_id.status', 'in', ['finalized', 'paid'])], order='id desc', limit=1)
            salary = None
            if payslip:
                salary = {'gross': payslip.gross_amount, 'deductions': payslip.deduction_amount,
                          'tax': payslip.tax_amount, 'net': payslip.net_amount, 'currency': payslip.currency_code}
            return {'attendance': [{'date': str(row.work_date), 'symbol': row.attendance_symbol or '',
                                    'hours': row.hours, 'overtime': row.overtime_hours} for row in rows],
                    'salary': salary}
        return self._serve(read)

    @http.route(PREFIX + '/notices', type='http', auth='public', methods=['GET'], save_session=False)
    def notices(self):
        def read(identity, employee):
            notices = request.env['hrm.zalo.notice'].sudo().search([
                ('company_id', '=', employee.hrm_company_id.id), ('published_at', '!=', False)], limit=10)
            return {'items': [{'title': row.title, 'body': row.body, 'important': row.important,
                              'published_at': row.published_at.isoformat() + 'Z',
                              'image': self._image_data(row.image.content) if row.image else None} for row in notices]}
        return self._serve(read)

    def _image_data(self, data):
        mime = guess_mimetype(data)
        if mime in ('image/jpeg', 'image/png', 'image/webp'):
            return f'data:{mime};base64,{base64.b64encode(data).decode()}'
        return None

    def _leave_types(self, employee):
        return request.env['hrm.leave.type'].sudo().search([
            ('tenant_id', '=', employee.tenant_id.id), ('status', '=', 'active'),
            ('requires_attachment', '=', False), ('unit', '=', 'day'),
            ('code', 'not in', ['ZMP_' + kind.upper() for kind, _label in REQUEST_KINDS])])

    @http.route(PREFIX + '/leave', type='http', auth='public', methods=['GET'], save_session=False)
    def leave(self):
        def read(identity, employee):
            rows = request.env['hrm.leave.request'].sudo().search([
                ('employee_id', '=', employee.id), ('tenant_id', '=', employee.tenant_id.id)],
                order='create_date desc, id desc', limit=50)
            tz = ZoneInfo(employee.hrm_company_id.timezone or 'Asia/Ho_Chi_Minh')
            return {'types': [{'id': row.id, 'name': row.name} for row in self._leave_types(employee)],
                    'options': [{'kind': kind, 'label': label, 'minutes': DURATIONS.get(kind, ())}
                                for kind, label in REQUEST_KINDS],
                    'items': [{'type': dict(REQUEST_KINDS).get(row.miniapp_kind, row.leave_type_id.name),
                               'status': row.status, 'days': row.requested_quantity, 'minutes': row.miniapp_minutes,
                               'reason': row.reason or '',
                               'start': row.start_at.replace(tzinfo=timezone.utc).astimezone(tz).date().isoformat(),
                               'end': row.end_at.replace(tzinfo=timezone.utc).astimezone(tz).date().isoformat()} for row in rows]}
        return self._serve(read)

    @http.route(PREFIX + '/leave', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def leave_submit(self):
        def submit(identity, employee):
            data = self._body()
            kind = data.get('kind')
            minutes = data.get('minutes', 0)
            if (kind is not None and (not isinstance(kind, str) or kind not in dict(REQUEST_KINDS))
                    or type(minutes) is not int or minutes not in DURATIONS.get(kind, (0,))):
                raise ApiError(400, 'invalid_leave', 'Chọn loại yêu cầu và thời lượng hợp lệ.')
            try:
                first = date.fromisoformat(data['start'])
                last = date.fromisoformat(data['end']) if kind in (None, 'days') else first
                reason = data['reason'].strip()
                leave_type = self._leave_types(employee).filtered(lambda row: row.id == data['type_id']) if kind is None else None
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ApiError(400, 'invalid_leave', 'Điền loại nghỉ, ngày và lý do hợp lệ.') from None
            days = (last - first).days + 1
            tz = ZoneInfo(employee.hrm_company_id.timezone or 'Asia/Ho_Chi_Minh')
            if ((kind is None and not leave_type) or not 0 < days <= 31 or (kind == 'days' and days < 2)
                    or not 0 < len(reason) <= 1000 or first < datetime.now(tz).date()):
                raise ApiError(400, 'invalid_leave', 'Chọn loại nghỉ, ngày hiện tại trở đi và lý do hợp lệ.')
            start = datetime.combine(first, time.min, tz).astimezone(timezone.utc).replace(tzinfo=None)
            end = datetime.combine(last, time(23, 59, 59), tz).astimezone(timezone.utc).replace(tzinfo=None)
            request.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE', (employee.id,))
            employee.invalidate_recordset()
            domain = [('zalo_user_id', '=', identity)] if identity else self._session_domain(self._bearer())
            if not employee.filtered_domain(employee._zalo_eligible() + domain):
                raise ApiError(403, 'link_required', 'Liên kết không còn hiệu lực.')
            model = request.env['hrm.leave.request'].sudo()
            overlap = [('employee_id', '=', employee.id), ('start_at', '<=', end),
                       ('end_at', '>=', start), ('status', 'not in', ['cancelled', 'rejected'])]
            if kind in ('am', 'pm'):
                overlap.append(('miniapp_kind', 'in', [False, 'day', 'days', kind, 'late', 'early', 'outside']))
            elif kind in DURATIONS:
                blocked = [False, 'day', 'days', kind]
                if kind != 'ot':
                    blocked += ['am', 'pm']
                overlap.append(('miniapp_kind', 'in', blocked))
            if model.search_count(overlap, limit=1):
                raise ApiError(409, 'leave_overlap', 'Khoảng ngày trùng đơn nghỉ đã có.')
            try:
                with request.env.cr.savepoint():
                    if kind:
                        leave_type = request.env['hrm.leave.type'].sudo()._miniapp_type(employee.tenant_id, kind)
                    quantity = minutes / 60 if minutes else (0.5 if kind in ('am', 'pm') else days)
                    row = model.create({'employee_id': employee.id, 'tenant_id': employee.tenant_id.id,
                                        'leave_type_id': leave_type.id, 'start_at': start, 'end_at': end,
                                        'requested_quantity': quantity, 'reason': reason,
                                        'miniapp_kind': kind or False, 'miniapp_minutes': minutes})
                    row.action_submit()
                    employee._log_zalo_event('zalo_leave_submitted', actor=False, request_id=row.id)
            except UserError:
                raise ApiError(400, 'invalid_leave', 'Không thể gửi đơn nghỉ này.') from None
            return {'id': row.id, 'status': row.status}
        return self._serve(submit)
