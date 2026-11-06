from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    hrm_tenant_id = fields.Many2one(
        "hrm.tenant",
        string="Primary HRM Tenant",
        help="Adapter for SPEC §13.1 user_account (passwords stay in Odoo auth).",
        ondelete="set null",
    )
    hrm_tenant_ids = fields.Many2many(
        "hrm.tenant",
        "hrm_user_tenant_rel",
        "user_id",
        "tenant_id",
        string="HRM Tenants",
        help="Tenants this user may access. Drives tenant record rules.",
    )
    hrm_status = fields.Selection(
        [("active", "Active"), ("suspended", "Suspended")],
        default="active",
        required=True,
    )
