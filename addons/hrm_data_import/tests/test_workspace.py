import io
from datetime import datetime
from openpyxl import Workbook, load_workbook
from odoo import fields
from odoo.tools.binary import BinaryBytes
from odoo.exceptions import UserError, AccessError
from .test_import import TestImportWorkflow


class TestWorkspace(TestImportWorkflow):
    def test_employee_assignment_popup_requires_reason_and_tracks_changes(self):
        wizard_model = self.env['hrm.employee.assignment.wizard']
        unassigned = self.env['hr.employee'].create({'name': 'Chưa phân công', 'tenant_id': self.tenant.id,
                                                   'hrm_company_id': self.company.id, 'employee_code': 'NEW-ASSIGN'})
        initial = wizard_model.browse(unassigned.action_assignment_popup()['res_id'])
        self.assertFalse(initial.department_id)
        with self.assertRaises(UserError):
            initial.action_apply()
        initial.write({'department_id': self.department.id, 'new_position': True, 'position_title': 'Hỗ trợ'})
        unassigned.write({'current_status': 'terminated', 'termination_date': '2026-10-01', 'active': False})
        with self.assertRaises(UserError):
            initial.action_apply()
        with self.assertRaises(UserError):
            unassigned.action_assignment_popup()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env['hrm.employee.assignment'].create({
                'employee_id': unassigned.id, 'tenant_id': self.tenant.id, 'company_id': self.company.id,
                'department_id': self.department.id, 'start_date': '2026-01-01',
            })
        unassigned.action_reactivate_employee()
        self.assertTrue(unassigned.active)
        self.assertEqual(unassigned.current_status, 'active')
        self.assertFalse(unassigned.termination_date)
        initial.action_apply()
        self.assertEqual(unassigned.current_assignment_id.position_id.title, 'Hỗ trợ')
        project = self.env['hrm.employee.project'].create({'name': 'Dự án A', 'company_id': self.company.id})
        action = self.employee.action_assignment_popup()
        self.assertEqual(action['target'], 'new')
        wizard = wizard_model.browse(action['res_id'])
        wizard.write({'new_position': True, 'position_title': 'Điều phối', 'project_ids': [(6, 0, project.ids)]})
        with self.assertRaises(UserError):
            wizard.action_apply()
        wizard.reason = 'Sửa thiếu chức vụ và dự án'
        wizard.action_apply()
        assignment = self.employee.current_assignment_id
        self.assertEqual(assignment.department_id, self.department)
        self.assertEqual(assignment.position_id.title, 'Điều phối')
        self.assertEqual(assignment.project_ids, project)
        log = self.employee.hrm_assignment_log_ids
        self.assertEqual((log.actor_id, log.previous_actor_id), (self.env.user, assignment.create_uid))
        self.assertEqual(log.reason, wizard.reason)
        self.assertIn('Dự án A', log.after)
        self.assertNotIn('Dự án A', log.before)
        row = self.env['hrm.attendance.month'].load_attendance_grid(self.period.id)['rows']
        row = next(entry for entry in row if entry['id'] == self.employee.id)
        self.assertEqual((row['department'], row['projects']), (self.department.name, project.name))

    def test_attendance_grid_revisions_and_import_conflict(self):
        grid = self.env['hrm.attendance.month']
        change = {'employee_id': self.employee.id, 'date': '2026-10-02', 'revision': 0, 'code': 'X+TC2'}
        result = grid.save_attendance_grid(self.period.id, [change])
        self.assertTrue(result['ok'], result)
        symbols = grid.update_grid_symbol(self.period.id, 'add', 'ca6', 6, 0)
        self.assertEqual(symbols['CA6'], (6, 0))
        config = self.env['hrm.attendance.symbol'].search([('company_id', '=', self.company.id), ('code', '=', 'CA6')])
        self.assertEqual(config.regular_hours, 6)
        self.assertEqual(grid.update_grid_symbol(self.period.id, 'edit', 'CA6', 5, 1)['CA6'], (5, 1))
        self.assertNotIn('CA6', grid.update_grid_symbol(self.period.id, 'delete', 'CA6'))
        self.assertNotIn('X+TC2', grid.update_grid_symbol(self.period.id, 'delete', 'X+TC2'))
        cell = grid.load_attendance_grid(self.period.id)['rows'][0]['cells'][change['date']]
        self.assertEqual((cell['regular'], cell['overtime'], cell['revision']), (8, 2, 1))
        with self.assertRaises(UserError):
            grid.save_attendance_grid(self.period.id, [change])
        import_batch = self.batch('0001,A,1,OK,2026-10-02,8\n')
        import_batch.action_preview()
        self.assertEqual(import_batch.state, 'failed')
        result = grid.save_attendance_grid(self.period.id, [dict(change, revision=1, code='X4')])
        self.assertTrue(result['ok'], result)
        cell = grid.load_attendance_grid(self.period.id)['rows'][0]['cells'][change['date']]
        self.assertEqual((cell['regular'], cell['overtime'], cell['revision']), (4, 0, 2))
        grid.set_grid_lock(self.period.id, True)
        self.assertEqual(grid.load_attendance_grid(self.period.id)['lock_mode'], 'manual')
        with self.assertRaises(UserError):
            grid.save_attendance_grid(self.period.id, [dict(change, revision=2)])
        with self.assertRaises(UserError):
            self.batch('0001,B,1,OK,2026-10-03,8\n').action_preview()
        grid.set_grid_lock(self.period.id, False)
        self.assertEqual(grid.load_attendance_grid(self.period.id)['lock_mode'], 'open')
        self.period.write({'status': 'finalized'})
        with self.assertRaises(UserError):
            grid.save_attendance_grid(self.period.id, [dict(change, revision=2)])
        with self.assertRaises(UserError):
            grid.set_grid_lock(self.period.id, False, 'Sửa công')

    def test_contract_allowance_tax_and_addendum(self):
        company = self.company
        structure = self.env['hrm.salary.structure'].create(dict(tenant_id=self.tenant.id,
            company_id=company.id, code='ALLOWANCE', name='Allowance test', currency_code='VND', effective_from='2026-01-01'))
        components = self.env['hrm.salary.component']
        components.create(dict(tenant_id=self.tenant.id, structure_id=structure.id, code='BASE', name='Base',
            component_type='earning', calculation_type='formula', configuration={'expression': 'base_salary'}, sequence_no=10))
        tax = components.create(dict(tenant_id=self.tenant.id, structure_id=structure.id, code='TEST_TAX', name='Test tax',
            component_type='tax', calculation_type='fixed', sequence_no=5))
        policy = self.env['hrm.payroll.formula'].create(dict(tenant_id=self.tenant.id, component_id=tax.id,
            effective_from='2026-01-01', expression='MIN(TAXABLE_ALLOWANCES, TAXABLE_GROSS - BASE_SALARY) * 0.1',
            test_context={'TAXABLE_ALLOWANCES': 270000, 'TAXABLE_GROSS': 5580000, 'BASE_SALARY': 5310000}))
        policy.action_approve()
        meal = self.env['hrm.allowance.type'].create(dict(name='Meal', code='MEAL', company_id=company.id,
            tax_mode='capped', exempt_limit=730000))
        self.assertEqual(meal._split(730000), (730000, 0))
        kind = self.env['hrm.contract.type'].create(dict(code='ALLOWANCE', name='Allowance test', employment_category='indefinite'))
        values = dict(tenant_id=self.tenant.id, company_id=company.id, employee_id=self.employee.id,
            contract_type_id=kind.id, base_salary=5310000, currency_code='VND', structure_id=structure.id)
        contract = self.env['hrm.employee.contract'].create(dict(values, contract_no='ALLOWANCE-01',
            start_date='2026-01-01', allowance_ids=[(0, 0, {'type_id': meal.id, 'amount': 730000})]))
        appendix = self.env['hrm.employee.contract'].create(dict(values, contract_no='ALLOWANCE-01-A', parent_id=contract.id,
            start_date='2026-10-01', allowance_ids=[(0, 0, {'type_id': meal.id, 'amount': 1000000})]))
        action = self.employee.action_new_employee_contract()
        self.assertEqual(action['target'], 'new')
        self.assertNotIn('res_id', action)
        defaults = self.env['hrm.employee.contract'].with_context(action['context']).default_get([
            'contract_no', 'start_date', 'employee_id', 'parent_id', 'status', 'base_salary', 'allowance_ids', 'signed_document',
        ])
        self.assertEqual(defaults['employee_id'], self.employee.id)
        self.assertEqual(defaults['status'], 'draft')
        self.assertFalse(defaults['parent_id'])
        self.assertFalse(defaults.get('contract_no'))
        self.assertFalse(defaults.get('signed_document'))
        self.assertEqual(defaults['allowance_ids'][0][2]['amount'], 730000)
        renewal_action = contract.action_renew_from_contract()
        renewal_model = self.env['hrm.employee.contract'].with_context(renewal_action['context'])
        renewal = renewal_model.create({'contract_no': 'ALLOWANCE-RENEW', 'start_date': '2027-01-01'})
        self.assertEqual(renewal.parent_id, contract)
        self.assertEqual(renewal.entry_type, 'renewal')
        self.assertEqual(renewal.status, 'draft')
        self.assertEqual(renewal.allowance_ids.amount, 730000)
        self.assertIn(renewal, self.employee.hrm_pending_contract_ids)
        self.assertNotIn(renewal, self.employee.hrm_active_contract_ids)
        for record in (contract, appendix):
            record.action_submit()
            record.action_approve()
            record.action_activate()
        self.assertIn(appendix, self.employee.hrm_active_contract_ids)
        self.assertNotIn(appendix, self.employee.hrm_pending_contract_ids)
        self.assertEqual(self.employee.hrm_active_contract_ids, appendix)
        self.assertIn(contract, self.employee.hrm_closed_contract_ids)
        self.assertEqual(self.employee.current_contract_id, appendix)
        with self.assertRaises(UserError):
            contract.allowance_ids.write({'amount': 2000000})
        self.period.write({'require_imported_attendance': False, 'require_imported_performance': False,
                           'selected_employee_ids': [(6, 0, self.employee.ids)]})
        action = self.period.action_quick_payroll()
        item = self.env['hrm.payroll'].browse(action['res_id']).item_ids
        allowance = item.detail_ids.filtered('contract_allowance')
        self.assertEqual((allowance.amount, allowance.tax_exempt_amount, allowance.taxable_amount), (1000000, 730000, 270000))
        self.assertEqual((item.gross_amount, item.tax_amount, item.net_amount), (6310000, 27000, 5725450))
        values = item._excel_values()
        self.assertEqual([values[column] for column in ('H', 'AG', 'AK', 'AL', 'AM')],
                         [1000000, 730000, 5580000, 27000, 5725450])
        workspace = self.env['hrm.monthly.workspace'].create(dict(company_id=company.id, year=2026, month='10'))
        sheet = load_workbook(io.BytesIO(workspace._salary_xlsx()), data_only=True)['Luong']
        self.assertEqual(sheet.max_column, 52)
        self.assertEqual([sheet[cell].value for cell in ('O11', 'P11', 'AG11', 'AH11')],
                         ['THỬ VIỆC', 'HĐLĐ', 'ĂN TRƯA', 'HỖ TRỢ ĐIỆN THOẠI'])
        self.assertIsNone(sheet['O12'].value)
        self.assertEqual([sheet[f'{column}12'].value for column in ('H', 'AG', 'AK', 'AL', 'AM')],
                         [1000000, 730000, 5580000, 27000, 5725450])
        unused = self.env['hrm.allowance.type'].create(dict(name='Đi lại', company_id=company.id))
        self.assertRegex(unused.code, r'^PC_DI_LAI_[A-F0-9]{8}$')
        history = self.env['hrm.allowance.version']
        history.create(dict(type_id=unused.id, effective_from='2026-01-01', reason='Initial history'))
        with self.assertRaises(UserError):
            history.create(dict(type_id=meal.id, effective_from='2026-01-01', reason='Would change existing payroll'))
        version = self.env['hrm.allowance.version'].create(dict(type_id=meal.id, effective_from='2027-01-01',
            tax_mode='capped', exempt_limit=500000, reason='New year'))
        self.assertEqual(meal._split(1000000, fields.Date.to_date('2026-10-01')), (730000, 270000))
        self.assertEqual(meal._split(1000000, fields.Date.to_date('2027-01-01')), (500000, 500000))
        with self.assertRaises(UserError):
            version.write({'exempt_limit': 400000})
        with self.assertRaises(UserError):
            meal.write({'exempt_limit': 400000})
        self.assertEqual(allowance.tax_exempt_amount, 730000)

    def test_vietnamese_and_english_ui_labels(self):
        for lang, company, employee in [('vi_VN', 'Công ty', 'Nhân viên'), ('en_US', 'Company', 'Employee')]:
            info = self.env['hrm.manual.input'].with_context(lang=lang).fields_get(['company_id', 'employee_id'])
            self.assertEqual(info['company_id']['string'], company)
            self.assertEqual(info['employee_id']['string'], employee)
        source_keys = dict(self.env['hrm.manual.input']._fields['dataset'].selection)
        self.assertEqual(set(source_keys), {'attendance', 'performance', 'salary'})
        screen = self.env['hrm.monthly.workspace'].create(dict(company_id=self.company.id, year=2026, month='10'))
        self.assertEqual(screen.with_context(lang='en_US').display_name, 'Monthly attendance and payroll')
        self.assertEqual(screen.with_context(lang='vi_VN').display_name, 'Công và lương theo tháng')
        screen.with_context(lang='en_US').action_refresh()
        self.assertIn('Month 10/2026', screen.notice)
        screen.with_context(lang='vi_VN').action_refresh()
        self.assertIn('Tháng 10/2026', screen.notice)

    def test_timesheet_matrix_history_and_revision_are_live(self):
        reports = self.env['hrm.attendance.month']
        scope = [('company_id', '=', self.company.id), ('employee_id', '=', self.employee.id)]
        october = reports.search(scope + [('month', '=', '10')])
        self.assertEqual(len(october), 1)
        self.assertEqual(october.source_count, 0)
        original_id = october.id
        batch = self.batch('0001,A,1,OK,2026-10-01,8\n0001,B,1,OK,2026-10-02,0\n')
        batch.action_preview(); batch.action_commit()
        october.invalidate_recordset()
        self.assertEqual(october.id, original_id)
        self.assertEqual(october.total_hours, 8)
        self.assertEqual(october.d01, '8')
        self.assertEqual(october.d02, '0')
        self.assertFalse(october.d03)
        self.assertEqual(october.recorded_days, 2)
        september = self.env['hrm.payroll.period'].create(dict(tenant_id=self.tenant.id,
            company_id=self.company.id, period_code='2026-09', period_start='2026-09-01', period_end='2026-09-30'))
        older = self.batch('0001,A,1,OK,2026-09-01,4\n')
        older.period_id = september
        older.action_preview(); older.action_commit()
        past = reports.search(scope + [('month', '=', '9')])
        self.assertEqual(past.total_hours, 4)
        self.assertEqual(past.d31, '—')
        correction = self.batch('0001,A,2,OK,2026-10-01,6\n')
        correction.action_preview(); correction.action_commit()
        october.invalidate_recordset()
        self.assertEqual(october.total_hours, 6)
        self.assertEqual(october.source_count, 2)
        self.assertEqual(len(reports.search(scope)), 2)
        details = self.env['hrm.attendance.day'].search([('employee_id', '=', self.employee.id), ('period_id', '=', self.period.id)])
        self.assertEqual(len(details), 2)
        self.assertEqual(sum(details.mapped('hours')), 6)
        self.assertEqual(october.action_details()['res_model'], 'hrm.attendance.day')

    def test_month_year_workspace_and_employee_scope(self):
        action = self.employee.action_monthly_overview()
        own = self.env['hrm.monthly.workspace'].browse(action['res_id'])
        self.assertEqual(own.employee_id, self.employee)
        self.assertEqual(own.period_id, self.period)
        view = self.env['hrm.monthly.workspace'].create(dict(company_id=self.company.id, year=2026, month='10'))
        view.action_refresh()
        self.assertEqual(view.period_id, self.period)
        self.assertEqual(view.line_ids.employee_id, self.employee)
        batch = self.batch('0001,A,1,OK,2026-10-01,8\n')
        batch.action_preview()
        batch.action_commit()
        view.action_refresh()
        self.assertEqual(view.line_ids.hours, 8)
        view.employee_id = self.employee
        view.action_all_employees()
        self.assertFalse(view.employee_id)
        self.assertEqual(view.line_ids.hours, 8)
        view.write({'month': '9'})
        self.assertFalse(view.line_ids)
        view.action_refresh()
        self.assertFalse(view.period_id)
        self.assertEqual(view.line_ids.hours, 0)
        with self.assertRaises(UserError): view.action_calculate()

    def employee_file(self, rows):
        book = Workbook()
        sheet = book.active
        sheet.title = 'VP'
        sheet.append(['code', 'full_name', 'working_status_id', 'birthday', 'email'])
        for row in rows: sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return self.env['hrm.employee.import'].create(dict(company_id=self.company.id,
            filename='employee.xlsx', file_data=BinaryBytes(buffer.getvalue())))

    def test_employee_import_preview_update_and_reject(self):
        batch = self.employee_file([['NEW01', 'Nhân viên nguồn', 'Đang làm việc', datetime(1995, 2, 3), 'test@example.test']])
        batch.action_preview()
        self.assertFalse(self.env['hr.employee'].search([('employee_code', '=', 'NEW01')]))
        batch.action_import()
        employee = self.env['hr.employee'].search([('employee_code', '=', 'NEW01')])
        self.assertEqual(str(employee.hrm_birth_date), '1995-02-03')
        self.assertEqual(employee.hrm_company_id, self.company)
        with self.assertRaises(UserError): batch.action_import()
        update = self.employee_file([['NEW01', 'Tên cập nhật', 'Đang làm việc', None, None]])
        update.update_existing = True
        update.action_import()
        self.assertEqual(employee.name, 'Tên cập nhật')
        self.assertEqual(employee.work_email, 'test@example.test')
        invalid = self.employee_file([['BAD', '=1+1', 'Đang làm việc']])
        with self.assertRaises(UserError): invalid.action_import()

    def test_monthly_readiness_and_reopen_lock(self):
        self.period.action_check_ready()
        self.assertIn('hợp đồng', self.period.readiness)
        self.period.action_quick_payroll()
        self.assertFalse(self.env['hrm.payroll'].search([('period_id', '=', self.period.id)]))
        self.period.write({'status': 'calculated'})
        with self.assertRaises(UserError): self.period.action_reopen_inputs()
        self.period.correction_reason = 'Sửa nguồn công theo xác nhận'
        self.period.action_reopen_inputs()
        self.assertEqual(self.period.status, 'processing')
        self.period.status = 'approved'
        with self.assertRaises(UserError): self.period.action_reopen_inputs()

    def test_contract_salary_selection_manual_input_recalculation(self):
        structure = self.env['hrm.salary.structure'].create(dict(tenant_id=self.tenant.id,
            company_id=self.company.id, code='FLOW', name='Flow', currency_code='VND', effective_from='2026-01-01'))
        component = self.env['hrm.salary.component'].create(dict(tenant_id=self.tenant.id,
            structure_id=structure.id, code='BASE', name='Base', component_type='earning',
            calculation_type='formula', configuration={'expression': 'base_salary'}))
        policy = self.env['hrm.payroll.formula'].create(dict(tenant_id=self.tenant.id,
            component_id=component.id, effective_from='2026-01-01', expression='BASE_SALARY',
            test_context={'BASE_SALARY': 1000}))
        policy.action_approve()
        kind = self.env['hrm.contract.type'].create(dict(code='FLOW-TEST', name='Test', employment_category='indefinite'))
        contract = self.env['hrm.employee.contract'].create(dict(tenant_id=self.tenant.id,
            company_id=self.company.id, employee_id=self.employee.id, contract_type_id=kind.id,
            contract_no='FLOW-01', start_date='2026-01-01', base_salary=1000, currency_code='VND',
            structure_id=structure.id))
        contract.action_submit()
        contract.action_approve()
        self.assertIn(contract, self.employee.hrm_pending_contract_ids)
        self.assertNotIn(contract, self.employee.hrm_active_contract_ids)
        self.assertEqual(contract.with_context(refresh_employee_contract_groups=True).action_activate(),
                         {'type': 'ir.actions.client', 'tag': 'reload'})
        self.assertIn(contract, self.employee.hrm_active_contract_ids)
        self.assertNotIn(contract, self.employee.hrm_pending_contract_ids)
        with self.assertRaises(UserError): contract.write({'base_salary': 2000})
        entry = self.env['hrm.manual.input'].create(dict(company_id=self.company.id,
            period_id=self.period.id, employee_id=self.employee.id, dataset='attendance',
            work_date='2026-10-01', regular_hours=8, source_record_id='DAY01', revision=1,
            approval_reference='Test source'))
        entry.action_publish()
        self.assertEqual(entry.batch_id.state, 'committed', entry.batch_id.message)
        self.period.write({'require_imported_attendance': True, 'require_imported_performance': False,
            'selected_employee_ids': [(6, 0, self.employee.ids)]})
        action = self.period.action_quick_payroll()
        run = self.env['hrm.payroll'].browse(action['res_id'])
        self.assertEqual(run.status, 'calculated')
        self.assertEqual(run.item_ids.net_amount, 895)
        grid = self.env['hrm.attendance.month']
        with self.assertRaises(UserError):
            grid.set_grid_lock(self.period.id, False)
        with self.assertRaises(UserError):
            grid.set_grid_lock(self.period.id, False, 'Đối chiếu lại công')
        salary_grid = self.env['hrm.payroll.period']
        salary_grid.update_salary_grid(self.period.id, 'unlock', reason='Đối chiếu lại công')
        self.assertFalse(run.item_ids)
        self.period.action_quick_payroll()
        self.assertEqual(run.calculation_version, 2)
        self.assertEqual(len(run.item_ids.detail_ids), 4)
        view = self.env['hrm.monthly.workspace'].create(dict(company_id=self.company.id, year=2026, month='10'))
        item = run.item_ids
        self.assertEqual(item.salary_year, '2026')
        self.assertEqual(item.salary_month, '10')
        self.assertEqual(item._excel_values()['G'], 1000)
        self.assertEqual(item._excel_values()['E'], self.department.name)
        self.assertEqual(item._excel_values()['AM'], 895)
        self.assertEqual(item._excel_values()['AF'], 105)
        self.assertEqual(item._excel_values()['AO'], 170)
        exported = load_workbook(io.BytesIO(view._salary_xlsx()), data_only=False)
        sheet = exported['Luong']
        self.assertEqual(sheet.max_column, 52)
        self.assertEqual(sheet['A12'].value, self.employee.employee_code)
        self.assertEqual(sheet['G12'].value, 1000)
        self.assertEqual(sheet['AM12'].value, 895)
        self.assertEqual(sheet['AO12'].value, 170)
        download_action = view.action_export_salary()
        self.assertEqual(download_action['type'], 'ir.actions.act_url')
        self.assertIn('download=true', download_action['url'])
        self.assertEqual(load_workbook(io.BytesIO(view.salary_export.content))['Luong']['AM12'].value, 895)
        adjustment = self.env['hrm.salary.adjustment'].create(dict(company_id=self.company.id,
            period_id=self.period.id, employee_id=self.employee.id, component_id=component.id,
            amount=1200, reason='Xác nhận sửa lương tháng'))
        with self.assertRaises(UserError): adjustment.action_approve()
        self.period.correction_reason = 'Điều chỉnh có căn cứ'
        self.period.action_reopen_inputs()
        adjustment.action_approve()
        with self.assertRaises(UserError): adjustment.write({'amount': 9000})
        with self.assertRaises(UserError): adjustment.unlink()
        self.period.action_quick_payroll()
        self.assertEqual(run.item_ids.net_amount, 1095)
        self.assertEqual(run.item_ids._excel_values()['V'], 1200)
        self.assertEqual(run.item_ids._excel_values()['AM'], 1095)
        self.assertEqual(sum(run.item_ids.detail_ids.mapped('amount')), 1305)
        sheet = load_workbook(io.BytesIO(view._salary_xlsx()), data_only=True)['Luong']
        self.assertEqual(sheet['AM12'].value, 1095)
        self.assertEqual(run.item_ids.with_context(lang='en_US').insurance_state, 'Insurance calculated')
        salary_grid.update_salary_grid(self.period.id, 'unlock', reason='Kiểm tra bảng nhập lương')
        change = {'employee_id': self.employee.id, 'component_id': component.id,
                  'revision': adjustment.id, 'amount': None}
        salary_grid.update_salary_grid(self.period.id, 'save', [change], 'Trả về công thức')
        self.assertEqual(run.item_ids.net_amount, 895)
        cell = salary_grid.load_salary_grid(self.period.id)['rows'][0]['values'][component.id]
        self.assertFalse(cell['manual'])
        salary_grid.update_salary_grid(self.period.id, 'save',
                                       [dict(change, revision=cell['revision'], amount=1200)], 'Điều chỉnh đã xác nhận')
        self.assertEqual(run.item_ids.net_amount, 1095)
        self.assertEqual(grid._grid_lock_mode(self.period), 'open')
        salary_grid.update_salary_grid(self.period.id, 'lock', reason='Đã đối chiếu')
        self.assertEqual(grid._grid_lock_mode(self.period), 'payroll')
        run.action_review(); run.action_approve(); run.action_finalize()
        issued = self.env['hrm.payslip'].search([('payroll_id', '=', run.id)])
        self.assertEqual(issued.net_amount, 1095)
        self.assertEqual(issued.deduction_amount, 105)
        self.assertEqual(len(issued.item_ids.filtered(lambda l: l.code.startswith('EMPLOYEE_'))), 3)
        self.assertEqual(contract.with_context(refresh_employee_contract_groups=True).action_expire(),
                         {'type': 'ir.actions.client', 'tag': 'reload'})
        self.assertIn(contract, self.employee.hrm_closed_contract_ids)
        self.assertNotIn(contract, self.employee.hrm_active_contract_ids)

    def test_compulsory_insurance_rates_caps_and_employer_separation(self):
        from ..models.insurance import insurance_amounts
        values = insurance_amounts(5310000, 2530000, 5310000)
        self.assertEqual(values['employee_social'], 424800)
        self.assertEqual(values['employee_health'], 79650)
        self.assertEqual(values['employee_unemployment'], 53100)
        self.assertEqual(values['employee_total'], 557550)
        self.assertEqual(values['employer_total'], 1141650)
        capped = insurance_amounts(200000000, 2530000, 5310000)
        self.assertEqual(capped['social_base'], 50600000)
        self.assertEqual(capped['unemployment_base'], 106200000)
        with self.assertRaises(UserError): insurance_amounts(0, 2530000, 5310000)

    def test_excel_formula_references_and_invalid_rows(self):
        from ..models.salary_quick import excel_expression
        from ..engine import formula
        self.assertEqual(excel_expression('=ROUND($G12*U12/N12;0)'), '=ROUND(BASE_SALARY*PAID_DAYS/STANDARD_DAYS;0)')
        self.assertEqual(formula(excel_expression('=ROUND(G12*U12/N12,0)'),
            {'BASE_SALARY': 5310000, 'PAID_DAYS': 20, 'STANDARD_DAYS': 22}), 4827273)
        self.assertEqual(formula(excel_expression('=SUM(H12:L12)'),
            dict(LUNCH=10, PETROL=20, PHONE=30, TRAVEL=40, HOUSING=50)), 150)
        with self.assertRaises(UserError): excel_expression('=G12+G13')
        with self.assertRaises(UserError): excel_expression('=AZ12')
