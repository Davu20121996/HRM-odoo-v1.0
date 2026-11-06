"""P7-learning quality gates: enrollment flow, uniqueness, matrix."""
from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP7Learning(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P7L",
                "name": "P7 Learn Tenant",
                "slug": "p7-learn-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Learner",
                "tenant_id": cls.tenant.id,
                "employee_code": "LR001",
            }
        )
        cls.course = cls.env["hrm.course"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "PY101",
                "name": "Python Basics",
                "duration_minutes": 480,
            }
        )
        cls.training = cls.env["hrm.training"].create(
            {
                "tenant_id": cls.tenant.id,
                "course_id": cls.course.id,
                "start_at": "2026-10-01 08:00:00",
                "end_at": "2026-10-01 17:00:00",
                "capacity": 20,
            }
        )
        cls.training.action_open()

    def test_enrollment_flow(self):
        enr = self.env["hrm.training.enrollment"].create(
            {
                "tenant_id": self.tenant.id,
                "training_id": self.training.id,
                "employee_id": self.employee.id,
            }
        )
        enr.action_complete(score=9.0)
        self.assertEqual(enr.status, "completed")
        self.assertAlmostEqual(enr.score, 9.0)
        self.assertTrue(enr.completion_at)
        with self.assertRaises(UserError):
            enr.action_complete()

    def test_enroll_once(self):
        self.env["hrm.training.enrollment"].create(
            {
                "tenant_id": self.tenant.id,
                "training_id": self.training.id,
                "employee_id": self.employee.id,
            }
        )
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hrm.training.enrollment"].create(
                {
                    "tenant_id": self.tenant.id,
                    "training_id": self.training.id,
                    "employee_id": self.employee.id,
                }
            )

    def test_skill_matrix(self):
        skill = self.env["hrm.skill"].create(
            {
                "tenant_id": self.tenant.id,
                "code": "PY",
                "name": "Python",
                "category": "Technical",
            }
        )
        self.env["hrm.skill.matrix"].create(
            {
                "tenant_id": self.tenant.id,
                "skill_id": skill.id,
                "required_level": "intermediate",
            }
        )
        cert = self.env["hrm.certification"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "name": "Python Certified",
                "issuer": "HRM Academy",
            }
        )
        self.assertEqual(cert.status, "valid")
