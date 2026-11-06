{
    "name": "HRM Time (P5)",
    "version": "20.0.1.0.0",
    "summary": "P5 time: schedules, shifts, devices, attendance pipeline, overtime, work entries (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_workflow"],
    "data": [
        "security/ir.access.csv",
        "views/time_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_time.xml', 'data/demo10_time.xml'],
    "installable": True,
    "application": True,
}
