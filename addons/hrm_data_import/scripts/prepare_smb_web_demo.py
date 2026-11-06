"""Prepare explicitly simulated configuration; business inputs are entered on web."""
from odoo.tools.binary import BinaryBytes
assert env.cr.dbname == 'hrm'
owner = env.ref('base.user_admin')
business = env['hrm.company'].with_user(owner).env
company = business['hrm.company'].search([('code', '=', 'DEMO-SOURCE')])
assert len(company) == 1 and company.create_uid == owner
tenant = company.tenant_id
employee = business['hr.employee'].search([('hrm_company_id', '=', company.id), ('employee_code', '=', 'TPV00005')])
assert len(employee) == 1

def get(model, domain, values):
    return business[model].search(domain, limit=1) or business[model].create(values)

structure = get('hrm.salary.structure', [('company_id', '=', company.id), ('code', '=', 'SMB_SIMULATION')], dict(
    tenant_id=tenant.id, company_id=company.id, code='SMB_SIMULATION',
    name='MÔ PHỎNG SMB — chưa áp dụng thuế/BHXH thực tế', currency_code='VND', effective_from='2026-10-01'))
components = {}
for code, name, typ, sequence, expression in [
    ('SIM_BASE', 'Lương theo công — MÔ PHỎNG', 'earning', 10, 'ROUND(BASE_SALARY * PAID_DAYS / STANDARD_DAYS, 0)'),
    ('SIM_KPI', 'Hiệu quả từ Excel — MÔ PHỎNG', 'earning', 20, '0'),
    ('SIM_BONUS', 'Thưởng nhập tay — MÔ PHỎNG', 'earning', 30, '0'),
    ('SIM_DEDUCTION', 'Khấu trừ ví dụ — MÔ PHỎNG', 'deduction', 40, '250000')]:
    comp = get('hrm.salary.component', [('structure_id', '=', structure.id), ('code', '=', code)], dict(
        tenant_id=tenant.id, structure_id=structure.id, code=code, name=name, component_type=typ,
        calculation_type='formula', sequence_no=sequence, configuration={'expression': expression}))
    policy = get('hrm.payroll.formula', [('component_id', '=', comp.id)], dict(
        tenant_id=tenant.id, component_id=comp.id, effective_from='2026-10-01', expression=expression,
        test_context={'BASE_SALARY': 5310000, 'PAID_DAYS': 20, 'STANDARD_DAYS': 22}))
    if policy.state == 'draft': policy.action_approve()
    components[code] = comp

kind = get('hrm.contract.type', [('code', '=', 'SMB_SIMULATION')], dict(
    tenant_id=tenant.id, code='SMB_SIMULATION', name='Hợp đồng MÔ PHỎNG demo', employment_category='fixed_term'))

for dataset, name, headers, extra in [
    ('attendance', 'MÔ PHỎNG — công 31 ngày', ['code', 'ho_va_ten', 'project'] + ['shifts_' + str(n) for n in range(1, 32)] + ['nghi_tinh_luong'],
     dict(monthly=True, first_day_column=4, symbols={'X': 8})),
    ('performance', 'MÔ PHỎNG — hiệu quả theo cột', ['Mã Nhân viên', 'Project', 'Họ Và Tên', 'Tổng Hiệu quả CV', 'KPI'],
     dict(amount_columns=True))]:
    mappings = [(0, 0, dict(column=1, target='employee_code', data_type='text', required=True)),
                (0, 0, dict(column=3 if dataset == 'attendance' else 2, target='project_code', data_type='text', required=False))]
    if dataset == 'performance':
        mappings.append((0, 0, dict(column=5, target='amount', data_type='number', required=True, component_id=components['SIM_KPI'].id)))
    profile = get('hrm.import.profile', [('company_id', '=', company.id), ('source', '=', 'SMB-SIM-' + dataset)], dict(
        tenant_id=tenant.id, company_id=company.id, name=name, dataset=dataset, source='SMB-SIM-' + dataset,
        sheet='Sheet1', headers=headers, locale='en', batch_identity=True, mapping_ids=mappings, **extra))
    if profile.state == 'draft': profile.action_approve()
    print('DEMO_PROFILE', dataset, profile.id)
print('DEMO_CONFIG_READY', company.id, employee.employee_code, structure.id, kind.id)
env.cr.commit()
