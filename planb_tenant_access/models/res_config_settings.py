# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planb_hide_system_settings = fields.Boolean(
        string="Hide Plan B System Settings",
        compute='_compute_planb_hide_system_settings',
        store=False,
    )

    def _compute_planb_hide_system_settings(self):
        for record in self:
            user = record.env.user
            record.planb_hide_system_settings = (
                not user._planb_is_internal_admin() and user._planb_lock_active()
            )
