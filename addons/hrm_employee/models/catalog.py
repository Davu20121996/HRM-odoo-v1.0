from odoo import fields, models

from odoo.addons.hrm_base.models.mixins import HrmMoney


class HrmJob(models.Model):
    _name = "hrm.job"
    _inherit = ["hrm.base.mixin"]
    _description = "Reusable job definition (SPEC §5.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    hr_job_id = fields.Many2one(
        "hr.job", ondelete="set null",
        help="Adapter link to the Odoo job (master-skill §7).",
    )
    code = fields.Char(required=True)
    title = fields.Char(required=True)
    description = fields.Text()
    grade_id = fields.Many2one("hrm.grade", ondelete="set null")
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Job code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Job UUID must be unique.")


class HrmGrade(models.Model):
    _name = "hrm.grade"
    _inherit = ["hrm.base.mixin"]
    _description = "Grade / salary band (SPEC §5.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    level = fields.Integer()
    min_salary = HrmMoney(digits=(19, 4))
    max_salary = HrmMoney(digits=(19, 4))
    currency_code = fields.Char(size=3)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Grade code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Grade UUID must be unique.")


class HrmPosition(models.Model):
    _name = "hrm.position"
    _inherit = ["hrm.base.mixin"]
    _description = "Concrete organizational seat (SPEC §5.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    department_id = fields.Many2one("hrm.department", required=True, ondelete="restrict")
    job_id = fields.Many2one("hrm.job", required=True, ondelete="restrict")
    grade_id = fields.Many2one("hrm.grade", ondelete="set null")
    location_id = fields.Many2one("hrm.location", ondelete="set null")
    code = fields.Char(required=True)
    title = fields.Char(required=True)
    headcount_limit = fields.Integer(default=1)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Position code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Position UUID must be unique.")


class HrmReportingLine(models.Model):
    _name = "hrm.reporting.line"
    _inherit = ["hrm.base.mixin"]
    _description = "Manager <-> employee reporting line (SPEC §5.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    manager_employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    relationship_type = fields.Selection(
        [
            ("line_manager", "Line Manager"),
            ("functional_manager", "Functional Manager"),
            ("matrix_manager", "Matrix Manager"),
        ],
        default="line_manager",
        required=True,
    )
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _no_self_report = models.Constraint(
        "CHECK(manager_employee_id <> employee_id)",
        "An employee cannot report to themselves.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Reporting line UUID must be unique.")
