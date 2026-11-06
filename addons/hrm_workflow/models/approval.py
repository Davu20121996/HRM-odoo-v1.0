from odoo import api, fields, models
from odoo.exceptions import UserError


class HrmApprovalRequest(models.Model):
    """One approver's verdict on one step. Immutable once decided, except
    HRM Admin correction which is audit-trailed (SPEC §12 rules)."""

    _name = "hrm.approval.request"
    _inherit = ["hrm.base.mixin"]
    _description = "Approval request (SPEC §12.4)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    instance_id = fields.Many2one(
        "hrm.workflow.instance", required=True, ondelete="cascade"
    )
    step_id = fields.Many2one("hrm.workflow.step", required=True, ondelete="restrict")
    approver_user_id = fields.Many2one("res.users", ondelete="set null")
    approver_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    decision = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"),
         ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="pending",
        required=True,
    )
    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"),
         ("rejected", "Rejected"), ("cancelled", "Cancelled")],
        default="pending",
        required=True,
    )
    comment = fields.Text()
    decided_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Approval UUID must be unique.")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("hrm_engine") and not self.env.user.has_group("hrm_base.group_hrm_admin"):
            raise UserError("Approvals are created by the workflow engine only.")
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        # Status must be read fresh: field cache is shared across envs in one
        # transaction, so a stale recordset could otherwise bypass this guard.
        self.invalidate_recordset()
        for rec in self:
            if rec.status != "pending" and any(
                f in vals for f in ("decision", "status", "comment", "decided_at")
            ):
                if not self.env.user.has_group("hrm_base.group_hrm_admin"):
                    raise UserError("Approval history is immutable once decided.")
                self.env["hrm.audit.log"].sudo().create(
                    {
                        "tenant_id": rec.tenant_id.id,
                        "actor_user_id": self.env.uid,
                        "action": "UPDATE",
                        "entity_type": "hrm.approval.request",
                        "entity_id": rec.id,
                        "entity_uuid": rec.uuid,
                        "old_value": {"decision": rec.decision},
                        "new_value": {"decision": vals.get("decision", rec.decision)},
                    }
                )
        return super().write(vals)

    def unlink(self):
        raise UserError("Approval history cannot be deleted.")

    # -- approver API --------------------------------------------------

    def _own_pending(self):
        rec = self.filtered(
            lambda a: a.status == "pending" and a.approver_user_id.id == self.env.uid
        )
        if not rec:
            raise UserError("No pending approval for you on this request.")
        if len(rec) > 1:
            raise UserError("Ambiguous approval request.")
        return rec

    def action_approve(self, comment=None):
        rec = self._own_pending()
        sudo_rec = rec.sudo().with_context(hrm_engine=True)
        sudo_rec.write(
            {"decision": "approved", "status": "approved",
             "comment": comment, "decided_at": fields.Datetime.now()}
        )
        sudo_rec.instance_id._on_step_decided()
        return True

    def action_reject(self, comment=None):
        rec = self._own_pending()
        sudo_rec = rec.sudo().with_context(hrm_engine=True)
        sudo_rec.write(
            {"decision": "rejected", "status": "rejected",
             "comment": comment, "decided_at": fields.Datetime.now()}
        )
        sudo_rec.instance_id._on_step_decided()
        return True
