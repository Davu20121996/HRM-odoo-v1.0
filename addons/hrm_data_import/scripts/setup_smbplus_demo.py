"""Seed the isolated SMBPlus demo database from the VP and KPI workbooks."""
import calendar
import csv
import io
from datetime import date
from pathlib import Path

from openpyxl import load_workbook
from odoo import Command
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname == 'hrm_smbplus_stage_20261106'
assert not env['hrm.company'].search_count([]), 'Chỉ chạy trên cơ sở dữ liệu demo mới.'
source = Path('/smbplus_source')
owner = env.ref('base.user_admin')
language = env['res.lang'].with_context(active_test=False).search([('code', '=', 'vi_VN')], limit=1)
language.active = True
modules = env['ir.module.module'].search([('state', '=', 'installed')]).mapped('name')
env['ir.module.module']._load_module_terms(modules, ['vi_VN'], overwrite=True)
owner.write({'group_ids': [Command.link(env.ref('hrm_base.group_hrm_admin').id),
                           Command.link(env.ref('hrm_data_import.group_import_approver').id)],
             'lang': 'vi_VN', 'tz': 'Asia/Ho_Chi_Minh'})
owner.company_id.name = 'SMBPlus'
business = env['hrm.company'].with_user(owner).env
tenant = business['hrm.tenant'].create({'code': 'SMBPLUS', 'slug': 'smbplus', 'name': 'SMBPlus', 'default_currency': 'VND'})
company = business['hrm.company'].create({
    'tenant_id': tenant.id, 'code': 'SMBPLUS', 'name': 'SMBPlus', 'legal_name': 'SMBPlus',
    'country_code': 'VN', 'currency_code': 'VND', 'timezone': 'Asia/Ho_Chi_Minh',
    'res_company_id': owner.company_id.id,
})
scope = {'company_id': company.id, 'tenant_id': tenant.id}
master = business['hrm.employee.import'].create({
    'company_id': company.id, 'filename': 'employee.xlsx', 'sheet': 'VP',
    'file_data': BinaryBytes((source / 'employee.xlsx').read_bytes()),
})
master.action_preview()
master.action_import()
staff = business['hr.employee'].with_context(active_test=False).search(
    [('hrm_company_id', '=', company.id)], order='employee_code, id')
assert len(staff) == 26 and len(staff.filtered('active')) == 21, master.result

department_model = business['hrm.department']
departments = {}
for code, title, parent in [
    ('MKT', 'Maketting', None), ('IT', 'IT', None), ('DEV', 'IT dev', 'IT'),
    ('HELP', 'IT helpdesk', 'IT'), ('CSKH', 'CSKH', None), ('KT', 'Kế toán', None),
]:
    departments[code] = department_model.create(dict(scope, code=code, name=title,
        parent_id=departments[parent].id if parent else False))
roles = {'LEAD': 'Lead', 'SEN': 'Senior', 'NV': 'Nhân viên'}
jobs = {key: business['hrm.job'].create(dict(scope, code=key, title=label)) for key, label in roles.items()}
department_order = ['MKT', 'DEV', 'HELP', 'CSKH', 'KT']
positions = {(dep, role): business['hrm.position'].create(dict(scope, code=f'{dep}-{role}',
    title=roles[role], department_id=departments[dep].id, job_id=jobs[role].id, effective_from='2026-09-01'))
    for dep in department_order for role in roles}
project = business['hrm.employee.project'].create({'name': 'SMBPlus · Chiến dịch Maketting', 'company_id': company.id})

structure = business['hrm.salary.structure'].create(dict(scope, code='SMBPLUS-DEMO', name='SMBPlus · Lương VP demo',
    currency_code='VND', effective_from='2026-09-01'))
component_model = business['hrm.salary.component']
formula_model = business['hrm.payroll.formula']

def component(code, title, kind, sequence, expression=None, sample=None, excel=None):
    record = component_model.create({'tenant_id': tenant.id, 'structure_id': structure.id,
        'code': code, 'name': title, 'component_type': kind, 'sequence_no': sequence,
        'calculation_type': 'fixed', 'configuration': {'fixed_amount': 0}})
    if expression:
        policy = formula_model.create({'tenant_id': tenant.id, 'component_id': record.id,
            'effective_from': '2026-09-01', 'expression': expression, 'test_context': sample,
            **({'excel_expression': excel} if excel else {})})
        policy.action_approve()
    return record

component('BASE', 'Lương theo công', 'earning', 10, 'ROUND(BASE_SALARY * PAID_DAYS / STANDARD_DAYS, 0)',
          {'BASE_SALARY': 5300000, 'PAID_DAYS': 21, 'STANDARD_DAYS': 22}, '=ROUND(G12*U12/N12,0)')
component('KPI', 'Hiệu quả công việc Maketting', 'earning', 20)
component('OVERTIME', 'Tiền làm thêm ngày thường (demo 150%)', 'earning', 30,
          'ROUND(BASE_SALARY / STANDARD_DAYS / 8 * OVERTIME_HOURS * 1.5, 0)',
          {'BASE_SALARY': 5300000, 'STANDARD_DAYS': 22, 'OVERTIME_HOURS': 30})
tax_base = 'MAX(0,TAXABLE_GROSS-EMPLOYEE_INSURANCE-15500000)'
tax = '+'.join([f'MIN(MAX(0,{tax_base}-{lower}),{width})*{rate}' for lower,width,rate in [
    (0,10000000,'.05'),(10000000,20000000,'.10'),(30000000,30000000,'.20'),(60000000,40000000,'.30'),
]]) + f'+MAX(0,{tax_base}-100000000)*.35'
component('PIT', 'Thuế TNCN (giả định cá nhân cư trú, 0 người phụ thuộc)', 'tax', 40,
          f'ROUND({tax},0)', {'TAXABLE_GROSS': 20000000, 'EMPLOYEE_INSURANCE': 556500})
allowances = {}
for code, name, cap in [('LUNCH', 'Ăn trưa', 730000), ('PETROL', 'Xăng xe', 1000000),
                         ('HOUSING', 'Nhà ở', None), ('TRAVEL', 'Đi lại', None)]:
    allowances[code] = business['hrm.allowance.type'].create({'company_id': company.id, 'code': code, 'name': name,
        'tax_mode': 'capped' if cap else 'taxable', 'exempt_limit': cap or 0})
kind = business['hrm.contract.type'].create({'tenant_id': tenant.id, 'code': 'SMBPLUS-HDLD',
    'name': 'Hợp đồng lao động SMBPlus', 'employment_category': 'fixed_term'})
employees_by_department = {key: [] for key in department_order}
active_staff = staff.filtered('active')
for index, employee in enumerate(active_staff + (staff - active_staff)):
    dep = department_order[index % len(department_order)]
    rank = index // len(department_order)
    role = 'LEAD' if rank == 0 else 'SEN' if rank == 1 else 'NV'
    position = positions[dep, role]
    if employee.active:
        employee.write({'hire_date': '2026-09-01', 'termination_date': False, 'current_status': 'active',
                        'job_title': position.title})
        assignment = business['hrm.employee.assignment'].create(dict(scope, employee_id=employee.id,
            department_id=departments[dep].id, position_id=position.id, job_id=position.job_id.id,
            start_date='2026-09-01', project_ids=[Command.link(project.id)] if dep == 'MKT' else []))
        employee.current_assignment_id = assignment
        employees_by_department[dep].append(employee)
    else:
        assignment = business['hrm.employee.assignment'].create(dict(scope, employee_id=employee.id,
            department_id=departments[dep].id, position_id=position.id, job_id=position.job_id.id,
            start_date='2025-09-01', end_date='2026-08-31', status='closed'))
    amounts = (2000000, 3000000, 3000000, 3000000) if role in ('LEAD', 'SEN') else (
        730000, 2000000, 1000000, 1000000)
    values = dict(scope, employee_id=employee.id, contract_type_id=kind.id,
        contract_no='SMBPLUS-' + employee.employee_code, structure_id=structure.id, base_salary=5300000,
        start_date='2026-09-01' if employee.active else '2025-09-01',
        end_date='2027-08-31' if employee.active else '2026-08-31',
        working_hours_per_week=44 if role == 'LEAD' else 40, currency_code='VND',
        job_description=f'Khối VP · {departments[dep].name} · {position.title}',
        workplace='Văn phòng SMBPlus',
        terms=f'<p>Hợp đồng minh họa SMBPlus. Phòng ban: {departments[dep].name}. Chức vụ: {position.title}.</p>',
        allowance_ids=[Command.create({'type_id': policy.id, 'amount': amount})
                       for policy, amount in zip(allowances.values(), amounts)])
    contract = business['hrm.employee.contract'].create(values)
    contract.action_submit()
    contract.action_approve()
    contract.action_activate()
    if not employee.active:
        contract.action_expire()

symbols = {'X': (8, 0), 'S1': (4, 0), 'C1': (4, 0), 'X+TC1': (8, 4), 'X+TC2H': (8, 2)}
for code, (regular, overtime) in symbols.items():
    business['hrm.attendance.symbol'].create({'company_id': company.id, 'code': code,
        'regular_hours': regular, 'overtime_hours': overtime})

def import_csv(period, dataset, headers, rows, symbols_config=None):
    profile = business['hrm.import.profile'].create(dict(scope, name=f'SMBPlus · {dataset} · {period.period_code}',
        dataset=dataset, source='SMBPLUS-' + dataset, headers=headers, batch_identity=True, locale='en',
        monthly=dataset == 'attendance', first_day_column=2, symbols=symbols_config or {},
        mapping_ids=[Command.create({'column': column, 'target': key, 'data_type': kind, 'required': True})
                     for column, key, kind in ([(1, 'employee_code', 'text')] if dataset == 'attendance' else
                        [(1, 'employee_code', 'text'), (2, 'component_code', 'text'), (3, 'amount', 'number'), (4, 'currency', 'text')])]))
    profile.action_approve()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    batch = business['hrm.import.batch'].create({'period_id': period.id, 'profile_id': profile.id,
        'filename': f'SMBPlus_{dataset}_{period.period_code}.csv', 'file_data': BinaryBytes(buffer.getvalue().encode('utf-8')),
        'source_revision': 1, 'approval_reference': 'SMBPlus demo · công mô phỏng; KPI trích từ Excel mô phỏng'})
    batch.action_preview()
    assert batch.state == 'ready', (batch.message, batch.line_ids.filtered('error')[:3].mapped('error'))
    batch.action_commit()
    assert batch.state == 'committed', batch.message
    return batch

efficiency = load_workbook(source / '03_HieuQua_SMB.xlsx', read_only=True, data_only=True)
for month in (9, 10):
    last = calendar.monthrange(2026, month)[1]
    weekdays = [day for day in range(1, last+1) if date(2026, month, day).weekday() < 5]
    period = business['hrm.payroll.period'].create(dict(scope, period_code=f'2026-{month:02}',
        period_start=date(2026, month, 1), period_end=date(2026, month, last), standard_days=len(weekdays),
        hours_per_day=8, require_imported_attendance=True, require_imported_performance=False))
    rows = []
    it = employees_by_department['DEV'] + employees_by_department['HELP']
    for employee in active_staff:
        marks = {day: 'X' for day in weekdays}
        marks[weekdays[-2]], marks[weekdays[-1]] = 'S1', 'C1'
        if employee in it:
            overtime_days = [day for day in weekdays[:-2] if month != 9 or day not in (1, 2)][:8]
            for day in overtime_days[:-1]:
                marks[day] = 'X+TC1'
            marks[overtime_days[-1]] = 'X+TC2H'
        rows.append([employee.employee_code] + [marks.get(day, '') for day in range(1, 32)])
    attendance = import_csv(period, 'attendance', ['employee_code'] + [f'D{d:02}' for d in range(1, 32)], rows,
        {key: {'regular_hours': regular, 'overtime_hours': overtime} for key, (regular, overtime) in symbols.items()})
    sheet = efficiency[f'T{month:02}_2026']
    values = iter(sheet.values)
    header = next(values)
    kpi_column = header.index('KPI')
    kpis = {str(row[0]).strip(): row[kpi_column] for row in values if row[0] and row[kpi_column] is not None}
    marketing = employees_by_department['MKT']
    assert all(employee.employee_code in kpis for employee in marketing)
    performance = import_csv(period, 'performance', ['employee_code', 'component_code', 'amount', 'currency'],
        [(employee.employee_code, 'KPI', kpis[employee.employee_code], 'VND') for employee in marketing])
    input_model = business['hrm.import.input']
    for employee in active_staff:
        inputs = input_model.search([('batch_id', '=', attendance.id), ('employee_id', '=', employee.id)])
        assert sum(float(row.payload['overtime_hours']) for row in inputs) == (30 if employee in it else 0)
    assert input_model.search([('batch_id', '=', performance.id)]).employee_id == input_model.search(
        [('batch_id', '=', performance.id), ('employee_id', 'in', [e.id for e in marketing])]).employee_id
    result = period.action_quick_payroll()
    assert result and result.get('res_model') == 'hrm.payroll', (result, period.readiness)
    run = business['hrm.payroll'].browse(result['res_id'])
    assert len(run.item_ids) == len(active_staff)
    for item in run.item_ids:
        assert abs(item.gross_amount - item.deduction_amount - item.tax_amount - item.net_amount) < .01
        assert len(item.detail_ids.filtered('contract_allowance')) == 4
        assert item.employee_insurance == 556500
    print(f'SMBPLUS {period.period_code}: {len(run.item_ids)} luong, {len(it)} IT x 30h, {len(marketing)} KPI.')
efficiency.close()
owner.write({'action_id': env.ref('hrm_base.action_hrm_company').id})
env.cr.commit()
