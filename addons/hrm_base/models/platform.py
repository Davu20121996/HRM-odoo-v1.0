from odoo import fields, models
from odoo.exceptions import UserError


class HrmAuditLog(models.Model):
    _name = "hrm.audit.log"
    _description = "Append-only audit log (SPEC §16)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="restrict")
    actor_user_id = fields.Many2one("res.users", ondelete="set null")
    actor_employee_ref = fields.Char(
        help="TODO P2: link to hrm.employee record (actor_employee_id)."
    )
    action = fields.Selection(
        [
            ("CREATE", "Create"),
            ("UPDATE", "Update"),
            ("DELETE", "Delete"),
            ("APPROVE", "Approve"),
            ("REJECT", "Reject"),
            ("LOGIN", "Login"),
            ("EXPORT", "Export"),
            ("IMPORT", "Import"),
            ("FINALIZE", "Finalize"),
            ("CLOSE", "Close"),
        ],
        required=True,
    )
    entity_type = fields.Char(required=True)
    entity_id = fields.Integer()
    entity_uuid = fields.Char()
    request_id = fields.Char()
    correlation_id = fields.Char()
    ip_address = fields.Char()
    user_agent = fields.Char()
    old_value = fields.Json()
    new_value = fields.Json()
    metadata = fields.Json(default=dict)

    def write(self, vals):
        raise UserError("Audit log is append-only and cannot be modified.")

    def unlink(self):
        raise UserError("Audit log is append-only and cannot be deleted.")


class HrmConfiguration(models.Model):
    _name = "hrm.configuration"
    _inherit = ["hrm.base.mixin"]
    _description = "Scoped product configuration (SPEC §17.1)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    scope_type = fields.Selection(
        [("tenant", "Tenant"), ("company", "Company"), ("module", "Module")],
        required=True,
    )
    scope_code = fields.Char(help="Company code or module name. Empty for tenant scope.")
    config_key = fields.Char(required=True)
    config_value = fields.Json(default=dict)
    effective_from = fields.Date(default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_scope_key_unique = models.Constraint(
        "UNIQUE(tenant_id, scope_type, scope_code, config_key)",
        "Configuration key must be unique per tenant+scope.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Configuration UUID must be unique.")


class HrmFeatureFlag(models.Model):
    _name = "hrm.feature.flag"
    _inherit = ["hrm.base.mixin"]
    _description = "Feature flag for gradual rollout (SPEC §17.2)."

    tenant_id = fields.Many2one(
        "hrm.tenant",
        ondelete="cascade",
        help="Empty = platform-wide flag.",
    )
    key = fields.Char(required=True)
    enabled = fields.Boolean(default=False)
    configuration = fields.Json(default=dict)
    effective_from = fields.Date(default=fields.Date.today)
    effective_to = fields.Date()

    _tenant_key_unique = models.Constraint(
        "UNIQUE(tenant_id, key)", "Feature flag key must be unique per tenant."
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Feature flag UUID must be unique.")
