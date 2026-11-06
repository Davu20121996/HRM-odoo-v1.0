from odoo import api, fields, models
from odoo.exceptions import UserError


class HrmWorkflowDefinition(models.Model):
    _name = "hrm.workflow.definition"
    _inherit = ["hrm.base.mixin"]
    _description = "Workflow definition (SPEC §12.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    entity_type = fields.Char(
        required=True, help="Model the workflow governs, e.g. hrm.leave.request."
    )
    version = fields.Integer(default=1, required=True)
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
        default="draft",
        required=True,
    )
    configuration = fields.Json(default=dict)
    step_ids = fields.One2many("hrm.workflow.step", "definition_id", order="sequence_no")

    _tenant_code_version_unique = models.Constraint(
        "UNIQUE(tenant_id, code, version)",
        "Workflow code+version must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Definition UUID must be unique.")

    def action_activate(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be activated.")
        self.write({"status": "active"})

    def action_archive(self):
        for rec in self:
            if rec.status != "active":
                raise UserError("Only active definitions can be archived.")
        self.write({"status": "archived"})

    def unlink(self):
        if any(r.status != "draft" for r in self):
            raise UserError("Only draft definitions can be deleted.")
        return super().unlink()


class HrmWorkflowStep(models.Model):
    _name = "hrm.workflow.step"
    _inherit = ["hrm.base.mixin"]
    _description = "Workflow step (SPEC §12.3)"
    _order = "sequence_no"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    definition_id = fields.Many2one(
        "hrm.workflow.definition", required=True, ondelete="cascade"
    )
    step_code = fields.Char(required=True)
    name = fields.Char(required=True)
    sequence_no = fields.Integer(default=10, required=True)
    approver_type = fields.Selection(
        [
            ("direct_manager", "Direct Manager"),
            ("specific_user", "Specific User"),
            ("specific_employee", "Specific Employee"),
            ("role", "Role"),
        ],
        required=True,
    )
    approver_user_id = fields.Many2one("res.users", ondelete="set null")
    approver_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    approver_role_id = fields.Many2one("hrm.role", ondelete="set null")
    configuration = fields.Json(default=dict)

    _definition_step_unique = models.Constraint(
        "UNIQUE(definition_id, step_code)",
        "Step code must be unique per definition.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Step UUID must be unique.")


class HrmWorkflowInstance(models.Model):
    """Engine-owned instance. Business modules only hold workflow_instance_id
    and call start/approve/reject — direct writes to status are rejected
    (SPEC §12 rules)."""

    _name = "hrm.workflow.instance"
    _inherit = ["hrm.base.mixin"]
    _description = "Workflow instance (SPEC §12.2)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    definition_id = fields.Many2one(
        "hrm.workflow.definition", required=True, ondelete="restrict"
    )
    entity_type = fields.Char(required=True)
    entity_id = fields.Integer()
    entity_uuid = fields.Char()
    current_state = fields.Char()
    started_at = fields.Datetime(required=True, default=fields.Datetime.now)
    started_by_id = fields.Many2one("res.users", ondelete="set null")
    completed_at = fields.Datetime()
    status = fields.Selection(
        [
            ("in_progress", "In Progress"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="in_progress",
        required=True,
    )
    approval_ids = fields.One2many("hrm.approval.request", "instance_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Instance UUID must be unique.")

    # -- engine guards -------------------------------------------------

    def write(self, vals):
        if not self.env.context.get("hrm_engine") and any(
            f in vals for f in ("status", "current_state", "completed_at")
        ):
            raise UserError("Workflow state is engine-owned. Use approve/reject/cancel.")
        return super().write(vals)

    # -- engine API ----------------------------------------------------

    @api.model
    def start(self, definition_code, tenant_id, entity_type, entity_id=None,
              entity_uuid=None, requester_employee_id=None):
        definition = self.env["hrm.workflow.definition"].search(
            [
                ("tenant_id", "=", tenant_id),
                ("code", "=", definition_code),
                ("status", "=", "active"),
            ],
            order="version desc",
            limit=1,
        )
        if not definition:
            raise UserError(f"No active workflow definition '{definition_code}'.")
        if not definition.step_ids:
            raise UserError(f"Workflow '{definition_code}' has no steps.")
        # NOTE: create in the caller's env (so access rights apply), and never
        # return a recordset carrying the hrm_engine flag — with_user/
        # with_context preserve context and would leak the flag to callers.
        instance = self.create(
            {
                "tenant_id": tenant_id,
                "definition_id": definition.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_uuid": entity_uuid,
                "started_by_id": self.env.uid,
            }
        )
        instance.with_context(hrm_engine=True)._enter_step(
            definition.step_ids[0], requester_employee_id
        )
        return instance

    def action_cancel(self, reason=None):
        for rec in self:
            if rec.status != "in_progress":
                continue
            sudo_rec = rec.sudo().with_context(hrm_engine=True)
            sudo_rec.write(
                {"status": "cancelled", "current_state": "cancelled",
                 "completed_at": fields.Datetime.now()}
            )
            sudo_rec.approval_ids.filtered(lambda a: a.status == "pending").write(
                {"status": "cancelled", "decision": "cancelled"}
            )
        return True

    # -- internals -----------------------------------------------------

    def _enter_step(self, step, requester_employee_id=None):
        self.ensure_one()
        sudo_self = self.sudo()
        sudo_self.write({"current_state": step.step_code})
        for user_id, employee_id in sudo_self._resolve_approvers(step, requester_employee_id):
            sudo_self.env["hrm.approval.request"].with_context(hrm_engine=True).create(
                {
                    "tenant_id": sudo_self.tenant_id.id,
                    "instance_id": sudo_self.id,
                    "step_id": step.id,
                    "approver_user_id": user_id,
                    "approver_employee_id": employee_id,
                }
            )
            if user_id:
                sudo_self.env["hrm.notification"].with_context(hrm_engine=True).create(
                    {
                        "tenant_id": sudo_self.tenant_id.id,
                        "recipient_user_id": user_id,
                        "channel": "in_app",
                        "template_code": "workflow.approval_needed",
                        "subject": f"Approval needed: {sudo_self.definition_id.name}",
                        "payload": {
                            "instance_id": sudo_self.id,
                            "step": step.step_code,
                            "entity_type": sudo_self.entity_type,
                            "entity_id": sudo_self.entity_id,
                        },
                        "status": "queued",
                    }
                )

    def _resolve_approvers(self, step, requester_employee_id=None):
        """Return list of (user_id, employee_id) tuples."""
        if step.approver_type == "specific_user":
            if not step.approver_user_id:
                raise UserError(f"Step {step.step_code} needs a specific user.")
            return [(step.approver_user_id.id, False)]
        if step.approver_type == "specific_employee":
            emp = step.approver_employee_id
            if not emp:
                raise UserError(f"Step {step.step_code} needs a specific employee.")
            return [(emp.user_id.id or False, emp.id)]
        if step.approver_type == "direct_manager":
            if not requester_employee_id:
                raise UserError(
                    f"Step {step.step_code} needs requester_employee_id for direct manager."
                )
            manager = self._find_manager(requester_employee_id)
            if not manager:
                raise UserError("No direct manager found for the requester.")
            return [(manager.user_id.id or False, manager.id)]
        if step.approver_type == "role":
            if not step.approver_role_id:
                raise UserError(f"Step {step.step_code} needs a role.")
            today = fields.Date.today()
            links = self.env["hrm.user.role"].search(
                [("role_id", "=", step.approver_role_id.id)]
            )
            links = links.filtered(
                lambda l: (l.effective_from or today) <= today
                and (not l.effective_to or l.effective_to >= today)
            )
            users = links.mapped("user_id")
            if not users:
                raise UserError(f"No active users hold role {step.approver_role_id.code}.")
            return [(u.id, False) for u in users]
        raise UserError(f"Unknown approver type on step {step.step_code}.")

    def _find_manager(self, employee_id):
        today = fields.Date.today()
        if "hrm.reporting.line" in self.env:
            line = self.env["hrm.reporting.line"].search(
                [
                    ("employee_id", "=", employee_id),
                    ("relationship_type", "=", "line_manager"),
                    ("effective_from", "<=", today),
                ],
                order="effective_from desc",
                limit=1,
            )
            if line and (not line.effective_to or line.effective_to >= today):
                return line.manager_employee_id
        employee = self.env["hr.employee"].browse(employee_id)
        return employee.parent_id or False

    def _on_step_decided(self):
        """Called (engine context) after each decision."""
        for rec in self:
            if rec.status != "in_progress":
                continue
            current = rec.approval_ids.filtered(
                lambda a: a.step_id.step_code == rec.current_state
            )
            if any(a.status == "rejected" for a in current):
                rec.write({"status": "rejected", "current_state": "rejected",
                           "completed_at": fields.Datetime.now()})
                current.filtered(lambda a: a.status == "pending").write(
                    {"status": "cancelled", "decision": "cancelled"}
                )
                rec._notify_starter("rejected")
            elif current and all(a.status == "approved" for a in current):
                steps = rec.definition_id.step_ids.sorted("sequence_no")
                codes = [s.step_code for s in steps]
                nxt = codes.index(rec.current_state) + 1
                if nxt < len(steps):
                    rec._enter_step(steps[nxt])
                else:
                    rec.write({"status": "approved", "current_state": "approved",
                               "completed_at": fields.Datetime.now()})
                    rec._notify_starter("approved")

    def _notify_starter(self, outcome):
        for rec in self:
            if rec.started_by_id:
                self.env["hrm.notification"].with_context(hrm_engine=True).create(
                    {
                        "tenant_id": rec.tenant_id.id,
                        "recipient_user_id": rec.started_by_id.id,
                        "channel": "in_app",
                        "template_code": f"workflow.{outcome}",
                        "subject": f"{rec.definition_id.name}: {outcome}",
                        "payload": {"instance_id": rec.id},
                        "status": "queued",
                    }
                )
