import math
import re
import unicodedata
from uuid import uuid4

from odoo import api, fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney
from odoo.exceptions import UserError

from .imports import audit

TAX_MODES = [
    ('taxable', 'Fully taxable'), ('exempt', 'Fully exempt'),
    ('capped', 'Exempt up to a limit'),
]


class AllowanceType(models.Model):
    _name = 'hrm.allowance.type'
    _description = 'Allowance tax policy'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    company_id = fields.Many2one('hrm.company', required=True, ondelete='restrict')
    tenant_id = fields.Many2one(related='company_id.tenant_id')
    tax_mode = fields.Selection(TAX_MODES, required=True, default='taxable', string='Tax treatment')
    exempt_limit = HrmMoney(digits=(19, 0), string='Monthly exemption limit')
    version_ids = fields.One2many('hrm.allowance.version', 'type_id', string='Policy history')
    active = fields.Boolean(default=True)

    _unique_code = models.Constraint('UNIQUE(company_id, code)', 'Allowance code must be unique per company.')

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            code = (vals.get('code') or '').strip().upper()
            if not code:
                name = (vals.get('name') or '').upper().replace('Đ', 'D')
                plain = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
                prefix = re.sub(r'[^A-Z0-9]+', '_', plain).strip('_') or 'ALLOWANCE'
                code = f'PC_{prefix[:24]}_{uuid4().hex[:8].upper()}'
            prepared.append(dict(vals, code=code))
        return super().create(prepared)

    @api.constrains('code', 'exempt_limit')
    def _check_policy(self):
        for rec in self:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,39}', rec.code):
                raise UserError(self.env._('Use an uppercase allowance code with letters, digits or underscores.'))
            if not math.isfinite(rec.exempt_limit) or rec.exempt_limit < 0:
                raise UserError(self.env._('The exemption limit must be a nonnegative amount.'))

    def write(self, vals):
        if 'company_id' in vals and any(rec.company_id.id != vals['company_id'] for rec in self):
            raise UserError(self.env._('An allowance policy cannot be moved to another company.'))
        if 'code' in vals and any(rec.code != vals['code'] for rec in self):
            raise UserError(self.env._('The allowance code cannot change after saving.'))
        for field in ('tax_mode', 'exempt_limit'):
            if field in vals and any(rec[field] != vals[field] for rec in self):
                raise UserError(self.env._('Add an effective-dated version to change the allowance policy.'))
        return super().write(vals)

    def _policy_at(self, effective_date):
        self.ensure_one()
        version = self.version_ids.filtered(lambda rec: rec.effective_from <= effective_date)[:1]
        return version or self

    def _split(self, amount, effective_date=None):
        policy = self._policy_at(effective_date) if effective_date else self
        exempt = 0
        if policy.tax_mode == 'exempt':
            exempt = amount
        elif policy.tax_mode == 'capped':
            exempt = min(amount, policy.exempt_limit)
        return exempt, amount - exempt


class AllowanceVersion(models.Model):
    _name = 'hrm.allowance.version'
    _description = 'Effective-dated allowance policy'
    _order = 'effective_from desc, id desc'

    type_id = fields.Many2one('hrm.allowance.type', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='type_id.company_id', store=True)
    effective_from = fields.Date(required=True, string='Effective from')
    tax_mode = fields.Selection(TAX_MODES, required=True, default='capped', string='Tax treatment')
    exempt_limit = HrmMoney(digits=(19, 0), string='Monthly exemption limit')
    reason = fields.Char(required=True)

    _unique_date = models.Constraint('UNIQUE(type_id, effective_from)', 'Only one version per effective date.')

    @api.model_create_multi
    def create(self, vals_list):
        policies = self.env['hrm.allowance.type'].browse([vals.get('type_id') for vals in vals_list if vals.get('type_id')])
        policies.check_access('write')
        if policies:
            self.env.cr.execute('SELECT id FROM hrm_allowance_type WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(policies.ids),))
            policies.invalidate_recordset(['version_ids'])
        latest = {policy.id: policy.version_ids[:1].effective_from for policy in policies}
        for vals in vals_list:
            start = fields.Date.to_date(vals.get('effective_from'))
            policy = policies.browse(vals.get('type_id'))
            previous = latest.get(policy.id)
            if not start or (previous and start <= previous):
                raise UserError(self.env._('Choose an effective date after the last allowance version.'))
            limit = vals.get('exempt_limit', 0)
            if not math.isfinite(limit) or limit < 0:
                raise UserError(self.env._('The exemption limit must be a nonnegative amount.'))
            if self.env['hrm.payslip.item'].search_count([
                ('payroll_id.company_id', '=', policy.company_id.id),
                ('payroll_id.period_id.period_end', '>=', start),
                ('payroll_id.status', 'not in', ['draft', 'processing']),
                ('contract_allowance', '=', True), ('code', '=', 'CONTRACT_ALLOWANCE_' + policy.code),
            ], limit=1):
                raise UserError(self.env._('Choose a date after the payroll periods that already used this allowance.'))
            latest[policy.id] = start
        versions = super().create(vals_list)
        for version in versions:
            audit(version.type_id, 'UPDATE', {'step': 'allowance_policy_version', 'version_id': version.id,
                'effective_from': str(version.effective_from), 'tax_mode': version.tax_mode,
                'exempt_limit': version.exempt_limit, 'reason': version.reason})
        return versions

    def write(self, vals):
        raise UserError(self.env._('Saved allowance versions are read-only. Add a new version.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_uninstall(self):
        raise UserError(self.env._('Saved allowance versions cannot be deleted.'))


class ContractAllowance(models.Model):
    _name = 'hrm.contract.allowance'
    _description = 'Contract allowance'

    contract_id = fields.Many2one('hrm.employee.contract', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    type_id = fields.Many2one('hrm.allowance.type', required=True, ondelete='restrict', string='Allowance type')
    amount = HrmMoney(required=True, digits=(19, 0), string='Monthly amount')
    tax_mode = fields.Selection(TAX_MODES, compute='_compute_split', string='Tax treatment')
    exempt_limit = fields.Float(compute='_compute_split', digits=(19, 0), string='Monthly exemption limit')
    tax_exempt_amount = fields.Float(compute='_compute_split', digits=(19, 0), string='Tax-exempt portion')
    taxable_amount = fields.Float(compute='_compute_split', digits=(19, 0), string='Taxable portion')

    _unique_type = models.Constraint('UNIQUE(contract_id, type_id)', 'Use one line per allowance type on each contract or addendum.')

    @api.depends('amount', 'contract_id.start_date', 'type_id.tax_mode', 'type_id.exempt_limit', 'type_id.version_ids')
    def _compute_split(self):
        today = fields.Date.context_today(self)
        for rec in self:
            date = max(today, rec.contract_id.start_date or today)
            policy = rec.type_id._policy_at(date) if rec.type_id else rec.type_id
            rec.tax_mode, rec.exempt_limit = policy.tax_mode, policy.exempt_limit
            exempt, taxable = rec.type_id._split(rec.amount, date) if policy else (0, 0)
            rec.tax_exempt_amount, rec.taxable_amount = exempt, taxable

    @api.constrains('contract_id', 'type_id', 'amount')
    def _check_line(self):
        for rec in self:
            if rec.type_id.company_id != rec.contract_id.company_id:
                raise UserError(self.env._('The allowance and contract must belong to the same company.'))
            if not math.isfinite(rec.amount) or rec.amount < 0:
                raise UserError(self.env._('The allowance amount must be nonnegative.'))

    @api.model
    def _check_editable(self, contracts):
        contracts.check_access('write')
        if contracts:
            self.env.cr.execute('SELECT id FROM hrm_employee_contract WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(contracts.ids),))
            contracts.invalidate_recordset(['status'])
        if any(c.status in ('approved', 'active', 'expired') for c in contracts):
            raise UserError(self.env._('Use an addendum to change an approved contract allowance.'))

    @api.model_create_multi
    def create(self, vals_list):
        default_contract = self.env.context.get('default_contract_id')
        contracts = self.env['hrm.employee.contract'].browse([
            vals.get('contract_id', default_contract) for vals in vals_list
            if vals.get('contract_id', default_contract)])
        self._check_editable(contracts)
        return super().create(vals_list)

    def write(self, vals):
        self.check_access('write')
        self._check_editable(self.contract_id | self.env['hrm.employee.contract'].browse(vals.get('contract_id')))
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        self._check_editable(self.contract_id)
        return super().unlink()


class Contract(models.Model):
    _inherit = 'hrm.employee.contract'

    allowance_ids = fields.One2many('hrm.contract.allowance', 'contract_id', string='Allowances')

    def action_new_allowance_addendum(self):
        self.ensure_one()
        self.check_access('read')
        if self.parent_id or self.status not in ('approved', 'active'):
            raise UserError(self.env._('Open an approved parent contract to add an allowance addendum.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form',
            'name': self.env._('Create allowance addendum'),
            'views': [(self.env.ref('hrm_employee.view_hrm_employee_contract_form').id, 'form')],
            'target': 'current',
            'context': {
                'contract_entry_kind': 'appendix',
                'default_parent_id': self.id, 'default_employee_id': self.employee_id.id,
                'default_company_id': self.company_id.id, 'default_tenant_id': self.tenant_id.id,
                'default_contract_type_id': self.contract_type_id.id, 'default_structure_id': self.structure_id.id,
                'default_currency_code': self.currency_code, 'default_base_salary': self.base_salary,
                'default_insurance_salary': self.insurance_salary,
                'default_working_hours_per_week': self.working_hours_per_week,
            },
        }

    @api.constrains('company_id')
    def _check_allowance_company(self):
        self.allowance_ids._check_line()


class PayslipLine(models.Model):
    _inherit = 'hrm.payslip.item'

    tax_exempt_amount = HrmMoney(readonly=True, digits=(19, 0), string='Tax-exempt portion')
    taxable_amount = HrmMoney(readonly=True, digits=(19, 0), string='Taxable portion')
    contract_allowance = fields.Boolean(readonly=True)


class Payroll(models.Model):
    _inherit = 'hrm.payroll'

    def _additional_earnings(self, employee, salary):
        earnings = super()._additional_earnings(employee, salary)
        start, end = self.period_id.period_start, self.period_id.period_end
        lines = {}
        if salary.parent_id and not salary.full_renewal:
            lines.update({line.type_id.id: line for line in salary.parent_id.allowance_ids})
        lines.update({line.type_id.id: line for line in salary.allowance_ids})
        codes = set(salary.structure_id.component_ids.filtered(lambda c: c.status == 'active').mapped('code'))
        snapshot = []
        for line in lines.values():
            code = 'CONTRACT_ALLOWANCE_' + line.type_id.code
            if code in codes:
                raise UserError(self.env._('A salary component duplicates the contract allowance code %(code)s.', code=code))
            if line.type_id.version_ids.filtered(lambda version: start < version.effective_from <= end):
                raise UserError(self.env._('The allowance policy changes mid-period. Split the payroll period first.'))
            policy = line.type_id._policy_at(start)
            exempt, taxable = line.type_id._split(line.amount, start)
            earnings.append(dict(code=code, name=line.type_id.name, amount=line.amount,
                                 tax_exempt_amount=exempt, taxable_amount=taxable, contract_allowance=True))
            snapshot.append(dict(contract_id=line.contract_id.id, type_id=line.type_id.id, code=code,
                                 amount=line.amount, exempt=exempt, taxable=taxable,
                                 mode=policy.tax_mode, limit=policy.exempt_limit,
                                 version_id=policy.id if policy._name == 'hrm.allowance.version' else None))
        if snapshot:
            audit(self, 'UPDATE', {'step': 'contract_allowances', 'employee_id': employee.id, 'lines': snapshot})
        return earnings
