"""Shared mixins for HRM P1 models.

Deviation note (master-skill §7 — Odoo is the adapter):
Odoo ORM requires an integer PK, so the canonical UUID (SPEC §2.5)
is carried in the ``uuid`` field (unique per model, used by APIs
and events) instead of replacing ``id``.
"""
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrmNumeric(fields.Float):
    """Float stored as PostgreSQL NUMERIC (SPEC §2.3 — cấm float8 cho tiền/số lượng).

    Odoo ``fields.Float`` dùng ``float8``; subclass này ép ``_column_type``
    sang ``numeric`` nên DDL thành NUMERIC, vẫn giữ API float ở Python.
    """

    _column_type = ("numeric", "numeric")


class HrmMoney(HrmNumeric):
    """Tiền NUMERIC(19,4) + mã ISO-4217 (SPEC §2.3, MUST#15)."""


class HrmBaseMixin(models.AbstractModel):
    _name = "hrm.base.mixin"
    _description = "HRM base mixin (uuid + optimistic-lock version)"

    uuid = fields.Char(
        string="UUID",
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        readonly=True,
        index=True,
    )
    version = fields.Integer(string="Version", default=1, readonly=True, copy=False)

    def write(self, vals):
        if "version" in vals and not self.env.context.get("hrm_engine"):
            raise UserError("Version is managed by optimistic locking; do not write it directly.")
        vals = {k: v for k, v in vals.items() if k != "version"}
        expected = self.env.context.get("hrm_expected_version")
        if expected is not None and len(self) == 1:
            if self.version != expected:
                raise UserError(
                    f"Concurrent update detected (expected version {expected}, "
                    f"got {self.version}). Please reload and retry."
                )
        res = super().write(vals)
        # Concurrency-safe increment at SQL level (single UPDATE).
        if not self.ids:
            return res
        self.env.cr.execute(
            f'UPDATE "{self._table}" SET version = version + 1 WHERE id IN %s',
            (tuple(self.ids),),
        )
        self.invalidate_recordset(["version"])
        return res
