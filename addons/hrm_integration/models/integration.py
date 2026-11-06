from odoo import fields, models
from odoo.exceptions import UserError


class HrmIntegrationConnection(models.Model):
    _name = "hrm.integration.connection"
    _inherit = ["hrm.base.mixin"]
    _description = "External integration connection (SPEC §18.5)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    provider = fields.Char(
        required=True, help="e.g. zalo, device_vendor, bank, tax_portal."
    )
    connection_type = fields.Selection(
        [("oauth", "OAuth"), ("api_key", "API Key"), ("webhook", "Webhook"),
         ("file", "File"), ("other", "Other")],
        default="api_key",
        required=True,
    )
    external_account_id = fields.Char()
    configuration = fields.Json(
        default=dict,
        help="Non-secret settings only. Credentials live in the secret manager.",
    )
    credential_reference = fields.Char(
        help="Secret manager reference. Never store raw secrets here."
    )
    status = fields.Selection(
        [("draft", "Draft"), ("connected", "Connected"), ("suspended", "Suspended")],
        default="draft",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Connection UUID must be unique.")

    def action_connect(self):
        for rec in self:
            if rec.status not in ("draft", "suspended"):
                raise UserError("Only draft/suspended connections can connect.")
            if not rec.configuration or not rec.configuration.get("base_url"):
                raise UserError("configuration.base_url is required to connect.")
        self.write({"status": "connected"})
        return True

    def action_suspend(self):
        self.write({"status": "suspended"})
        return True


class HrmImportJob(models.Model):
    _name = "hrm.import.job"
    _inherit = ["hrm.base.mixin"]
    _description = "Bulk import job with progress tracking (SPEC §18.6)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    entity_type = fields.Char(required=True)
    file_storage_key = fields.Char(required=True)
    mapping = fields.Json(default=dict)
    total_rows = fields.Integer(default=0)
    processed_rows = fields.Integer(default=0)
    success_rows = fields.Integer(default=0)
    failed_rows = fields.Integer(default=0)
    status = fields.Selection(
        [("draft", "Draft"), ("running", "Running"), ("done", "Done"),
         ("failed", "Failed")],
        default="draft",
        required=True,
    )
    error_report_storage_key = fields.Char()
    started_at = fields.Datetime()
    completed_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Import job UUID must be unique.")

    def action_start(self, total_rows=0):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be started.")
        self.write(
            {"status": "running", "total_rows": total_rows,
             "started_at": fields.Datetime.now()}
        )
        return True

    def action_add_result(self, success=True, count=1):
        for rec in self:
            if rec.status != "running":
                raise UserError("Job is not running.")
            rec.write(
                {
                    "processed_rows": rec.processed_rows + count,
                    "success_rows": rec.success_rows + (count if success else 0),
                    "failed_rows": rec.failed_rows + (0 if success else count),
                }
            )
        return True

    def action_finish(self):
        for rec in self:
            if rec.status != "running":
                raise UserError("Job is not running.")
        self.write({"status": "done", "completed_at": fields.Datetime.now()})
        return True

    def action_fail(self, error=None):
        self.write(
            {
                "status": "failed",
                "completed_at": fields.Datetime.now(),
                "error_report_storage_key": (error or "")[:500],
            }
        )
        return True
