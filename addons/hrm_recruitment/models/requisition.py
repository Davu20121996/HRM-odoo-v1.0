from odoo import fields, models
from odoo.exceptions import UserError


class HrmJobRequisition(models.Model):
    _name = "hrm.job.requisition"
    _inherit = ["hrm.base.mixin"]
    _description = "Job requisition (SPEC §6.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    department_id = fields.Many2one("hrm.department", required=True, ondelete="restrict")
    position_id = fields.Many2one("hrm.position", ondelete="set null")
    job_id = fields.Many2one("hrm.job", required=True, ondelete="restrict")
    requested_by_id = fields.Many2one("hr.employee", ondelete="set null")
    approved_headcount = fields.Integer(required=True, default=1)
    target_hire_date = fields.Date()
    description = fields.Text()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("open", "Open"),
            ("filled", "Filled"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
        help="Set when the approval runs through the P3 engine.",
    )
    application_ids = fields.One2many("hrm.application", "requisition_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Requisition UUID must be unique.")

    _TRANSITIONS = {
        "draft": ("pending_approval", "cancelled"),
        "pending_approval": ("approved", "cancelled"),
        "approved": ("open", "cancelled"),
        "open": ("filled", "cancelled"),
        "filled": (),
        "cancelled": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(
                    f"Cannot move requisition {rec.display_name} "
                    f"from {rec.status} to {to_status}."
                )
        self.write({"status": to_status})

    def _start_workflow(self):
        self.ensure_one()
        if self.workflow_instance_id:
            return self.workflow_instance_id
        try:
            inst = self.env["hrm.workflow.instance"].start(
                "recruitment", self.tenant_id.id, "hrm.job.requisition",
                entity_id=self.id, entity_uuid=self.uuid,
                requester_employee_id=self.requested_by_id.id if self.requested_by_id else False,
            )
        except Exception:
            return False
        if inst:
            self.with_context(hrm_engine=True).write({"workflow_instance_id": inst.id})
        return inst

    def action_submit(self):
        for rec in self:
            rec._start_workflow()
        self._move("pending_approval")

    def action_approve(self):
        for rec in self:
            if rec.workflow_instance_id and rec.workflow_instance_id.status != "approved":
                raise UserError("Workflow instance must approve first (engine owns transition).")
        self._move("approved")

    def action_open(self):
        self._move("open")

    def action_fill(self):
        self._move("filled")

    def action_cancel(self):
        self._move("cancelled")
