{
    "name": "HRM Workflow (P3)",
    "version": "20.0.1.0.0",
    "summary": "P3 shared workflow/approval engine + notifications (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hr"],
    "data": [
        "security/ir.access.csv",
        "views/workflow_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_workflow.xml', 'data/demo10_workflow.xml', 'data/demo10_security.xml'],
    "installable": True,
    "application": True,
}
