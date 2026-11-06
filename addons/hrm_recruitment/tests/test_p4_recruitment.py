"""P4 quality gates: requisition flow, stages, offer -> employee conversion."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP4Recruitment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P4T",
                "name": "P4 Tenant",
                "slug": "p4-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.company = cls.env["hrm.company"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "P4C",
                "name": "P4 Company",
                "currency_code": "VND",
            }
        )
        cls.dept = cls.env["hrm.department"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "P4D",
                "name": "P4 Dept",
            }
        )
        cls.job = cls.env["hrm.job"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "DEV",
                "title": "Developer",
            }
        )
        cls.requisition = cls.env["hrm.job.requisition"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "department_id": cls.dept.id,
                "job_id": cls.job.id,
                "approved_headcount": 2,
            }
        )
        cls.stage_screen = cls.env["hrm.recruitment.stage"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "SCREEN",
                "name": "Screening",
                "sequence_no": 10,
                "stage_type": "screen",
            }
        )
        cls.candidate = cls.env["hrm.candidate"].create(
            {
                "tenant_id": cls.tenant.id,
                "candidate_code": "CAND-001",
                "first_name": "Binh",
                "last_name": "Tran",
                "email": "binh@example.com",
            }
        )
        cls.application = cls.env["hrm.application"].create(
            {
                "tenant_id": cls.tenant.id,
                "candidate_id": cls.candidate.id,
                "requisition_id": cls.requisition.id,
            }
        )

    def test_requisition_flow(self):
        self.requisition.action_submit()
        self.requisition.action_approve()
        self.requisition.action_open()
        self.assertEqual(self.requisition.status, "open")
        with self.assertRaises(UserError):
            self.requisition.action_approve()

    def test_move_stage(self):
        self.application.action_move_stage(self.stage_screen.id)
        self.assertEqual(self.application.current_stage_id.id, self.stage_screen.id)
        self.assertEqual(self.application.status, "in_progress")

    def test_offer_accept_creates_employee(self):
        offer = self.env["hrm.offer"].create(
            {
                "tenant_id": self.tenant.id,
                "application_id": self.application.id,
                "offer_no": "OFFER-001",
                "base_salary": 25000000,
                "currency_code": "VND",
                "start_date": "2026-10-01",
            }
        )
        offer.action_submit()
        offer.action_send()
        employee = offer.action_accept()
        self.assertEqual(offer.status, "accepted")
        self.assertEqual(offer.employee_id.id, employee.id)
        self.assertEqual(employee.employee_code, "CAND-001")
        self.assertEqual(employee.person_id.first_name, "Binh")
        self.assertEqual(self.application.status, "hired")
        self.assertEqual(self.candidate.status, "hired")
        self.assertTrue(employee.current_assignment_id)
        self.assertEqual(
            employee.current_assignment_id.department_id.id, self.dept.id
        )
        with self.assertRaises(UserError):
            offer.action_accept()

    def test_offer_must_be_sent_before_accept(self):
        offer = self.env["hrm.offer"].create(
            {
                "tenant_id": self.tenant.id,
                "application_id": self.application.id,
                "offer_no": "OFFER-002",
                "base_salary": 10000000,
                "currency_code": "VND",
            }
        )
        with self.assertRaises(UserError):
            offer.action_accept()

    def test_interview_evaluation(self):
        interviewer = self.env["hr.employee"].create(
            {
                "name": "Interviewer",
                "tenant_id": self.tenant.id,
                "employee_code": "INT-001",
            }
        )
        interview = self.env["hrm.interview"].create(
            {
                "tenant_id": self.tenant.id,
                "application_id": self.application.id,
                "interviewer_employee_id": interviewer.id,
                "scheduled_at": "2026-09-30 09:00:00",
            }
        )
        evaluation = self.env["hrm.interview.evaluation"].create(
            {
                "tenant_id": self.tenant.id,
                "interview_id": interview.id,
                "evaluator_employee_id": interviewer.id,
                "score": 8.5,
                "recommendation": "hire",
            }
        )
        evaluation.action_submit()
        interview.action_done()
        self.assertTrue(evaluation.submitted_at)
        self.assertEqual(interview.status, "done")
