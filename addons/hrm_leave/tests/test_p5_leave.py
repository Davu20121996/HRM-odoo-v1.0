"""P5-leave quality gates: allocation, ledger balance, approval posts usage."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP5Leave(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P5L",
                "name": "P5 Leave Tenant",
                "slug": "p5-leave-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Leave Taker",
                "tenant_id": cls.tenant.id,
                "employee_code": "L001",
            }
        )
        cls.leave_type = cls.env["hrm.leave.type"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "ANNUAL",
                "name": "Phep nam",
                "paid": True,
                "unit": "day",
            }
        )
        cls.env["hrm.leave.allocation"].create(
            {
                "tenant_id": cls.tenant.id,
                "employee_id": cls.employee.id,
                "leave_type_id": cls.leave_type.id,
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "allocated_quantity": 12,
            }
        ).action_activate()

    def _request(self, qty):
        return self.env["hrm.leave.request"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "leave_type_id": self.leave_type.id,
                "start_at": "2026-10-01 08:00:00",
                "end_at": "2026-10-01 17:00:00",
                "requested_quantity": qty,
            }
        )

    def test_allocation_posts_ledger(self):
        balance = self.env["hrm.leave.balance.ledger"].balance_of(
            self.tenant.id, self.employee.id, self.leave_type.id
        )
        self.assertEqual(balance, 12)

    def test_approve_posts_usage(self):
        req = self._request(2)
        req.action_submit()
        req.action_approve()
        self.assertEqual(req.status, "approved")
        balance = self.env["hrm.leave.balance.ledger"].balance_of(
            self.tenant.id, self.employee.id, self.leave_type.id
        )
        self.assertEqual(balance, 10)
        req.action_take()
        self.assertEqual(req.status, "taken")

    def test_insufficient_balance_rejected(self):
        req = self._request(99)
        req.action_submit()
        with self.assertRaises(UserError):
            req.action_approve()
        self.assertEqual(req.status, "pending_approval")

    def test_ledger_immutable(self):
        line = self.env["hrm.leave.balance.ledger"].search(
            [("employee_id", "=", self.employee.id)], limit=1
        )
        with self.assertRaises(UserError):
            line.write({"quantity": 100})
        with self.assertRaises(UserError):
            line.unlink()

    def test_bad_dates_rejected(self):
        with self.assertRaises(UserError):
            self.env["hrm.leave.request"].create(
                {
                    "tenant_id": self.tenant.id,
                    "employee_id": self.employee.id,
                    "leave_type_id": self.leave_type.id,
                    "start_at": "2026-10-02 08:00:00",
                    "end_at": "2026-10-01 17:00:00",
                    "requested_quantity": 1,
                }
            )
