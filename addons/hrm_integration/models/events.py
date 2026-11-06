import hashlib
import hmac
import json
import logging
import urllib.request
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
MAX_RETRIES = 3


class HrmEventOutbox(models.Model):
    """Transactional outbox (SPEC §18.1). Business code calls enqueue() in
    the SAME transaction as its own writes; the publisher (cron) dispatches."""

    _name = "hrm.event.outbox"
    _inherit = ["hrm.base.mixin"]
    _description = "Event outbox (SPEC §18.1)"
    _order = "id"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    event_id = fields.Char(readonly=True, copy=False, help="Canonical event UUID (SPEC §30).")
    event_type = fields.Char(required=True)
    event_version = fields.Integer(default=1, required=True)
    aggregate_type = fields.Char(required=True)
    aggregate_id = fields.Char()
    correlation_id = fields.Char()
    payload = fields.Json(default=dict)
    occurred_at = fields.Datetime(required=True, default=fields.Datetime.now)
    published_at = fields.Datetime()
    status = fields.Selection(
        [("pending", "Pending"), ("published", "Published"), ("failed", "Failed")],
        default="pending",
        required=True,
    )
    retry_count = fields.Integer(default=0)
    last_error = fields.Text()

    def write(self, vals):
        if self.env.context.get("hrm_engine"):
            return super().write(vals)
        if any(rec.status in ("published", "failed") for rec in self):
            raise UserError("Published/failed outbox events are immutable.")
        return super().write(vals)

    def unlink(self):
        if any(rec.status in ("published", "failed") for rec in self):
            raise UserError("Published/failed outbox events cannot be deleted.")
        return super().unlink()

    @api.model
    def enqueue(self, event_type, aggregate_type, tenant_id, aggregate_id=None,
                payload=None, event_version=1, correlation_id=None):
        """Standard envelope (SPEC §30). Call inside the business transaction."""
        import uuid as _uuid
        return self.create(
            {
                "tenant_id": tenant_id,
                "event_id": str(_uuid.uuid4()),
                "event_type": event_type,
                "event_version": event_version,
                "aggregate_type": aggregate_type,
                "aggregate_id": str(aggregate_id) if aggregate_id is not None else None,
                "correlation_id": correlation_id,
                "payload": {
                    "event_version": event_version,
                    "tenant_id": tenant_id,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": str(aggregate_id) if aggregate_id is not None else None,
                    "occurred_at": fields.Datetime.now().isoformat(),
                    "actor_id": self.env.uid,
                    "correlation_id": correlation_id,
                    "data": payload or {},
                },
            }
        )

    @api.model
    def action_publish_pending(self, limit=100):
        """Cron entry: dispatch pending events to matching webhook endpoints."""
        events = self.search([("status", "=", "pending")], order="id", limit=limit)
        for event in events.with_context(hrm_engine=True):
            try:
                event._dispatch()
            except Exception as e:
                _logger.exception("Outbox dispatch failed for event %s", event.id)
                event._register_failure(str(e))
        return True

    def _dispatch(self):
        self.ensure_one()
        endpoints = self.env["hrm.webhook.endpoint"].search(
            [
                ("tenant_id", "=", self.tenant_id.id),
                ("status", "=", "active"),
            ]
        )
        matched = endpoints.filtered(
            lambda ep: not (ep.event_filters or {}).get("event_types")
            or self.event_type in (ep.event_filters or {}).get("event_types", [])
        )
        ok = True
        for endpoint in matched:
            attempt = self.retry_count + 1
            delivery = self.env["hrm.webhook.delivery"].search([
                ("event_id", "=", self.id),
                ("endpoint_id", "=", endpoint.id),
                ("attempt_no", "=", attempt),
            ], limit=1)
            if not delivery:
                delivery = self.env["hrm.webhook.delivery"].create(
                    {
                        "tenant_id": self.tenant_id.id,
                        "endpoint_id": endpoint.id,
                        "event_id": self.id,
                        "attempt_no": attempt,
                        "status": "pending",
                    }
                )
            if not self._deliver(endpoint, delivery):
                ok = False
        if not matched:
            self.write({"status": "published", "published_at": fields.Datetime.now()})
        elif ok:
            self.write({"status": "published", "published_at": fields.Datetime.now()})
        else:
            self._register_failure("One or more webhook deliveries failed.")

    def _deliver(self, endpoint, delivery):
        body = json.dumps(
            {"event_id": self.id, "event_type": self.event_type,
             "payload": self.payload}
        ).encode()
        secret = ""
        try:
            import os
            if endpoint.secret_reference:
                secret = os.environ.get(endpoint.secret_reference, "") or self.env["ir.config_parameter"].sudo().get_param(endpoint.secret_reference, "") or ""
            if not secret:
                secret = (endpoint.configuration or {}).get("secret", "")
        except Exception:
            secret = (endpoint.configuration or {}).get("secret", "")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            endpoint.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-HRM-Event": self.event_type,
                "X-HRM-Signature": f"sha256={signature}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                delivery.write(
                    {
                        "status": "sent",
                        "http_status": response.status,
                        "response_body": (response.read(500) or b"").decode(
                            "utf-8", "replace"),
                        "sent_at": fields.Datetime.now(),
                    }
                )
                return True
        except Exception as e:
            delivery.write(
                {
                    "status": "failed",
                    "response_body": str(e)[:2000],
                    "sent_at": fields.Datetime.now(),
                    "next_retry_at": fields.Datetime.now()
                    + timedelta(minutes=5 * (self.retry_count + 1)),
                }
            )
            return False

    def _register_failure(self, message):
        for rec in self:
            retries = rec.retry_count + 1
            vals = {"retry_count": retries, "last_error": message[:2000]}
            if retries >= MAX_RETRIES:
                vals["status"] = "failed"
            rec.write(vals)


class HrmWebhookEndpoint(models.Model):
    _name = "hrm.webhook.endpoint"
    _inherit = ["hrm.base.mixin"]
    _description = "Webhook endpoint (SPEC §18.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    url = fields.Char(required=True)
    secret_reference = fields.Char(
        help="Reference to the secret manager entry. DEV ONLY: put the raw "
        "secret in configuration.secret (never in production)."
    )
    configuration = fields.Json(
        default=dict,
        help="event_filters lives in event_filters; DEV secret in secret.",
    )
    event_filters = fields.Json(
        default=dict, help="e.g. {event_types: [EmployeeCreated, LeaveApproved]}."
    )
    status = fields.Selection(
        [("active", "Active"), ("suspended", "Suspended")],
        default="active",
        required=True,
    )
    delivery_ids = fields.One2many("hrm.webhook.delivery", "endpoint_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Endpoint UUID must be unique.")

    @api.constrains("configuration", "secret_reference", "status")
    def _check_secret(self):
        import os
        for rec in self:
            has_raw = bool((rec.configuration or {}).get("secret"))
            if has_raw and not rec.secret_reference:
                if os.environ.get("ODOO_ENV") == "production":
                    raise UserError("Raw webhook secret forbidden in production; use secret_reference (Secret Manager).")
                _logger.warning("Webhook %s uses DEV plaintext secret; set secret_reference for prod.", rec.name)


class HrmWebhookDelivery(models.Model):
    _name = "hrm.webhook.delivery"
    _description = "Webhook delivery attempt (SPEC §18.3)."
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    endpoint_id = fields.Many2one(
        "hrm.webhook.endpoint", required=True, ondelete="cascade"
    )
    event_id = fields.Many2one("hrm.event.outbox", required=True, ondelete="cascade")
    attempt_no = fields.Integer(required=True, default=1)

    _endpoint_event_attempt_unique = models.Constraint(
        "UNIQUE(endpoint_id, event_id, attempt_no)",
        "One delivery row per endpoint+event+attempt.",
    )
    status = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
        default="pending",
        required=True,
    )
    http_status = fields.Integer()
    response_body = fields.Text()
    sent_at = fields.Datetime()
    next_retry_at = fields.Datetime()


class HrmIdempotencyKey(models.Model):
    _name = "hrm.idempotency.key"
    _description = "Idempotency key (SPEC §18.4)."

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    key = fields.Char(required=True)
    request_hash = fields.Char(required=True)
    response_status = fields.Char()
    response_body = fields.Json()
    created_at = fields.Datetime(required=True, default=fields.Datetime.now)
    expires_at = fields.Datetime()

    _tenant_key_unique = models.Constraint(
        "UNIQUE(tenant_id, key)",
        "Idempotency key must be unique per tenant.",
    )

    @api.model
    def check_or_reserve(self, tenant_id, key, request_hash):
        """Returns (record, is_replay). Same key+hash -> replay with stored
        response; same key+different hash -> conflict."""
        existing = self.search(
            [("tenant_id", "=", tenant_id), ("key", "=", key)], limit=1
        )
        if existing:
            if existing.request_hash != request_hash:
                raise UserError(f"Idempotency key '{key}' already used by another request.")
            return existing, True
        return (
            self.create(
                {"tenant_id": tenant_id, "key": key, "request_hash": request_hash}
            ),
            False,
        )

    def store_response(self, status, body=None):
        self.write({"response_status": status, "response_body": body or {}})
        return True
