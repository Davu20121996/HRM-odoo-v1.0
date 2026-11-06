from odoo import fields, models
from odoo.exceptions import UserError


class HrmNotification(models.Model):
    _name = "hrm.notification"
    _inherit = ["hrm.base.mixin"]
    _description = "Notification (SPEC §14)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    recipient_user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    channel = fields.Selection(
        [("in_app", "In App"), ("email", 'Email'), ("sms", "SMS"),
         ("push", "Push"), ("webhook", "Webhook")],
        default="in_app",
        required=True,
    )
    template_code = fields.Char(required=True)
    subject = fields.Char()
    payload = fields.Json(default=dict)
    status = fields.Selection(
        [("queued", "Queued"), ("sent", "Sent"), ("read", "Read"), ("failed", "Failed")],
        default="queued",
        required=True,
    )
    scheduled_at = fields.Datetime()
    sent_at = fields.Datetime()
    read_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Notification UUID must be unique.")

    def action_mark_read(self):
        for rec in self:
            if rec.recipient_user_id.id != self.env.uid and not self.env.user.has_group(
                "hrm_base.group_hrm_admin"
            ):
                raise UserError("You can only mark your own notifications as read.")
        self.write({"status": "read", "read_at": fields.Datetime.now()})
        return True

    def action_mark_sent(self):
        for rec in self:
            if rec.status != "queued" and not self.env.context.get("hrm_engine"):
                raise UserError("Only queued notifications can be marked sent.")
        self.write({"status": "sent", "sent_at": fields.Datetime.now()})
        return True

    def unlink(self):
        raise UserError("Notifications are audit trail and cannot be deleted.")
