{
    "name": "HRM Performance (P7)",
    "version": "20.0.1.0.0",
    "summary": "P7 performance: cycles, goals, KPI/OKR, appraisals, 360 feedback (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_workflow"],
    "data": [
        "security/ir.access.csv",
        "views/performance_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_performance.xml', 'data/demo10_performance.xml'],
    "installable": True,
    "application": True,
}
