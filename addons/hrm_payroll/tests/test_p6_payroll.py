"""P6 quality gates: calculation math, overlap, finalize immutability, extras."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP6Payroll(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P6T",
                "name": "P6 Tenant",
                "slug": "p6-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.company = cls.env["hrm.company"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "P6C",
                "name": "P6 Company",
                "currency_code": "VND",
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Payroll Earner",
                "tenant_id": cls.tenant.id,
                "employee_code": "P001",
                "current_status": "active",
            }
        )
        cls.structure = cls.env["hrm.salary.structure"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "code": "STD",
                "name": "Standard",
                "currency_code": "VND",
                "component_ids": [
                    (0, 0, {
                        "tenant_id": cls.tenant.id,
                        "code": "BASE",
                        "name": "Luong co ban",
                        "component_type": "earning",
                        "calculation_type": "formula",
                        "sequence_no": 10,
                        "configuration": {"expression": "base_salary"},
                    }),
                    (0, 0, {
                        "tenant_id": cls.tenant.id,
                        "code": "ALLOW",
                        "name": "Phu cap",
                        "component_type": "earning",
                        "calculation_type": "fixed",
                        "sequence_no": 20,
                        "configuration": {"fixed_amount": 2000000},
                    }),
                    (0, 0, {
                        "tenant_id": cls.tenant.id,
                        "code": "BHXH",
                        "name": "BHXH NLĐ",
                        "component_type": "contribution",
                        "calculation_type": "percentage",
                        "sequence_no": 30,
                        "configuration": {"percent": 8.0, "base": "base_salary"},
                    }),
                ],
            }
        )
        cls.env["hrm.employee.salary"].create(
            {
                "tenant_id": cls.tenant.id,
                "employee_id": cls.employee.id,
                "structure_id": cls.structure.id,
                "effective_from": "2026-01-01",
                "base_salary": 10000000,
                "currency_code": "VND",
            }
        )
        cls.period = cls.env["hrm.payroll.period"].create(
            {
                "tenant_id": cls.tenant.id,
                "company_id": cls.company.id,
                "period_code": "2026-09",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
            }
        )

    def _run_full_cycle(self):
        run = self.env["hrm.payroll"].create(
            {
                "tenant_id": self.tenant.id,
                "company_id": self.company.id,
                "period_id": self.period.id,
            }
        )
        run.action_start()
        run.action_calculate()
        run.action_review()
        run.action_approve()
        run.action_finalize()
        return run

    def test_calculation_math(self):
        run = self.env["hrm.payroll"].create(
            {
                "tenant_id": self.tenant.id,
                "company_id": self.company.id,
                "period_id": self.period.id,
            }
        )
        run.action_start()
        run.action_calculate()
        item = run.item_ids.filtered(
            lambda i: i.employee_id.id == self.employee.id
        )
        self.assertEqual(len(item), 1)
        # gross = 10M + 2M, deduction = 8% of 10M, net = rest
        self.assertAlmostEqual(item.gross_amount, 12000000)
        self.assertAlmostEqual(item.deduction_amount, 800000)
        self.assertAlmostEqual(item.net_amount, 11200000)

    def test_bonus_adds_to_gross(self):
        self.env["hrm.bonus"].create(
            {
                "tenant_id": self.tenant.id,
                "employee_id": self.employee.id,
                "amount": 1000000,
                "currency_code": "VND",
                "effective_date": "2026-09-15",
                "status": "approved",
            }
        )
        run = self.env["hrm.payroll"].create(
            {
                "tenant_id": self.tenant.id,
                "company_id": self.company.id,
                "period_id": self.period.id,
            }
        )
        run.action_start()
        run.action_calculate()
        item = run.item_ids.filtered(
            lambda i: i.employee_id.id == self.employee.id
        )
        self.assertAlmostEqual(item.gross_amount, 13000000)

    def test_finalize_locks_everything(self):
        run = self._run_full_cycle()
        self.assertEqual(run.status, "finalized")
        payslip = self.env["hrm.payslip"].search([("payroll_id", "=", run.id)])
        self.assertEqual(len(payslip), 1)
        self.assertEqual(payslip.status, "issued")
        self.assertEqual(len(payslip.item_ids), 3)
        with self.assertRaises(UserError):
            run.write({"run_no": 2})
        with self.assertRaises(UserError):
            payslip.write({"net_amount": 1})
        run.action_mark_paid()
        self.assertEqual(run.status, "paid")
        self.assertEqual(payslip.status, "paid")

    def test_salary_no_overlap(self):
        with self.assertRaises(UserError):
            self.env["hrm.employee.salary"].create(
                {
                    "tenant_id": self.tenant.id,
                    "employee_id": self.employee.id,
                    "structure_id": self.structure.id,
                    "effective_from": "2026-06-01",
                    "base_salary": 11000000,
                    "currency_code": "VND",
                }
            )

    def test_run_no_unique_per_period(self):
        from psycopg2 import IntegrityError

        self.env["hrm.payroll"].create(
            {
                "tenant_id": self.tenant.id,
                "company_id": self.company.id,
                "period_id": self.period.id,
            }
        )
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hrm.payroll"].create(
                {
                    "tenant_id": self.tenant.id,
                    "company_id": self.company.id,
                    "period_id": self.period.id,
                }
            )
