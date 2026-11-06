{
    'name': 'SMBPlus · Zalo Mini App',
    'version': '20.0.1.0.0',
    'author': 'SMBPlus',
    'license': 'LGPL-3',
    'depends': ['hrm_data_import', 'hrm_leave'],
    'data': ['views.xml'],
    'assets': {'web.assets_backend': [
        'hrm_zalo/static/src/staff_dashboard.js',
        'hrm_zalo/static/src/staff_dashboard.xml',
        'hrm_zalo/static/src/staff_dashboard.css',
    ]},
    'installable': True,
}
