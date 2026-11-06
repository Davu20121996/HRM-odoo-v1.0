"""P2 quality gates: person/employee, overlap, self-report, immutability, transitions."""
from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP2CoreHr(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P2T",
                "name": "P2 Tenant",
                "slug": "p2-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.company = cls.env["hrm.company"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "P2C",
                "name": "P2 Company",
                "currency_code": "VND",
            }
        )
        cls.dept = cls.env["hrm.department"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "P2D",
                "name": "P2 Dept",
            }
        )
        cls.person = cls.env["hrm.person"].create(
            {
                "tenant_id": cls.tenant.id,
                "first_name": "An",
                "last_name": "Nguyen Van",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Nguyen Van An",
                "tenant_id": cls.tenant.id,
                "person_id": cls.person.id,
                "employee_code": "E001",
            }
        )

    def test_person_employee_unique_per_tenant(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hr.employee"].create(
                {
                    "name": "Duplicate Person",
                    "tenant_id": self.tenant.id,
                    "person_id": self.person.id,
                    "employee_code": "E002",
                }
            )

    def test_assignment_no_overlap_primary(self):
        self.env["hrm.employee.assignment"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "company_id": self.company.id,
                "department_id": self.dept.id,
                "assignment_type": "primary",
                "start_date": "2026-01-01",
            }
        )
        with self.assertRaises(UserError):
            self.env["hrm.employee.assignment"].create(
                {
                    "tenant_id": self.tenant.id,
                    "employee_id": self.employee.id,
                    "company_id": self.company.id,
                    "department_id": self.dept.id,
                    "assignment_type": "primary",
                    "start_date": "2026-06-01",
                }
            )

    def test_reporting_line_no_self_report(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hrm.reporting.line"].create(
                {
                    "tenant_id": self.tenant.id,
                    "company_id": self.company.id,
                    "manager_employee_id": self.employee.id,
                    "employee_id": self.employee.id,
                }
            )

    def test_salary_history_immutable(self):
        hist = self.env["hrm.salary.history"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "effective_from": "2026-01-01",
                "base_salary": 20000000,
                "currency_code": "VND",
                "change_type": "hire",
            }
        )
        with self.assertRaises(UserError):
            hist.write({"base_salary": 1})
        with self.assertRaises(UserError):
            hist.unlink()

    def test_contract_transitions_enforced(self):
        ctype = self.env["hrm.contract.type"].search(
            [("code", "=", "UNLIMITED")], limit=1
        )
        contract = self.env["hrm.employee.contract"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "company_id": self.company.id,
                "contract_type_id": ctype.id,
                "contract_no": "HD-001",
                "start_date": "2026-01-01",
                "base_salary": 20000000,
            }
        )
        with self.assertRaises(UserError):
            contract.action_activate()
        contract.action_submit()
        contract.action_approve()
        contract.action_activate()
        self.assertEqual(contract.status, "active")

    def test_employee_status_move_writes_history(self):
        self.employee.action_onboard()
        self.employee.action_activate()
        self.assertEqual(self.employee.current_status, "active")
        hist = self.env["hrm.employment.status.history"].search(
            [("employee_id", "=", self.employee.id)], order="id"
        )
        self.assertEqual([h.to_status for h in hist], ["onboarding", "active"])
        with self.assertRaises(UserError):
            hist.unlink()
