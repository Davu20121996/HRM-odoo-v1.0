from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric


class HrmContractType(models.Model):
    _name = "hrm.contract.type"
    _inherit = ["hrm.base.mixin"]
    _description = "Contract type (SPEC §5.5)"

    tenant_id = fields.Many2one(
        "hrm.tenant", ondelete="cascade",
        help="Empty = global catalogue entry.",
    )
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    employment_category = fields.Selection(
        [
            ("indefinite", "Indefinite"),
            ("fixed_term", "Fixed Term"),
            ("probation", "Probation"),
            ("part_time", "Part Time"),
            ("contractor", "Contractor"),
        ],
        required=True,
    )
    default_duration_days = fields.Integer()
    is_indefinite = fields.Boolean(default=False)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _code_unique = models.Constraint("UNIQUE(code)", "Contract type code must be unique.")
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Contract type UUID must be unique.")


class HrmEmployeeContract(models.Model):
    _name = "hrm.employee.contract"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee contract, state machine (SPEC §5.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    contract_type_id = fields.Many2one("hrm.contract.type", required=True, ondelete="restrict")
    contract_no = fields.Char(required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date()
    probation_start = fields.Date()
    probation_end = fields.Date()
    base_salary = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, default="VND", size=3)
    working_hours_per_week = HrmNumeric(digits=(6, 2))
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved · Awaiting activation"),
            ("active", "In effect"),
            ("expired", "Contract closed"),
        ],
        default="draft",
        required=True,
    )
    signed_at = fields.Datetime()
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")

    _tenant_no_unique = models.Constraint(
        "UNIQUE(tenant_id, contract_no)",
        "Contract number must be unique per tenant.",
    )

    def unlink(self):
        if any(r.status in ("active", "approved") for r in self):
            raise UserError("Active/approved contracts cannot be hard-deleted. Expire instead. (MUST#5)")
        return super().unlink()
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Contract UUID must be unique.")

    _TRANSITIONS = {
        "draft": ("pending_approval",),
        "pending_approval": ("approved", "draft"),
        "approved": ("active",),
        "active": ("expired",),
        "expired": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(
                    f"Cannot move contract {rec.contract_no} "
                    f"from {rec.status} to {to_status}."
                )
        self.write({"status": to_status})

    def action_submit(self):
        self._move("pending_approval")

    def action_approve(self):
        self._move("approved")

    def action_activate(self):
        self._move("active")

    def action_expire(self):
        self._move("expired")


class HrmEmployeeAssignment(models.Model):
    """Canonical historical org assignment. Transfer = new record (SPEC §5.7)."""

    _name = "hrm.employee.assignment"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee assignment (SPEC §5.7)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    business_unit_id = fields.Many2one("hrm.business.unit", ondelete="restrict")
    department_id = fields.Many2one("hrm.department", required=True, ondelete="restrict")
    position_id = fields.Many2one("hrm.position", ondelete="restrict")
    job_id = fields.Many2one("hrm.job", ondelete="restrict")
    grade_id = fields.Many2one("hrm.grade", ondelete="restrict")
    location_id = fields.Many2one("hrm.location", ondelete="restrict")
    manager_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    assignment_type = fields.Selection(
        [("primary", "Primary"), ("secondary", "Secondary")],
        default="primary",
        required=True,
    )
    is_primary = fields.Boolean(default=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date()
    status = fields.Selection(
        [("active", "Active"), ("closed", "Closed")],
        default="active",
        required=True,
    )
    reason = fields.Char()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Assignment UUID must be unique.")

    def unlink(self):
        raise UserError("Assignments are historical truth and cannot be hard-deleted. Close instead. (MUST#5)")

    @api.constrains("employee_id", "company_id", "assignment_type", "start_date", "end_date")
    def _check_no_overlap_primary(self):
        from datetime import date

        try:
            self.env.cr.execute(
                'SELECT id FROM hrm_employee_assignment WHERE employee_id IN %s FOR UPDATE',
                (tuple(self.mapped("employee_id").ids or (0,)),),
            )
        except Exception:
            pass
        for rec in self:
            if rec.assignment_type != "primary" or not rec.start_date:
                continue
            rec_end = rec.end_date or date.max
            domain = [
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("company_id", "=", rec.company_id.id),
                ("assignment_type", "=", "primary"),
                ("start_date", "<=", rec_end),
            ]
            others = self.search(domain).filtered(
                lambda o: (o.end_date or date.max) >= rec.start_date
            )
            if others:
                raise UserError(
                    "Overlapping primary assignments are not allowed. "
                    "Close the current one before opening a new assignment."
                )


class HrmSalaryHistory(models.Model):
    _name = "hrm.salary.history"
    _description = "Immutable compensation history (SPEC §5.11)."
    _order = "effective_from desc"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    contract_id = fields.Many2one("hrm.employee.contract", ondelete="set null")
    effective_from = fields.Date(required=True)
    effective_to = fields.Date()
    base_salary = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    change_type = fields.Char(required=True)
    change_reason = fields.Char()
    source_type = fields.Char()
    source_id = fields.Integer()

    def write(self, vals):
        raise UserError("Salary history is immutable. Create a new record instead.")

    def unlink(self):
        raise UserError("Salary history is immutable.")


class HrmEmploymentStatusHistory(models.Model):
    _name = "hrm.employment.status.history"
    _description = "Immutable employment status history (SPEC §5.12)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    from_status = fields.Char()
    to_status = fields.Char(required=True)
    effective_at = fields.Datetime(required=True, default=fields.Datetime.now)
    reason = fields.Char()
    actor_id = fields.Many2one("res.users", ondelete="set null")
    reference_type = fields.Char()
    reference_id = fields.Integer()

    def write(self, vals):
        raise UserError("Employment status history is immutable.")

    def unlink(self):
        raise UserError("Employment status history is immutable.")
