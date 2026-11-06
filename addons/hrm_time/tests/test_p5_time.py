"""P5-time quality gates: ingest idempotency, pipeline, lock, OT entries."""
from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP5Time(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P5T",
                "name": "P5 Tenant",
                "slug": "p5-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.company = cls.env["hrm.company"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "P5C",
                "name": "P5 Company",
                "currency_code": "VND",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Time Keeper",
                "tenant_id": cls.tenant.id,
                "employee_code": "T001",
            }
        )
        cls.shift = cls.env["hrm.shift"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "HC",
                "name": "Hanh chinh",
"start_time": "08:00:00",
                "end_time": "17:30:00",
            }
        )
        cls.env["hrm.shift.assignment"].create(
            {
                "tenant_id": cls.tenant.id,
                "employee_id": cls.employee.id,
                "shift_id": cls.shift.id,
                "effective_from": "2026-01-01",
            }
        )
        cls.device = cls.env["hrm.attendance.device"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "DEV-01",
                "name": "Gate 1",
                "device_type": "biometric",
            }
        )

    def _ingest_day(self):
        Event = self.env["hrm.attendance.device.event"]
        Event.ingest(
            self.tenant.id, "DEV-01", "check_in", "2026-09-29 08:15:00",
            external_event_id="EV-IN-1", employee_id=self.employee.id,
        )
        Event.ingest(
            self.tenant.id, "DEV-01", "check_out", "2026-09-29 17:30:00",
            external_event_id="EV-OUT-1", employee_id=self.employee.id,
        )

    def test_ingest_idempotent(self):
        Event = self.env["hrm.attendance.device.event"]
        e1 = Event.ingest(
            self.tenant.id, "DEV-01", "check_in", "2026-09-29 08:15:00",
            external_event_id="EV-DUP", employee_id=self.employee.id,
        )
        e2 = Event.ingest(
            self.tenant.id, "DEV-01", "check_in", "2026-09-29 08:15:00",
            external_event_id="EV-DUP", employee_id=self.employee.id,
        )
        self.assertEqual(e1.id, e2.id)
        with self.assertRaises(UserError):
            e1.write({"event_time": "2026-09-29 09:00:00"})
        with self.assertRaises(UserError):
            e1.unlink()

    def test_process_computes_late(self):
        self._ingest_day()
        att = self.env["hrm.attendance"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "work_date": "2026-09-29",
            }
        )
        att.action_process()
        self.assertEqual(att.status, "calculated")
        self.assertEqual(att.late_minutes, 15)
        self.assertEqual(att.worked_minutes, 555)
        att.action_validate()
        att.action_lock()
        self.assertEqual(att.status, "locked")
        with self.assertRaises(UserError):
            att.write({"late_minutes": 0})
        entry = self.env["hrm.work.entry"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("work_date", "=", "2026-09-29"),
                ("entry_type", "=", "attendance"),
            ]
        )
        self.assertEqual(len(entry), 1)

    def test_adjustment_on_locked(self):
        self._ingest_day()
        att = self.env["hrm.attendance"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "work_date": "2026-09-29",
            }
        )
        att.action_process()
        att.action_validate()
        att.action_lock()
        adj = self.env["hrm.attendance.adjustment"].create(
            {
                "tenant_id": self.tenant.id,
                "attendance_id": att.id,
                "employee_id": self.employee.id,
                "requested_by_id": self.env.uid,
                "reason": "Forgot to check in on time",
                "old_value": {"late_minutes": 15},
                "new_value": {"late_minutes": 0},
            }
        )
        adj.action_approve()
        self.assertEqual(adj.status, "approved")
        self.assertEqual(
            self.env["hrm.attendance"].browse(att.id).late_minutes, 0
        )

    def test_overtime_creates_entry(self):
        ot = self.env["hrm.overtime.request"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "work_date": "2026-09-29",
                "start_at": "2026-09-29 18:00:00",
                "end_at": "2026-09-29 20:00:00",
                "requested_minutes": 120,
                "reason": "Release",
            }
        )
        ot.action_submit()
        ot.action_approve()
        self.assertEqual(ot.approved_minutes, 120)
        entry = self.env["hrm.work.entry"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("entry_type", "=", "overtime"),
            ]
        )
        self.assertEqual(len(entry), 1)
        self.assertAlmostEqual(entry.quantity, 2.0)

    def test_one_attendance_per_day(self):
        self.env["hrm.attendance"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "work_date": "2026-09-29",
            }
        )
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hrm.attendance"].create(
                {
                    "tenant_id": self.tenant.id,
                    "employee_id": self.employee.id,
                    "work_date": "2026-09-29",
                }
            )
