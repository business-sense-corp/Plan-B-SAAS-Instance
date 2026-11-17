# -*- coding: utf-8 -*-
from odoo import models, api


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _fill_onboarding_data(self, dashboard_data):
        # Neutralize onboarding steps on accounting dashboard
        return

    @api.model
    def is_sample_action_available(self):
        # Suppress "try our sample" promotional button on vendor bills empty state
        return False
