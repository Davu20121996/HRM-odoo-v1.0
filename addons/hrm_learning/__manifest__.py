{
    "name": "HRM Learning (P7)",
    "version": "20.0.1.0.0",
    "summary": "P7 learning: courses, trainings, enrollments, certifications, skills (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee"],
    "data": [
        "security/ir.access.csv",
        "views/learning_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_learning.xml', 'data/demo10_learning.xml'],
    "installable": True,
    "application": True,
}
