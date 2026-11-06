import json
from datetime import date, timedelta
from unittest.mock import patch

from odoo import Command
from odoo.tests import HttpCase, tagged

from ..controllers import ZaloMiniApp


@tagged('post_install', '-at_install')
class TestMiniApp(HttpCase):
    def test_dashboard_company_and_month_categories(self):
        owner = self.env.ref('base.user_admin')
        owner.group_ids = [Command.link(self.env.ref('hrm_data_import.group_import_approver').id)]
        tenant = self.env['hrm.tenant'].with_user(owner).create(
            {'name': 'Dashboard Test', 'slug': 'dashboard-test', 'code': 'DASH-TEST'})
        company = self.env['hrm.company'].with_user(owner).create(
            {'name': 'Dashboard Test', 'code': 'DASH-TEST', 'tenant_id': tenant.id, 'currency_code': 'VND'})
        today = date(2026, 11, 6)
        employee = self.env['hr.employee'].create({
            'name': 'New employee', 'employee_code': 'DASH01', 'tenant_id': tenant.id,
            'hrm_company_id': company.id, 'current_status': 'active', 'hire_date': today,
            'hrm_birth_date': date(2000, 11, 20),
        })
        leave_type = self.env['hrm.leave.type'].create({
            'tenant_id': tenant.id, 'name': 'Maternity', 'code': 'MAT', 'dashboard_maternity': True,
        })
        self.env['hrm.leave.request'].create({
            'tenant_id': tenant.id, 'employee_id': employee.id, 'leave_type_id': leave_type.id,
            'start_at': '2026-11-05 08:00:00', 'end_at': '2026-11-07 08:00:00',
            'status': 'approved', 'requested_quantity': 3,
        })
        dashboard = self.env['hrm.zalo.dashboard'].with_user(owner).new({'company_id': company.id})
        with patch('odoo.fields.Date.context_today', return_value=today):
            data = json.loads(dashboard.dashboard_payload)
        self.assertEqual((data['working'], data['maternity'], data['new']), (0, 1, 1))
        self.assertEqual(data['birthdays'][0]['date'], '20/11')

    def test_link_profile_notice_and_leave(self):
        owner = self.env.ref('base.user_admin')
        owner.group_ids = [Command.link(self.env.ref('hrm_data_import.group_import_approver').id)]
        tenant = self.env['hrm.tenant'].with_user(owner).create(
            {'name': 'Zalo Test', 'slug': 'zalo-test', 'code': 'ZALO-TEST'})
        company = self.env['hrm.company'].with_user(owner).create(
            {'name': 'Zalo Test', 'code': 'ZALO-TEST', 'tenant_id': tenant.id, 'currency_code': 'VND'})
        other = self.env['hrm.company'].with_user(owner).create(
            {'name': 'Other Test', 'code': 'ZALO-OTHER', 'tenant_id': tenant.id, 'currency_code': 'VND'})
        employee = self.env['hr.employee'].create({'name': 'Zalo employee', 'employee_code': 'ZT01',
            'hrm_company_id': company.id, 'tenant_id': tenant.id, 'current_status': 'active'})
        wizard = self.env['hrm.zalo.code'].with_user(owner).create({'employee_id': employee.id, 'code': '012345'})
        wizard.action_issue()
        self.assertTrue(employee.zalo_code_digest)
        notices = self.env['hrm.zalo.notice']
        notices.create({'company_id': company.id, 'title': 'Published', 'body': 'Hello'}).action_publish()
        notices.create({'company_id': company.id, 'title': 'Draft', 'body': 'Private draft'})
        notices.create({'company_id': other.id, 'title': 'Other company', 'body': 'Private'}).action_publish()
        leave_type = self.env['hrm.leave.type'].create(
            {'tenant_id': tenant.id, 'name': 'Test leave', 'code': 'ZALO-TEST', 'allow_negative_balance': True})
        foreign_period = self.env['hrm.payroll.period'].create({'tenant_id': tenant.id, 'company_id': other.id,
            'period_code': 'OTHER', 'period_start': '2026-11-01', 'period_end': '2026-11-30'})

        def call(path, body=None, token='test'):
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            return self.url_open('/hrm/zalo/v1' + path, data=json.dumps(body) if body is not None else None,
                                 headers=headers)

        config = self.env['ir.config_parameter'].sudo()
        config.set_str('hrm_zalo.enabled', 'False')
        credentials = {'employee_code': 'ZT01', 'code': '012345'}
        self.assertEqual(call('/session').status_code, 503)
        self.assertEqual(call('/login', credentials, token=None).status_code, 503)
        config.set_str('hrm_zalo.enabled', 'True')
        with patch.object(ZaloMiniApp, '_verify', return_value='700123'):
            self.assertFalse(call('/session').json()['linked'])
            self.assertEqual(call('/profile').status_code, 403)
            self.assertEqual(call('/link', credentials).status_code, 200)
            self.assertTrue(call('/session').json()['linked'])
            self.assertEqual(call('/profile').json()['employee_code'], 'ZT01')
            self.assertIsNone(call('/profile').json()['avatar'])
            self.assertEqual(call(f'/periods/{foreign_period.id}').status_code, 404)
            self.assertEqual([row['title'] for row in call('/notices').json()['items']], ['Published'])
            day = (date.today() + timedelta(days=2)).isoformat()
            data = {'start': day, 'end': day, 'reason': 'Test', 'type_id': leave_type.id}
            submitted = call('/leave', data).json()
            self.assertEqual(submitted['status'], 'pending_approval')
            self.assertEqual(call('/leave', data).status_code, 409)
            dashboard = self.env['hrm.zalo.dashboard'].with_user(owner).create({'company_id': company.id})
            self.assertEqual(json.loads(dashboard.dashboard_payload)['pending_leave'][0]['id'], submitted['id'])
            pending_action = dashboard.action_pending_leave()
            self.assertEqual(pending_action['res_model'], 'hrm.leave.request')
            self.env['hrm.leave.request'].with_user(owner).browse(submitted['id']).action_approve()
            self.assertEqual(call('/leave').json()['items'][0]['status'], 'approved')
            self.assertEqual(call('/leave').json()['items'][0]['reason'], 'Test')
        with patch.object(ZaloMiniApp, '_verify', return_value='700124'):
            self.assertEqual(call('/link', credentials).status_code, 400)

        old_credentials = dict(credentials)
        credentials['code'] = '021234'
        self.env['hrm.zalo.code'].with_user(owner).create({
            'employee_id': employee.id, 'code': credentials['code'],
        }).action_issue()
        self.assertEqual(call('/login', old_credentials, token=None).status_code, 400)
        self.assertEqual(call('/login', dict(credentials, employee_code='OTHER'), token=None).status_code, 400)
        first_token = call('/login', credentials, token=None).json()['session_token']
        for _ in range(6):
            login = call('/login', credentials, token=None)
            self.assertEqual(login.status_code, 200)
        token = login.json()['session_token']
        self.assertNotEqual(first_token, token)
        self.assertEqual(call('/profile', token=first_token).status_code, 401)
        self.assertEqual(call('/profile', token=token).json()['employee_code'], 'ZT01')
        self.assertEqual(call(f'/periods/{foreign_period.id}', token=token).status_code, 404)
        next_day = (date.today() + timedelta(days=3)).isoformat()
        self.assertEqual(call('/leave', dict(data, start=next_day, end=next_day), token=token).status_code, 200)
        first = date.today() + timedelta(days=5)
        work_days = [first + timedelta(days=index) for index in range(5)]
        period = self.env['hrm.payroll.period'].create({
            'tenant_id': tenant.id, 'company_id': company.id, 'period_code': 'ZMP-CONG',
            'period_start': first, 'period_end': work_days[-1], 'hours_per_day': 8,
        })
        grid = self.env['hrm.attendance.month'].with_user(owner)
        self.assertTrue(grid.save_attendance_grid(period.id, [
            {'employee_id': employee.id, 'date': day.isoformat(), 'code': 'X', 'revision': 0}
            for day in (work_days[1], work_days[3])
        ])['ok'])
        self.assertEqual(len(call('/leave', token=token).json()['options']), 8)
        for day, kind, minutes in zip(work_days, ['day', 'am', 'ot', 'outside'], [0, 0, 120, 15]):
            reply = call('/leave', {'kind': kind, 'start': day.isoformat(), 'reason': 'Kiểm thử',
                                    'minutes': minutes}, token=token).json()
            self.assertEqual(reply['status'], 'pending_approval')
            self.env['hrm.leave.request'].with_user(owner).browse(reply['id']).action_approve()
        attendance = call(f'/periods/{period.id}', token=token).json()['attendance']
        self.assertEqual([(row['symbol'], row['hours'], row['overtime']) for row in attendance],
                         [('RO', 0, 0), ('1/2RO', 4, 0), ('W', 0, 2), ('X+RN', 7.75, 0)])
        delayed_day = work_days[-1].isoformat()
        reply = call('/leave', {'kind': 'pm', 'start': delayed_day, 'reason': 'Chưa có công',
                                'minutes': 0}, token=token).json()
        delayed = self.env['hrm.leave.request'].with_user(owner).browse(reply['id'])
        delayed.action_approve()
        self.assertEqual((delayed.status, delayed.miniapp_attendance_state), ('approved', 'waiting'))
        self.assertIn('ZT01', delayed.miniapp_attendance_message)
        self.assertTrue(grid.save_attendance_grid(period.id, [{
            'employee_id': employee.id, 'date': delayed_day, 'code': 'X', 'revision': 0,
        }])['ok'])
        delayed.action_apply_miniapp_attendance()
        self.assertEqual(delayed.miniapp_attendance_state, 'applied')
        self.assertFalse(delayed.action_apply_miniapp_attendance())
        self.assertEqual(call(f'/periods/{period.id}', token=token).json()['attendance'][-1]['hours'], 4)
        self.assertIn('leave_history_action', grid.load_attendance_grid(period.id))
        with patch.object(ZaloMiniApp, '_verify_token', return_value='700124'):
            self.assertEqual(call('/link-session', {'zalo_token': 'test'}, token=token).status_code, 409)
        employee.sudo().write({'zalo_user_id': False})
        with patch.object(ZaloMiniApp, '_verify_token', return_value='700123'):
            self.assertTrue(call('/link-session', {'zalo_token': 'test'}, token=token).json()['linked'])
            self.assertTrue(call('/session').json()['linked'])
            self.assertEqual(call('/profile').json()['employee_code'], 'ZT01')
        self.assertEqual(call('/profile', token=token).status_code, 401)
        employee.with_user(owner).action_zalo_unlink()
        self.assertEqual(call('/profile', token=token).status_code, 401)
