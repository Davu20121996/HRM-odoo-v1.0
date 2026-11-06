{
    "name": "HRM Leave (P5)",
    "version": "20.0.1.0.0",
    "summary": "P5 leave: types, policies, allocations, requests, ledger balances (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_workflow"],
    "data": [
        "security/ir.access.csv",
        "views/leave_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_leave.xml', 'data/demo10_leave.xml'],
    "installable": True,
    "application": True,
}
