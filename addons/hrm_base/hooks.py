"""Post-init seed: SPEC §27 roles + core permissions.

Idempotent: skips existing records so re-install/upgrade is safe.
"""
from odoo import api, SUPERUSER_ID

SEED_ROLES = [
    ("PLATFORM_ADMIN", "Platform Admin", True),
    ("TENANT_ADMIN", "Tenant Admin", False),
    ("HR_ADMIN", "HR Admin", False),
    ("HR_MANAGER", "HR Manager", False),
    ("MANAGER", "Manager", False),
    ("EMPLOYEE", "Employee", False),
    ("PAYROLL_ADMIN", "Payroll Admin", False),
    ("RECRUITER", "Recruiter", False),
]

SEED_PERMISSIONS = [
    ("tenant.read", "tenant", "read", "Read tenant"),
    ("tenant.write", "tenant", "write", "Write tenant"),
    ("company.read", "company", "read", "Read company"),
    ("company.write", "company", "write", "Write company"),
    ("employee.read", "employee", "read", "Read employee"),
    ("employee.write", "employee", "write", "Write employee"),
    ("employee.archive", "employee", "archive", "Archive employee"),
    ("organization.read", "organization", "read", "Read organization"),
    ("organization.write", "organization", "write", "Write organization"),
    ("contract.read", "contract", "read", "Read contract"),
    ("contract.write", "contract", "write", "Write contract"),
    ("attendance.read", "attendance", "read", "Read attendance"),
    ("attendance.write", "attendance", "write", "Write attendance"),
    ("leave.read", "leave", "read", "Read leave"),
    ("leave.write", "leave", "write", "Write leave"),
    ("leave.approve", "leave", "approve", "Approve leave"),
    ("payroll.read", "payroll", "read", "Read payroll"),
    ("payroll.process", "payroll", "process", "Process payroll"),
    ("payroll.approve", "payroll", "approve", "Approve payroll"),
    ("payroll.finalize", "payroll", "finalize", "Finalize payroll"),
    ("recruitment.read", "recruitment", "read", "Read recruitment"),
    ("recruitment.write", "recruitment", "write", "Write recruitment"),
    ("performance.read", "performance", "read", "Read performance"),
    ("performance.write", "performance", "write", "Write performance"),
    ("learning.read", "learning", "read", "Read learning"),
    ("learning.write", "learning", "write", "Write learning"),
    ("workflow.read", "workflow", "read", "Read workflow"),
    ("workflow.write", "workflow", "write", "Write workflow"),
    ("audit.read", "audit", "read", "Read audit log"),
    ("configuration.read", "configuration", "read", "Read configuration"),
    ("configuration.write", "configuration", "write", "Write configuration"),
]

# System roles that receive every permission out of the box.
FULL_ACCESS_ROLES = {"PLATFORM_ADMIN", "TENANT_ADMIN", "HR_ADMIN"}


def _post_init_hook(env):
    perm_by_code = {}
    for code, resource, action, desc in SEED_PERMISSIONS:
        perm = env["hrm.permission"].search([("code", "=", code)], limit=1)
        if not perm:
            perm = env["hrm.permission"].create(
                {"code": code, "resource": resource, "action": action, "description": desc}
            )
        perm_by_code[code] = perm

    all_perm_ids = [p.id for p in perm_by_code.values()]
    for code, name, is_system in SEED_ROLES:
        role = env["hrm.role"].search([("code", "=", code)], limit=1)
        if not role:
            role = env["hrm.role"].create(
                {"code": code, "name": name, "is_system": is_system, "tenant_id": False}
            )
        if code in FULL_ACCESS_ROLES:
            existing = set(role.permission_ids.ids)
            missing = [pid for pid in all_perm_ids if pid not in existing]
            if missing:
                role.write({"permission_ids": [(4, pid) for pid in missing]})

    # Grant the default admin user HRM Admin so the UI is usable out of the box.
    admin_group = env.ref("hrm_base.group_hrm_admin", raise_if_not_found=False)
    admin_user = env.ref("base.user_admin", raise_if_not_found=False)
    if admin_group and admin_user and admin_group.id not in admin_user.group_ids.ids:
        admin_user.write({"group_ids": [(4, admin_group.id)]})
