# -*- coding: utf-8 -*-
{
    'name': 'Plan-B Clean UI',
    'version': '19.0.1.1.0',
    'category': 'Technical',
    'summary': 'Disable web tours, sample data, promotional videos, onboarding panels, PWA install prompts, and white-label notifications and Discuss/PlanbBot',
    'author': 'Plan-B',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'mail',
        'mail_bot',
        'sale',
        'account',
        'onboarding',
    ],
    'data': [
        'data/mail_data.xml',
        'views/sale_order_views.xml',
        'views/webclient_templates.xml',
        'views/discuss_public_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'planb_clean_ui/static/src/js/tour_disable.js',
            'planb_clean_ui/static/src/js/sample_data_disable.js',
            'planb_clean_ui/static/src/js/pwa_disable.js',
            'planb_clean_ui/static/src/views/sale_action_helper_patch.js',
            'planb_clean_ui/static/src/views/sale_action_helper.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
