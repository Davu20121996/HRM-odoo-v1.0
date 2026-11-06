"""Run through odoo shell, only against the explicitly named QA database.

Creates synthetic fixtures; actions under test are performed in the browser.
"""
import csv
import io
import json
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname == 'hrm_import_qa_20261104', 'QA database only'

def record(model, domain, values):
    return env[model].search(domain, limit=1) or env[model].create(values)

tenant = record('hrm.tenant', [('code', '=', 'QA_IMPORT')], dict(code='QA_IMPORT', name='QA HRM Import', slug='qa-hrm-import', default_currency='VND', status='active'))
company = record('hrm.company', [('tenant_id', '=', tenant.id), ('code', '=', 'QA')], dict(tenant_id=tenant.id, code='QA', name='QA Company', currency_code='VND'))
department = record('hrm.department', [('tenant_id', '=', tenant.id), ('code', '=', 'QA')], dict(tenant_id=tenant.id, company_id=company.id, code='QA', name='QA HR'))
employee = record('hr.employee', [('tenant_id', '=', tenant.id), ('employee_code', '=', 'QA001')], dict(name='QA Employee 001', tenant_id=tenant.id, employee_code='QA001', current_status='active'))
record('hrm.employee.assignment', [('employee_id', '=', employee.id)], dict(tenant_id=tenant.id, company_id=company.id, department_id=department.id, employee_id=employee.id, start_date='2026-01-01'))
admin = env.ref('base.user_admin')
admin.write({'hrm_tenant_ids': [(4, tenant.id)]})
structure = record('hrm.salary.structure', [('tenant_id', '=', tenant.id), ('code', '=', 'QA')], dict(tenant_id=tenant.id, company_id=company.id, code='QA', name='QA Salary', currency_code='VND', effective_from='2026-01-01'))
components = {}
for seq, code, label, kind in [(10, 'BASE', 'Luong theo cong', 'earning'), (20, 'PERF', 'Hieu qua', 'earning'), (30, 'MEAL', 'Tien an', 'earning'), (40, 'DED', 'Khau tru test', 'deduction'), (50, 'TAX', 'Thue test', 'tax')]:
    components[code] = record('hrm.salary.component', [('structure_id', '=', structure.id), ('code', '=', code)], dict(tenant_id=tenant.id, structure_id=structure.id, code=code, name=label, component_type=kind, calculation_type='fixed', sequence_no=seq, configuration={'fixed_amount': 0}))
record('hrm.employee.salary', [('employee_id', '=', employee.id), ('structure_id', '=', structure.id)], dict(tenant_id=tenant.id, employee_id=employee.id, structure_id=structure.id, effective_from='2026-01-01', base_salary=13000000, currency_code='VND'))
period = record('hrm.payroll.period', [('tenant_id', '=', tenant.id), ('period_code', '=', 'QA-2026-10')], dict(tenant_id=tenant.id, company_id=company.id, period_code='QA-2026-10', period_start='2026-10-01', period_end='2026-10-31', standard_days=26, hours_per_day=8, require_imported_attendance=True, require_imported_performance=True))

def csv_data(headers, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')

identity = ['employee_code', 'source_record_id', 'revision', 'approval_reference']
monthly_headers = identity + [f'D{day:02}' for day in range(1, 32)]
money_headers = identity + ['component_code', 'amount', 'currency']
files = {
    '01-attendance.csv': csv_data(monthly_headers, [['QA001', 'TIME-QA001', 1, 'QA-APPROVED'] + ['X'] * 24 + [''] * 7]),
    '02-performance.csv': csv_data(money_headers, [['QA001', 'PERF-QA001', 1, 'QA-APPROVED', 'PERF', 1600000, 'VND']]),
    '03-salary-input.csv': csv_data(money_headers, [['QA001', 'DED-QA001', 1, 'QA-APPROVED', 'DED', 1000000, 'VND'], ['QA001', 'TAX-QA001', 1, 'QA-APPROVED', 'TAX', 500000, 'VND']]),
    '04-invalid-employee.csv': csv_data(money_headers, [['UNKNOWN', 'BAD-001', 1, 'QA-APPROVED', 'PERF', 1, 'VND']]),
    '05-performance-zero.csv': csv_data(money_headers, [['QA001', 'PERF-QA001', 2, 'QA-APPROVED', 'PERF', 0, 'VND']]),
    '06-performance-restored.csv': csv_data(money_headers, [['QA001', 'PERF-QA001', 3, 'QA-APPROVED', 'PERF', 1600000, 'VND']]),
    '07-history.csv': csv_data(money_headers, [['QA001', 'HISTORY-001', 1, 'QA-APPROVED', 'NET_HISTORY', 12820000, 'VND']]),
}
profiles = {}
for dataset, filename in [('attendance', '01-attendance.csv'), ('performance', '02-performance.csv'), ('salary', '03-salary-input.csv'), ('history', '07-history.csv')]:
    headers = monthly_headers if dataset == 'attendance' else money_headers
    targets = identity if dataset == 'attendance' else money_headers
    profile = record('hrm.import.profile', [('tenant_id', '=', tenant.id), ('dataset', '=', dataset)], dict(
        name='QA ' + dataset, tenant_id=tenant.id, company_id=company.id, dataset=dataset, source='QA-' + dataset,
        locale='en', headers=headers, sample_filename=filename, sample_data=BinaryBytes(files[filename]),
        monthly=dataset == 'attendance', first_day_column=5, symbols={'X': 8},
        mapping_ids=[(0, 0, dict(column=i, target=target, data_type='number' if target in ('revision', 'amount') else 'text', required=True)) for i, target in enumerate(targets, 1)]))
    profiles[dataset] = profile
    if dataset != 'attendance' and profile.state == 'draft': profile.with_user(admin).action_approve()

formulas = {}
for code, expression in [('BASE', '=ROUND(BASE_SALARY * PAID_DAYS / STANDARD_DAYS; 0)'), ('MEAL', '=ROUND(PAID_DAYS * 30000; 0)')]:
    formulas[code] = record('hrm.payroll.formula', [('component_id', '=', components[code].id)], dict(tenant_id=tenant.id, component_id=components[code].id, effective_from='2026-10-01', expression=expression))

batches = {}
for filename, dataset in [('01-attendance.csv', 'attendance'), ('02-performance.csv', 'performance'), ('03-salary-input.csv', 'salary'), ('04-invalid-employee.csv', 'performance'), ('05-performance-zero.csv', 'performance'), ('06-performance-restored.csv', 'performance'), ('07-history.csv', 'history'), ('08-performance-duplicate.csv', 'performance')]:
    content = files.get(filename, files['02-performance.csv'])
    batches[filename] = record('hrm.import.batch', [('filename', '=', filename), ('period_id', '=', period.id)], dict(profile_id=profiles[dataset].id, period_id=period.id, filename=filename, file_data=BinaryBytes(content)))
run = record('hrm.payroll', [('period_id', '=', period.id)], dict(tenant_id=tenant.id, company_id=company.id, period_id=period.id))
env.cr.commit()
print('QA_FIXTURES=' + json.dumps({'period': period.id, 'run': run.id, 'profiles': {k:v.id for k,v in profiles.items()}, 'formulas': {k:v.id for k,v in formulas.items()}, 'batches': {k:v.id for k,v in batches.items()}}))
