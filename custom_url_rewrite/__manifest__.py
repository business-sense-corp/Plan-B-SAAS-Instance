{
    'name': 'Custom URL Rewrite',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Remove /odoo prefix from backend action URLs',
    'license': 'LGPL-3',
    # Ticket BS-0034: Do NOT depend on 'website'.
    # The 'website' link field on res.partner (customized in chage_website.xml)
    # is defined in Odoo core 'base' (base.view_partner_form), provided via 'contacts'.
    'depends': ['web', 'mail', 'contacts'],
    'data': [
        "data/hide_menu_data.xml",
        "data/hide_url_early.xml",
        "data/login_template.xml",
        "data/change_icon.xml",
        "data/chage_website.xml"
    ],
    'assets': {
        'web.assets_backend': [
            'custom_url_rewrite/static/src/router_patch.js',
            'custom_url_rewrite/static/src/css/remove_help.css',
            'custom_url_rewrite/static/src/css/remove_install_app.css',
            'custom_url_rewrite/static/src/remove_help.js',
            'custom_url_rewrite/static/src/css/backend_hide_apps.css',
            'custom_url_rewrite/static/src/hide_install_app.js'
        ],
    },
    'installable': True,
    'application': False,
    "post_init_hook": "post_init_hook",
}
