from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestCompanyIsolation(TransactionCase):
    def test_salary_export_and_adjustment_are_company_private(self):
        from odoo.exceptions import UserError
        workspace = self.env['hrm.monthly.workspace'].with_user(self.b).sudo().create(dict(
            company_id=self.cb.id, year=2026, month='10'))
        with self.assertRaises(AccessError): workspace.with_user(self.a)._salary_xlsx()
        with self.assertRaises(AccessError): workspace.with_user(self.a).action_export_salary()
        structure = self.env['hrm.salary.structure'].create(dict(tenant_id=self.tenant.id,
            company_id=self.cb.id, code='PRIVATE_SALARY', name='Private', currency_code='VND'))
        component = self.env['hrm.salary.component'].create(dict(tenant_id=self.tenant.id,
            structure_id=structure.id, code='BASE', name='Base', component_type='earning', calculation_type='fixed'))
        adjustment = self.env['hrm.salary.adjustment'].create(dict(company_id=self.cb.id,
            period_id=self.periods[1].id, employee_id=self.employees[1].id,
            component_id=component.id, amount=1234, reason='Private'))
        with self.assertRaises(AccessError): adjustment.with_user(self.a).read(['amount'])
        with self.assertRaises(AccessError): adjustment.with_user(self.a).action_approve()

    def test_timesheet_matrix_is_company_private(self):
        report = self.env['hrm.attendance.month']
        left = report.search([('company_id', '=', self.ca.id)])
        right = report.search([('company_id', '=', self.cb.id)])
        self.assertEqual(len(left), 1)
        self.assertEqual(len(right), 1)
        visible = report.with_user(self.a).search([('tenant_id', '=', self.tenant.id)])
        self.assertEqual(visible.ids, left.ids)
        with self.assertRaises(AccessError): right.with_user(self.a).read(['total_hours'])
        with self.assertRaises(AccessError): right.with_user(self.a).action_details()
        with self.assertRaises(AccessError): right.with_user(self.a).action_monthly_workspace()

    def test_monthly_dashboard_cannot_leak_another_company(self):
        screen = self.env['hrm.monthly.workspace'].with_user(self.b).sudo().create(dict(
            company_id=self.cb.id, year=2026, month='10'))
        screen.with_user(self.b).action_refresh()
        with self.assertRaises(AccessError): screen.with_user(self.a).action_refresh()
        with self.assertRaises(AccessError): screen.line_ids.with_user(self.a).action_inputs()
        with self.assertRaises(AccessError): screen.with_user(self.a).action_calculate()

    def test_new_employee_import_and_manual_input_are_private(self):
        from odoo.tools.binary import BinaryBytes
        record = self.env['hrm.employee.import'].with_user(self.b).sudo().create(dict(
            company_id=self.cb.id, filename='private.xlsx', file_data=BinaryBytes(b'private source')))
        with self.assertRaises(AccessError):
            record.with_user(self.a).read(['file_data', 'mapping_ids'])
        with self.assertRaises(AccessError):
            record.mapping_ids.with_user(self.a).read(['source', 'target'])
        row = self.env['hrm.manual.input'].with_user(self.b).sudo().create(dict(
            company_id=self.cb.id, period_id=self.periods[1].id, employee_id=self.employees[1].id,
            source_record_id='PRIVATE-DAY', approval_reference='Private', work_date='2026-10-01', regular_hours=8))
        with self.assertRaises(AccessError):
            row.with_user(self.a).action_publish()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref('hrm_base.group_hrm_admin')
        cls.accounts = cls.env['res.users'].with_context(no_reset_password=True).create([
            dict(name='Scope A', login='scope-a.test', group_ids=[(4, group.id)]),
            dict(name='Scope B', login='scope-b.test', group_ids=[(4, group.id)]),
        ])
        cls.a, cls.b = cls.accounts
        # Deliberately share the same tenant: tenant filtering alone is insufficient.
        cls.tenant = cls.env['hrm.tenant'].create(dict(code='COMPANY_SCOPE_TEST', name='Shared tenant', slug='company-scope-test'))
        cls.ca = cls.env['hrm.company'].with_user(cls.a).sudo().create(dict(tenant_id=cls.tenant.id, code='A', name='Company A', currency_code='VND'))
        cls.cb = cls.env['hrm.company'].with_user(cls.b).sudo().create(dict(tenant_id=cls.tenant.id, code='B', name='Company B', currency_code='VND'))
        cls.profiles = []
        cls.employees = []
        cls.periods = []
        for user, company in [(cls.a, cls.ca), (cls.b, cls.cb)]:
            cls.profiles.append(cls.env['hrm.import.profile'].with_user(user).sudo().create(dict(
                name=company.name, tenant_id=cls.tenant.id, company_id=company.id, dataset='performance', source='TEST')))
            cls.employees.append(cls.env['hr.employee'].with_user(user).sudo().create(dict(
                name='Employee '+company.code, tenant_id=cls.tenant.id, hrm_company_id=company.id, employee_code='SCOPE-'+company.code)))
            cls.periods.append(cls.env['hrm.payroll.period'].with_user(user).sudo().create(dict(
                tenant_id=cls.tenant.id, company_id=company.id, period_code='2026-10', period_start='2026-10-01', period_end='2026-10-31')))

    def test_hrm_admin_only_sees_own_company_in_same_tenant(self):
        self.assertTrue(self.a.has_group('hrm_base.group_hrm_admin'))
        visible = self.env['hrm.company'].with_user(self.a).search([('tenant_id', '=', self.tenant.id)])
        self.assertEqual(visible.ids, self.ca.ids)
        self.assertEqual(self.env['hrm.import.profile'].with_user(self.a).search([('tenant_id', '=', self.tenant.id), ('source', '=', 'TEST')]).ids, self.profiles[0].ids)
        self.assertEqual(self.env['hr.employee'].with_user(self.a).search([('tenant_id', '=', self.tenant.id)]).ids, self.employees[0].ids)
        self.assertEqual(self.env['hrm.payroll.period'].with_user(self.a).search([('tenant_id', '=', self.tenant.id)]).ids, self.periods[0].ids)

    def test_direct_read_write_and_download_foreign_records_rejected(self):
        for rec in [self.cb, self.profiles[1], self.employees[1], self.periods[1]]:
            with self.subTest(model=rec._name), self.assertRaises(AccessError):
                rec.with_user(self.a).read(['id'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.profiles[1].with_user(self.a).write({'name': 'Forbidden'})
        with self.assertRaises(AccessError):
            self.profiles[1].with_user(self.a).action_download_template()

    def test_cannot_create_profile_for_other_company(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['hrm.import.profile'].with_user(self.a).create(dict(
                name='Forbidden', tenant_id=self.tenant.id, company_id=self.cb.id, dataset='salary', source='BAD'))

    def test_cannot_forge_company_ownership_or_assign_scope(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['hrm.company'].with_user(self.a).create(dict(
                name='Forged', code='FORGED', tenant_id=self.tenant.id, create_uid=self.b.id))
        with self.assertRaises(AccessError): self.ca.with_user(self.a).write({'create_uid': self.b.id})
        with self.assertRaises(AccessError): self.a.write({'hrm_company_ids': [(4, self.cb.id)]})

    def test_audit_snapshot_does_not_leak_other_company(self):
        other = self.env['hrm.audit.log'].create(dict(tenant_id=self.tenant.id, company_id=self.cb.id,
            actor_user_id=self.b.id, action='IMPORT', entity_type='hrm.import.batch', metadata={'amount': 123}))
        with self.assertRaises(AccessError): other.with_user(self.a).read(['metadata'])

    def test_demo_workspace_and_original_file_are_company_scoped(self):
        from odoo.tools.binary import BinaryBytes
        workspace = self.env['hrm.demo.workspace'].create(dict(name='Company B workspace', company_id=self.cb.id))
        source = self.env['hrm.demo.source'].create(dict(workspace_id=workspace.id,
            filename='fixture.xlsx', file_data=BinaryBytes(b'fixture'), sha256='test', state='empty', record_count=0))
        with self.assertRaises(AccessError): workspace.with_user(self.a).action_employees()
        with self.assertRaises(AccessError): source.with_user(self.a).read(['file_data'])
        with self.assertRaises(AccessError): source.with_user(self.a).action_download()
        self.assertEqual(source.with_user(self.b).file_data.content, b'fixture')

    def test_demo_counts_include_departed_staff_without_fabricating_payroll(self):
        self.employees[0].write({'current_status': 'terminated', 'active': False})
        workspace = self.env['hrm.demo.workspace'].create(dict(name='Company A workspace', company_id=self.ca.id))
        visible = workspace.with_user(self.a)
        self.assertEqual(visible.employee_count, 1)
        self.assertEqual(visible.working_count, 0)
        self.assertEqual(visible.departed_count, 1)
