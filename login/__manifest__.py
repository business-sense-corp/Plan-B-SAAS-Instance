{
    'name': 'Login',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Manage Login and Odoo databases',
    'author': 'Plan B',
    'depends': ['base', 'web', 'account'],
    'data': [
        'views/login_templates.xml',
        'views/custom_page_title.xml'
    ],
    'assets': {
    'web.assets_backend': [
        'login/static/src/js/user_menu.js',
    ],
   },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
