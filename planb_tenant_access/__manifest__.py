# -*- coding: utf-8 -*-
{
    'name': 'Plan B Tenant Access Control',
    'version': '1.0.1',
    'category': 'Administration',
    'summary': 'Restrict tenant users to paid package modules and slots',
    'author': 'Plan B',
    'depends': ['base'],
    'data': [
        'security/planb_tenant_access_security.xml',
        'security/ir.model.access.csv',
        'wizard/tenant_user_password_wizard_views.xml',
        'views/tenant_user_slot_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}