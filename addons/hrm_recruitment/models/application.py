from odoo import fields, models
def _emit(ENV, event_type, tenant_id, aggregate_type, aggregate_id, payload=None, aggregate_uuid=None):
    """Transactional outbox emit (MUST#11): same transaction as business write."""
    try:
        if "hrm.event.outbox" not in ENV:
            return False
        ENV["hrm.event.outbox"].enqueue(
            event_type, aggregate_type, tenant_id,
            aggregate_id=aggregate_id, payload=payload or {},
            correlation_id=aggregate_uuid)
        return True
    except Exception:
        return False

from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric
from odoo.exceptions import UserError


class HrmApplication(models.Model):
    _name = "hrm.application"
    _inherit = ["hrm.base.mixin"]
    _description = "Job application (SPEC §6.3)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    candidate_id = fields.Many2one("hrm.candidate", required=True, ondelete="cascade")
    requisition_id = fields.Many2one(
        "hrm.job.requisition", required=True, ondelete="restrict"
    )
    current_stage_id = fields.Many2one("hrm.recruitment.stage", ondelete="set null")
    applied_at = fields.Datetime(required=True, default=fields.Datetime.now)
    source = fields.Char()
    status = fields.Selection(
        [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("offered", "Offered"),
            ("hired", "Hired"),
            ("rejected", "Rejected"),
            ("withdrawn", "Withdrawn"),
        ],
        default="new",
        required=True,
    )
    rejection_reason = fields.Char()
    interview_ids = fields.One2many("hrm.interview", "application_id")
    offer_ids = fields.One2many("hrm.offer", "application_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Application UUID must be unique.")

    _TRANSITIONS = {
        "new": ("in_progress", "rejected", "withdrawn"),
        "in_progress": ("offered", "rejected", "withdrawn"),
        "offered": ("hired", "rejected", "withdrawn"),
        "hired": (), "rejected": (), "withdrawn": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(f"Cannot move application {rec.id} {rec.status} -> {to_status}.")
        self.write({"status": to_status})

    def action_move_stage(self, stage_id):
        stage = self.env["hrm.recruitment.stage"].browse(stage_id)
        if not stage.exists() or stage.tenant_id.id != self.tenant_id.id:
            raise UserError("Invalid stage for this application.")
        if self.status == "new":
            self._move("in_progress")
        self.write({"current_stage_id": stage.id})
        if stage.stage_type == "rejected":
            self.action_reject("Stage moved to rejected.")
        elif stage.stage_type == "hired":
            self._move("hired")
        elif stage.stage_type == "offer":
            self._move("offered")
        return True

    def action_reject(self, reason=None):
        self._move("rejected")
        self.write({"rejection_reason": reason})
        return True

    def action_withdraw(self):
        self._move("withdrawn")
        return True


class HrmInterview(models.Model):
    _name = "hrm.interview"
    _inherit = ["hrm.base.mixin"]
    _description = "Interview (SPEC §6.5)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    application_id = fields.Many2one("hrm.application", required=True, ondelete="cascade")
    interviewer_employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="restrict"
    )
    scheduled_at = fields.Datetime(required=True)
    duration_minutes = fields.Integer(default=60)
    location = fields.Char()
    meeting_url = fields.Char()
    status = fields.Selection(
        [("scheduled", "Scheduled"), ("done", "Done"), ("cancelled", "Cancelled")],
        default="scheduled",
        required=True,
    )
    evaluation_ids = fields.One2many("hrm.interview.evaluation", "interview_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Interview UUID must be unique.")

    def action_done(self):
        for rec in self:
            if rec.status != "scheduled":
                raise UserError("Only scheduled interviews can be done.")
        self.write({"status": "done"})

    def action_cancel(self):
        for rec in self:
            if rec.status != "scheduled":
                raise UserError("Only scheduled interviews can be cancelled.")
        self.write({"status": "cancelled"})


class HrmInterviewEvaluation(models.Model):
    _name = "hrm.interview.evaluation"
    _inherit = ["hrm.base.mixin"]
    _description = "Interview evaluation (SPEC §6.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    interview_id = fields.Many2one("hrm.interview", required=True, ondelete="cascade")
    evaluator_employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="restrict"
    )
    score = HrmNumeric(digits=(6, 2))
    recommendation = fields.Selection(
        [("hire", "Hire"), ("no_hire", "No Hire"), ("maybe", "Maybe")],
    )
    comments = fields.Text()
    submitted_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Evaluation UUID must be unique.")

    def action_submit(self):
        for rec in self:
            if rec.submitted_at:
                raise UserError("Evaluation already submitted.")
        self.write({"submitted_at": fields.Datetime.now()})


class HrmOffer(models.Model):
    _name = "hrm.offer"
    _inherit = ["hrm.base.mixin"]
    _description = "Job offer; accept creates the employee (SPEC §6.7)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    application_id = fields.Many2one("hrm.application", required=True, ondelete="restrict")
    employee_id = fields.Many2one(
        "hr.employee", readonly=True, ondelete="set null",
        help="Set on accept.",
    )
    offer_no = fields.Char(required=True)
    issued_at = fields.Datetime(required=True, default=fields.Datetime.now)
    expires_at = fields.Datetime()
    base_salary = HrmMoney(digits=(19, 4))
    currency_code = fields.Char(size=3)
    start_date = fields.Date()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_approval", "Pending Approval"),
            ("sent", "Sent"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
            ("expired", "Expired"),
        ],
        default="draft",
        required=True,
    )
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
        help="Set when the approval runs through the P3 engine.",
    )

    _tenant_no_unique = models.Constraint(
        "UNIQUE(tenant_id, offer_no)",
        "Offer number must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Offer UUID must be unique.")

    _TRANSITIONS = {
        "draft": ("pending_approval", "cancelled"),
        "pending_approval": ("sent", "cancelled"),
        "sent": ("accepted", "declined", "expired"),
        "accepted": (),
        "declined": (),
        "expired": (),
        "cancelled": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(
                    f"Cannot move offer {rec.offer_no} from {rec.status} to {to_status}."
                )
        self.write({"status": to_status})

    def action_submit(self):
        for rec in self:
            if not rec.workflow_instance_id:
                try:
                    inst = rec.env["hrm.workflow.instance"].start(
                        "offer", rec.tenant_id.id, "hrm.offer",
                        entity_id=rec.id, entity_uuid=rec.uuid)
                    if inst:
                        rec.with_context(hrm_engine=True).write({"workflow_instance_id": inst.id})
                except Exception:
                    pass
        self._move("pending_approval")

    def action_send(self):
        self.ensure_one()
        if self.status == "pending_approval":
            if self.workflow_instance_id and self.workflow_instance_id.status != "approved":
                raise UserError("Workflow instance must approve first (engine owns transition).")
            self._move("sent")
        elif self.status != "sent":
            raise UserError(f"Cannot send offer in status {self.status}.")
        if self.application_id.status == "in_progress":
            self.application_id._move("offered")
        self.application_id.candidate_id.write({"status": "offer"})

    def action_decline(self):
        self._move("declined")

    def action_expire(self):
        self._move("expired")

    def action_accept(self):
        """Accept the offer: create person (if needed) + employee + primary
        assignment. RECRUITMENT -> EMPLOYEE (master-skill §3)."""
        self.ensure_one()
        if self.status != "sent":
            raise UserError(f"Only a sent offer can be accepted (now {self.status}).")
        if self.employee_id:
            raise UserError("Offer already converted to an employee.")
        candidate = self.application_id.candidate_id
        requisition = self.application_id.requisition_id

        person = candidate.person_id
        if not person:
            person = self.env["hrm.person"].create(
                {
                    "tenant_id": self.tenant_id.id,
                    "first_name": candidate.first_name,
                    "last_name": candidate.last_name,
                    "person_code": candidate.candidate_code,
                }
            )
            candidate.write({"person_id": person.id})

        code = candidate.candidate_code
        if self.env["hr.employee"].search_count(
            [("tenant_id", "=", self.tenant_id.id), ("employee_code", "=", code)]
        ):
            raise UserError(
                f"Employee code {code} already exists. Set a free candidate code first."
            )
        employee = self.env["hr.employee"].create(
            {
                "name": f"{candidate.first_name} {candidate.last_name}",
                "tenant_id": self.tenant_id.id,
                "person_id": person.id,
                "employee_code": code,
                "hire_date": self.start_date,
            }
        )
        assignment = self.env["hrm.employee.assignment"].create(
            {
                "tenant_id": self.tenant_id.id,
                "employee_id": employee.id,
                "company_id": requisition.company_id.id,
                "department_id": requisition.department_id.id,
                "position_id": requisition.position_id.id or False,
                "job_id": requisition.job_id.id or False,
                "assignment_type": "primary",
                "is_primary": True,
                "start_date": self.start_date or fields.Date.today(),
                "reason": f"Hired via offer {self.offer_no}",
            }
        )
        employee.write({"current_assignment_id": assignment.id})
        self.write({"status": "accepted", "employee_id": employee.id})
        _emit(self.env, "EmployeeCreated", self.tenant_id.id, "hr.employee",
              employee.id, {"offer_no": self.offer_no}, aggregate_uuid=employee.uuid if hasattr(employee, "uuid") else None)
        self.application_id.write({"status": "hired"})
        candidate.write({"status": "hired"})
        return employee
