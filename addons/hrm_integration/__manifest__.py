{
    "name": "HRM Integration (P8)",
    "version": "20.0.1.0.0",
    "summary": "P8 events/integration: outbox, webhooks, idempotency, imports, connections (master-skill §8)",
    "author": "HRM",
    "license": "LGPL-3",
    "depends": ["hrm_base", "hrm_employee"],
    "data": [
        "security/ir.access.csv",
        "data/cron.xml",
        "views/integration_views.xml",
        "views/menus.xml",
    ],
    "demo": ['data/demo_integration.xml', 'data/demo10_integration.xml'],
    "installable": True,
    "application": True,
}
