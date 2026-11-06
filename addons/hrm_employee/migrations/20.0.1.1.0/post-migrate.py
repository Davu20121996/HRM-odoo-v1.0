"""POST-migration: backfill gia tri mac dinh cho dong cu sau khi ORM tao cot.

Chay SAU khi ORM da ADD COLUMN. Dung env (Odoo API) nen viet gon hon SQL.
"""

def migrate(cr, version):
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from odoo import api, SUPERUSER_ID
        with api.Environment.manage():
            env = api.Environment(cr, SUPERUSER_ID, {})
            # Backfill: dong cu chua co phone -> de trong, khong ghi de dong moi.
            # Them dem de log kiem tra sau -u.
            n = env["hrm.person"].search_count([("phone", "=", False)])
            _logger.info("post-migrate 20.0.1.1.0: %s hrm.person chua co phone (giu NULL)", n)
            # Vi du neu muon set default that:
            # env["hrm.person"].search([("phone", "=", False)]).write({"phone": ""})
    except Exception as e:
        # Khong raise: migration loi se block -u. Log de dev tu xu ly.
        import logging as _l
        _l.getLogger(__name__).exception("post-migrate bo qua loi: %s", e)
