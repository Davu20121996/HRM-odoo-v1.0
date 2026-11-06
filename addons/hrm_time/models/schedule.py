from odoo import api, fields, models
from odoo.addons.hrm_base.models.mixins import HrmMoney, HrmNumeric


class HrmWorkSchedule(models.Model):
    _name = "hrm.work.schedule"
    _inherit = ["hrm.base.mixin"]
    _description = "Work schedule (SPEC §7.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    timezone = fields.Char(default="UTC", required=True)
    weekly_hours = HrmNumeric(digits=(6, 2), required=True)
    rules = fields.Json(default=dict)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Schedule code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Schedule UUID must be unique.")


class HrmShift(models.Model):
    _name = "hrm.shift"
    _inherit = ["hrm.base.mixin"]
    _description = "Shift (SPEC §7.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    work_schedule_id = fields.Many2one("hrm.work.schedule", ondelete="set null")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    # SPEC §7.2 TIME — Odoo không có fields.Time nên lưu "HH:MM:SS" (UTC).
    start_time = fields.Char(required=True, size=8, default="08:00:00")
    end_time = fields.Char(required=True, size=8, default="17:30:00")
    cross_midnight = fields.Boolean(default=False)
    break_rules = fields.Json(default=dict)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Shift code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Shift UUID must be unique.")

    @api.constrains("start_time", "end_time")
    def _check_hhmmss(self):
        import re
        pat = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
        for rec in self:
            for val in (rec.start_time, rec.end_time):
                if not val or not pat.match(val):
                    from odoo.exceptions import UserError as _UE
                    raise _UE("Shift time must be HH:MM:SS (SPEC TIME, UTC).")


class HrmShiftAssignment(models.Model):
    _name = "hrm.shift.assignment"
    _inherit = ["hrm.base.mixin"]
    _description = "Employee -> shift, effective-dated (SPEC §7.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    shift_id = fields.Many2one("hrm.shift", required=True, ondelete="restrict")
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Shift assignment UUID must be unique.")

    @api.constrains("employee_id", "effective_from", "effective_to")
    def _check_no_overlap(self):
        from datetime import date as _date
        for rec in self:
            if not rec.effective_from:
                continue
            rec_end = rec.effective_to or _date.max
            others = self.search([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("effective_from", "<=", rec_end),
            ]).filtered(lambda o: (o.effective_to or _date.max) >= rec.effective_from)
            if others:
                from odoo.exceptions import UserError as _UE
                raise _UE("Overlapping shift assignments are not allowed for the same employee.")


class HrmAttendanceDevice(models.Model):
    _name = "hrm.attendance.device"
    _inherit = ["hrm.base.mixin"]
    _description = "Attendance device (SPEC §7.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    location_id = fields.Many2one("hrm.location", ondelete="set null")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    device_type = fields.Selection(
        [("biometric", "Biometric"), ("rfid", "RFID"), ("mobile", "Mobile"),
         ("web", "Web"), ("api", "API")],
        required=True,
    )
    external_device_id = fields.Char()
    ip_address = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("inactive", "Inactive")],
        default="active",
        required=True,
    )
    last_sync_at = fields.Datetime()
    configuration = fields.Json(default=dict)

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)",
        "Device code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Device UUID must be unique.")
