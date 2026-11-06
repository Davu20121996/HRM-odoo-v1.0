from odoo import fields, models


class HrmCandidate(models.Model):
    _name = "hrm.candidate"
    _inherit = ["hrm.base.mixin"]
    _description = "Candidate (SPEC §6.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    person_id = fields.Many2one(
        "hrm.person", ondelete="set null",
        help="Linked once the candidate becomes a known person/employee.",
    )
    candidate_code = fields.Char(required=True)
    first_name = fields.Char(required=True)
    last_name = fields.Char(required=True)
    email = fields.Char()
    phone = fields.Char()
    source = fields.Char()
    status = fields.Selection(
        [
            ("new", "New"),
            ("screening", "Screening"),
            ("interview", "Interview"),
            ("offer", "Offer"),
            ("hired", "Hired"),
            ("rejected", "Rejected"),
        ],
        default="new",
        required=True,
    )
    resume_attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    application_ids = fields.One2many("hrm.application", "candidate_id")

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, candidate_code)",
        "Candidate code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Candidate UUID must be unique.")


class HrmRecruitmentStage(models.Model):
    _name = "hrm.recruitment.stage"
    _inherit = ["hrm.base.mixin"]
    _description = "Recruitment pipeline stage (SPEC §6.4)"
    _order = "sequence_no"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    pipeline_code = fields.Char(default="default")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    sequence_no = fields.Integer(default=10, required=True)
    stage_type = fields.Selection(
        [
            ("screen", "Screen"),
            ("interview", "Interview"),
            ("offer", "Offer"),
            ("hired", "Hired"),
            ("rejected", "Rejected"),
        ],
        required=True,
    )
    is_terminal = fields.Boolean(default=False)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, pipeline_code, code)",
        "Stage code must be unique per tenant+pipeline.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Stage UUID must be unique.")
