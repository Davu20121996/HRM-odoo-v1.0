from odoo import api, fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric
from odoo.exceptions import UserError


class HrmSkill(models.Model):
    _name = "hrm.skill"
    _inherit = ["hrm.base.mixin"]
    _description = "Skill master (SPEC §11)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    category = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Skill code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Skill UUID must be unique.")


class HrmCourse(models.Model):
    _name = "hrm.course"
    _inherit = ["hrm.base.mixin"]
    _description = "Course (SPEC §11.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    description = fields.Text()
    duration_minutes = fields.Integer()
    provider = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Course code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Course UUID must be unique.")


class HrmTraining(models.Model):
    _name = "hrm.training"
    _inherit = ["hrm.base.mixin"]
    _description = "Training session (SPEC §11.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    course_id = fields.Many2one("hrm.course", required=True, ondelete="restrict")
    trainer_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    location_id = fields.Many2one("hrm.location", ondelete="set null")
    start_at = fields.Datetime(required=True)
    end_at = fields.Datetime(required=True)
    capacity = fields.Integer()
    status = fields.Selection(
        [("draft", "Draft"), ("open", "Open"), ("done", "Done"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )
    enrollment_ids = fields.One2many("hrm.training.enrollment", "training_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Training UUID must be unique.")

    def action_open(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be opened.")
        self.write({"status": "open"})
        return True

    def action_done(self):
        for rec in self:
            if rec.status != "open":
                raise UserError("Only open trainings can be closed.")
        self.write({"status": "done"})
        return True

    def action_cancel(self):
        self.write({"status": "cancelled"})
        return True


class HrmTrainingPlan(models.Model):
    _name = "hrm.training.plan"
    _inherit = ["hrm.base.mixin"]
    _description = "Training plan (SPEC §11.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("done", "Done")],
        default="draft",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Training plan UUID must be unique.")


class HrmTrainingEnrollment(models.Model):
    _name = "hrm.training.enrollment"
    _inherit = ["hrm.base.mixin"]
    _description = "Training enrollment (SPEC §11.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    training_id = fields.Many2one("hrm.training", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    enrolled_at = fields.Datetime(required=True, default=fields.Datetime.now)
    completion_at = fields.Datetime()
    score = HrmNumeric(digits=(8, 4))
    status = fields.Selection(
        [("enrolled", "Enrolled"), ("completed", "Completed"), ("cancelled", "Cancelled")],
        default="enrolled",
        required=True,
    )

    _training_employee_unique = models.Constraint(
        "UNIQUE(training_id, employee_id)",
        "An employee can enroll in a training only once.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Enrollment UUID must be unique.")

    def action_complete(self, score=None):
        for rec in self:
            if rec.status != "enrolled":
                raise UserError("Only enrolled records can be completed.")
        self.write(
            {
                "status": "completed",
                "completion_at": fields.Datetime.now(),
                "score": score if score is not None else self.score,
            }
        )
        return True

    def action_cancel(self):
        for rec in self:
            if rec.status != "enrolled":
                raise UserError("Only enrolled records can be cancelled.")
        self.write({"status": "cancelled"})
        return True


class HrmCertification(models.Model):
    _name = "hrm.certification"
    _inherit = ["hrm.base.mixin"]
    _description = "Certification (SPEC §11.5)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    issuer = fields.Char(required=True)
    certificate_no = fields.Char()
    issued_at = fields.Datetime()
    expires_at = fields.Datetime()
    status = fields.Selection(
        [("valid", "Valid"), ("expired", "Expired"), ("revoked", "Revoked")],
        default="valid",
        required=True,
    )
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Certification UUID must be unique.")


class HrmSkillMatrix(models.Model):
    _name = "hrm.skill.matrix"
    _inherit = ["hrm.base.mixin"]
    _description = "Required skill level per job (SPEC §11.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    job_id = fields.Many2one("hrm.job", ondelete="cascade")
    skill_id = fields.Many2one("hrm.skill", required=True, ondelete="cascade")
    required_level = fields.Selection(
        [("beginner", "Beginner"), ("intermediate", "Intermediate"),
         ("advanced", "Advanced"), ("expert", "Expert")],
        required=True,
    )
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _job_skill_unique = models.Constraint(
        "UNIQUE(job_id, skill_id)",
        "A skill is required once per job.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Skill matrix UUID must be unique.")

    @api.constrains("job_id", "skill_id", "effective_from", "effective_to")
    def _check_global_unique_and_overlap(self):
        from datetime import date as _date
        for rec in self:
            if not rec.job_id:
                dup = self.search([
                    ("id", "!=", rec.id),
                    ("tenant_id", "=", rec.tenant_id.id),
                    ("job_id", "=", False),
                    ("skill_id", "=", rec.skill_id.id),
                ], limit=1)
                if dup:
                    raise UserError("Global skill requirement already exists for this skill.")
            if rec.effective_from:
                rec_end = rec.effective_to or _date.max
                others = self.search([
                    ("id", "!=", rec.id),
                    ("tenant_id", "=", rec.tenant_id.id),
                    ("job_id", "=", rec.job_id.id if rec.job_id else False),
                    ("skill_id", "=", rec.skill_id.id),
                    ("effective_from", "<=", rec_end),
                ]).filtered(lambda o: (o.effective_to or _date.max) >= rec.effective_from)
                if others:
                    raise UserError("Overlapping skill-matrix periods are not allowed.")
