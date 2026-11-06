from odoo import api, fields, models
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


class HrmPayrollPeriod(models.Model):
    _name = "hrm.payroll.period"
    _inherit = ["hrm.base.mixin"]
    _description = "Payroll period (SPEC §9.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    period_code = fields.Char(required=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    payment_date = fields.Date()
    status = fields.Selection(
        [
            ("open", "Open"),
            ("processing", "Processing"),
            ("calculated", "Calculated"),
            ("review", "Review"),
            ("approved", "Approved"),
            ("finalized", "Finalized"),
            ("paid", "Paid"),
        ],
        default="open",
        required=True,
    )
    payroll_ids = fields.One2many("hrm.payroll", "period_id")

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, period_code)",
        "Period code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Period UUID must be unique.")

    @api.constrains("period_start", "period_end")
    def _check_dates(self):
        for rec in self:
            if rec.period_end < rec.period_start:
                raise UserError("Period end must be after start.")

    _TRANSITIONS = {
        "open": ("processing",),
        "processing": ("calculated",),
        "calculated": ("review",),
        "review": ("approved",),
        "approved": ("finalized",),
        "finalized": ("paid",),
        "paid": (),
    }

    def _move(self, to_status):
        for rec in self:
            if to_status not in rec._TRANSITIONS.get(rec.status, ()):
                raise UserError(f"Cannot move period {rec.period_code} {rec.status} -> {to_status}.")
        self.write({"status": to_status})

    def action_start_processing(self):
        self._move("processing")

    def action_mark_calculated(self):
        self._move("calculated")

    def action_to_review(self):
        self._move("review")

    def action_approve(self):
        self._move("approved")

    def action_finalize(self):
        self._move("finalized")

    def action_mark_paid(self):
        self._move("paid")

    def unlink(self):
        if any(r.status not in ("open",) for r in self):
            raise UserError("Only open periods can be deleted.")
        return super().unlink()


class HrmPayroll(models.Model):
    """Payroll run. FINALIZED/PAID runs are immutable (SPEC §9.5)."""

    _name = "hrm.payroll"
    _inherit = ["hrm.base.mixin"]
    _description = "Payroll run (SPEC §9.5)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    period_id = fields.Many2one("hrm.payroll.period", required=True, ondelete="restrict")
    run_no = fields.Integer(default=1, required=True)
    calculation_version = fields.Integer(default=0)
    started_at = fields.Datetime()
    completed_at = fields.Datetime()
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("processing", "Processing"),
            ("calculated", "Calculated"),
            ("review", "Review"),
            ("approved", "Approved"),
            ("finalized", "Finalized"),
            ("paid", "Paid"),
        ],
        default="draft",
        required=True,
    )
    item_ids = fields.One2many("hrm.payroll.item", "payroll_id")

    _period_run_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, period_id, run_no)",
        "Run number must be unique per tenant+company+period.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Payroll UUID must be unique.")

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status in ("finalized", "paid") for rec in self):
            raise UserError("Finalized/paid payroll runs are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(rec.status in ("finalized", "paid", "approved") for rec in self):
            raise UserError("Approved/finalized/paid runs cannot be deleted.")
        return super().unlink()

    # -- run lifecycle -------------------------------------------------

    def action_start(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be started.")
        self.write({"status": "processing", "started_at": fields.Datetime.now()})
        return True

    def _eligible_employees(self):
        self.ensure_one()
        return self.env["hr.employee"].search(
            [
                ("tenant_id", "=", self.tenant_id.id),
                ("current_status", "in", ("active", "onboarding")),
            ]
        )

    def _active_salary(self, employee):
        self.ensure_one()
        ref = self.period_id.period_end
        salaries = self.env["hrm.employee.salary"].search(
            [
                ("tenant_id", "=", self.tenant_id.id),
                ("employee_id", "=", employee.id),
                ("status", "=", "active"),
                ("effective_from", "<=", ref),
            ],
            order="effective_from desc",
        )
        return salaries.filtered(
            lambda s: not s.effective_to or s.effective_to >= ref
        )[:1]

    def _period_extras(self, employee):
        """Approved bonuses (+) and active deductions (-) effective in the period."""
        self.ensure_one()
        start, end = self.period_id.period_start, self.period_id.period_end
        bonus = sum(
            self.env["hrm.bonus"].search(
                [
                    ("tenant_id", "=", self.tenant_id.id),
                    ("employee_id", "=", employee.id),
                    ("status", "=", "approved"),
                    ("effective_date", ">=", start),
                    ("effective_date", "<=", end),
                ]
            ).mapped("amount")
        )
        deduction = sum(
            self.env["hrm.deduction"].search(
                [
                    ("tenant_id", "=", self.tenant_id.id),
                    ("employee_id", "=", employee.id),
                    ("status", "=", "active"),
                    ("effective_from", "<=", end),
                ]
            ).filtered(
                lambda d: not d.effective_to or d.effective_to >= start
            ).mapped("amount")
        )
        return bonus, deduction

    def _period_hours(self, employee):
        entries = self.env["hrm.work.entry"].search(
            [
                ("tenant_id", "=", self.tenant_id.id),
                ("employee_id", "=", employee.id),
                ("work_date", ">=", self.period_id.period_start),
                ("work_date", "<=", self.period_id.period_end),
                ("status", "in", ("approved", "locked")),
            ]
        )
        return {
            "worked_hours": sum(
                entries.filtered(lambda e: e.entry_type == "attendance").mapped("quantity")
            ),
            "overtime_hours": sum(
                entries.filtered(lambda e: e.entry_type == "overtime").mapped("quantity")
            ),
        }

    def action_calculate(self):
        for rec in self:
            if rec.status != "processing":
                raise UserError("Only processing runs can be calculated.")
        for rec in self.with_context(hrm_engine=True):
            rec.item_ids.unlink()
            for employee in rec._eligible_employees():
                salary = rec._active_salary(employee)
                if not salary:
                    continue
                components = salary.structure_id.component_ids.filtered(
                    lambda c: c.status == "active"
                )
                hours = rec._period_hours(employee)
                ctx = {
                    "base_salary": salary.base_salary,
                    "gross": 0.0,
                    "worked_hours": hours["worked_hours"],
                    "overtime_hours": hours["overtime_hours"],
                }
                ctx = rec._calculation_context(employee, salary, ctx)
                earnings = rec._additional_earnings(employee, salary)
                gross = sum(line['amount'] for line in earnings)
                deduction, tax = 0.0, 0.0
                ctx['gross'] = gross
                exempt = sum(line.get('tax_exempt_amount', 0) for line in earnings)
                ctx.update(TAX_EXEMPT_ALLOWANCES=exempt, TAXABLE_ALLOWANCES=gross - exempt)
                lines = []
                tax_components = components.filtered(lambda c: c.component_type == "tax")
                bonus, extra_deduction = rec._period_extras(employee)
                for comp in components - tax_components:
                    ctx['TAXABLE_GROSS'] = gross - exempt
                    amount = comp.compute_amount(ctx)
                    ctx[comp.code] = amount
                    lines.append((comp, amount))
                    if comp.component_type == "earning":
                        gross += amount
                        ctx["gross"] = gross
                    else:
                        deduction += amount
                gross += bonus
                deduction += extra_deduction
                ctx['TAXABLE_GROSS'] = gross - exempt
                tax_ctx = dict(ctx, gross=ctx['TAXABLE_GROSS'])
                for comp in tax_components:
                    amount = comp.compute_amount(tax_ctx)
                    tax_ctx[comp.code] = amount
                    lines.append((comp, amount))
                    tax += amount
                net = gross - deduction - tax
                item = self.env["hrm.payroll.item"].create(
                    {
                        "tenant_id": rec.tenant_id.id,
                        "payroll_id": rec.id,
                        "employee_id": employee.id,
                        "gross_amount": gross,
                        "deduction_amount": deduction,
                        "tax_amount": tax,
                        "net_amount": net,
                        "currency_code": salary.currency_code,
                        "status": "calculated",
                    }
                )
                if earnings:
                    self.env['hrm.payslip.item'].create([
                        dict(line, tenant_id=rec.tenant_id.id, payroll_id=rec.id,
                             employee_id=employee.id, currency_code=salary.currency_code,
                             sequence_no=0, status='calculated') for line in earnings])
                for seq, (comp, amount) in enumerate(lines, start=1):
                    self.env["hrm.payslip.item"].create(
                        {
                            "tenant_id": rec.tenant_id.id,
                            "payroll_id": rec.id,
                            "employee_id": employee.id,
                            "salary_component_id": comp.id,
                            "code": comp.code,
                            "name": comp.name,
                            "amount": amount,
                            "currency_code": salary.currency_code,
                            "sequence_no": seq,
                            "status": "calculated",
                        }
                    )
            rec.write(
                {"status": "calculated",
                 "calculation_version": rec.calculation_version + 1}
            )
            _emit(rec.env, "PayrollCalculated", rec.tenant_id.id, "hrm.payroll",
                  rec.id, {"period_id": rec.period_id.id, "run_no": rec.run_no},
                  aggregate_uuid=rec.uuid)
        return True

    def _additional_earnings(self, employee, salary):
        return []

    def _calculation_context(self, employee, salary, context):
        """Extension point for approved imported inputs and formula policies."""
        return context

    def action_review(self):
        for rec in self:
            if rec.status != "calculated":
                raise UserError("Only calculated runs go to review.")
        self.write({"status": "review"})
        return True

    def action_approve(self):
        for rec in self:
            if rec.status != "review":
                raise UserError("Only reviewed runs can be approved.")
        self.write({"status": "approved"})
        return True

    def action_finalize(self):
        """APPROVED -> FINALIZED: issue payslips, lock everything."""
        for rec in self:
            if rec.status != "approved":
                raise UserError("Only approved runs can be finalized.")
        for rec in self.with_context(hrm_engine=True):
            for item in rec.item_ids:
                item.write({"status": "finalized"})
                payslip = self.env["hrm.payslip"].create(
                    {
                        "tenant_id": rec.tenant_id.id,
                        "payroll_id": rec.id,
                        "employee_id": item.employee_id.id,
                        "payslip_no": f"{rec.period_id.period_code}-{rec.run_no:02d}-{item.employee_id.id:05d}",
                        "gross_amount": item.gross_amount,
                        "deduction_amount": item.deduction_amount,
                        "tax_amount": item.tax_amount,
                        "net_amount": item.net_amount,
                        "currency_code": item.currency_code,
                        "issued_at": fields.Datetime.now(),
                        "status": "issued",
                    }
                )
                self.env["hrm.payslip.item"].search(
                    [
                        ("payroll_id", "=", rec.id),
                        ("employee_id", "=", item.employee_id.id),
                        ("payslip_id", "=", False),
                    ]
                ).write({"payslip_id": payslip.id})
            rec.env["hrm.payslip.item"].search(
                [("payroll_id", "=", rec.id)]
            ).write({"status": "finalized"})
            rec.write({"status": "finalized", "completed_at": fields.Datetime.now()})
            _emit(rec.env, "PayrollFinalized", rec.tenant_id.id, "hrm.payroll",
                  rec.id, {"period_id": rec.period_id.id, "run_no": rec.run_no},
                  aggregate_uuid=rec.uuid)
        return True

    def action_mark_paid(self):
        for rec in self:
            if rec.status != "finalized":
                raise UserError("Only finalized runs can be paid.")
        for rec in self.with_context(hrm_engine=True):
            rec.write({"status": "paid"})
            rec.env["hrm.payslip"].search([("payroll_id", "=", rec.id)]).write(
                {"status": "paid"}
            )
        return True


class HrmPayrollItem(models.Model):
    _name = "hrm.payroll.item"
    _description = "Payroll line per employee (SPEC §9.6)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    payroll_id = fields.Many2one("hrm.payroll", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    gross_amount = HrmMoney(digits=(19, 4), required=True)
    deduction_amount = HrmMoney(digits=(19, 4), default=0.0)
    tax_amount = HrmMoney(digits=(19, 4), default=0.0)
    net_amount = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    status = fields.Selection(
        [("calculated", "Calculated"), ("finalized", "Finalized")],
        default="calculated",
        required=True,
    )

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status == "finalized" for rec in self):
            raise UserError("Finalized payroll items are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(rec.status == "finalized" for rec in self):
            raise UserError("Finalized payroll items cannot be deleted.")
        if self.env.context.get("hrm_engine"):
            return super().unlink()
        # recalculation path uses engine context; manual deletes of drafts only
        if any(rec.payroll_id.status in ("finalized", "paid") for rec in self):
            raise UserError("Items of finalized/paid runs cannot be deleted.")
        return super().unlink()


class HrmPayslip(models.Model):
    _name = "hrm.payslip"
    _inherit = ["hrm.base.mixin"]
    _description = "Payslip (SPEC §9.7)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    payroll_id = fields.Many2one("hrm.payroll", required=True, ondelete="restrict")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    payslip_no = fields.Char(required=True)
    gross_amount = HrmMoney(digits=(19, 4), required=True)
    deduction_amount = HrmMoney(digits=(19, 4), default=0.0)
    tax_amount = HrmMoney(digits=(19, 4), default=0.0)
    net_amount = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    issued_at = fields.Datetime()
    status = fields.Selection(
        [("draft", "Draft"), ("issued", "Issued"), ("paid", "Paid"),
         ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )
    document_id = fields.Many2one("hrm.employee.document", ondelete="set null")
    item_ids = fields.One2many("hrm.payslip.item", "payslip_id")

    _tenant_no_unique = models.Constraint(
        "UNIQUE(tenant_id, payslip_no)",
        "Payslip number must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Payslip UUID must be unique.")

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status in ("issued", "paid") for rec in self):
            raise UserError("Issued/paid payslips are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(rec.status in ("issued", "paid") for rec in self):
            raise UserError("Issued/paid payslips cannot be deleted.")
        return super().unlink()


class HrmPayslipItem(models.Model):
    _name = "hrm.payslip.item"
    _description = "Payslip line per component (SPEC §9.8)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    payslip_id = fields.Many2one("hrm.payslip", ondelete="cascade")
    payroll_id = fields.Many2one("hrm.payroll", ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", ondelete="cascade")
    salary_component_id = fields.Many2one("hrm.salary.component", ondelete="set null")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    quantity = HrmNumeric(digits=(12, 4))
    rate = HrmMoney(digits=(19, 4))
    amount = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    sequence_no = fields.Integer(default=10)
    status = fields.Selection(
        [("calculated", "Calculated"), ("finalized", "Finalized")],
        default="calculated",
        required=True,
    )

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status == "finalized" for rec in self):
            raise UserError("Finalized payslip lines are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(rec.status == "finalized" for rec in self):
            raise UserError("Finalized payslip lines cannot be deleted.")
        return super().unlink()


class HrmBonus(models.Model):
    _name = "hrm.bonus"
    _inherit = ["hrm.base.mixin"]
    _description = "One-off bonus (SPEC §9.9)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    bonus_type = fields.Char(required=True, default="bonus")
    amount = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    effective_date = fields.Date(required=True)
    reason = fields.Char()
    status = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft",
        required=True,
    )
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Bonus UUID must be unique.")

    def action_approve(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be approved.")
        self.write({"status": "approved"})
        return True

    def action_reject(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be rejected.")
        self.write({"status": "rejected"})
        return True

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status == "approved" for rec in self):
            raise UserError("Approved bonuses are immutable. Create a new one.")
        return super().write(vals)


class HrmDeduction(models.Model):
    _name = "hrm.deduction"
    _inherit = ["hrm.base.mixin"]
    _description = "Recurring/one-off deduction (SPEC §9.10)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    deduction_type = fields.Char(required=True, default="deduction")
    amount = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    effective_from = fields.Date(required=True)
    effective_to = fields.Date()
    reason = fields.Char()
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft",
        required=True,
    )
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Deduction UUID must be unique.")

    def action_activate(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be activated.")
        self.write({"status": "active"})
        return True

    def action_close(self):
        for rec in self:
            if rec.status != "active":
                raise UserError("Only active deductions can be closed.")
        self.write({"status": "closed"})
        return True
