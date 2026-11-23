# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
from odoo.addons.planb_clean_ui.hooks import migrate_discuss_records


def migrate(cr, version):
    """Execute Discuss and PlanbBot white-label data migrations on upgrade."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_discuss_records(env)
