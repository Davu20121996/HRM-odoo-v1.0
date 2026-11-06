from odoo import api, fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric
from odoo.exceptions import UserError


class HrmPerformanceCycle(models.Model):
    _name = "hrm.performance.cycle"
    _inherit = ["hrm.base.mixin"]
    _description = "Performance cycle (SPEC §10.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", ondelete="restrict")
    name = fields.Char(required=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("review", "Review"),
            ("calibration", "Calibration"),
            ("finalized", "Finalized"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
    )
    configuration = fields.Json(default=dict)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Cycle UUID must be unique.")

    _TRANSITIONS = {
        "draft": ("open",),
        "open": ("review",),
        "review": ("calibration", "open"),
        "calibration": ("finalized",),
        "finalized": ("closed",),
        "closed": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(
                    f"Cannot move cycle {rec.name} from {rec.status} to {to_status}."
                )
        self.write({"status": to_status})

    def action_open(self):
        self._move("open")

    def action_review(self):
        self._move("review")

    def action_calibrate(self):
        self._move("calibration")

    def action_finalize(self):
        self._move("finalized")

    def action_close(self):
        self._move("closed")


class HrmGoal(models.Model):
    _name = "hrm.goal"
    _inherit = ["hrm.base.mixin"]
    _description = "Goal (SPEC §10.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    cycle_id = fields.Many2one(
        "hrm.performance.cycle", required=True, ondelete="restrict"
    )
    parent_goal_id = fields.Many2one("hrm.goal", ondelete="set null")
    child_ids = fields.One2many("hrm.goal", "parent_goal_id")
    title = fields.Char(required=True)
    description = fields.Text()
    weight = HrmNumeric(digits=(8, 4))
    target_value = HrmMoney(digits=(19, 4))
    actual_value = HrmMoney(digits=(19, 4))
    progress = HrmNumeric(
        digits=(6, 3), compute="_compute_progress", store=True,
        help="actual / target as %. Null target and 0 target yield 0.",
    )
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done"),
         ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Goal UUID must be unique.")

    @api.depends("target_value", "actual_value")
    def _compute_progress(self):
        for rec in self:
            if rec.target_value:
                rec.progress = rec.actual_value / rec.target_value * 100.0
            else:
                rec.progress = 0.0

    def action_activate(self):
        self.write({"status": "active"})

    def action_done(self):
        self.write({"status": "done"})


class HrmKpi(models.Model):
    _name = "hrm.kpi"
    _inherit = ["hrm.base.mixin"]
    _description = "KPI definition (SPEC §10.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    cycle_id = fields.Many2one(
        "hrm.performance.cycle", required=True, ondelete="cascade"
    )
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    measurement_unit = fields.Char()
    target_type = fields.Char(default="numeric")
    configuration = fields.Json(default=dict)

    _cycle_code_unique = models.Constraint(
        "UNIQUE(cycle_id, code)",
        "KPI code must be unique per cycle.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "KPI UUID must be unique.")


class HrmOkr(models.Model):
    _name = "hrm.okr"
    _inherit = ["hrm.base.mixin"]
    _description = "OKR (SPEC §10.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    cycle_id = fields.Many2one(
        "hrm.performance.cycle", required=True, ondelete="cascade"
    )
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    objective = fields.Text(required=True)
    progress = HrmNumeric(digits=(6, 3), default=0.0)
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done")],
        default="draft",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "OKR UUID must be unique.")

    @api.constrains("progress")
    def _check_progress(self):
        for rec in self:
            if not 0 <= rec.progress <= 100:
                raise UserError("OKR progress must be between 0 and 100.")


class HrmCompetency(models.Model):
    _name = "hrm.competency"
    _inherit = ["hrm.base.mixin"]
    _description = "Competency catalogue (SPEC §10.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    description = fields.Text()
    category = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Competency code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Competency UUID must be unique.")


class HrmAppraisal(models.Model):
    _name = "hrm.appraisal"
    _inherit = ["hrm.base.mixin"]
    _description = "Appraisal (SPEC §10.5)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    cycle_id = fields.Many2one(
        "hrm.performance.cycle", required=True, ondelete="restrict"
    )
    reviewer_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    overall_score = HrmNumeric(digits=(8, 4))
    status = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("calibrated", "Calibrated"),
         ("finalized", "Finalized")],
        default="draft",
        required=True,
    )
    comments = fields.Text()
    feedback_ids = fields.One2many("hrm.feedback.360", "appraisal_id")
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Appraisal UUID must be unique.")

    def action_submit(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be submitted.")
        self.write({"status": "submitted"})
        return True

    def action_calibrate(self):
        """Calibrated score = mean of submitted 360 scores, else mean goal
        progress of the employee in this cycle."""
        for rec in self:
            if rec.status != "submitted":
                raise UserError("Only submitted appraisals can be calibrated.")
            scores = rec.feedback_ids.filtered(
                lambda f: f.status == "submitted" and f.score is not False
            ).mapped("score")
            if scores:
                overall = sum(scores) / len(scores)
            else:
                goals = self.env["hrm.goal"].search(
                    [
                        ("tenant_id", "=", rec.tenant_id.id),
                        ("employee_id", "=", rec.employee_id.id),
                        ("cycle_id", "=", rec.cycle_id.id),
                        ("status", "=", "done"),
                    ]
                )
                overall = (
                    sum(goals.mapped("progress")) / len(goals) if goals else 0.0
                )
            rec.write({"overall_score": overall, "status": "calibrated"})
        return True

    def action_finalize(self):
        for rec in self:
            if rec.status != "calibrated":
                raise UserError("Only calibrated appraisals can be finalized.")
        self.write({"status": "finalized"})
        return True


class HrmFeedback360(models.Model):
    _name = "hrm.feedback.360"
    _inherit = ["hrm.base.mixin"]
    _description = "360 feedback (SPEC §10.7)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    appraisal_id = fields.Many2one("hrm.appraisal", required=True, ondelete="cascade")
    reviewer_employee_id = fields.Many2one(
        "hr.employee", required=True, ondelete="restrict"
    )
    relationship_type = fields.Selection(
        [("manager", "Manager"), ("peer", "Peer"), ("report", "Direct Report"),
         ("self", "Self"), ("other", "Other")],
        required=True,
    )
    score = HrmNumeric(digits=(8, 4))
    comments = fields.Text()
    submitted_at = fields.Datetime()
    status = fields.Selection(
        [("pending", "Pending"), ("submitted", "Submitted")],
        default="pending",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Feedback UUID must be unique.")

    def action_submit(self):
        for rec in self:
            if rec.status != "pending":
                raise UserError("Only pending feedback can be submitted.")
        self.write({"status": "submitted", "submitted_at": fields.Datetime.now()})
        return True
