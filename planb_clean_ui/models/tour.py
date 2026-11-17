# -*- coding: utf-8 -*-
from odoo import models, api


class WebTourTour(models.Model):
    _inherit = "web_tour.tour"

    @api.model
    def get_current_tour(self):
        return False

    @api.model
    def consume(self, tourName):
        return False
