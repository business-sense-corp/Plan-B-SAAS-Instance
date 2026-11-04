# -*- coding: utf-8 -*-
{
    'name': 'Plan B Password Reset (OTP)',
    'version': '19.0.1.1.0',
    'category': 'Technical',
    'summary': 'Self-service password recovery with a one-time code sent by e-mail',
    'description': """
Plan B Password Reset (OTP)
===========================

Self-service password recovery for both the management server and the tenant
servers, using a 6-digit one-time code delivered by e-mail.

The module is intentionally UI-independent of the management addons: it can be
installed on the management database and on every tenant database, and each
database resets only its own users.

See changes/10-forgot-password/ for the full design and security notes.
""",
    'author': 'Plan B',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/config_parameters.xml',
        'views/forgot_password_templates.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
