"""P7-performance quality gates: cycle flow, goal progress, 360 calibration."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP7Performance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P7P",
                "name": "P7 Perf Tenant",
                "slug": "p7-perf-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Performer",
                "tenant_id": cls.tenant.id,
                "employee_code": "PF001",
            }
        )
        cls.reviewer = cls.env["hr.employee"].create(
            {
                "name": "Reviewer",
                "tenant_id": cls.tenant.id,
                "employee_code": "PF002",
            }
        )
        cls.cycle = cls.env["hrm.performance.cycle"].create(
            {
                "tenant_id": cls.tenant.id,
                "name": "2026 H2",
                "period_start": "2026-07-01",
                "period_end": "2026-12-31",
            }
        )

    def test_cycle_flow(self):
        self.cycle.action_open()
        self.cycle.action_review()
        self.cycle.action_calibrate()
        self.cycle.action_finalize()
        self.cycle.action_close()
        self.assertEqual(self.cycle.status, "closed")
        with self.assertRaises(UserError):
            self.cycle.action_open()

    def test_goal_progress(self):
        goal = self.env["hrm.goal"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "cycle_id": self.cycle.id,
                "title": "Ship v2",
                "target_value": 100,
                "actual_value": 75,
            }
        )
        self.assertAlmostEqual(goal.progress, 75.0)
        goal.action_activate()
        goal.action_done()
        self.assertEqual(goal.status, "done")

    def test_appraisal_calibration_from_360(self):
        appraisal = self.env["hrm.appraisal"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "cycle_id": self.cycle.id,
                "reviewer_employee_id": self.reviewer.id,
            }
        )
        for score, rel in [(8.0, "manager"), (6.0, "peer")]:
            self.env["hrm.feedback.360"].create(
                {
                    "tenant_id": self.tenant.id,
                    "appraisal_id": appraisal.id,
                    "reviewer_employee_id": self.reviewer.id,
                    "relationship_type": rel,
                    "score": score,
                    "status": "submitted",
                    "submitted_at": "2026-09-01 10:00:00",
                }
            )
        appraisal.action_submit()
        appraisal.action_calibrate()
        self.assertAlmostEqual(appraisal.overall_score, 7.0)
        appraisal.action_finalize()
        self.assertEqual(appraisal.status, "finalized")

    def test_okr_bounds(self):
        okr = self.env["hrm.okr"].create(
            {
                "tenant_id": self.tenant.id,
                "cycle_id": self.cycle.id,
                "employee_id": self.employee.id,
                "objective": "Grow revenue",
                "progress": 40,
            }
        )
        with self.assertRaises(UserError):
            okr.write({"progress": 150})
