{
    "name": "HRM Recruitment (P4)",
    "version": "20.0.1.0.0",
    "summary": "P4 recruitment: candidate, requisition, application, interview, offer -> employee (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_workflow"],
    "data": [
        "security/ir.access.csv",
        "views/recruitment_views.xml",
        "views/menus.xml",
        "demo/demo_recruitment.xml",
        "demo/demo10_recruitment.xml",
    ],
    "installable": True,
    "application": True,
}
