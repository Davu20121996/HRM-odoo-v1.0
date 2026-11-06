from odoo import api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    """Adapter: HRM employee -> Odoo hr.employee (master-skill §7).

    One employee links exactly one person (SPEC §4.2). History lives in
    hrm.employee.assignment / hrm.employee.contract / hrm.salary.history —
    never overwritten on this record.
    """

    _inherit = ["hr.employee", "hrm.base.mixin"]
    _description = "Employee (SPEC §4.2)"

    tenant_id = fields.Many2one(
        "hrm.tenant",
        ondelete="restrict",
        help="Empty only for pre-existing/system rows (adapter reality).",
    )
    person_id = fields.Many2one("hrm.person", ondelete="restrict")
    employee_code = fields.Char()
    hire_date = fields.Date()
    termination_date = fields.Date()
    current_assignment_id = fields.Many2one("hrm.employee.assignment", ondelete="set null")
    current_contract_id = fields.Many2one("hrm.employee.contract", ondelete="set null")
    current_status = fields.Selection(
        [
            ("hired", "Hired"),
            ("onboarding", "Onboarding"),
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("termination_pending", "Termination Pending"),
            ("terminated", "Terminated"),
            ("alumni", "Alumni"),
        ],
        default="hired",
        required=True,
    )
    status_reason = fields.Char()

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, employee_code)",
        "Employee code must be unique per tenant.",
    )
    _tenant_person_unique = models.Constraint(
        "UNIQUE(tenant_id, person_id)",
        "A person can have only one employee record per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Employee UUID must be unique.")

    # -- state machine: only declared transitions are allowed ----------

    _TRANSITIONS = {
        "hired": ("onboarding",),
        "onboarding": ("active", "terminated"),
        "active": ("suspended", "termination_pending", "terminated"),
        "suspended": ("active", "termination_pending", "terminated"),
        "termination_pending": ("terminated", "active"),
        "terminated": ("alumni", "active"),
        "alumni": ("active",),
    }

    def _move_status(self, to_status, reason=None):
        for rec in self:
            allowed = rec._TRANSITIONS.get(rec.current_status, ())
            if to_status not in allowed:
                raise UserError(
                    f"Cannot move employee {rec.display_name} "
                    f"from {rec.current_status} to {to_status}."
                )
        history_vals = [
            {
                "tenant_id": rec.tenant_id.id or False,
                "employee_id": rec.id,
                "from_status": rec.current_status,
                "to_status": to_status,
                "reason": reason,
            }
            for rec in self
        ]
        self.write({"current_status": to_status, "status_reason": reason})
        self.env["hrm.employment.status.history"].sudo().create(history_vals)

    def action_onboard(self):
        self._move_status("onboarding")

    def action_activate(self):
        self._move_status("active")

    def action_suspend(self, reason=None):
        self._move_status("suspended", reason)

    def action_terminate(self, reason=None):
        self._move_status("terminated", reason)
