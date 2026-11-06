"""VN localization package (master-skill §6, SPEC: localization owns tax/insurance).

Core must never hard-code VN rates — rules are versioned + effective-dated here,
and payroll Core calls them via PAYROLL_RULE_HANDLERS.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hrm_base.models.mixins import HrmNumeric


class HrmPersonIdentifier(models.Model):
    _name = "hrm.person.identifier"
    _inherit = ["hrm.base.mixin"]
    _description = "VN identifiers: CCCD/passport/MST/BHXH (tokenized)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    person_id = fields.Many2one("hrm.person", required=True, ondelete="cascade")
    id_type = fields.Selection(
        [("cccd", "CCCD"), ("passport", "Passport"), ("mst", "MST"),
         ("bhxh", "BHXH"), ("bhyt", "BHYT")],
        required=True,
    )
    id_value_ref = fields.Char(required=True, help="Token/reference — never store raw sensitive value in logs.")
    issued_at = fields.Date()
    expires_at = fields.Date()
    status = fields.Selection([("active", "Active"), ("archived", "Archived")], default="active", required=True)

    _tenant_person_type_unique = models.Constraint(
        "UNIQUE(tenant_id, person_id, id_type)", "One active identifier per person+type.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Identifier UUID must be unique.")


class HrmInsuranceRule(models.Model):
    _name = "hrm.insurance.rule"
    _inherit = ["hrm.base.mixin"]
    _description = "VN insurance rates DN/NLD (versioned, effective-dated)"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="cascade", help="Empty = national default.")
    code = fields.Char(required=True, default="vn_bhxh_bhyt_bhtn")
    name = fields.Char(required=True)
    employer_bhxh = HrmNumeric(digits=(6, 3), default=17.5)
    employee_bhxh = HrmNumeric(digits=(6, 3), default=8.0)
    employer_bhyt = HrmNumeric(digits=(6, 3), default=3.0)
    employee_bhyt = HrmNumeric(digits=(6, 3), default=1.5)
    employer_bhtn = HrmNumeric(digits=(6, 3), default=1.0)
    employee_bhtn = HrmNumeric(digits=(6, 3), default=1.0)
    employer_tnld = HrmNumeric(digits=(6, 3), default=0.5)
    kpcd_rate = HrmNumeric(digits=(6, 3), default=2.0)
    base_salary_min = HrmNumeric(digits=(19, 4))
    base_salary_max = HrmNumeric(digits=(19, 4))
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection([("active", "Active"), ("archived", "Archived")], default="active", required=True)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Insurance rule UUID must be unique.")

    @api.model
    def current(self, tenant_id=False, on_date=False):
        on_date = on_date or fields.Date.today()
        domain = [("status", "=", "active"), ("effective_from", "<=", on_date)]
        if tenant_id:
            domain += ["|", ("tenant_id", "=", tenant_id), ("tenant_id", "=", False)]
        rules = self.search(domain, order="effective_from desc, id desc", limit=1)
        return rules


class HrmTaxRule(models.Model):
    _name = "hrm.tax.rule"
    _inherit = ["hrm.base.mixin"]
    _description = "VN PIT brackets (luy tien) + giam tru"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="cascade")
    code = fields.Char(required=True, default="vn_pit")
    name = fields.Char(required=True)
    self_deduction = HrmNumeric(digits=(19, 4), default=11000000.0)
    dependent_deduction = HrmNumeric(digits=(19, 4), default=4400000.0)
    brackets = fields.Json(default=list, help="[{upto, percent}] e.g. [{upto:5000000,percent:5},...]")
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection([("active", "Active"), ("archived", "Archived")], default="active", required=True)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Tax rule UUID must be unique.")


class HrmPayrollRule(models.Model):
    _name = "hrm.payroll.rule"
    _inherit = ["hrm.base.mixin"]
    _description = "VN OT coefficients, night-shift, rounding"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="cascade")
    code = fields.Char(required=True, default="vn_ot")
    name = fields.Char(required=True)
    ot_day = HrmNumeric(digits=(6, 3), default=1.5)
    ot_weekend = HrmNumeric(digits=(6, 3), default=2.0)
    ot_holiday = HrmNumeric(digits=(6, 3), default=3.0)
    night_coeff = HrmNumeric(digits=(6, 3), default=1.3)
    max_ot_month = HrmNumeric(digits=(6, 2), default=40.0)
    max_ot_year = HrmNumeric(digits=(6, 2), default=200.0)
    rounding = fields.Selection([("1000", "1.000"), ("100", "100"), ("1", "1")], default="1000")
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection([("active", "Active"), ("archived", "Archived")], default="active", required=True)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Payroll rule UUID must be unique.")


class HrmStatutoryRule(models.Model):
    _name = "hrm.statutory.rule"
    _inherit = ["hrm.base.mixin"]
    _description = "VN holidays, standard workdays, region minimum wage"

    tenant_id = fields.Many2one("hrm.tenant", ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    rule_type = fields.Selection(
        [("holiday", "Holiday"), ("workday", "Standard Workday"), ("min_wage", "Min Wage")],
        required=True,
    )
    configuration = fields.Json(default=dict)
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection([("active", "Active"), ("archived", "Archived")], default="active", required=True)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Statutory rule UUID must be unique.")


def _vn_bhxh_employee(ctx):
    rate = 8.0 + 1.5 + 1.0
    try:
        from odoo.api import Environment
    except Exception:
        return ctx.get("base_salary", 0.0) * rate / 100.0
    return ctx.get("base_salary", 0.0) * rate / 100.0


def _vn_pit(ctx):
    taxable = ctx.get("gross", 0.0) - ctx.get("employee_insurance", 0.0) - 11000000.0
    if taxable <= 0:
        return 0.0
    brackets = [(5000000, 5), (10000000, 10), (18000000, 15), (32000000, 20), (52000000, 25), (80000000, 30), (float("inf"), 35)]
    tax, prev = 0.0, 0.0
    for upto, pct in brackets:
        if taxable <= prev:
            break
        portion = min(taxable, upto) - prev
        tax += portion * pct / 100.0
        prev = upto
    return tax


try:
    from odoo.addons.hrm_payroll.models.salary import PAYROLL_RULE_HANDLERS
    PAYROLL_RULE_HANDLERS.setdefault("vn_bhxh_employee", _vn_bhxh_employee)
    PAYROLL_RULE_HANDLERS.setdefault("vn_pit", _vn_pit)
except Exception:
    pass
