{
    "name": "HRM Payroll (P6)",
    "version": "20.0.1.0.0",
    "summary": "P6 payroll: structures, salaries, periods, runs, payslips, bonuses (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_workflow", "hrm_time"],
    "data": [
        "security/ir.access.csv",
        "views/payroll_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_payroll.xml', 'data/demo10_payroll.xml'],
    "installable": True,
    "application": True,
}
