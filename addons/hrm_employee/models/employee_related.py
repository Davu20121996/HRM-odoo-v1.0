from odoo import fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric
from odoo.exceptions import UserError


class HrmEmployeeContact(models.Model):
    _name = "hrm.employee.contact"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee contact channel (SPEC §4.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    contact_type = fields.Selection(
        [("email", 'Email'), ("phone", "Phone"), ("address", "Address")],
        required=True,
    )
    label = fields.Char()
    value = fields.Char(required=True)
    is_primary = fields.Boolean(default=False)
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Contact UUID must be unique.")


class HrmEmployeeFamily(models.Model):
    _name = "hrm.employee.family"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee family / dependants (SPEC §4.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    person_id = fields.Many2one("hrm.person", ondelete="set null")
    name = fields.Char(required=True)
    relationship_type = fields.Selection(
        [
            ("spouse", "Spouse"),
            ("child", "Child"),
            ("parent", "Parent"),
            ("sibling", "Sibling"),
            ("other", "Other"),
        ],
        required=True,
    )
    is_dependent = fields.Boolean(default=False)
    date_of_birth = fields.Date()
    notes = fields.Char()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Family UUID must be unique.")


class HrmEmergencyContact(models.Model):
    _name = "hrm.emergency.contact"
    _inherit = ["hrm.base.mixin"]
    _description = "Emergency contact (SPEC §4.5)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    relationship = fields.Char(required=True)
    phone = fields.Char(required=True)
    email = fields.Char()
    address = fields.Char()
    priority = fields.Integer(default=1)
    is_primary = fields.Boolean(default=False)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Emergency contact UUID must be unique.")


class HrmEmployeeEducation(models.Model):
    _name = "hrm.employee.education"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee education (SPEC §4.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    institution = fields.Char(required=True)
    degree = fields.Char(required=True)
    field_of_study = fields.Char()
    start_date = fields.Date()
    end_date = fields.Date()
    grade = fields.Char()
    country_code = fields.Char(size=2)
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Education UUID must be unique.")


class HrmEmployeeCertification(models.Model):
    _name = "hrm.employee.certification"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee certification (SPEC §4.7)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    certification_name = fields.Char(required=True)
    issuer = fields.Char(required=True)
    certificate_no = fields.Char()
    issued_date = fields.Date()
    expiry_date = fields.Date()
    status = fields.Selection(
        [("valid", "Valid"), ("expired", "Expired"), ("revoked", "Revoked")],
        default="valid",
        required=True,
    )
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Certification UUID must be unique.")


class HrmEmployeeSkill(models.Model):
    _name = "hrm.employee.skill"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee skill (SPEC §4.8)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    level = fields.Selection(
        [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced"), ("expert", "Expert")],
        required=True,
    )
    years_experience = HrmNumeric(digits=(6, 2))
    verified_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Skill UUID must be unique.")


class HrmEmployeeDocument(models.Model):
    _name = "hrm.employee.document"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee document metadata; binaries in object storage (SPEC §4.9)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    document_type = fields.Char(required=True)
    file_name = fields.Char(required=True)
    storage_key = fields.Char(required=True)
    mime_type = fields.Char()
    file_size_bytes = fields.Integer()
    checksum_sha256 = fields.Char()
    issued_at = fields.Datetime()
    expires_at = fields.Datetime()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Document UUID must be unique.")


class HrmEmployeeHistory(models.Model):
    _name = "hrm.employee.history"
    _description = "Immutable employee history projection (SPEC §4.10)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    event_type = fields.Char(required=True)
    event_at = fields.Datetime(required=True, default=fields.Datetime.now)
    actor_id = fields.Many2one("res.users", ondelete="set null")
    reference_type = fields.Char()
    reference_id = fields.Integer()
    payload = fields.Json(default=dict)

    def write(self, vals):
        raise UserError("Employee history is immutable.")

    def unlink(self):
        raise UserError("Employee history is immutable.")
