"""P3 quality gates: engine start/approve/reject, auth, immutability, notifications."""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestP3Workflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P3T",
                "name": "P3 Tenant",
                "slug": "p3-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )
        cls.user_a = cls.env["res.users"].create(
            {"name": "Approver A", "login": "approver_a@example.com"}
        )
        cls.user_b = cls.env["res.users"].create(
            {"name": "Approver B", "login": "approver_b@example.com"}
        )
        hrm_user = cls.env.ref("hrm_base.group_hrm_user")
        (cls.user_a + cls.user_b).write(
            {
                "group_ids": [(4, hrm_user.id)],
                "hrm_tenant_ids": [(6, 0, [cls.tenant.id])],
            }
        )
        cls.definition = cls.env["hrm.workflow.definition"].create(
            {
                "tenant_id": cls.tenant.id,
                "code": "TEST2STEP",
                "name": "Two step test",
                "entity_type": "hrm.leave.request",
                "status": "active",
                "step_ids": [
                    (0, 0, {
                        "tenant_id": cls.tenant.id,
                        "step_code": "S1",
                        "name": "Step one",
                        "sequence_no": 10,
                        "approver_type": "specific_user",
                        "approver_user_id": cls.user_a.id,
                    }),
                    (0, 0, {
                        "tenant_id": cls.tenant.id,
                        "step_code": "S2",
                        "name": "Step two",
                        "sequence_no": 20,
                        "approver_type": "specific_user",
                        "approver_user_id": cls.user_b.id,
                    }),
                ],
            }
        )

    def test_full_approval_flow(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=1
        )
        self.assertEqual(inst.status, "in_progress")
        self.assertEqual(inst.current_state, "S1")
        req_a = inst.approval_ids.filtered(
            lambda a: a.approver_user_id.id == self.user_a.id
        )
        self.assertEqual(len(req_a), 1)
        req_a.with_user(self.user_a).action_approve("ok step1")
        self.assertEqual(inst.current_state, "S2")
        req_b = inst.approval_ids.filtered(
            lambda a: a.approver_user_id.id == self.user_b.id
        )
        req_b.with_user(self.user_b).action_approve("ok step2")
        self.assertEqual(inst.status, "approved")
        self.assertTrue(inst.completed_at)

    def test_reject_stops_flow(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=2
        )
        req_a = inst.approval_ids.filtered(
            lambda a: a.approver_user_id.id == self.user_a.id
        )
        req_a.with_user(self.user_a).action_reject("nope")
        self.assertEqual(inst.status, "rejected")
        self.assertEqual(len(inst.approval_ids), 1)

    def test_wrong_approver_rejected(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=3
        )
        req_a = inst.approval_ids.filtered(
            lambda a: a.approver_user_id.id == self.user_a.id
        )
        with self.assertRaises(UserError):
            req_a.with_user(self.user_b).action_approve("intruder")

    def test_decided_approval_immutable(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=4
        )
        req_a = inst.approval_ids.filtered(
            lambda a: a.approver_user_id.id == self.user_a.id
        )
        req_a.with_user(self.user_a).action_approve("done")
        with self.assertRaises(UserError):
            req_a.with_user(self.user_a).write({"comment": "rewrite history"})
        with self.assertRaises(UserError):
            req_a.unlink()
        with self.assertRaises(UserError):
            inst.write({"status": "approved"})

    def test_start_returns_clean_context(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=6
        )
        self.assertNotIn("hrm_engine", inst.env.context)

    def test_approver_gets_notification(self):
        inst = self.env["hrm.workflow.instance"].start(
            "TEST2STEP", self.tenant.id, "hrm.leave.request", entity_id=5
        )
        notifs = self.env["hrm.notification"].search(
            [
                ("recipient_user_id", "=", self.user_a.id),
                ("template_code", "=", "workflow.approval_needed"),
            ]
        )
        self.assertTrue(notifs)
        self.assertGreaterEqual(len(notifs), 1)
        notifs[0].with_user(self.user_a).action_mark_read()
        self.assertEqual(notifs[0].status, "read")
        self.assertEqual(notifs[0].payload["instance_id"], inst.id)
