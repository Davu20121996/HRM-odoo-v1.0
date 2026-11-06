"""Reset-free seed for a newly initialized, empty staging DB; no legacy data deletion."""
import hashlib
import json
from pathlib import Path
from odoo.tools.binary import BinaryBytes
from odoo.addons.hrm_data_import.engine import number, read_table
from odoo.addons.hrm_data_import.models.imports import accepts_performance
assert env.cr.dbname == 'hrm_smb_stage_20261104'
assert not env['hrm.company'].search_count([]), 'Only a new, empty database is accepted.'
owner = env.ref('base.user_admin')
business = env['hrm.company'].with_user(owner).env
root = Path('/tmp/smb_clean')
tenant = business['hrm.tenant'].create(dict(code='SMB', name='SMB', slug='smb', default_currency='VND', country_code='VN'))
owner.company_id.sudo().write({'name': 'SMB (MÔ PHỎNG)'})
company = business['hrm.company'].create(dict(tenant_id=tenant.id, code='SMB', name='Công ty SMB',
    legal_name='SMB — MÔ PHỎNG PHẦN MỀM', currency_code='VND', country_code='VN',
    timezone='Asia/Ho_Chi_Minh', res_company_id=owner.company_id.id))
business['hrm.import.profile'].search([('company_id', '=', company.id), ('state', '=', 'draft'),
    ('source', 'in', ['MANUAL-DAILY','MANUAL-MONTHLY','MANUAL-PERFORMANCE','MANUAL-SALARY','MANUAL-HISTORY'])]).unlink()
master = business['hrm.employee.import'].create(dict(company_id=company.id, filename='01_NhanVien_SMB.xlsx',
    file_data=BinaryBytes((root/'01_NhanVien_SMB.xlsx').read_bytes()), sheet='VP'))
master.action_preview()
master.action_import()
staff = business['hr.employee'].with_context(active_test=False).search([('hrm_company_id', '=', company.id)])
assert len(staff)==26 and len(staff.filtered('active'))==21
structure = business['hrm.salary.structure'].create(dict(tenant_id=tenant.id, company_id=company.id,
    code='SMB_DEMO', name='SMB — MÔ PHỎNG, chưa áp dụng thuế/BHXH thực tế', effective_from='2026-09-01', currency_code='VND'))
base = business['hrm.salary.component'].create(dict(tenant_id=tenant.id, structure_id=structure.id,
    code='BASE', name='Lương theo ngày công', component_type='earning', calculation_type='formula', sequence_no=10,
    configuration={'expression': 'base_salary'}))
policy = business['hrm.payroll.formula'].create(dict(tenant_id=tenant.id, component_id=base.id,
    effective_from='2026-09-01', expression='ROUND(BASE_SALARY * PAID_DAYS / STANDARD_DAYS, 0)',
    test_context={'BASE_SALARY':5310000,'PAID_DAYS':20,'STANDARD_DAYS':22}))
policy.action_approve()
components={}
for column, code, name in [(5,'KPI','KPI'),(7,'TRAINING','Phụ cấp đào tạo'),(9,'RESP','Phụ cấp trách nhiệm'),
    (11,'PARK','Gửi xe'),(13,'SALES','Hoa hồng'),(15,'CONTEST','Thi đua tháng'),(17,'OTHER','Khác'),
    (18,'HOLIDAY','Lễ'),(21,'PROJECT','Thưởng dự án mô phỏng')]:
    comp = business['hrm.salary.component'].create(dict(tenant_id=tenant.id, structure_id=structure.id,
        code=code, name=name, component_type='earning', calculation_type='fixed', sequence_no=column+20,
        configuration={'fixed_amount':0}))
    components[column]=comp
business['hrm.salary.component'].create(dict(tenant_id=tenant.id, structure_id=structure.id,
    code='DEMO_DEDUCT', name='Khấu trừ MÔ PHỎNG (không phải thuế/BHXH)', component_type='deduction',
    calculation_type='fixed', sequence_no=100, configuration={'fixed_amount':250000}))
kind=business['hrm.contract.type'].create(dict(tenant_id=tenant.id, code='SMB-DEMO', name='Hợp đồng MÔ PHỎNG',employment_category='fixed_term'))
contracts={}
for employee in staff:
    contract=business['hrm.employee.contract'].create(dict(tenant_id=tenant.id, company_id=company.id,
        employee_id=employee.id, contract_type_id=kind.id, contract_no='MO_PHONG-'+employee.employee_code,
        start_date='2026-09-01' if employee.active else '2024-01-01',
        end_date='2027-08-31' if employee.active else '2026-08-31', base_salary=5310000, currency_code='VND',
        structure_id=structure.id, working_hours_per_week=40, job_description='Nhân viên văn phòng — MÔ PHỎNG',
        workplace='Văn phòng SMB — MÔ PHỎNG', terms='<p>MÔ PHỎNG PHẦN MỀM, không phải hợp đồng thực tế. '
        'Mã, tên và thông tin nhân viên theo sheet VP. Lương cơ bản 5.310.000 do người dùng cung cấp. '
        'Ngày hợp đồng, giờ công, hiệu quả và khấu trừ được tạo để demo. Chưa áp dụng thuế/BHXH thực tế.</p>'))
    contract.action_submit();contract.action_approve();contract.action_activate()
    if not employee.active: contract.action_expire()
    contracts[employee.employee_code]=contract
first=staff.filtered('active').sorted('employee_code')[0]
old=business['hrm.employee.contract'].sudo().create(dict(tenant_id=tenant.id, company_id=company.id,
    employee_id=first.id, contract_type_id=kind.id, contract_no='MO_PHONG-CU-'+first.employee_code,
    start_date='2025-01-01',end_date='2026-08-31',base_salary=5310000,currency_code='VND',structure_id=structure.id,
    status='expired', terms='<p>Hợp đồng lịch sử MÔ PHỎNG, đã hết hạn.</p>'))
appendix=business['hrm.employee.contract'].sudo().create(dict(tenant_id=tenant.id, company_id=company.id,
    employee_id=first.id, contract_type_id=kind.id, contract_no='MO_PHONG-PL01-'+first.employee_code,
    parent_id=contracts[first.employee_code].id,start_date='2026-09-15',base_salary=0,currency_code='VND',
    status='expired', changes_salary=False,terms='<p>Phụ lục MÔ PHỎNG: bổ sung nhiệm vụ báo cáo tuần. Không thay đổi lương.</p>'))
expected=json.loads((root/'expected.json').read_text())
workspace=business['hrm.demo.workspace'].sudo().create(dict(company_id=company.id,
    name='SMB — bộ demo đồng bộ theo VP', prepared_on='2026-11-04',
    notes='26 hồ sơ VP (21 đang làm, 5 nghỉ). Công, hiệu quả và hợp đồng là MÔ PHỎNG. '
    'Lương cơ bản 5.310.000 theo người dùng. Tháng 09 đã có phiếu; tháng 10 sẵn sàng tính trên web.'))
for filename, count in [('01_NhanVien_SMB.xlsx',26),('02_Cong_SMB.xlsx',42),('03_HieuQua_SMB.xlsx',42),('04_DoiChieuLuong_SMB.xlsx',42)]:
    payload=(root/filename).read_bytes()
    business['hrm.demo.source'].sudo().create(dict(workspace_id=workspace.id,filename=filename,
        file_data=BinaryBytes(payload),sha256=hashlib.sha256(payload).hexdigest(),sheets='VP' if count==26 else 'T09_2026; T10_2026' if filename[0:2] in ('02','03') else 'DoiChieu',
        record_count=count,state='imported',details='MÔ PHỎNG theo yêu cầu; mã nhân viên đồng bộ VP. File đối chiếu không nhập trùng vào lương.'))
for month in (9,10):
    period=business['hrm.payroll.period'].create(dict(tenant_id=tenant.id,company_id=company.id,
        period_code=f'MO_PHONG-2026-{month:02}',period_start=f'2026-{month:02}-01',
        period_end=f'2026-{month:02}-'+('30' if month==9 else '31'),standard_days=22,hours_per_day=8,
        require_imported_attendance=True,require_imported_performance=True))
    for dataset, filename in [('attendance','02_Cong_SMB.xlsx'),('performance','03_HieuQua_SMB.xlsx')]:
        payload=(root/filename).read_bytes();sheet=f'T{month:02}_2026'
        headers,source_rows=read_table(payload,filename,sheet,1)
        mappings=[(0,0,dict(column=1,target='employee_code',data_type='text',required=True)),
            (0,0,dict(column=3 if dataset=='attendance' else 2,target='project_code',data_type='text',required=True))]
        if dataset=='performance':
            mappings += [(0,0,dict(column=c,target='amount',data_type='number',required=True,component_id=comp.id))
                         for c,comp in components.items() if accepts_performance(comp)]
            excluded = {str(raw[0]).strip(): sum(number(raw[c-1], 'en') for c,comp in components.items()
                         if not accepts_performance(comp) and raw[c-1] not in (None, ''))
                        for _,raw in source_rows if raw and raw[0]}
        profile=business['hrm.import.profile'].create(dict(tenant_id=tenant.id,company_id=company.id,
            name=f'MÔ PHỎNG — {"Công" if dataset=="attendance" else "Hiệu quả"} tháng {month:02}/2026',
            dataset=dataset,source='SMB-DEMO-'+dataset,sheet=sheet,header_row=1,headers=headers,
            locale='en',batch_identity=True,monthly=dataset=='attendance',first_day_column=4,
            symbols={},amount_columns=dataset=='performance',mapping_ids=mappings,
            sample_filename=filename,sample_data=BinaryBytes(payload)))
        profile.action_approve()
        batch=business['hrm.import.batch'].create(dict(profile_id=profile.id,period_id=period.id,
            filename=filename,file_data=BinaryBytes(payload),source_revision=1,
            approval_reference=f'MÔ PHỎNG được người dùng cho phép; tháng {month:02}/2026'))
        batch.action_preview();assert batch.state=='ready',batch.message
        batch.action_commit();assert batch.state=='committed',batch.message
    screen=business['hrm.monthly.workspace'].create(dict(company_id=company.id,year=2026,month=str(month)))
    if month==9:
        result=period.action_quick_payroll();assert isinstance(result,dict) and result.get('res_model')=='hrm.payroll',period.readiness
        run=business['hrm.payroll'].browse(result['res_id'])
        for item in run.item_ids:
            value=next(v for v in expected if v['month']==month and v['code']==item.employee_id.employee_code)
            assert round(item.net_amount)==value['net']-excluded.get(item.employee_id.employee_code, 0), (
                item.employee_id.employee_code,item.net_amount,value['net'])
        run.action_review();run.action_approve();run.action_finalize()
        period.action_to_review();period.action_approve();period.action_finalize()
    screen.action_refresh()
    assert len(screen.line_ids)==26
    print('MONTH_READY',month,'dashboard',screen.id,'inputs',business['hrm.import.input'].search_count([('period_id','=',period.id)]))
assert business['hrm.company'].search_count([])==1
assert business['hrm.payroll.item'].search_count([])==21
assert business['hrm.payslip'].search_count([])==21
env.cr.commit()
print('SMB_CLEAN_READY: 1 company, 26 employees, 2 months, 21 contracts active, September reconciled, October ready.')
