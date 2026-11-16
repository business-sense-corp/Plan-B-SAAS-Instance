# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = "res.users"

    tour_enabled = fields.Boolean(
        compute="_compute_tour_enabled",
        store=True,
        readonly=False,
        default=False,
        string="Onboarding",
    )

    @api.depends("create_date")
    def _compute_tour_enabled(self):
        for user in self:
            user.tour_enabled = False

    @api.model
    def switch_tour_enabled(self, val):
        self.env.user.sudo().tour_enabled = False
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["tour_enabled"] = False
        return super().create(vals_list)
