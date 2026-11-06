from odoo import fields, models
from odoo.exceptions import UserError


class Workspace(models.Model):
    _name = 'hrm.demo.workspace'
    _description = 'Demo company from source data'

    name = fields.Char(required=True)
    company_id = fields.Many2one('hrm.company', required=True, ondelete='restrict')
    tenant_id = fields.Many2one(related='company_id.tenant_id', store=True)
    prepared_on = fields.Date(string='Demo preparation date', readonly=True)
    source_ids = fields.One2many('hrm.demo.source', 'workspace_id', readonly=True)
    employee_count = fields.Integer(compute='_compute_counts', string='Source records')
    working_count = fields.Integer(compute='_compute_counts', string='Active employment')
    departed_count = fields.Integer(compute='_compute_counts', string='Terminated')
    notes = fields.Text(string='Source data status', readonly=True)

    def _compute_counts(self):
        for rec in self:
            staff = self.env['hr.employee'].with_context(active_test=False).search([('hrm_company_id', '=', rec.company_id.id)])
            rec.employee_count = len(staff)
            rec.working_count = len(staff.filtered(lambda e: e.current_status == 'active'))
            rec.departed_count = len(staff.filtered(lambda e: e.current_status == 'terminated'))

    def action_employees(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': 'Nhân viên từ file nguồn',
            'res_model': 'hr.employee', 'view_mode': 'list,form',
            'views': [(self.env.ref('hrm_data_import.view_demo_employee_list').id, 'list'), (False, 'form')],
            'domain': [('hrm_company_id', '=', self.company_id.id)], 'context': {'active_test': False}}

    def action_profiles(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': 'Mapping theo file nguồn của công ty',
            'res_model': 'hrm.import.profile', 'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id), ('source', '=like', 'ORIGINAL-%')]}

    def action_logs(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': 'Log dựng công ty và nhập hồ sơ',
            'res_model': 'hrm.audit.log', 'view_mode': 'list,form',
            'domain': [('company_id', '=', self.company_id.id)]}


class Source(models.Model):
    _name = 'hrm.demo.source'
    _description = 'Source file and demo reconciliation'
    _rec_name = 'filename'

    workspace_id = fields.Many2one('hrm.demo.workspace', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='workspace_id.company_id', store=True)
    tenant_id = fields.Many2one(related='workspace_id.tenant_id', store=True)
    filename = fields.Char(required=True)
    file_data = fields.Binary(required=True, attachment=True)
    sha256 = fields.Char(required=True)
    sheets = fields.Char(string='Source worksheet')
    record_count = fields.Integer(string='Populated business rows')
    state = fields.Selection([('imported', 'Loaded'), ('empty', 'No data rows')], required=True)
    details = fields.Text(string='Validation results')
    profile_id = fields.Many2one('hrm.import.profile', string='Draft column mapping', ondelete='restrict')

    _source_unique = models.Constraint('UNIQUE(workspace_id, filename)', 'Mỗi file chỉ có một bản nguồn trong bộ demo.')

    def action_download(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_url', 'target': 'download',
            'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=filename&download=true'}

    def write(self, vals):
        raise UserError('File nguồn được giữ bất biến để đối chiếu. Tạo bộ nguồn mới khi thay file.')

    def unlink(self):
        raise UserError('Không xóa file nguồn của bộ demo đã dựng.')
