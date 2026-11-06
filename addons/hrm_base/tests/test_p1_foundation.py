"""P1 quality gates: tenant isolation, uniques, audit immutability, versioning."""
from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP1Foundation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "T1",
                "name": "Tenant One",
                "slug": "tenant-one",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.company = cls.env["hrm.company"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "C1",
                "name": "Company One",
                "currency_code": "VND",
            }
        )

    def test_seed_roles_permissions(self):
        self.assertEqual(self.env["hrm.role"].search_count([]), 8)
        self.assertGreaterEqual(self.env["hrm.permission"].search_count([]), 30)
        admin = self.env["hrm.role"].search([("code", "=", "HR_ADMIN")], limit=1)
        self.assertTrue(admin.permission_ids)

    def test_company_code_unique_per_tenant(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["hrm.company"].create(
                {
                    "tenant_id": self.tenant.id,
                    "code": "C1",
                    "name": "Duplicate",
                    "currency_code": "VND",
                }
            )

    def test_audit_log_immutable(self):
        log = self.env["hrm.audit.log"].create(
            {
                "tenant_id": self.tenant.id,
                "action": "CREATE",
                "entity_type": "hrm.company",
                "entity_id": self.company.id,
            }
        )
        with self.assertRaises(UserError):
            log.write({"action": "UPDATE"})
        with self.assertRaises(UserError):
            log.unlink()

    def test_version_increments_on_write(self):
        dept = self.env["hrm.department"].create(
            {
                "tenant_id": self.tenant.id,
                "company_id": self.company.id,
                "code": "D1",
                "name": "Dept One",
            }
        )
        self.assertEqual(dept.version, 1)
        dept.write({"name": "Dept One Renamed"})
        self.assertEqual(dept.version, 2)

    def test_tenant_record_rule(self):
        other_tenant = self.env["hrm.tenant"].create(
            {"code": "T2", "name": "Tenant Two", "slug": "tenant-two"}
        )
        user = self.env["res.users"].create(
            {
                "name": "Scoped User",
                "login": "scoped@example.com",
                "hrm_tenant_ids": [(6, 0, [self.tenant.id])],
                "group_ids": [(6, 0, [self.env.ref("hrm_base.group_hrm_user").id])],
            }
        )
        companies = (
            self.env["hrm.company"].with_user(user).search([("id", "in", [self.company.id])])
        )
        self.assertEqual(len(companies), 1)
        other_company = self.env["hrm.company"].create(
            {
                "tenant_id": other_tenant.id,
                "code": "C9",
                "name": "Other Co",
                "currency_code": "VND",
            }
        )
        hidden = (
            self.env["hrm.company"].with_user(user).search([("id", "=", other_company.id)])
        )
        self.assertEqual(len(hidden), 0)
