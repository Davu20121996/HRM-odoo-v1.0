from odoo.tests.common import TransactionCase


class TestVnRules(TransactionCase):
    def test_insurance_current_and_pit(self):
        tenant = self.env["hrm.tenant"].create({
            "code": "VN1", "name": "VN Co", "slug": "vn-co",
            "status": "active", "timezone": "Asia/Ho_Chi_Minh",
            "locale": "vi-VN", "default_currency": "VND",
        })
        rule = self.env["hrm.insurance.rule"].create({
            "tenant_id": False, "code": "vn_bhxh", "name": "BHXH default",
            "effective_from": "2024-01-01", "status": "active",
        })
        self.assertTrue(self.env["hrm.insurance.rule"].current(False, "2024-06-01"))
        from odoo.addons.hrm_payroll.models.salary import PAYROLL_RULE_HANDLERS
        self.assertIn("vn_pit", PAYROLL_RULE_HANDLERS)
        self.assertEqual(PAYROLL_RULE_HANDLERS["vn_pit"]({"gross": 10000000.0}), 0.0)
