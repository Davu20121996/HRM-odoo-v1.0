"""Versioned API (MUST#20: /api/v1/..., never expose DB table names).

Tenant scope via X-Tenant-Code header. Idempotent POST via Idempotency-Key
(header) backed by hrm.idempotency.key.
"""
import hashlib
import json

from odoo import http
from odoo.http import Response, request


def _json(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False, default=str),
                    status=status, content_type="application/json")


def _tenant():
    code = request.httprequest.headers.get("X-Tenant-Code")
    if not code:
        return None, _json({"error": "Missing X-Tenant-Code"}, 400)
    tenant = request.env["hrm.tenant"].sudo().search([("code", "=", code)], limit=1)
    if not tenant:
        return None, _json({"error": f"Unknown tenant '{code}'"}, 404)
    return tenant, None


def _bearer_raw():
    """Lay raw token tu header Authorization: Bearer <token>."""
    auth = request.httprequest.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _auth_tenant(require_token=False):
    """Xac thuc kep cho app ngoai (Zalo Mini App...).

    - Luon can X-Tenant-Code (chong nham tenant).
    - Neu co Bearer -> check hrm.api.token (het han + rate limit).
    - Neu khong co Bearer:
      + require_token=True  -> 401 (bat buoc dung token).
      + require_token=False -> dung session Odoo hien tai (auth=user cu).
    Tra ve (tenant, error_response).
    """
    tenant, err = _tenant()
    if err:
        return None, err
    raw = _bearer_raw()
    if raw:
        _rec, msg = request.env["hrm.api.token"].sudo().check_bearer(
            tenant.id, raw)
        if msg:
            status = 429 if "Rate limit" in msg else 401
            return None, _json({"error": msg}, status)
        return tenant, None
    if require_token:
        return None, _json(
            {"error": "Missing Authorization: Bearer <token>"}, 401)
    if not request.session.uid:
        return None, _json({"error": "Chua login va thieu Bearer token"}, 401)
    return tenant, None


def _idempotent(tenant_id):
    key = request.httprequest.headers.get("Idempotency-Key")
    if not key:
        return None, False
    body = request.httprequest.get_data() or b""
    h = hashlib.sha256(body).hexdigest()
    rec, replay = request.env["hrm.idempotency.key"].sudo().check_or_reserve(
        tenant_id, key, h)
    if replay and rec.response_body:
        return rec.response_body, True
    request._hrm_idem = rec
    return None, False


def _serialize_employee(rec):
    """Serialize hr.employee cho Zalo Mini App (demo)."""
    person = rec.person_id
    return {
        "id": rec.id,
        "uuid": rec.uuid,
        "employee_code": rec.employee_code,
        "name": rec.name,
        "person": {
            "id": person.id if person else None,
            "display_name": person.display_name if person else None,
            "first_name": person.first_name if person else None,
            "last_name": person.last_name if person else None,
        } if person else None,
        "work_email": rec.work_email or None,
        "work_phone": rec.work_phone or None,
        "mobile_phone": getattr(rec, "mobile_phone", None),
        "hire_date": str(rec.hire_date) if rec.hire_date else None,
        "current_status": rec.current_status,
    }


class HrmApiV1(http.Controller):
    @http.route("/api/v1/health", type="http", auth="none", methods=["GET"])
    def health(self):
        return _json({"status": "ok", "api": "v1"})

    @http.route("/api/v1/events", type="http", auth="user", methods=["GET"])
    def events(self):
        tenant, err = _tenant()
        if err:
            return err
        rows = request.env["hrm.event.outbox"].search(
            [("tenant_id", "=", tenant.id)], order="id desc", limit=50)
        return _json({"events": [{
            "event_id": r.event_id or r.uuid, "type": r.event_type,
            "aggregate": r.aggregate_type, "status": r.status,
            "occurred_at": str(r.occurred_at)} for r in rows]})

    @http.route("/api/v1/leave/requests", type="http", auth="user", methods=["POST"])
    def leave_create(self):
        tenant, err = _tenant()
        if err:
            return err
        cached, replay = _idempotent(tenant.id)
        if replay:
            return _json(cached)
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except Exception:
            return _json({"error": "Invalid JSON"}, 400)
        try:
            rec = request.env["hrm.leave.request"].create({
                "tenant_id": tenant.id,
                "employee_id": data["employee_id"],
                "leave_type_id": data["leave_type_id"],
                "start_at": data["start_at"], "end_at": data["end_at"],
                "requested_quantity": data.get("requested_quantity", 1.0),
                "reason": data.get("reason", ""),
            })
        except Exception as e:
            return _json({"error": str(e)}, 400)
        body = {"id": rec.id, "uuid": rec.uuid, "status": rec.status}
        if hasattr(request, "_hrm_idem") and request._hrm_idem:
            request._hrm_idem.sudo().store_response("201", body)
        return _json(body, 201)

    @http.route("/api/v1/attendance/events", type="http", auth="user", methods=["POST"])
    def attendance_ingest(self):
        tenant, err = _tenant()
        if err:
            return err
        cached, replay = _idempotent(tenant.id)
        if replay:
            return _json(cached)
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except Exception:
            return _json({"error": "Invalid JSON"}, 400)
        try:
            rec = request.env["hrm.attendance.device.event"].ingest(
                tenant.id, data["device_code"], data["event_type"], data["event_time"],
                external_event_id=data.get("external_event_id"),
                employee_id=data.get("employee_id"),
                employee_external_ref=data.get("employee_external_ref"),
                payload=data.get("payload"),
            )
        except Exception as e:
            return _json({"error": str(e)}, 400)
        body = {"id": rec.id, "external_event_id": rec.external_event_id}
        if hasattr(request, "_hrm_idem") and request._hrm_idem:
            request._hrm_idem.sudo().store_response("201", body)
        return _json(body, 201)

    # ---------- Auth: renew / revoke Bearer token ----------
    # GHI CHU (quyet dinh team): KHONG co endpoint login bang password.
    # API key do admin tao truc tiep trong HRM (Integration > API Tokens
    # > nut Generate Key). Mini App chi dung Bearer, khong biet password.

    @http.route("/api/v1/auth/renew", type="http", auth="none",
                methods=["POST"], cors="*", csrf=False)
    def auth_renew(self):
        """Renew/rotate token: vo hieu raw cu, cap raw moi.

        Headers: X-Tenant-Code + Authorization: Bearer <raw cu>.
        Body optional: {ttl_days}. Grace 7 ngay sau het han.
        """
        tenant, err = _tenant()
        if err:
            return err
        raw = _bearer_raw()
        if not raw:
            return _json({"error": "Missing Authorization: Bearer <token>"}, 401)
        rec = request.env["hrm.api.token"].sudo()._find_by_raw(tenant.id, raw)
        if not rec:
            return _json({"error": "Invalid token"}, 401)
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except Exception:
            data = {}
        try:
            new_raw = rec.rotate(ttl_days=data.get("ttl_days", 90))
        except Exception as e:
            return _json({"error": str(e)}, 401)
        rec = request.env["hrm.api.token"].sudo().browse(rec.id)
        return _json({
            "token": new_raw,
            "token_tail": rec.token_tail,
            "expires_at": str(rec.expires_at),
            "note": "Raw cu da vo hieu. Update Bearer moi cho Mini App.",
        })

    @http.route("/api/v1/auth/revoke", type="http", auth="none",
                methods=["POST"], cors="*", csrf=False)
    def auth_revoke(self):
        """Logout token: thu hoi Bearer hien tai."""
        tenant, err = _tenant()
        if err:
            return err
        raw = _bearer_raw()
        if not raw:
            return _json({"error": "Missing Authorization: Bearer <token>"}, 401)
        rec = request.env["hrm.api.token"].sudo()._find_by_raw(tenant.id, raw)
        if not rec:
            return _json({"error": "Invalid token"}, 401)
        rec.action_revoke()
        return _json({"revoked": True, "name": rec.name})

    # ---------- Zalo Mini App (demo, Bearer token) ----------
    @http.route("/api/v1/zalo/employees", type="http", auth="none",
                methods=["GET"], cors="*", csrf=False)
    def zalo_employees(self):
        """Lay tat ca employee theo tenant. Query: ?limit=20&offset=0&status=active"""
        tenant, err = _auth_tenant()
        if err:
            return err
        try:
            limit = int(request.httprequest.args.get("limit", 20))
            offset = int(request.httprequest.args.get("offset", 0))
        except ValueError:
            return _json({"error": "limit/offset phai la so"}, 400)
        limit = max(1, min(limit, 100))
        domain = [("tenant_id", "=", tenant.id)]
        status = request.httprequest.args.get("status")
        if status:
            domain.append(("current_status", "=", status))
        rows = request.env["hr.employee"].sudo().search(
            domain, order="id desc", limit=limit, offset=offset)
        total = request.env["hr.employee"].sudo().search_count(domain)
        return _json({
            "total": total, "limit": limit, "offset": offset,
            "employees": [_serialize_employee(r) for r in rows],
        })

    @http.route("/api/v1/zalo/employees/<string:employee_code>",
                type="http", auth="none", methods=["GET"], cors="*", csrf=False)
    def zalo_employee_get(self, employee_code):
        """Lay 1 employee theo employee_code + header X-Tenant-Code."""
        tenant, err = _auth_tenant()
        if err:
            return err
        rec = request.env["hr.employee"].sudo().search([
            ("tenant_id", "=", tenant.id),
            ("employee_code", "=", employee_code),
        ], limit=1)
        if not rec:
            return _json(
                {"error": f"Khong tim thay employee_code '{employee_code}'"}, 404)
        return _json(_serialize_employee(rec))

    @http.route("/api/v1/zalo/employees/<string:employee_code>/update",
                type="http", auth="none", methods=["POST"], cors="*", csrf=False)
    def zalo_employee_update(self, employee_code):
        """Sua thong tin employee. Body JSON: {name, work_email, work_phone, mobile_phone}."""
        tenant, err = _auth_tenant()
        if err:
            return err
        try:
            data = json.loads(request.httprequest.get_data() or b"{}")
        except Exception:
            return _json({"error": "Invalid JSON"}, 400)
        # Cho phep truyen employee_code trong body (uu tien URL)
        code = data.get("employee_code") or employee_code
        rec = request.env["hr.employee"].sudo().search([
            ("tenant_id", "=", tenant.id),
            ("employee_code", "=", code),
        ], limit=1)
        if not rec:
            return _json(
                {"error": f"Khong tim thay employee_code '{code}'"}, 404)
        allowed = ("name", "work_email", "work_phone", "mobile_phone")
        vals = {k: data[k] for k in allowed if k in data}
        if not vals:
            return _json(
                {"error": f"Khong co field nao de sua. Cho phep: {list(allowed)}"},
                400)
        try:
            rec.write(vals)
        except Exception as e:
            return _json({"error": str(e)}, 400)
        return _json({"updated": True, "employee": _serialize_employee(rec)})
