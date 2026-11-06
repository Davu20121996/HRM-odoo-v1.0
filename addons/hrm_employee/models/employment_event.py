"""Probation / promotion / transfer (SPEC §5.8-5.10).

Transfer/promotion = new assignment/contract/salary, never overwrite (MUST#9).
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hrm_base.models.mixins import HrmNumeric


class HrmProbation(models.Model):
    _name = "hrm.probation"
    _inherit = ["hrm.base.mixin"]
    _description = "Probation (SPEC §5.8)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    contract_id = fields.Many2one("hrm.employee.contract", required=True, ondelete="restrict")
    start_date = fields.Date(required=True)
    planned_end_date = fields.Date(required=True)
    actual_end_date = fields.Date()
    result = fields.Selection(
        [("passed", "Passed"), ("failed", "Failed"), ("extended", "Extended")],
    )
    status = fields.Selection(
        [("pending", "Pending"), ("active", "Active"), ("passed", "Passed"),
         ("failed", "Failed"), ("extended", "Extended")],
        default="pending", required=True,
    )
    notes = fields.Text()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Probation UUID must be unique.")

    _TRANSITIONS = {
        "pending": ("active",),
        "active": ("passed", "failed", "extended"),
        "extended": ("passed", "failed"),
        "passed": (), "failed": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(f"Cannot move probation {rec.id} {rec.status} -> {to_status}.")
        self.write({"status": to_status})

    def action_start(self):
        self._move("active")

    def action_pass(self):
        self._move("passed")
        self.write({"result": "passed", "actual_end_date": fields.Date.today()})

    def action_fail(self):
        self._move("failed")
        self.write({"result": "failed", "actual_end_date": fields.Date.today()})

    def action_extend(self, new_planned_end=False):
        self._move("extended")
        vals = {"result": "extended"}
        if new_planned_end:
            vals["planned_end_date"] = new_planned_end
        self.write(vals)

    def unlink(self):
        if any(r.status != "pending" for r in self):
            raise UserError("Only pending probations can be deleted.")
        return super().unlink()


class HrmPromotion(models.Model):
    _name = "hrm.promotion"
    _inherit = ["hrm.base.mixin"]
    _description = "Promotion (SPEC §5.9)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    from_assignment_id = fields.Many2one("hrm.employee.assignment", ondelete="set null")
    to_position_id = fields.Many2one("hrm.position", required=True, ondelete="restrict")
    from_grade_id = fields.Many2one("hrm.grade", ondelete="set null")
    to_grade_id = fields.Many2one("hrm.grade", ondelete="set null")
    effective_date = fields.Date(required=True)
    reason = fields.Char()
    status = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("done", "Done"), ("cancelled", "Cancelled")],
        default="draft", required=True,
    )
    workflow_instance_id = fields.Many2one("hrm.workflow.instance", readonly=True, ondelete="set null")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Promotion UUID must be unique.")

    def action_approve(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be approved.")
        self.write({"status": "approved"})

    def action_done(self):
        """Apply: close old primary assignment, open new one (MUST#9)."""
        for rec in self:
            if rec.status != "approved":
                raise UserError("Only approved promotions can be applied.")
        for rec in self.with_context(hrm_engine=True):
            old = rec.from_assignment_id
            if old and old.status == "active":
                old.write({"status": "closed", "end_date": rec.effective_date})
            self.env["hrm.employee.assignment"].create({
                "tenant_id": rec.tenant_id.id,
                "employee_id": rec.employee_id.id,
                "company_id": (old.company_id.id if old else rec.employee_id.company_id.id),
                "department_id": (old.department_id.id if old else rec.employee_id.department_id.id),
                "position_id": rec.to_position_id.id,
                "job_id": rec.to_position_id.job_id.id,
                "grade_id": rec.to_grade_id.id if rec.to_grade_id else False,
                "start_date": rec.effective_date,
                "assignment_type": "primary",
                "is_primary": True,
                "reason": f"promotion:{rec.id}",
            })
            rec.write({"status": "done"})
        return True

    def unlink(self):
        if any(r.status != "draft" for r in self):
            raise UserError("Only draft promotions can be deleted.")
        return super().unlink()


class HrmTransfer(models.Model):
    _name = "hrm.transfer"
    _inherit = ["hrm.base.mixin"]
    _description = "Transfer (SPEC §5.10)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    from_company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    to_company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    from_department_id = fields.Many2one("hrm.department", ondelete="set null")
    to_department_id = fields.Many2one("hrm.department", ondelete="set null")
    from_position_id = fields.Many2one("hrm.position", ondelete="set null")
    to_position_id = fields.Many2one("hrm.position", ondelete="set null")
    effective_date = fields.Date(required=True)
    reason = fields.Char()
    status = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("done", "Done"), ("cancelled", "Cancelled")],
        default="draft", required=True,
    )
    workflow_instance_id = fields.Many2one("hrm.workflow.instance", readonly=True, ondelete="set null")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Transfer UUID must be unique.")

    def action_approve(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be approved.")
        self.write({"status": "approved"})

    def action_done(self):
        for rec in self:
            if rec.status != "approved":
                raise UserError("Only approved transfers can be applied.")
        for rec in self.with_context(hrm_engine=True):
            old_assignments = self.env["hrm.employee.assignment"].search([
                ("employee_id", "=", rec.employee_id.id),
                ("company_id", "=", rec.from_company_id.id),
                ("status", "=", "active"),
                ("assignment_type", "=", "primary"),
            ])
            old_assignments.write({"status": "closed", "end_date": rec.effective_date})
            self.env["hrm.employee.assignment"].create({
                "tenant_id": rec.tenant_id.id,
                "employee_id": rec.employee_id.id,
                "company_id": rec.to_company_id.id,
                "department_id": rec.to_department_id.id if rec.to_department_id else False,
                "position_id": rec.to_position_id.id if rec.to_position_id else False,
                "start_date": rec.effective_date,
                "assignment_type": "primary",
                "is_primary": True,
                "reason": f"transfer:{rec.id}",
            })
            rec.write({"status": "done"})
        return True

    def unlink(self):
        if any(r.status != "draft" for r in self):
            raise UserError("Only draft transfers can be deleted.")
        return super().unlink()
