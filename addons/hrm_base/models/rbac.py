from odoo import fields, models


class HrmRole(models.Model):
    _name = "hrm.role"
    _inherit = ["hrm.base.mixin"]
    _description = "Role (SPEC §13.2). tenant NULL = platform/system role."

    tenant_id = fields.Many2one("hrm.tenant", ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    is_system = fields.Boolean(default=False)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    permission_ids = fields.Many2many(
        "hrm.permission", "hrm_role_permission_rel", "role_id", "permission_id"
    )

    _code_unique = models.Constraint("UNIQUE(code)", "Role code must be unique.")
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Role UUID must be unique.")


class HrmPermission(models.Model):
    _name = "hrm.permission"
    _description = "Globally defined permission (SPEC §13.3)."

    code = fields.Char(required=True)
    resource = fields.Char(required=True)
    action = fields.Char(required=True)
    description = fields.Char()

    _code_unique = models.Constraint("UNIQUE(code)", "Permission code must be unique.")


class HrmRolePermission(models.Model):
    _name = "hrm.role.permission"
    _description = "Role <-> permission link (SPEC §13.4)."

    role_id = fields.Many2one("hrm.role", required=True, ondelete="cascade")
    permission_id = fields.Many2one("hrm.permission", required=True, ondelete="cascade")

    _role_permission_unique = models.Constraint(
        "UNIQUE(role_id, permission_id)", "Role-permission link must be unique."
    )


class HrmUserRole(models.Model):
    _name = "hrm.user.role"
    _description = "User <-> role assignment, effective-dated (SPEC §13.5)."

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    role_id = fields.Many2one("hrm.role", required=True, ondelete="cascade")
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _user_role_from_unique = models.Constraint(
        "UNIQUE(user_id, role_id, effective_from)",
        "User-role-effective_from must be unique.",
    )


class HrmRoleScope(models.Model):
    _name = "hrm.role.scope"
    _inherit = ["hrm.base.mixin"]
    _description = "Data scope of a role (SPEC §13.6)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    role_id = fields.Many2one("hrm.role", required=True, ondelete="cascade")
    scope_type = fields.Selection(
        [
            ("tenant", "Tenant"),
            ("company", "Company"),
            ("business_unit", "Business Unit"),
            ("department", "Department"),
            ("self", "Self"),
            ("direct_reports", "Direct Reports"),
        ],
        required=True,
    )
    scope_ref = fields.Reference(
        selection=[
            ("hrm.tenant", "Tenant"),
            ("hrm.company", "Company"),
            ("hrm.business.unit", "Business Unit"),
            ("hrm.department", "Department"),
        ],
        help="Empty for SELF / DIRECT_REPORTS scopes.",
    )
    configuration = fields.Json(default=dict)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Role scope UUID must be unique.")
