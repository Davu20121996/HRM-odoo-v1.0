"""Final reconciliation against generated Excel; no fabricated verification results."""
import json
from pathlib import Path
assert env.cr.dbname == 'hrm'
owner=env.ref('base.user_admin')
business=env['hrm.company'].with_user(owner).env
company=business['hrm.company'].search([('code','=','SMB')])
assert len(company)==1 and env['hrm.company'].search_count([])==1
assert env['hr.employee'].with_context(active_test=False).search_count([])==26
assert business['hr.employee'].search_count([('hrm_company_id','=',company.id)])==21
drafts=business['hrm.import.profile'].search([('company_id','=',company.id),('state','=','draft'),
    ('source','in',['MANUAL-DAILY','MANUAL-MONTHLY','MANUAL-PERFORMANCE','MANUAL-SALARY','MANUAL-HISTORY'])])
assert not business['hrm.import.batch'].search_count([('profile_id','in',drafts.ids)])
count=len(drafts)
drafts.unlink()
if count:
    business['hrm.audit.log'].sudo().create(dict(tenant_id=company.tenant_id.id,company_id=company.id,
        actor_user_id=owner.id,action='UPDATE',entity_type='hrm.import.profile',
        metadata={'step':'remove_unused_starter_templates','count':count,'reason':'Clean synchronized SMB demo requested by user'}))
expected=json.loads(Path('/tmp/smb_clean/expected.json').read_text())
items=business['hrm.payroll.item'].search([('payroll_id.company_id','=',company.id)])
assert len(items)==42
for item in items:
    month=item.payroll_id.period_id.period_start.month
    row=next(r for r in expected if r['month']==month and r['code']==item.employee_id.employee_code)
    assert round(item.net_amount)==row['net'],(month,item.employee_id.employee_code,item.net_amount,row['net'])
    detail=business['hrm.payslip.item'].search([('payroll_id','=',item.payroll_id.id),('employee_id','=',item.employee_id.id)])
    assert len(detail)==11
assert business['hrm.payslip'].search_count([('payroll_id.company_id','=',company.id)])==21
assert business['hrm.import.input'].search_count([('company_id','=',company.id)])==1660
for screen in business['hrm.monthly.workspace'].search([('company_id','=',company.id)]):screen.action_refresh()
total=sum(round(i.net_amount) for i in items)
assert total==sum(r['net'] for r in expected)
env.cr.commit()
print('PASS: one company; 26 VP employees (21 active, 5 departed); 42 monthly results match Excel; 462 component lines; 21 issued September payslips; 1660 source inputs; total net',total)
