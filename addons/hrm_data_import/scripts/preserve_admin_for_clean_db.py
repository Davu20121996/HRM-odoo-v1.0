"""Preserve existing authentication for the same admin during DB replacement. Never log credentials."""
from odoo import sql_db
assert env.cr.dbname == 'hrm_smb_stage_20261104'
with sql_db.db_connect('hrm').cursor() as original:
    original.execute("SELECT column_name FROM information_schema.columns WHERE table_name='res_users'")
    old_columns={r[0] for r in original.fetchall()}
    env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='res_users'")
    new_columns={r[0] for r in env.cr.fetchall()}
    fields_to_keep=[key for key in ('login','password','active','totp_secret') if key in old_columns]
    assert set(fields_to_keep)<=new_columns, 'Authentication schema differs; stop before replacing DB.'
    original.execute('SELECT '+','.join(fields_to_keep)+' FROM res_users WHERE id=2')
    values=original.fetchone();assert values and values[1]
    env.cr.execute('UPDATE res_users SET '+','.join(key+'=%s' for key in fields_to_keep)+' WHERE id=2',values)
    for key in ('database.uuid','database.secret'):
        original.execute('SELECT value FROM ir_config_parameter WHERE key=%s',(key,))
        row=original.fetchone()
        if row: env['ir.config_parameter'].sudo().set_str(key,row[0])
env['ir.config_parameter'].sudo().set_str('web.base.url','http://localhost:8069')
env.ref('base.user_admin').write({'action_id': env.ref('hrm_base.action_hrm_company').id})
env.cr.commit()
print('Existing admin authentication retained without disclosure. Default screen: company information.')

