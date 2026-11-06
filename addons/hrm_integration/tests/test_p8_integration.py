"""P8 quality gates: outbox publish, HMAC delivery, retries, idempotency, imports."""
import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class _HookHandler(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _HookHandler.received.append(
            {"body": body, "signature": self.headers.get("X-HRM-Signature")}
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


class TestP8Integration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant = cls.env["hrm.tenant"].create(
            {
                "code": "P8T",
                "name": "P8 Tenant",
                "slug": "p8-tenant",
                "status": "active",
                "default_currency": "VND",
            }
        )

    def test_publish_no_endpoint_marks_published(self):
        event = self.env["hrm.event.outbox"].enqueue(
            "EmployeeCreated", "Employee", self.tenant.id,
            aggregate_id="1", payload={"code": "E1"},
        )
        self.assertEqual(event.status, "pending")
        self.env["hrm.event.outbox"].action_publish_pending()
        self.assertEqual(event.status, "published")
        self.assertTrue(event.published_at)
        with self.assertRaises(UserError):
            event.write({"last_error": "x"})

    def test_webhook_delivery_with_signature(self):
        _HookHandler.received = []
        server = HTTPServer(("127.0.0.1", 18099), _HookHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            self.env["hrm.webhook.endpoint"].create(
                {
                    "tenant_id": self.tenant.id,
                    "name": "Test hook",
                    "url": "http://127.0.0.1:18099/hook",
                    "configuration": {"secret": "s3cr3t"},
                    "event_filters": {"event_types": ["EmployeeCreated"]},
                }
            )
            self.env["hrm.event.outbox"].enqueue(
                "EmployeeCreated", "Employee", self.tenant.id, aggregate_id="2"
            )
            self.env["hrm.event.outbox"].action_publish_pending()
        finally:
            thread.join(timeout=15)
            server.server_close()
        self.assertEqual(len(_HookHandler.received), 1)
        body = _HookHandler.received[0]["body"]
        expected = "sha256=" + hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
        self.assertEqual(_HookHandler.received[0]["signature"], expected)
        data = json.loads(body)
        self.assertEqual(data["event_type"], "EmployeeCreated")
        delivery = self.env["hrm.webhook.delivery"].search([], limit=1)
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(delivery.http_status, 200)

    def test_failed_delivery_retries_then_dead(self):
        self.env["hrm.webhook.endpoint"].create(
            {
                "tenant_id": self.tenant.id,
                "name": "Dead hook",
                "url": "http://127.0.0.1:9/hook",
            }
        )
        event = self.env["hrm.event.outbox"].enqueue(
            "LeaveApproved", "Leave", self.tenant.id, aggregate_id="3"
        )
        Outbox = self.env["hrm.event.outbox"]
        Outbox.action_publish_pending()
        self.assertEqual(event.retry_count, 1)
        self.assertEqual(event.status, "pending")
        Outbox.action_publish_pending()
        Outbox.action_publish_pending()
        self.assertEqual(event.retry_count, 3)
        self.assertEqual(event.status, "failed")

    def test_idempotency_replay(self):
        Keys = self.env["hrm.idempotency.key"]
        rec, replay = Keys.check_or_reserve(self.tenant.id, "REQ-1", "hash-abc")
        self.assertFalse(replay)
        rec.store_response("200", {"ok": True})
        rec2, replay2 = Keys.check_or_reserve(self.tenant.id, "REQ-1", "hash-abc")
        self.assertTrue(replay2)
        self.assertEqual(rec2.response_status, "200")
        with self.assertRaises(UserError):
            Keys.check_or_reserve(self.tenant.id, "REQ-1", "different-hash")

    def test_import_job_progress(self):
        job = self.env["hrm.import.job"].create(
            {
                "tenant_id": self.tenant.id,
                "entity_type": "hr.employee",
                "file_storage_key": "imports/emp.csv",
            }
        )
        job.action_start(total_rows=10)
        job.action_add_result(success=True, count=7)
        job.action_add_result(success=False, count=3)
        job.action_finish()
        self.assertEqual(
            (job.processed_rows, job.success_rows, job.failed_rows), (10, 7, 3)
        )
        self.assertEqual(job.status, "done")

    def test_connection_requires_base_url(self):
        conn = self.env["hrm.integration.connection"].create(
            {
                "tenant_id": self.tenant.id,
                "provider": "zalo",
                "connection_type": "api_key",
            }
        )
        with self.assertRaises(UserError):
            conn.action_connect()
        conn.write({"configuration": {"base_url": "https://api.example.com"}})
        conn.action_connect()
        self.assertEqual(conn.status, "connected")
