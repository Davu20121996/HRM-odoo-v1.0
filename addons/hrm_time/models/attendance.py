from datetime import datetime, timedelta

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


class HrmAttendanceDeviceEvent(models.Model):
    """Raw immutable device event (SPEC §7.5). Idempotent on
    (tenant, device, external_event_id)."""

    _name = "hrm.attendance.device.event"
    _description = "Raw device event, immutable (SPEC §7.5)"
    _order = "event_time desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    device_id = fields.Many2one(
        "hrm.attendance.device", required=True, ondelete="restrict"
    )
    employee_external_ref = fields.Char()
    employee_id = fields.Many2one("hr.employee", ondelete="set null")
    event_type = fields.Selection(
        [("check_in", "Check In"), ("check_out", "Check Out")],
        required=True,
    )
    event_time = fields.Datetime(required=True)
    payload = fields.Json(default=dict)
    external_event_id = fields.Char(required=True, default=lambda self: __import__('uuid').uuid4().hex)
    received_at = fields.Datetime(required=True, default=fields.Datetime.now)
    processed_at = fields.Datetime()

    _device_event_unique = models.Constraint(
        "UNIQUE(tenant_id, device_id, external_event_id)",
        "Device event must be unique per tenant+device+external id.",
    )

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(f in vals for f in ("event_time", "event_type", "payload", "device_id",
                                    "external_event_id", "received_at", "processed_at",
                                    "employee_id", "employee_external_ref", "tenant_id")):
            raise UserError("Raw device events are immutable (link employee only via engine).")
        return super().write(vals)

    def unlink(self):
        raise UserError("Raw device events are immutable.")

    @api.model
    def ingest(self, tenant_id, device_code, event_type, event_time,
               external_event_id=None, employee_external_ref=None,
               employee_id=None, payload=None):
        """Idempotent ingestion. Returns the event record."""
        device = self.env["hrm.attendance.device"].search(
            [("tenant_id", "=", tenant_id), ("code", "=", device_code)], limit=1
        )
        if not device:
            raise UserError(f"Unknown device '{device_code}'.")
        if external_event_id:
            existing = self.search(
                [
                    ("tenant_id", "=", tenant_id),
                    ("device_id", "=", device.id),
                    ("external_event_id", "=", external_event_id),
                ],
                limit=1,
            )
            if existing:
                return existing
        return self.create(
            {
                "tenant_id": tenant_id,
                "device_id": device.id,
                "employee_external_ref": employee_external_ref,
                "employee_id": employee_id,
                "event_type": event_type,
                "event_time": event_time,
                "payload": payload or {},
                "external_event_id": external_event_id,
            }
        )


class HrmAttendance(models.Model):
    """Normalized business attendance, pipeline
    RAW -> NORMALIZED -> CALCULATED -> VALIDATED -> LOCKED (SPEC §7.6)."""

    _name = "hrm.attendance"
    _inherit = ["hrm.base.mixin"]
    _description = "Attendance (SPEC §7.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    work_date = fields.Date(required=True)
    check_in_at = fields.Datetime()
    check_out_at = fields.Datetime()
    worked_minutes = fields.Integer(default=0)
    late_minutes = fields.Integer(default=0)
    early_leave_minutes = fields.Integer(default=0)
    overtime_minutes = fields.Integer(default=0)
    status = fields.Selection(
        [
            ("raw", "Raw"),
            ("normalized", "Normalized"),
            ("calculated", "Calculated"),
            ("validated", "Validated"),
            ("locked", "Locked"),
        ],
        default="raw",
        required=True,
    )
    source = fields.Selection(
        [("manual", "Manual"), ("biometric", "Biometric"), ("mobile", "Mobile"),
         ("web", "Web"), ("import", "Import"), ("api", "API")],
        default="manual",
        required=True,
    )
    calculation_version = fields.Integer(default=0)
    locked_at = fields.Datetime()

    _tenant_employee_date_unique = models.Constraint(
        "UNIQUE(tenant_id, employee_id, work_date)",
        "One attendance row per employee+day.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Attendance UUID must be unique.")

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status == "locked" for rec in self):
            raise UserError(
                "Locked attendance cannot be modified. "
                "Use an attendance adjustment instead."
            )
        return super().write(vals)

    def unlink(self):
        raise UserError("Attendance rows cannot be hard-deleted; use adjustments. (MUST#5)")

    # -- pipeline --------------------------------------------------------

    def action_process(self):
        """RAW -> NORMALIZED -> CALCULATED from device events + shift."""
        for rec in self:
            if rec.status not in ("raw", "normalized"):
                raise UserError(f"Cannot process attendance in status {rec.status}.")
            next_day = rec.work_date + timedelta(days=1)
            events = self.env["hrm.attendance.device.event"].search(
                [
                    ("tenant_id", "=", rec.tenant_id.id),
                    ("employee_id", "=", rec.employee_id.id),
                    ("event_time", ">=", f"{rec.work_date} 00:00:00"),
                    ("event_time", "<", f"{next_day} 00:00:00"),
                    ("processed_at", "=", False),
                ]
            )
            if events:
                ins = events.filtered(lambda e: e.event_type == "check_in").mapped("event_time")
                outs = events.filtered(lambda e: e.event_type == "check_out").mapped("event_time")
                rec.check_in_at = min(ins) if ins else min(events.mapped("event_time"))
                rec.check_out_at = max(outs) if outs else max(events.mapped("event_time"))
                events.with_context(hrm_engine=True).write(
                    {"processed_at": fields.Datetime.now()}
                )
            if rec.check_in_at and rec.check_out_at:
                delta = rec.check_out_at - rec.check_in_at
                rec.worked_minutes = max(0, int(delta.total_seconds() // 60))
                sched = rec._scheduled_times()
                if sched:
                    start_dt = datetime.combine(rec.work_date, sched[0])
                    end_dt = datetime.combine(rec.work_date, sched[1])
                    rec.late_minutes = max(
                        0, int((rec.check_in_at - start_dt).total_seconds() // 60)
                    )
                    rec.early_leave_minutes = max(
                        0, int((end_dt - rec.check_out_at).total_seconds() // 60)
                    )
            rec.calculation_version += 1
            rec.status = "calculated"
        return True

    def _scheduled_times(self):
        """Return (start_time, end_time) as time objects (SPEC TIME, UTC)."""
        from datetime import time as _time
        self.ensure_one()
        assign = self.env["hrm.shift.assignment"].search(
            [
                ("tenant_id", "=", self.tenant_id.id),
                ("employee_id", "=", self.employee_id.id),
                ("effective_from", "<=", self.work_date),
            ],
            order="effective_from desc",
            limit=1,
        )
        assign = assign.filtered(
            lambda a: not a.effective_to or a.effective_to >= self.work_date
        )
        if not assign or not assign.shift_id:
            return None
        shift = assign.shift_id
        def _parse(val):
            parts = [int(p) for p in str(val).split(":")]
            while len(parts) < 3:
                parts.append(0)
            return _time(parts[0] % 24, parts[1] % 60, parts[2] % 60)
        return (_parse(shift.start_time), _parse(shift.end_time))

    def action_validate(self):
        for rec in self:
            if rec.status != "calculated":
                raise UserError(f"Only calculated attendance can be validated.")
        self.write({"status": "validated"})
        return True

    def action_lock(self):
        """VALIDATED -> LOCKED + emit attendance work entry for payroll."""
        for rec in self:
            if rec.status != "validated":
                raise UserError("Only validated attendance can be locked.")
        self.with_context(hrm_engine=True).write(
            {"status": "locked", "locked_at": fields.Datetime.now()}
        )
        for _r in self:
            _emit(self.env, "AttendanceValidated", _r.tenant_id.id, "hrm.attendance",
                  _r.id, {"work_date": str(_r.work_date)}, aggregate_uuid=_r.uuid)
        for rec in self:
            if self.env["hrm.work.entry"].search([
                ("tenant_id", "=", rec.tenant_id.id),
                ("source_type", "=", "hrm.attendance"),
                ("source_id", "=", rec.id),
            ], limit=1):
                continue
            self.env["hrm.work.entry"].create(
                {
                    "tenant_id": rec.tenant_id.id,
                    "employee_id": rec.employee_id.id,
                    "work_date": rec.work_date,
                    "entry_type": "attendance",
                    "quantity": rec.worked_minutes / 60.0,
                    "unit": "hour",
                    "source_type": "hrm.attendance",
                    "source_id": rec.id,
                    "status": "locked",
                }
            )
        return True


class HrmAttendanceAdjustment(models.Model):
    _name = "hrm.attendance.adjustment"
    _inherit = ["hrm.base.mixin"]
    _description = "Attendance adjustment request (SPEC §7.7)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    attendance_id = fields.Many2one("hrm.attendance", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    requested_by_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    reason = fields.Text(required=True)
    old_value = fields.Json(default=dict)
    new_value = fields.Json(default=dict)
    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="pending",
        required=True,
    )
    approved_by_id = fields.Many2one("res.users", ondelete="set null")
    approved_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Adjustment UUID must be unique.")

    def action_approve(self):
        for rec in self:
            if rec.status != "pending":
                raise UserError("Only pending adjustments can be approved.")
        for rec in self:
            vals = dict(rec.new_value or {})
            vals = {k: v for k, v in vals.items() if k in (
                "check_in_at", "check_out_at", "worked_minutes",
                "late_minutes", "early_leave_minutes", "overtime_minutes")}
            if vals:
                rec.attendance_id.with_context(hrm_engine=True).write(vals)
            rec.write(
                {"status": "approved", "approved_by_id": self.env.uid,
                 "approved_at": fields.Datetime.now()}
            )
        return True

    def action_reject(self):
        for rec in self:
            if rec.status != "pending":
                raise UserError("Only pending adjustments can be rejected.")
        self.write({"status": "rejected"})
        return True


class HrmOvertimeRequest(models.Model):
    _name = "hrm.overtime.request"
    _inherit = ["hrm.base.mixin"]
    _description = "Overtime request (SPEC §7.8)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    work_date = fields.Date(required=True)
    start_at = fields.Datetime(required=True)
    end_at = fields.Datetime(required=True)
    requested_minutes = fields.Integer(required=True)
    approved_minutes = fields.Integer()
    reason = fields.Text()
    status = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"),
         ("rejected", "Rejected")],
        default="draft",
        required=True,
    )
    workflow_instance_id = fields.Many2one(
        "hrm.workflow.instance", readonly=True, ondelete="set null",
        help="Set when the approval runs through the P3 engine.",
    )

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Overtime UUID must be unique.")

    @api.constrains("start_at", "end_at", "requested_minutes")
    def _check_times(self):
        for r in self:
            if r.end_at <= r.start_at:
                raise UserError("Overtime end must be after start.")
            if (r.requested_minutes or 0) <= 0:
                raise UserError("Requested minutes must be positive.")

    def action_submit(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Only drafts can be submitted.")
        self.write({"status": "submitted"})
        return True

    def action_approve(self, approved_minutes=None):
        for rec in self:
            if rec.status != "submitted":
                raise UserError("Only submitted requests can be approved.")
            minutes = approved_minutes if approved_minutes is not None else rec.requested_minutes
            rec.write({"status": "approved", "approved_minutes": minutes})
            exists = self.env["hrm.work.entry"].search([
                ("tenant_id", "=", rec.tenant_id.id),
                ("source_type", "=", "hrm.overtime.request"),
                ("source_id", "=", rec.id),
            ], limit=1)
            if exists:
                continue
            self.env["hrm.work.entry"].create(
                {
                    "tenant_id": rec.tenant_id.id,
                    "employee_id": rec.employee_id.id,
                    "work_date": rec.work_date,
                    "entry_type": "overtime",
                    "quantity": minutes / 60.0,
                    "unit": "hour",
                    "source_type": "hrm.overtime.request",
                    "source_id": rec.id,
                    "status": "approved",
                }
            )
        return True

    def action_reject(self):
        for rec in self:
            if rec.status != "submitted":
                raise UserError("Only submitted requests can be rejected.")
        self.write({"status": "rejected"})
        return True


class HrmTimesheet(models.Model):
    _name = "hrm.timesheet"
    _inherit = ["hrm.base.mixin"]
    _description = "Timesheet period rollup (SPEC §7.9)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    total_minutes = fields.Integer(default=0)
    status = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved")],
        default="draft",
        required=True,
    )
    submitted_at = fields.Datetime()
    approved_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Timesheet UUID must be unique.")

    def action_rollup(self):
        """Sum locked/calculated attendance minutes in the period."""
        for rec in self:
            rows = self.env["hrm.attendance"].search(
                [
                    ("tenant_id", "=", rec.tenant_id.id),
                    ("employee_id", "=", rec.employee_id.id),
                    ("work_date", ">=", rec.period_start),
                    ("work_date", "<=", rec.period_end),
                    ("status", "in", ("locked",)),
                ]
            )
            rec.total_minutes = sum(rows.mapped("worked_minutes"))
        return True

    def action_submit(self):
        self.action_rollup()
        self.write({"status": "submitted", "submitted_at": fields.Datetime.now()})
        return True

    def action_approve(self):
        for rec in self:
            if rec.status != "submitted":
                raise UserError("Only submitted timesheets can be approved.")
        self.write({"status": "approved", "approved_at": fields.Datetime.now()})
        return True


class HrmWorkEntry(models.Model):
    """Canonical payroll/time input (SPEC §7.10)."""

    _name = "hrm.work.entry"
    _inherit = ["hrm.base.mixin"]
    _description = "Work entry (SPEC §7.10)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    work_date = fields.Date(required=True)
    entry_type = fields.Selection(
        [("attendance", "Attendance"), ("overtime", "Overtime"),
         ("leave", "Leave"), ("manual", "Manual")],
        required=True,
    )
    quantity = HrmNumeric(digits=(12, 4), required=True)
    unit = fields.Selection(
        [("hour", "Hour"), ("day", "Day")], default="hour", required=True
    )
    source_type = fields.Char(default="")
    source_id = fields.Integer(default=0)
    status = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("locked", "Locked")],
        default="draft",
        required=True,
    )

    _tenant_day_type_unique = models.Constraint(
        "UNIQUE(tenant_id, employee_id, work_date, entry_type, source_type, source_id)",
        "Duplicate work entry for the same source.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Work entry UUID must be unique.")

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(r.status in ("approved", "locked") for r in self):
            raise UserError("Approved/locked work entries are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(r.status in ("approved", "locked") for r in self):
            raise UserError("Approved/locked work entries cannot be deleted.")
        return super().unlink()
