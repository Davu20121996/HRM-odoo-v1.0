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


class HrmLeaveType(models.Model):
    _name = "hrm.leave.type"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave type (SPEC §8.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    paid = fields.Boolean(default=True)
    requires_attachment = fields.Boolean(default=False)
    allow_negative_balance = fields.Boolean(default=False)
    unit = fields.Selection(
        [("day", "Day"), ("hour", "Hour")], default="day", required=True
    )
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Leave type code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Leave type UUID must be unique.")


class HrmLeavePolicy(models.Model):
    _name = "hrm.leave.policy"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave policy (SPEC §8.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    country_code = fields.Char(size=2)
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    rule_ids = fields.One2many("hrm.leave.policy.rule", "policy_id")

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Leave policy code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Leave policy UUID must be unique.")


class HrmLeavePolicyRule(models.Model):
    _name = "hrm.leave.policy.rule"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave policy rule (SPEC §8.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    policy_id = fields.Many2one("hrm.leave.policy", required=True, ondelete="cascade")
    leave_type_id = fields.Many2one("hrm.leave.type", required=True, ondelete="restrict")
    rule_type = fields.Char(required=True, default="quota")
    configuration = fields.Json(
        default=dict,
        help="e.g. {annual_quota: 12, carry_forward: 5, prorate_on_join: true}.",
    )
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Policy rule UUID must be unique.")


class HrmLeaveAllocation(models.Model):
    _name = "hrm.leave.allocation"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave allocation, posts to the ledger (SPEC §8.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    leave_type_id = fields.Many2one("hrm.leave.type", required=True, ondelete="restrict")
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    allocated_quantity = HrmNumeric(digits=(12, 4), required=True)
    source_type = fields.Char(default="manual")
    source_id = fields.Integer()
    status = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Allocation UUID must be unique.")
    _period_unique = models.Constraint(
        "UNIQUE(tenant_id, employee_id, leave_type_id, period_start, period_end)",
        "Duplicate allocation for the same employee+type+period.",
    )

    def action_activate(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be activated.")
            rec.write({"status": "active"})
            self.env["hrm.leave.balance.ledger"]._post(
                tenant_id=rec.tenant_id.id,
                employee_id=rec.employee_id.id,
                leave_type_id=rec.leave_type_id.id,
                transaction_type="allocation",
                quantity=rec.allocated_quantity,
                reference_type="hrm.leave.allocation",
                reference_id=rec.id,
            )
        return True

    def action_cancel(self):
        for rec in self:
            if rec.status != "active":
                raise UserError("Only active allocations can be cancelled.")
            rec.write({"status": "cancelled"})
            self.env["hrm.leave.balance.ledger"]._post(
                tenant_id=rec.tenant_id.id,
                employee_id=rec.employee_id.id,
                leave_type_id=rec.leave_type_id.id,
                transaction_type="adjustment",
                quantity=-rec.allocated_quantity,
                reference_type="hrm.leave.allocation",
                reference_id=rec.id,
            )
        return True


class HrmLeaveRequest(models.Model):
    _name = "hrm.leave.request"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave request, state machine (SPEC §8.5)"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    leave_type_id = fields.Many2one("hrm.leave.type", required=True, ondelete="restrict")
    start_at = fields.Datetime(required=True)
    end_at = fields.Datetime(required=True)
    requested_quantity = HrmNumeric(digits=(12, 4), required=True)
    reason = fields.Text()
    attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("pending_approval", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("taken", "Taken"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
        help="Set when the approval runs through the P3 engine.",
    )
    approval_ids = fields.One2many("hrm.leave.approval", "request_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Leave request UUID must be unique.")

    @api.constrains("start_at", "end_at")
    def _check_dates(self):
        for rec in self:
            if rec.end_at < rec.start_at:
                raise UserError("Leave end must be after start.")

    def action_submit(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be submitted.")
            if rec.leave_type_id.requires_attachment and not rec.attachment_id:
                raise UserError("This leave type requires an attachment.")
        self.write({"status": "submitted"})
        # submitted -> pending_approval in one step for now; the P3 engine
        # can take over approval routing later via workflow_instance_id.
        self.write({"status": "pending_approval"})
        return True

    def _balance(self):
        self.ensure_one()
        return self.env["hrm.leave.balance.ledger"].balance_of(
            self.tenant_id.id, self.employee_id.id, self.leave_type_id.id
        )

    def action_approve(self):
        """Approve + post usage to the ledger. Records the approver."""
        for rec in self:
            if rec.status != "pending_approval":
                raise UserError("Only pending requests can be approved.")
            if (
                not rec.leave_type_id.allow_negative_balance
                and rec._balance() < rec.requested_quantity
            ):
                raise UserError(
                    f"Insufficient balance: {rec._balance()} < {rec.requested_quantity}."
                )
        for rec in self:
            employee = self.env["hr.employee"].search(
                [("user_id", "=", self.env.uid)], limit=1
            )
            self.env["hrm.leave.approval"].create(
                {
                    "tenant_id": rec.tenant_id.id,
                    "request_id": rec.id,
                    "approver_employee_id": employee.id or False,
                    "sequence_no": 1,
                    "decision": "approved",
                    "decided_at": fields.Datetime.now(),
                }
            )
            self.env["hrm.leave.balance.ledger"]._post(
                tenant_id=rec.tenant_id.id,
                employee_id=rec.employee_id.id,
                leave_type_id=rec.leave_type_id.id,
                transaction_type="usage",
                quantity=-rec.requested_quantity,
                reference_type="hrm.leave.request",
                reference_id=rec.id,
            )
            rec.write({"status": "approved"})
            _emit(self.env, "LeaveApproved", rec.tenant_id.id, "hrm.leave.request",
                  rec.id, {"leave_type_id": rec.leave_type_id.id,
                           "quantity": float(rec.requested_quantity)},
                  aggregate_uuid=rec.uuid)
        return True

    def action_reject(self, comment=None):
        for rec in self:
            if rec.status != "pending_approval":
                raise UserError("Only pending requests can be rejected.")
            employee = self.env["hr.employee"].search(
                [("user_id", "=", self.env.uid)], limit=1
            )
            self.env["hrm.leave.approval"].create(
                {
                    "tenant_id": rec.tenant_id.id,
                    "request_id": rec.id,
                    "approver_employee_id": employee.id or False,
                    "sequence_no": 1,
                    "decision": "rejected",
                    "comment": comment,
                    "decided_at": fields.Datetime.now(),
                }
            )
            rec.write({"status": "rejected"})
            _emit(self.env, "LeaveRejected", rec.tenant_id.id, "hrm.leave.request",
                  rec.id, {}, aggregate_uuid=rec.uuid)
        return True

    def action_take(self):
        for rec in self:
            if rec.status != "approved":
                raise UserError("Only approved requests can be marked taken.")
        self.write({"status": "taken"})
        for rec in self:
            exists = self.env["hrm.work.entry"].search([
                ("tenant_id", "=", rec.tenant_id.id),
                ("source_type", "=", "hrm.leave.request"),
                ("source_id", "=", rec.id),
            ], limit=1)
            if not exists:
                self.env["hrm.work.entry"].create({
                    "tenant_id": rec.tenant_id.id,
                    "employee_id": rec.employee_id.id,
                    "work_date": (rec.start_at.date() if rec.start_at else fields.Date.today()),
                    "entry_type": "leave",
                    "quantity": rec.requested_quantity,
                    "unit": "day" if rec.leave_type_id.unit == "day" else "hour",
                    "source_type": "hrm.leave.request",
                    "source_id": rec.id,
                    "status": "approved",
                })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.status not in ("draft", "submitted", "pending_approval"):
                raise UserError("Only unapproved requests can be cancelled.")
        self.write({"status": "cancelled"})
        return True


class HrmLeaveApproval(models.Model):
    _name = "hrm.leave.approval"
    _inherit = ["hrm.base.mixin"]
    _description = "Leave approval verdict (SPEC §8.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    request_id = fields.Many2one("hrm.leave.request", required=True, ondelete="cascade")
    approver_employee_id = fields.Many2one("hr.employee", ondelete="set null")
    sequence_no = fields.Integer(default=1, required=True)
    decision = fields.Selection(
        [("approved", "Approved"), ("rejected", "Rejected")],
        required=True,
    )
    comment = fields.Text()
    decided_at = fields.Datetime(required=True, default=fields.Datetime.now)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Leave approval UUID must be unique.")

    def write(self, vals):
        raise UserError("Leave approvals are immutable once recorded.")

    _request_seq_unique = models.Constraint(
        "UNIQUE(request_id, sequence_no)",
        "Approval sequence must be unique per request.",
    )

    def unlink(self):
        raise UserError("Leave approvals cannot be deleted.")


class HrmLeaveBalanceLedger(models.Model):
    """Immutable balance ledger — the audit source of truth (SPEC §8.7)."""

    _name = "hrm.leave.balance.ledger"
    _description = "Leave balance ledger, immutable (SPEC §8.7)"
    _order = "id"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    leave_type_id = fields.Many2one("hrm.leave.type", required=True, ondelete="restrict")
    transaction_type = fields.Selection(
        [("allocation", "Allocation"), ("usage", "Usage"),
         ("adjustment", "Adjustment"), ("expiry", "Expiry")],
        required=True,
    )
    quantity = HrmNumeric(digits=(12, 4), required=True)
    balance_after = HrmNumeric(digits=(12, 4))
    reference_type = fields.Char(required=True)
    reference_id = fields.Integer()
    occurred_at = fields.Datetime(required=True, default=fields.Datetime.now)
    created_by_id = fields.Many2one("res.users", ondelete="set null")

    _idempotent_unique = models.Constraint(
        "UNIQUE(tenant_id, employee_id, leave_type_id, reference_type, reference_id, transaction_type)",
        "Duplicate ledger posting for the same reference.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Ledger UUID must be unique.")

    def write(self, vals):
        raise UserError("The leave ledger is immutable.")

    def unlink(self):
        raise UserError("The leave ledger is immutable.")

    @api.model
    def _post(self, tenant_id, employee_id, leave_type_id, transaction_type,
              quantity, reference_type, reference_id):
        # Idempotent: same reference posts only once (SPEC §8.7).
        existing = self.search([
            ("tenant_id", "=", tenant_id),
            ("employee_id", "=", employee_id),
            ("leave_type_id", "=", leave_type_id),
            ("reference_type", "=", reference_type),
            ("reference_id", "=", reference_id),
            ("transaction_type", "=", transaction_type),
        ], limit=1)
        if existing:
            return existing
        # Serialize postings per employee+type to keep balance_after correct.
        self.env.cr.execute(
            'SELECT id FROM hrm_leave_balance_ledger WHERE employee_id=%s AND leave_type_id=%s FOR UPDATE',
            (employee_id, leave_type_id),
        )
        self.env.cr.execute(
            'SELECT COALESCE(SUM(quantity),0) FROM hrm_leave_balance_ledger WHERE tenant_id=%s AND employee_id=%s AND leave_type_id=%s',
            (tenant_id, employee_id, leave_type_id),
        )
        balance = float(self.env.cr.fetchone()[0] or 0.0)
        try:
            return self.create(
                {
                    "tenant_id": tenant_id,
                    "employee_id": employee_id,
                    "leave_type_id": leave_type_id,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "balance_after": balance + float(quantity or 0.0),
                    "reference_type": reference_type,
                    "reference_id": reference_id,
                    "created_by_id": self.env.uid,
                }
            )
        except Exception as e:
            # UniqueViolation under race -> fetch winner.
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                return self.search([
                    ("tenant_id", "=", tenant_id),
                    ("employee_id", "=", employee_id),
                    ("leave_type_id", "=", leave_type_id),
                    ("reference_type", "=", reference_type),
                    ("reference_id", "=", reference_id),
                    ("transaction_type", "=", transaction_type),
                ], limit=1)
            raise

    @api.model
    def balance_of(self, tenant_id, employee_id, leave_type_id):
        self.env.cr.execute(
            'SELECT COALESCE(SUM(quantity),0) FROM hrm_leave_balance_ledger WHERE tenant_id=%s AND employee_id=%s AND leave_type_id=%s',
            (tenant_id, employee_id, leave_type_id),
        )
        return float(self.env.cr.fetchone()[0] or 0.0)
