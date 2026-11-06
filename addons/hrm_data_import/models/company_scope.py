"""Company ownership is a server-side boundary, including for HRM admins."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Users(models.Model):
    _inherit = 'res.users'

    hrm_company_ids = fields.Many2many('hrm.company', compute='_compute_hrm_owned', compute_sudo=False,
        string='Companies created by this account', readonly=True)
    hrm_owned_tenant_ids = fields.Many2many('hrm.tenant', compute='_compute_hrm_owned', compute_sudo=False,
        string='Management units owned by this account', readonly=True)

    def _compute_hrm_owned(self):
        for user in self:
            companies = self.env['hrm.company'].sudo().search([('create_uid', '=', user.id)])
            user.hrm_company_ids = companies
            user.hrm_owned_tenant_ids = companies.tenant_id | self.env['hrm.tenant'].sudo().search([('create_uid', '=', user.id)])

    def write(self, vals):
        if set(vals) & {'hrm_company_ids', 'hrm_owned_tenant_ids'}:
            raise AccessError('Phạm vi công ty lấy từ người tạo công ty; không tự gán qua tài khoản.')
        return super().write(vals)


class Company(models.Model):
    _inherit = 'hrm.company'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('create_uid', self.env.uid) != self.env.uid for v in vals_list):
            raise AccessError('Không được giả người tạo công ty.')
        if not self.env.su:
            for vals in vals_list:
                self.env['hrm.tenant'].browse(vals.get('tenant_id')).check_access('read')
        companies = super().create(vals_list)
        self.env['res.users'].invalidate_model(['hrm_company_ids', 'hrm_owned_tenant_ids'])
        self.env['ir.access']._clear_caches()
        if 'hrm.import.profile' in self.env:
            from ..hooks import create_company_templates
            create_company_templates(companies.sudo().env, companies.sudo())
        return companies

    def write(self, vals):
        if not self.env.su and 'create_uid' in vals:
            raise AccessError('Không được chuyển quyền sở hữu bằng cách sửa người tạo.')
        if not self.env.su and vals.get('tenant_id'):
            self.env['hrm.tenant'].browse(vals['tenant_id']).check_access('read')
        result = super().write(vals)
        self.env['res.users'].invalidate_model(['hrm_company_ids', 'hrm_owned_tenant_ids'])
        self.env['ir.access']._clear_caches()
        return result


class Tenant(models.Model):
    _inherit = 'hrm.tenant'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('create_uid', self.env.uid) != self.env.uid for v in vals_list):
            raise AccessError('Không được giả người tạo tenant.')
        records = super().create(vals_list)
        self.env['res.users'].invalidate_model(['hrm_owned_tenant_ids'])
        self.env['ir.access']._clear_caches()
        return records

    def write(self, vals):
        if not self.env.su and 'create_uid' in vals: raise AccessError('Không sửa người tạo tenant.')
        return super().write(vals)


class Employee(models.Model):
    _inherit = 'hr.employee'

    hrm_company_id = fields.Many2one('hrm.company', string='HRM company', ondelete='restrict', index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('tenant_id') and not vals.get('hrm_company_id'):
                companies = self.env['hrm.company'].search([('tenant_id', '=', vals['tenant_id'])])
                if len(companies) == 1: vals['hrm_company_id'] = companies.id
        return super().create(vals_list)

    @api.constrains('hrm_company_id', 'tenant_id', 'person_id')
    def _check_hrm_company(self):
        for rec in self:
            if rec.hrm_company_id and rec.hrm_company_id.tenant_id != rec.tenant_id:
                raise ValidationError('Nhân viên và công ty phải cùng tenant.')
            if rec.person_id.company_id and rec.hrm_company_id and rec.person_id.company_id != rec.hrm_company_id:
                raise ValidationError('Hồ sơ cá nhân không thuộc công ty nhân viên.')


class EmployeePublic(models.Model):
    _inherit = 'hr.employee.public'
    hrm_company_id = fields.Many2one('hrm.company', readonly=True)


class Person(models.Model):
    _inherit = 'hrm.person'
    company_id = fields.Many2one('hrm.company', string='Company', ondelete='restrict', index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('tenant_id') and not vals.get('company_id'):
                companies = self.env['hrm.company'].search([('tenant_id', '=', vals['tenant_id'])])
                if len(companies) == 1: vals['company_id'] = companies.id
        return super().create(vals_list)

    @api.constrains('company_id', 'tenant_id')
    def _check_company(self):
        for rec in self:
            if rec.company_id and rec.company_id.tenant_id != rec.tenant_id:
                raise ValidationError('Hồ sơ cá nhân và công ty phải cùng tenant.')


class Audit(models.Model):
    _inherit = 'hrm.audit.log'
    company_id = fields.Many2one('hrm.company', string='Company', ondelete='restrict', index=True)


class Access(models.Model):
    _inherit = 'ir.access'

    def _make_record_access_error(self, records, operation):
        # Core's multi-company hint assumes company_id points to res.company.
        # HRM uses hrm.company. Also never disclose names/IDs in denied reads.
        if records._name.startswith('hrm.') or records._name in ('hr.employee', 'hr.employee.public'):
            return AccessError('Bạn không có quyền truy cập dữ liệu này. Chỉ được sử dụng công ty do tài khoản tạo.')
        return super()._make_record_access_error(records, operation)
