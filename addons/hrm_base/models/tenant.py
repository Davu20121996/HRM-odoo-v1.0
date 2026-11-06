from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrmTenant(models.Model):
    _name = "hrm.tenant"
    _inherit = ["hrm.base.mixin"]
    _description = "SaaS tenant boundary (SPEC §3.1)"

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    slug = fields.Char(required=True)
    status = fields.Selection(
        [
            ("trial", "Trial"),
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("closed", "Closed"),
        ],
        default="trial",
        required=True,
    )
    timezone = fields.Char(default="UTC", required=True)
    locale = fields.Char(default="en-US", required=True)
    default_currency = fields.Char(default="USD", required=True, size=3)
    country_code = fields.Char(size=2)
    settings = fields.Json(default=dict)

    company_ids = fields.One2many("hrm.company", "tenant_id")

    _code_unique = models.Constraint("UNIQUE(code)", "Tenant code must be unique.")
    _slug_unique = models.Constraint("UNIQUE(slug)", "Tenant slug must be unique.")
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Tenant UUID must be unique.")

    @api.constrains("default_currency")
    def _check_currency(self):
        import re

        for rec in self:
            if not re.fullmatch(r"[A-Z]{3}", rec.default_currency or ""):
                raise ValidationError("default_currency must be ISO-4217 (e.g. VND).")

    def name_get(self):
        return [(rec.id, f"[{rec.code}] {rec.name}") for rec in self]
