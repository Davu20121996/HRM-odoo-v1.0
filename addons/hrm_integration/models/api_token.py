"""API token cho app ngoai (Zalo Mini App...): Bearer + het han + rate limit.

Su dung:
    token = env["hrm.api.token"].create_token(tenant_id, "zalo-miniapp",
              ttl_days=90, rate_limit_per_hour=600)
    # tra ve raw token 1 lan duy nhat -> dua cho Mini App
    # Mini App goi: Authorization: Bearer <raw> + X-Tenant-Code: TEN01
"""
import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


def _sha256(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class HrmApiToken(models.Model):
    _name = "hrm.api.token"
    _inherit = ["hrm.base.mixin"]
    _description = "API token (Bearer) cho app ngoai"
    _order = "id desc"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="cascade")
    name = fields.Char(required=True, help="Vd: zalo-miniapp-prod")
    token_hash = fields.Char(required=True, readonly=True, copy=False,
                             help="SHA256 cua raw token. Khong luu raw.")
    token_tail = fields.Char(readonly=True, help="4 ky tu cuoi de nhan dien")
    expires_at = fields.Datetime(required=True)
    active = fields.Boolean(default=True)
    # Rate limit: so request toi da moi gio (sliding window don gian)
    rate_limit_per_hour = fields.Integer(default=600)
    window_start = fields.Datetime()
    requests_in_window = fields.Integer(default=0)
    last_used_at = fields.Datetime(readonly=True)
    revoked_at = fields.Datetime(readonly=True)

    _tenant_name_unique = models.Constraint(
        "UNIQUE(tenant_id, name)", "Token name phai duy nhat theo tenant.")

    @api.model
    def create_token(self, tenant_id, name, ttl_days=90, rate_limit_per_hour=600):
        """Tao token moi. Tra ve (record, raw). Raw CHI HIEN 1 LAN."""
        ttl_days = max(1, min(int(ttl_days or 90), 365))
        raw = "hrm_" + secrets.token_urlsafe(32)
        rec = self.create({
            "tenant_id": tenant_id,
            "name": name,
            "token_hash": _sha256(raw),
            "token_tail": raw[-4:],
            "expires_at": fields.Datetime.now() + timedelta(days=ttl_days),
            "rate_limit_per_hour": rate_limit_per_hour,
        })
        return rec, raw

    def action_revoke(self):
        self.write({"active": False, "revoked_at": fields.Datetime.now()})
        return True

    @api.model
    def _find_by_raw(self, tenant_id, raw):
        if not raw:
            return None
        return self.search([
            ("tenant_id", "=", tenant_id),
            ("token_hash", "=", _sha256(raw)),
        ], limit=1)

    def rotate(self, ttl_days=90):
        """Renew/rotate: vo hieu raw cu, sinh raw MOI. Tra ve raw moi.

        Cho phep renew token vua het han trong 7 ngay (grace) de app
        tu refresh ma khong bat user login lai. Het han qua 7 ngay
        hoac da revoke -> UserError, bat login lay token moi.
        """
        self.ensure_one()
        if not self.active:
            raise UserError("Token da bi thu hoi. Hay login lay token moi.")
        now = fields.Datetime.now()
        if self.expires_at and self.expires_at < now - timedelta(days=7):
            raise UserError("Token het han qua 7 ngay. Hay login lay token moi.")
        raw = "hrm_" + secrets.token_urlsafe(32)
        self.sudo().write({
            "token_hash": _sha256(raw),
            "token_tail": raw[-4:],
            "expires_at": now + timedelta(days=max(1, min(int(ttl_days or 90), 365))),
            "window_start": now,
            "requests_in_window": 0,
            "last_used_at": now,
        })
        return raw

    @api.model
    def check_bearer(self, tenant_id, raw):
        """Validate Bearer. Tra ve (record, error_response). Dung trong controller."""
        if not raw:
            return None, "Missing Authorization: Bearer <token>"
        rec = self.search([
            ("tenant_id", "=", tenant_id),
            ("token_hash", "=", _sha256(raw)),
        ], limit=1)
        if not rec or not rec.active:
            return None, "Invalid or revoked token"
        now = fields.Datetime.now()
        if rec.expires_at and rec.expires_at < now:
            return None, "Token expired"
        # -- rate limit (window 1 gio, reset lazy) --
        window = rec.window_start
        if not window or (now - window).total_seconds() >= 3600:
            rec.sudo().write({"window_start": now, "requests_in_window": 1,
                              "last_used_at": now})
            return rec, None
        if rec.requests_in_window >= (rec.rate_limit_per_hour or 600):
            return None, "Rate limit exceeded (429). Giam toc do goi hoac tang limit."
        rec.sudo().write({"requests_in_window": rec.requests_in_window + 1,
                          "last_used_at": now})
        return rec, None

    @api.model
    def cron_cleanup_expired(self, limit=500):
        """Cron: tat token het han > 30 ngay (giu lich su)."""
        cutoff = fields.Datetime.now() - timedelta(days=30)
        olds = self.search([("expires_at", "<", cutoff), ("active", "=", True)],
                           limit=limit)
        olds.write({"active": False})
        return len(olds)

    def action_generate_new_key(self):
        """Nut Generate Key tren form: xoay raw moi + mo popup hien 1 lan."""
        self.ensure_one()
        raw = self.rotate()
        wiz = self.env["hrm.api.token.show"].create({
            "name": self.name,
            "raw": raw,
            "expires_at": self.expires_at,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "hrm.api.token.show",
            "view_mode": "form",
            "res_id": wiz.id,
            "target": "new",
        }


class HrmApiTokenShow(models.TransientModel):
    _name = "hrm.api.token.show"
    _description = "Popup hien raw token 1 lan duy nhat sau Generate"

    name = fields.Char(readonly=True)
    raw = fields.Char(readonly=True)
    expires_at = fields.Datetime(readonly=True)
