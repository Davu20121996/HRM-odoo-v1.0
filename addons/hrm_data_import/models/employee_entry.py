from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.mimetypes import guess_mimetype


class Employee(models.Model):
    _inherit = 'hr.employee'

    hrm_main_contract_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id', domain=[('parent_id', '=', False)], string='Contracts')
    hrm_addendum_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id', domain=[('parent_id', '!=', False)], string='Addenda and renewals')
    hrm_active_contract_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('status', '=', 'active')],
        string='In effect')
    hrm_pending_contract_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('status', 'in', ['draft', 'pending_approval', 'approved'])],
        string='Awaiting action')
    hrm_closed_contract_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('status', '=', 'expired')],
        string='Closed history')
    hrm_active_addendum_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('parent_id', '!=', False), ('status', '=', 'active')],
        string='In effect')
    hrm_pending_addendum_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('parent_id', '!=', False), ('status', 'in', ['draft', 'pending_approval', 'approved'])],
        string='Awaiting action')
    hrm_closed_addendum_ids = fields.One2many(
        'hrm.employee.contract', 'employee_id',
        domain=[('parent_id', '!=', False), ('status', '=', 'expired')],
        string='Closed history')
    hrm_education_ids = fields.One2many('hrm.employee.education', 'employee_id', string='Qualifications')
    hrm_resume_filename = fields.Char(groups='hrm_data_import.group_import_operator')
    hrm_resume = fields.Binary(string='Personal résumé', attachment=True,
                              groups='hrm_data_import.group_import_operator')

    def action_new_employee_contract(self):
        self.ensure_one()
        self.check_access('read')
        contracts = self.env['hrm.employee.contract']
        domain = [('employee_id', '=', self.id), ('company_id', '=', self.hrm_company_id.id),
                  ('parent_id', '=', False)]
        source = contracts.search(domain + [('status', '=', 'active')], order='start_date desc, id desc', limit=1)
        source = source or contracts.search(domain, order='start_date desc, id desc', limit=1)
        return source.action_new_contract_from_existing() if source else contracts._new_contract_action(self)

    @api.constrains('hrm_resume')
    def _check_resume_file(self):
        accepted = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
        for record in self:
            if not record.hrm_resume:
                continue
            data = record.hrm_resume.content
            if len(data) > 10 * 1024 * 1024 or guess_mimetype(data) not in accepted:
                raise ValidationError(self.env._('Upload a PDF, JPG, PNG or WebP résumé up to 10 MB.'))


class Education(models.Model):
    _inherit = 'hrm.employee.education'

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals.get('employee_id') or self.env.context.get('default_employee_id'))
            prepared.append(dict(vals, tenant_id=employee.tenant_id.id) if employee else vals)
        return super().create(prepared)

    @api.constrains('tenant_id', 'employee_id')
    def _check_education_tenant(self):
        if any(record.tenant_id != record.employee_id.tenant_id for record in self):
            raise ValidationError(self.env._('The qualification must belong to the employee’s management unit.'))


class Contract(models.Model):
    _inherit = 'hrm.employee.contract'

    contract_department_id = fields.Many2one('hrm.department', related='employee_id.hrm_assignment_department',
                                            string='Phòng ban hiện tại')
    contract_position_id = fields.Many2one('hrm.position', related='employee_id.hrm_assignment_position',
                                          string='Chức vụ hiện tại')
    full_renewal = fields.Boolean(copy=False, string='Tái ký toàn bộ')
    entry_type = fields.Selection([('contract', 'Hợp đồng'), ('renewal', 'Tái ký')],
                                  compute='_compute_entry_type', string='Loại')

    @api.depends('parent_id')
    def _compute_entry_type(self):
        for record in self:
            record.entry_type = 'renewal' if record.parent_id else 'contract'

    def action_activate(self):
        result = super().action_activate()
        if self.env.context.get('refresh_employee_contract_groups'):
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return result

    def action_expire(self):
        result = super().action_expire()
        if self.env.context.get('refresh_employee_contract_groups'):
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        return result

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        source_id = self.env.context.get('contract_copy_source_id')
        if source_id and 'allowance_ids' in fields_list:
            source = self.browse(source_id)
            source.check_access('read')
            defaults['allowance_ids'] = [
                Command.create({'type_id': line.type_id.id, 'amount': line.amount})
                for line in source.allowance_ids
            ]
        return defaults

    def _new_contract_action(self, employee, defaults=None):
        self.check_access('create')
        return {
            'type': 'ir.actions.act_window', 'name': 'Hợp đồng mới',
            'res_model': self._name, 'view_mode': 'form',
            'views': [(self.env.ref('hrm_employee.view_hrm_employee_contract_form').id, 'form')],
            'target': 'new',
            'context': {
                'contract_entry_kind': 'contract', 'default_parent_id': False, 'default_status': 'draft',
                'default_employee_id': employee.id, 'default_company_id': employee.hrm_company_id.id,
                'default_tenant_id': employee.tenant_id.id,
                **{f'default_{key}': value for key, value in (defaults or {}).items()},
            },
        }

    def _copy_entry_defaults(self):
        self.ensure_one()
        self.check_access('read')
        if self.parent_id:
            raise ValidationError('Mở hợp đồng gốc để nhân bản.')
        defaults = {name: self[name] for name in (
            'base_salary', 'insurance_salary', 'currency_code', 'working_hours_per_week',
            'terms', 'job_description', 'workplace',
        )}
        defaults.update(contract_type_id=self.contract_type_id.id, structure_id=self.structure_id.id)
        return defaults

    def action_new_contract_from_existing(self):
        action = self._new_contract_action(self.employee_id, self._copy_entry_defaults())
        action['context']['contract_copy_source_id'] = self.id
        return action

    def action_renew_from_contract(self):
        action = self._new_contract_action(self.employee_id, self._copy_entry_defaults())
        action['name'] = 'Tái ký từ hợp đồng ' + self.contract_no
        action['context'].update(contract_entry_kind='appendix', default_parent_id=self.id,
                                 contract_copy_source_id=self.id, lock_renewal_parent=True,
                                 default_full_renewal=True)
        return action

    @api.onchange('parent_id')
    def _onchange_entry_parent(self):
        for record in self:
            parent = record.parent_id
            if not parent:
                continue
            for field_name in ('employee_id', 'company_id', 'tenant_id', 'contract_type_id', 'structure_id',
                               'currency_code', 'base_salary', 'insurance_salary', 'working_hours_per_week'):
                record[field_name] = parent[field_name]

    @api.model_create_multi
    def create(self, vals_list):
        entry_kind = self.env.context.get('contract_entry_kind')
        for vals in vals_list:
            parent_id = vals.get('parent_id', self.env.context.get('default_parent_id'))
            if self.env.context.get('lock_renewal_parent') and parent_id != self.env.context.get('contract_copy_source_id'):
                raise ValidationError('Hợp đồng gốc phải là hợp đồng đã chọn để tái ký.')
            if entry_kind == 'appendix' and not parent_id:
                raise ValidationError(self.env._('Select the original contract before saving an addendum.'))
            if entry_kind == 'contract' and parent_id:
                raise ValidationError(self.env._('Use Addenda and renewals to create a linked addendum.'))
            if parent_id and not vals.get('changes_salary', self.env.context.get('default_changes_salary')):
                parent = self.browse(parent_id)
                parent.check_access('read')
                vals.setdefault('base_salary', parent.base_salary)
                vals.setdefault('insurance_salary', parent.insurance_salary)
                vals.setdefault('structure_id', parent.structure_id.id)
        return super().create(vals_list)

    @api.constrains('base_salary', 'parent_id', 'changes_salary')
    def _check_required_base_salary(self):
        if any((not record.parent_id or record.changes_salary) and record.base_salary <= 0 for record in self):
            raise ValidationError(self.env._('Enter a base salary greater than zero.'))
