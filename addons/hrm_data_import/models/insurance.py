"""Vietnamese compulsory insurance for the configured ordinary employee case.

Employee amounts reduce net pay; employer amounts never reduce employee net.
Snapshots are written only when payroll is calculated, never while exporting.
"""
from decimal import Decimal, ROUND_HALF_UP
from odoo import fields, models
from odoo.exceptions import UserError
from .imports import audit

EMPLOYEE_CODES = {'EMPLOYEE_SOCIAL', 'EMPLOYEE_HEALTH', 'EMPLOYEE_UNEMPLOYMENT', 'EMPLOYEE_INSURANCE'}


def insurance_amounts(base, reference, regional_minimum):
    if base <= 0 or reference <= 0 or regional_minimum <= 0:
        raise UserError('Cần lương đóng bảo hiểm, mức tham chiếu và lương tối thiểu vùng lớn hơn 0.')
    social_base = min(Decimal(str(base)), Decimal(str(reference))*20)
    unemployment_base = min(Decimal(str(base)), Decimal(str(regional_minimum))*20)
    def amount(salary, rate):
        return float((salary*Decimal(rate)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    result = dict(base=base, social_base=float(social_base), unemployment_base=float(unemployment_base),
        employee_social=amount(social_base, '.08'), employee_health=amount(social_base, '.015'),
        employee_unemployment=amount(unemployment_base, '.01'),
        employer_social=amount(social_base, '.17'), employer_accident=amount(social_base, '.005'),
        employer_health=amount(social_base, '.03'), employer_unemployment=amount(unemployment_base, '.01'))
    result['employee_total'] = sum(result[k] for k in ('employee_social', 'employee_health', 'employee_unemployment'))
    result['employer_total'] = sum(result[k] for k in ('employer_social', 'employer_accident', 'employer_health', 'employer_unemployment'))
    return result


class InsurancePeriod(models.Model):
    _inherit = 'hrm.payroll.period'
    insurance_regional_minimum = fields.Float(string='Regional minimum wage for unemployment insurance', default=5310000,
        help='Default: region I in 2026. Select the company region; the unemployment insurance cap is 20 times this wage.')

    def write(self, vals):
        if 'insurance_regional_minimum' in vals:
            for rec in self:
                if rec.status not in ('open', 'processing'):
                    raise UserError('Mở lại kỳ trước khi đổi thông số bảo hiểm; kỳ đã chốt không sửa.')
        return super().write(vals)


class InsuranceContract(models.Model):
    _inherit = 'hrm.employee.contract'
    insurance_salary = fields.Float(string='Insurable salary', digits=(19, 0),
        help='0 = contract base salary. Enter the verified insurable salary if eligible allowances apply.')

    def write(self, vals):
        if 'insurance_salary' in vals:
            if vals['insurance_salary'] < 0: raise UserError('Lương đóng bảo hiểm không được âm.')
            if any(r.status in ('approved', 'active', 'expired') for r in self):
                raise UserError('Lương đóng BH trong hợp đồng đã duyệt chỉ thay đổi bằng phụ lục/hợp đồng mới.')
        return super().write(vals)


class InsurancePayroll(models.Model):
    _inherit = 'hrm.payroll'

    def _insurance(self, salary):
        start = self.period_id.period_start
        if str(start) < '2025-07-01':
            raise UserError('Kỳ trước 07/2025 cần cấu hình chính sách bảo hiểm theo thời điểm trước khi tính.')
        reference = 2530000 if str(start) >= '2026-07-01' else 2340000
        if salary.structure_id.component_ids.filtered(lambda c: c.status == 'active' and c.code in EMPLOYEE_CODES):
            raise UserError('BH người lao động được hệ thống tính bắt buộc. Bỏ khoản BH trùng trong cơ cấu để tránh trừ hai lần.')
        values = insurance_amounts(salary.insurance_salary or salary.base_salary, reference,
                                  self.period_id.insurance_regional_minimum)
        values.update(reference=reference, regional_minimum=self.period_id.insurance_regional_minimum,
            employee_rates={'social': 8, 'health': 1.5, 'unemployment': 1},
            employer_rates={'social': 17, 'accident': .5, 'health': 3, 'unemployment': 1},
            policy='VN ordinary employee: BHXH/BHYT/BHTN; no union fee', contract_id=salary.id)
        return values

    def _calculation_context(self, employee, salary, context):
        result = super()._calculation_context(employee, salary, context)
        insurance = self._insurance(salary)
        result.update(INSURANCE_BASE=insurance['base'], EMPLOYEE_INSURANCE=insurance['employee_total'],
            employee_insurance=insurance['employee_total'],
            EMPLOYEE_SOCIAL=insurance['employee_social'], EMPLOYEE_HEALTH=insurance['employee_health'],
            EMPLOYEE_UNEMPLOYMENT=insurance['employee_unemployment'], EMPLOYER_INSURANCE=insurance['employer_total'])
        return result

    def action_calculate(self):
        result = super().action_calculate()
        if isinstance(result, dict): return result
        for run in self.filtered(lambda r: r.status == 'calculated'):
            for item in run.item_ids:
                values = run._insurance(run._active_salary(item.employee_id))
                total = values['employee_total']
                item.write({'insurance_snapshot': values, 'employee_insurance': total,
                    'employer_insurance': values['employer_total'],
                    'deduction_amount': item.deduction_amount + total, 'net_amount': item.net_amount - total})
                for code, title, key in [('EMPLOYEE_SOCIAL', 'BHXH NLĐ 8%', 'employee_social'),
                    ('EMPLOYEE_HEALTH', 'BHYT NLĐ 1,5%', 'employee_health'),
                    ('EMPLOYEE_UNEMPLOYMENT', 'BHTN NLĐ 1%', 'employee_unemployment')]:
                    self.env['hrm.payslip.item'].create(dict(tenant_id=run.tenant_id.id, payroll_id=run.id,
                        employee_id=item.employee_id.id, code=code, name=title, amount=values[key],
                        currency_code=item.currency_code, sequence_no=1000, status='calculated'))
                audit(run, 'UPDATE', {'step': 'compulsory_insurance', 'employee_id': item.employee_id.id,
                    'version': run.calculation_version, 'insurance': values, 'net': item.net_amount})
        return result


class InsuranceResult(models.Model):
    _inherit = 'hrm.payroll.item'
    insurance_snapshot = fields.Json(readonly=True, string='Insurance calculation snapshot')
    employee_insurance = fields.Float(readonly=True, digits=(19, 0), string='Employee insurance')
    employer_insurance = fields.Float(readonly=True, digits=(19, 0), string='Employer insurance')
    insurance_state = fields.Char(compute='_compute_insurance_state', string='Insurance status')

    def _compute_insurance_state(self):
        for rec in self:
            rec.insurance_state = 'Đã tính BH' if rec.insurance_snapshot else 'Chưa tính BH — không xuất'

    def _excel_values(self, ordinal=1):
        values = super()._excel_values(ordinal)
        insurance = self.insurance_snapshot
        if insurance:
            values.update(AF=self.employee_insurance,
                AD=self.deduction_amount-self.employee_insurance,
                AO=insurance['employer_social'], AP=insurance['employer_accident'],
                AQ=insurance['employer_health'], AR=insurance['employer_unemployment'],
                AT=self.employer_insurance, AU=insurance['employee_social'],
                AV=insurance['employee_health'], AW=insurance['employee_unemployment'],
                AY=self.employee_insurance, AZ=self.employer_insurance+self.employee_insurance)
        else:
            values['AN'] = (values.get('AN', '') + ' — LỊCH SỬ CHƯA TÍNH BH; cần đối chiếu').strip()
        return values


class InsuranceExport(models.Model):
    _inherit = 'hrm.monthly.workspace'

    def _salary_xlsx(self):
        period = self._period()
        domain = [('company_id', '=', self.company_id.id), ('period_id', '=', period.id)]
        if self.employee_id: domain.append(('employee_id', '=', self.employee_id.id))
        items = self.env['hrm.payroll.item'].search(domain)
        if items.filtered(lambda r: not r.insurance_snapshot):
            raise UserError('Tháng này có lương chưa tính bảo hiểm bắt buộc. Mở lại kỳ chưa chốt và tính lại trước khi xuất; lịch sử đã chốt cần xử lý điều chỉnh riêng.')
        return super()._salary_xlsx()
