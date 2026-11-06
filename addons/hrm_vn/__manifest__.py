{
    "name": "HRM Vietnam Localization",
    "version": "20.0.1.0.0",
    "summary": "VN localization: identifiers, insurance/tax/payroll/statutory rules (master-skill §6)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee", "hrm_payroll"],
    "data": [
        "security/ir.access.csv",
        "views/vn_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_vn.xml', 'data/demo10_vn.xml'],
    "installable": True,
    "application": False,
}
