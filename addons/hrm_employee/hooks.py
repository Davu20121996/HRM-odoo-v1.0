"""Post-init seed: global contract type catalogue (tenant NULL)."""


def _post_init_hook(env):
    # Adding the UUID column to an existing employee table can backfill one
    # default into multiple legacy rows. Preserve the oldest ID, repair only
    # duplicates, then enforce the unique constraint that initialization skipped.
    import uuid
    env.cr.execute('''
        SELECT id, uuid FROM (
            SELECT id, uuid, row_number() OVER (PARTITION BY uuid ORDER BY id) AS n
            FROM hr_employee WHERE uuid IS NOT NULL
        ) duplicates WHERE n > 1
    ''')
    for employee_id, old_uuid in env.cr.fetchall():
        employee = env['hr.employee'].browse(employee_id)
        new_uuid = str(uuid.uuid4())
        employee.write({'uuid': new_uuid})
        env['hrm.audit.log'].sudo().create({
            'tenant_id': employee.tenant_id.id or False, 'actor_user_id': env.uid,
            'action': 'UPDATE', 'entity_type': 'hr.employee', 'entity_id': employee.id,
            'old_value': {'uuid': old_uuid}, 'new_value': {'uuid': new_uuid},
            'metadata': {'step': 'legacy_uuid_backfill_repair'},
        })
    env['hr.employee'].flush_model(['uuid'])
    env.cr.execute("SELECT 1 FROM pg_constraint WHERE conrelid='hr_employee'::regclass AND conname='hr_employee_uuid_unique'")
    if not env.cr.fetchone():
        env.cr.execute('ALTER TABLE hr_employee ADD CONSTRAINT hr_employee_uuid_unique UNIQUE(uuid)')
    seeds = [
        ("UNLIMITED", "Hop dong khong xac dinh thoi han", "indefinite", True),
        ("FIXED12", "Hop dong xac dinh thoi han 12 thang", "fixed_term", False),
        ("PROBATION", "Hop dong thu viec", "probation", False),
    ]
    for code, name, category, indefinite in seeds:
        if not env["hrm.contract.type"].search([("code", "=", code)], limit=1):
            env["hrm.contract.type"].create(
                {
                    "tenant_id": False,
                    "code": code,
                    "name": name,
                    "employment_category": category,
                    "is_indefinite": indefinite,
                }
            )
