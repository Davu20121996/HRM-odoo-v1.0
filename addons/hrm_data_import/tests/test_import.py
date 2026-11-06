from odoo.tools.binary import BinaryBytes

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestImportWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.write({'group_ids': [(4, cls.env.ref('hrm_data_import.group_import_approver').id)]})
        cls.tenant = cls.env['hrm.tenant'].create(dict(code='IMPORT_TEST', name='Import test', slug='import-test', default_currency='VND'))
        cls.company = cls.env['hrm.company'].create(dict(tenant_id=cls.tenant.id, code='C', name='C', currency_code='VND'))
        cls.department = cls.env['hrm.department'].create(dict(tenant_id=cls.tenant.id, company_id=cls.company.id, code='D', name='D'))
        cls.employee = cls.env['hr.employee'].create(dict(name='Import test', tenant_id=cls.tenant.id, employee_code='0001', current_status='active'))
        cls.env['hrm.employee.assignment'].create(dict(tenant_id=cls.tenant.id, company_id=cls.company.id,
            department_id=cls.department.id, employee_id=cls.employee.id, start_date='2026-01-01'))
        cls.period = cls.env['hrm.payroll.period'].create(dict(tenant_id=cls.tenant.id, company_id=cls.company.id,
            period_code='2026-10', period_start='2026-10-01', period_end='2026-10-31'))
        cls.profile = cls.env['hrm.import.profile'].create(dict(name='Daily CSV', tenant_id=cls.tenant.id,
            company_id=cls.company.id, dataset='attendance', source='clock', locale='en',
            headers=['employee', 'source', 'revision', 'approval', 'date', 'hours'], mapping_ids=[
                (0, 0, dict(column=i, target=target, data_type=kind, required=True))
                for i, target, kind in [(1, 'employee_code', 'text'), (2, 'source_record_id', 'text'),
                    (3, 'revision', 'number'), (4, 'approval_reference', 'text'),
                    (5, 'work_date', 'date'), (6, 'regular_hours', 'number')]]))
        cls.profile.action_approve()

    def batch(self, rows):
        return self.env['hrm.import.batch'].create(dict(profile_id=self.profile.id, period_id=self.period.id,
            filename='test.csv', file_data=BinaryBytes(('employee,source,revision,approval,date,hours\n'+rows).encode())))

    def test_idempotency_replacement_and_zero(self):
        first = self.batch('0001,A,1,OK,2026-10-01,8\n')
        first.action_preview()
        self.assertEqual(first.state, 'ready')
        first.action_commit()
        self.assertEqual(first.state, 'committed', first.message)
        duplicate = self.batch('0001,A,1,OK,2026-10-01,8\n')
        duplicate.action_preview()
        self.assertEqual(duplicate.line_ids.result, 'unchanged')
        duplicate.action_commit()
        replacement = self.batch('0001,A,2,OK,2026-10-01,0\n')
        replacement.action_preview()
        self.assertEqual(replacement.line_ids.result, 'update')
        replacement.action_commit()
        data = self.env['hrm.import.input'].search([('period_id', '=', self.period.id)])
        self.assertEqual(len(data), 1)
        self.assertEqual(data.payload['regular_hours'], '0')
        self.assertEqual(first.line_ids.normalized['regular_hours'], '8')

    def test_preview_conflict_rolls_back_prior_rows(self):
        first = self.batch('0001,A,1,OK,2026-10-01,8\n')
        first.action_preview()
        first.action_commit()
        pending = self.batch('0001,B,1,OK,2026-10-02,4\n0001,A,2,OK,2026-10-01,4\n')
        pending.action_preview()
        concurrent = self.batch('0001,A,2,OK,2026-10-01,6\n')
        concurrent.action_preview()
        concurrent.action_commit()
        self.assertEqual(concurrent.state, 'committed', concurrent.message)
        pending.action_commit()
        self.assertEqual(pending.state, 'failed')
        self.assertIn('PREVIEW_CONFLICT', pending.message)
        self.assertFalse(self.env['hrm.import.input'].search([('period_id', '=', self.period.id), ('source_record_id', '=', 'B')]))

    def test_reject_duplicate_missing_employee_and_locked_period(self):
        batch = self.batch('0001,A,1,OK,2026-10-01,8\n0001,A,1,OK,2026-10-01,8\n9999,B,1,OK,2026-10-01,8\n')
        batch.action_preview()
        self.assertEqual(batch.state, 'failed')
        self.assertEqual(len(batch.line_ids.filtered(lambda r: r.result == 'reject')), 2)
        self.period.write({'status': 'finalized'})
        with self.assertRaises(UserError): batch.action_preview()

    def test_approved_mapping_is_immutable(self):
        with self.assertRaises(UserError): self.profile.write({'name': 'changed'})
        with self.assertRaises(UserError): self.profile.mapping_ids[0].write({'column': 2})
        with self.assertRaises(UserError): self.profile.mapping_ids[0].unlink()

    def test_cannot_forge_batch_state(self):
        with self.assertRaises(UserError):
            self.env['hrm.import.batch'].create(dict(profile_id=self.profile.id, period_id=self.period.id,
                filename='forged.csv', file_data=BinaryBytes(b'x'), state='ready'))

    def test_wide_performance_template_and_import(self):
        import io
        from openpyxl import load_workbook
        structure = self.env['hrm.salary.structure'].create(dict(tenant_id=self.tenant.id,
            company_id=self.company.id, code='WIDE', name='Wide test', currency_code='VND'))
        components = [self.env['hrm.salary.component'].create(dict(tenant_id=self.tenant.id,
            structure_id=structure.id, code=code, name=code, component_type='earning', calculation_type='fixed')) for code in ['KPI', 'SALES']]
        headers = ['employee', 'source', 'revision', 'approval', 'KPI', 'SALES']
        profile = self.env['hrm.import.profile'].create(dict(name='Wide performance', tenant_id=self.tenant.id,
            company_id=self.company.id, dataset='performance', source='perf-wide', locale='en',
            amount_columns=True, headers=headers, mapping_ids=[
                (0, 0, dict(column=i, target=target, data_type='number' if target == 'revision' else 'text'))
                for i, target in enumerate(['employee_code', 'source_record_id', 'revision', 'approval_reference'], 1)] + [
                (0, 0, dict(column=i, target='amount', data_type='number', required=False, component_id=comp.id))
                for i, comp in enumerate(components, 5)]))
        profile.action_approve()
        template = load_workbook(io.BytesIO(profile.template_data.content))
        self.assertEqual([c.value for c in template.worksheets[0][1]], headers)
        self.assertIn('HuongDan', template.sheetnames)
        template.close()
        batch = self.env['hrm.import.batch'].create(dict(profile_id=profile.id, period_id=self.period.id,
            filename='wide.csv', file_data=BinaryBytes(b'employee,source,revision,approval,KPI,SALES\n0001,P1,1,OK,1600000,0\n')))
        batch.action_preview()
        self.assertEqual(batch.state, 'ready', batch.message)
        self.assertEqual(len(batch.line_ids), 2)
        batch.action_commit()
        self.assertEqual(batch.state, 'committed', batch.message)
        inputs = self.env['hrm.import.input'].search([('batch_id', '=', batch.id)])
        self.assertEqual(set(inputs.mapped('source_record_id')), {'P1:KPI', 'P1:SALES'})
        self.assertEqual(inputs.filtered(lambda r: r.payload['component_code'] == 'SALES').payload['amount'], '0')
        base = components[0].copy({'code': 'BASE'})
        unsafe = profile.copy()
        unsafe.mapping_ids.filtered(lambda line: line.component_id == components[0]).component_id = base
        with self.assertRaises(UserError):
            unsafe.action_approve()
        legacy_batch = self.batch('0001,A,1,OK,2026-10-01,8\n')
        legacy_batch.profile_id = self.profile.copy({'dataset': 'salary'})
        with self.assertRaises(UserError):
            legacy_batch.action_preview()
