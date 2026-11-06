"""Idempotent setup through odoo shell. No invented attendance or pay amounts.

Read /tmp/hrm_demo_sources/{employee,timesheet_employee,business_efficiency,salaries}.xlsx.
Run on hrm only. Creates records as the existing admin account, never as another
company's owner. Original files stay immutable in the company-scoped source log.
"""
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from openpyxl import load_workbook
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname == 'hrm', 'This setup targets the main hrm database only.'
owner = env.ref('base.user_admin')
business = env['hrm.company'].with_user(owner).sudo().env
root = Path('/tmp/hrm_demo_sources')
filenames = ['employee.xlsx', 'timesheet_employee.xlsx', 'business_efficiency.xlsx', 'salaries.xlsx']
payloads = {name: (root / name).read_bytes() for name in filenames}
hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}

def get(model, domain, values):
    records = business[model].with_context(active_test=False) if model == 'hr.employee' else business[model]
    return records.search(domain, limit=1) or records.create(values)

tenant = get('hrm.tenant', [('code', '=', 'DEMO-SOURCE-HRM')], dict(
    code='DEMO-SOURCE-HRM', name='Không gian công ty demo từ file nguồn', slug='demo-source-hrm',
    status='active', default_currency='VND', country_code='VN', timezone='Asia/Ho_Chi_Minh', locale='vi-VN'))
assert tenant.create_uid == owner, 'Do not reuse another account’s tenant.'
company = get('hrm.company', [('tenant_id', '=', tenant.id), ('code', '=', 'DEMO-SOURCE')], dict(
    tenant_id=tenant.id, code='DEMO-SOURCE', name='Công ty Demo HRM', legal_name='Công ty Demo HRM',
    status='active', currency_code='VND', country_code='VN', timezone='Asia/Ho_Chi_Minh'))
assert company.create_uid == owner, 'Do not reuse another account’s company.'
workspace = get('hrm.demo.workspace', [('company_id', '=', company.id)], dict(
    name='Công ty Demo HRM — dữ liệu từ 4 file nguồn', company_id=company.id, prepared_on=date(2026, 11, 4),
    notes='26 hồ sơ nguồn ở employee.xlsx / VP: 21 đang làm, 5 nghỉ việc. '
          'Sheet TSR chưa có mã nhân viên. Ba file công, hiệu quả và lương chỉ có khung mẫu. '
          'Chưa có ngày tuyển dụng, hợp đồng hoặc lương nguồn; chưa tạo bảng công, kỳ lương hay phiếu lương. '
          'Mẫu lương ghi tháng 01/2022, không được coi là chính sách hiện tại. '
          'Cột mã số thuế/BHXH cần đối chiếu trước khi nhập. Tên công ty là tên demo; hồ sơ và trạng thái theo dữ liệu nguồn.'))
for name in filenames:
    old = business['hrm.demo.source'].search([('workspace_id', '=', workspace.id), ('filename', '=', name)])
    if old:
        assert old.sha256 == hashes[name], 'Source changed: create a new source bundle instead of overwriting history.'

book = load_workbook(io.BytesIO(payloads['employee.xlsx']), data_only=True)
sheet = book['VP']
rows = [(n, str(sheet.cell(n, 2).value).strip()) for n in range(2, sheet.max_row + 1) if sheet.cell(n, 2).value]
assert len(rows) == 26 and len({code for n, code in rows}) == 26
counts = {'active': 0, 'terminated': 0}
for row, code in rows:
    status = sheet.cell(row, 1).value
    assert status in ('Đang làm việc', 'Nghỉ việc'), 'Unknown employment state requires explicit mapping.'
    state = 'active' if status == 'Đang làm việc' else 'terminated'
    counts[state] += 1
    name = str(sheet.cell(row, 5).value).strip()
    assert name
    # Split only the literal full-name value. Ignore cached first-name formulas
    # and all ambiguous tax/insurance identifiers.
    parts = name.split()
    person = get('hrm.person', [('tenant_id', '=', tenant.id), ('person_code', '=', code)], dict(
        tenant_id=tenant.id, company_id=company.id, person_code=code,
        last_name=parts[0], first_name=' '.join(parts[1:]) or parts[0]))
    employee = get('hr.employee', [('tenant_id', '=', tenant.id), ('employee_code', '=', code)], dict(
        name=name, tenant_id=tenant.id, hrm_company_id=company.id, person_id=person.id,
        employee_code=code, current_status=state, active=state == 'active',
        additional_note=f'Nguồn: employee.xlsx / VP / dòng {row}. Trạng thái nguyên bản: {status}. '
                        'Ngày vào/nghỉ việc, chức danh, hợp đồng và lương chưa có dữ liệu nguồn.'))
    assert employee.hrm_company_id == company and employee.current_status == state
book.close()
assert counts == {'active': 21, 'terminated': 5}

profiles = {}
for filename, dataset, sheet_name, header_row in [
    ('timesheet_employee.xlsx', 'attendance', 'Sheet1', 1),
    ('business_efficiency.xlsx', 'performance', 'HieuQua (2)', 1),
    ('salaries.xlsx', 'history', 'Luong', 10),
]:
    book = load_workbook(io.BytesIO(payloads[filename]), data_only=True)
    ws = book[sheet_name]
    width = 35 if dataset == 'attendance' else (20 if dataset == 'performance' else 52)
    headers = [str(ws.cell(header_row, c).value or '').strip() for c in range(1, width + 1)]
    mappings = [(0, 0, dict(column=1, target='employee_code', data_type='text', required=True))]
    if dataset == 'attendance': mappings.append((0, 0, dict(column=3, target='project_code', data_type='text', required=False)))
    if dataset == 'performance': mappings.append((0, 0, dict(column=2, target='project_code', data_type='text', required=False)))
    profile = get('hrm.import.profile', [('company_id', '=', company.id), ('source', '=', 'ORIGINAL-'+dataset.upper())], dict(
        name={'attendance': 'Mẫu gốc — Công 31 ngày', 'performance': 'Mẫu gốc — Hiệu quả nhiều cột', 'history': 'Mẫu gốc — Lương lịch sử nhiều tầng'}[dataset],
        company_id=company.id, tenant_id=tenant.id, dataset=dataset, source='ORIGINAL-'+dataset.upper(),
        sheet=sheet_name, header_row=header_row, headers=headers, locale='vi',
        monthly=dataset == 'attendance', first_day_column=4, symbols={}, amount_columns=dataset == 'performance',
        sample_filename=filename, sample_data=BinaryBytes(payloads[filename]), mapping_ids=mappings))
    # Remain draft: source templates do not define approval, revisions, KPI units,
    # the payroll calendar or all required business mappings.
    assert profile.state == 'draft'
    profile.write({'batch_identity': True, 'cached_header': dataset in ('performance', 'history'),
                   'data_start_row': 12 if dataset == 'history' else 2})
    profile.action_read_headers()
    profiles[filename] = profile.id
    book.close()

details = {
    'employee.xlsx': ('TSR; VP', 26, 'imported', 'Đã nạp 26 mã và họ tên từ VP, 21 đang làm và 5 nghỉ việc. Không tự tạo ngày tuyển dụng hoặc lương. Không nhập mã thuế/định danh/BHXH do có cột cần đối chiếu.'),
    'timesheet_employee.xlsx': ('Sheet1', 0, 'empty', 'Có khung 31 ngày và cột nghi_tinh_luong; chưa có dòng công, kỳ và bảng quy đổi ký hiệu. Chưa ghi công bằng 0.'),
    'business_efficiency.xlsx': ('HieuQua (2)', 0, 'empty', 'Có các khoản và header mô tả dùng công thức đã có cache; chưa có số tiền. KPI chưa xác nhận đơn vị. Tổng hiệu quả phải đối chiếu, không cộng đúp cùng khoản chi tiết.'),
    'salaries.xlsx': ('Luong', 0, 'empty', 'Mẫu tháng 01/2022, header nhiều tầng hàng 9–11; chưa có dòng lương. Cần adapter header nhiều hàng và xác nhận kỳ/chính sách trước khi nhập. Chưa tạo phiếu lương.'),
}
for name, (sheets, count, state, detail) in details.items():
    get('hrm.demo.source', [('workspace_id', '=', workspace.id), ('filename', '=', name)], dict(
        workspace_id=workspace.id, filename=name, file_data=BinaryBytes(payloads[name]), sha256=hashes[name],
        sheets=sheets, record_count=count, state=state, details=detail, profile_id=profiles.get(name)))

event = business['hrm.audit.log'].search([('company_id', '=', company.id), ('entity_type', '=', 'hrm.demo.workspace'), ('entity_id', '=', workspace.id)], limit=1)
if not event:
    business['hrm.audit.log'].create(dict(tenant_id=tenant.id, company_id=company.id, actor_user_id=owner.id,
        action='IMPORT', entity_type='hrm.demo.workspace', entity_id=workspace.id,
        metadata={'step': 'setup_from_original_files', 'sources_sha256': hashes,
                  'employees': 26, 'active': 21, 'terminated': 5, 'attendance_rows': 0,
                  'performance_rows': 0, 'salary_rows': 0, 'invented_financial_records': False}))

# Verify as a normal logged-in account, not with elevated access.
visible = business['hrm.company'].with_user(owner).sudo(False).search([])
assert company in visible and all(c.create_uid == owner for c in visible)
staff = business['hr.employee'].with_user(owner).sudo(False).with_context(active_test=False).search([('hrm_company_id', '=', company.id)])
assert len(staff) == 26
assert len(staff.filtered(lambda e: e.current_status == 'active')) == 21
assert len(staff.filtered(lambda e: e.current_status == 'terminated')) == 5
assert not business['hrm.payroll'].search([('company_id', '=', company.id)])
business.cr.commit()
print('COMPANY_DEMO=' + json.dumps({'company_id': company.id, 'workspace_id': workspace.id,
    'owner_login': owner.login, 'employee_count': len(staff), 'active': 21, 'terminated': 5,
    'source_files': len(filenames), 'payroll_runs': 0, 'profile_ids': profiles}, ensure_ascii=False))
