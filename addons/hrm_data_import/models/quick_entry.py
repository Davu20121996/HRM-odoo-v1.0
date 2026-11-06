from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def single_owned_company(record):
    companies = record.env.user.hrm_company_ids
    return companies.id if len(companies) == 1 else False


class QuickOrganizationEntry(models.AbstractModel):
    _name = 'hrm.quick.organization.entry'
    _description = 'Defaults for organization records'

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'company_id' in fields_list and not defaults.get('company_id'):
            parent = self.browse(defaults.get('parent_id')) if 'parent_id' in self._fields else self.browse()
            defaults['company_id'] = parent.company_id.id if parent else single_owned_company(self)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['company_id', 'parent_id'])
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            parent = self.browse(vals.get('parent_id', defaults.get('parent_id')))
            company = self.env['hrm.company'].browse(vals.get('company_id') or (
                parent.company_id.id if parent else defaults.get('company_id')))
            if company:
                company.check_access('read')
                vals['company_id'] = company.id
                vals.setdefault('tenant_id', company.tenant_id.id)
            if not vals.get('code'):
                vals['code'] = uuid4().hex[:12].upper()
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if vals.get('company_id') and 'tenant_id' not in vals:
            company = self.env['hrm.company'].browse(vals['company_id'])
            company.check_access('read')
            vals = dict(vals, tenant_id=company.tenant_id.id)
        return super().write(vals)

    @api.constrains('company_id', 'tenant_id', 'parent_id')
    def _check_organization_parent(self):
        for record in self:
            if record.tenant_id != record.company_id.tenant_id:
                raise ValidationError(self.env._('The management unit must match the company.'))
            if record.parent_id and record.parent_id.company_id != record.company_id:
                raise ValidationError(self.env._('The parent must belong to the same company.'))
            if self.search_count([('parent_id', '=', record.id), ('company_id', '!=', record.company_id.id)], limit=1):
                raise ValidationError(self.env._('The child records must belong to the same company.'))
            if record._has_cycle():
                raise ValidationError(self.env._('A record cannot be its own ancestor.'))


class Department(models.Model):
    _name = 'hrm.department'
    _inherit = ['hrm.department', 'hrm.quick.organization.entry']

    def action_add_child_department(self):
        self.ensure_one()
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id('hrm_data_import.action_add_child_department')
        action['context'] = {
            'default_company_id': self.company_id.id, 'default_parent_id': self.id,
            'lock_department_company': True, 'lock_parent_department': True,
        }
        return action


class BusinessUnit(models.Model):
    _name = 'hrm.business.unit'
    _inherit = ['hrm.business.unit', 'hrm.quick.organization.entry']


class Location(models.Model):
    _name = 'hrm.location'
    _inherit = ['hrm.location', 'hrm.quick.organization.entry']


class CostCenter(models.Model):
    _name = 'hrm.cost.center'
    _inherit = ['hrm.cost.center', 'hrm.quick.organization.entry']


class Company(models.Model):
    _inherit = 'hrm.company'

    department_ids = fields.One2many('hrm.department', 'company_id', string='Departments')


class CompanyEntryDefaults(models.AbstractModel):
    _name = 'hrm.company.entry.defaults'
    _description = 'Company and management unit entry defaults'
    _entry_company_field = 'company_id'

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        field_name = self._entry_company_field
        if field_name not in fields_list:
            return defaults
        if not defaults.get(field_name) and not defaults.get('tenant_id'):
            defaults[field_name] = single_owned_company(self)
        company = self.env['hrm.company'].browse(defaults.get(field_name))
        if company and 'tenant_id' in fields_list and not defaults.get('tenant_id'):
            defaults['tenant_id'] = company.tenant_id.id
        return defaults


class Employee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee', 'hrm.company.entry.defaults']
    _entry_company_field = 'hrm_company_id'

    @api.onchange('hrm_company_id')
    def _onchange_entry_company(self):
        if self.hrm_company_id:
            self.tenant_id = self.hrm_company_id.tenant_id


class Contract(models.Model):
    _name = 'hrm.employee.contract'
    _inherit = ['hrm.employee.contract', 'hrm.company.entry.defaults']

    @api.onchange('company_id')
    def _onchange_entry_company(self):
        if self.company_id:
            self.tenant_id = self.company_id.tenant_id
        if self.employee_id and self.employee_id.hrm_company_id != self.company_id:
            self.employee_id = False


class Period(models.Model):
    _name = 'hrm.payroll.period'
    _inherit = ['hrm.payroll.period', 'hrm.company.entry.defaults']

    @api.onchange('company_id')
    def _onchange_entry_company(self):
        if self.company_id:
            self.tenant_id = self.company_id.tenant_id


class ManualInput(models.Model):
    _inherit = 'hrm.manual.input'

    company_id = fields.Many2one(default=single_owned_company)


class MonthlyWorkspace(models.Model):
    _inherit = 'hrm.monthly.workspace'

    company_id = fields.Many2one(default=single_owned_company)
