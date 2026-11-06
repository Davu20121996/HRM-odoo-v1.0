import ast
import math
from numbers import Number

from odoo import api, fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric
from odoo.exceptions import UserError

# Country-specific RULE handlers register here, e.g.
# PAYROLL_RULE_HANDLERS["vn_pit"] = callable(ctx) -> float
# (master-skill §6 — localization owns tax/insurance logic, never Core.)
PAYROLL_RULE_HANDLERS = {}


def safe_eval_formula(expression, context):
    """Tiny arithmetic evaluator for FORMULA components.

    Allows numbers, context names, + - * / %, parentheses and
    min()/max()/round(). Anything else raises.
    """
    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Load,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
        ast.UAdd, ast.USub, ast.Call, ast.Name, ast.Constant,
    )
    allowed_funcs = {"min": min, "max": max, "round": round}
    numeric_context = {k: v for k, v in context.items() if isinstance(v, Number) and not isinstance(v, complex)}
    if len(expression or '') > 2000:
        raise UserError('Payroll formula is too long.')
    try:
        tree = ast.parse(expression or "", mode="eval")
    except SyntaxError as e:
        raise UserError(f"Invalid payroll formula '{expression}': {e}.")
    nodes = list(ast.walk(tree))
    if len(nodes) > 200:
        raise UserError('Payroll formula is too complex.')
    for node in nodes:
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or abs(node.value) > 1e15):
            raise UserError('Only bounded numeric constants are allowed.')
        if not isinstance(node, allowed_nodes):
            raise UserError(f"Forbidden construct in payroll formula '{expression}'.")
        if isinstance(node, ast.Name) and node.id not in numeric_context and node.id not in allowed_funcs:
            raise UserError(f"Unknown name '{node.id}' in payroll formula '{expression}'.")
        if isinstance(node, ast.Call) and not (
            isinstance(node.func, ast.Name) and node.func.id in allowed_funcs
        ):
            raise UserError(f"Only min()/max()/round() allowed in '{expression}'.")
    namespace = dict(allowed_funcs)
    namespace.update({k: v for k, v in numeric_context.items() if k not in allowed_funcs})
    try:
        amount = float(eval(compile(tree, "<payroll>", "eval"), {"__builtins__": {}}, namespace))
        if not math.isfinite(amount) or abs(amount) > 1e18:
            raise UserError('Payroll result is outside the supported range.')
        return amount
    except Exception as e:
        raise UserError(f"Cannot evaluate payroll formula '{expression}': {e}.")


class HrmSalaryStructure(models.Model):
    _name = "hrm.salary.structure"
    _inherit = ["hrm.base.mixin"]
    _description = "Salary structure (SPEC §9.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    currency_code = fields.Char(required=True, default="VND", size=3)
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    component_ids = fields.One2many(
        "hrm.salary.component", "structure_id", order="sequence_no"
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Structure code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Structure UUID must be unique.")


class HrmSalaryComponent(models.Model):
    _name = "hrm.salary.component"
    _inherit = ["hrm.base.mixin"]
    _description = "Salary component (SPEC §9.2)"
    _order = "sequence_no"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    structure_id = fields.Many2one(
        "hrm.salary.structure", required=True, ondelete="cascade"
    )
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    component_type = fields.Selection(
        [("earning", "Earning"), ("deduction", "Deduction"),
         ("tax", "Tax"), ("contribution", "Contribution")],
        required=True,
    )
    calculation_type = fields.Selection(
        [("fixed", "Fixed"), ("percentage", "Percentage"),
         ("formula", "Formula"), ("rule", "Rule")],
        required=True,
    )
    sequence_no = fields.Integer(default=10, required=True)
    configuration = fields.Json(
        default=dict,
        help="fixed: {fixed_amount}. percentage: {percent, base: base_salary|gross}. "
        "formula: {expression}. rule: {rule_code}.",
    )
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _structure_code_unique = models.Constraint(
        "UNIQUE(structure_id, code)",
        "Component code must be unique per structure.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Component UUID must be unique.")

    def compute_amount(self, ctx):
        """ctx: {base_salary, gross, overtime_hours, worked_hours}. Returns float."""
        self.ensure_one()
        cfg = self.configuration or {}
        if self.calculation_type == "fixed":
            return float(cfg.get("fixed_amount", 0.0))
        if self.calculation_type == "percentage":
            base = ctx.get("gross", 0.0) if cfg.get("base") == "gross" else ctx.get("base_salary", 0.0)
            return base * float(cfg.get("percent", 0.0)) / 100.0
        if self.calculation_type == "formula":
            if not cfg.get("expression"):
                raise UserError(f"Formula component {self.code} has no expression.")
            return safe_eval_formula(cfg["expression"], ctx)
        if self.calculation_type == "rule":
            handler = PAYROLL_RULE_HANDLERS.get(cfg.get("rule_code"))
            if not handler:
                raise UserError(f"Payroll rule handler missing for {self.code}: {cfg.get('rule_code')}.")
            return float(handler(dict(ctx)))
        raise UserError(f"Unknown calculation type on {self.code}.")


class HrmEmployeeSalary(models.Model):
    _name = "hrm.employee.salary"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee salary assignment, no active overlap (SPEC §9.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    structure_id = fields.Many2one(
        "hrm.salary.structure", required=True, ondelete="restrict"
    )
    effective_from = fields.Date(required=True)
    effective_to = fields.Date()
    base_salary = HrmMoney(digits=(19, 4), required=True)
    currency_code = fields.Char(required=True, size=3)
    configuration = fields.Json(default=dict)
    status = fields.Selection(
        [("active", "Active"), ("closed", "Closed")],
        default="active",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Employee salary UUID must be unique.")

    @api.constrains("employee_id", "structure_id", "status", "effective_from", "effective_to")
    def _check_no_overlap(self):
        from datetime import date

        try:
            self.env.cr.execute(
                'SELECT id FROM hrm_employee_salary WHERE employee_id IN %s FOR UPDATE',
                (tuple(self.mapped("employee_id").ids or (0,)),),
            )
        except Exception:
            pass
        for rec in self:
            if rec.status != "active" or not rec.effective_from:
                continue
            rec_end = rec.effective_to or date.max
            others = self.search(
                [
                    ("id", "!=", rec.id),
                    ("employee_id", "=", rec.employee_id.id),
                    ("structure_id", "=", rec.structure_id.id),
                    ("status", "=", "active"),
                    ("effective_from", "<=", rec_end),
                ]
            ).filtered(lambda o: (o.effective_to or date.max) >= rec.effective_from)
            if others:
                raise UserError(
                    "Overlapping active salaries are not allowed for the same "
                    "employee+structure. Close the current one first."
                )
