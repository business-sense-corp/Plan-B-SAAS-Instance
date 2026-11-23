# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.webmanifest import WebManifest


class PlanBCleanUIWebManifest(WebManifest):

    @http.route('/web/manifest.webmanifest', type='http', auth='public', methods=['GET'], readonly=True)
    def webmanifest(self):
        """Return empty manifest to prevent browser PWA installation heuristics."""
        return request.make_json_response({}, {
            'Content-Type': 'application/manifest+json',
        })

    @http.route('/web/manifest.scoped_app_manifest', type='http', auth='public', methods=['GET'])
    def scoped_app_manifest(self, app_id, path='', app_name=''):
        """Return empty scoped app manifest to prevent any scoped PWA installation."""
        return request.make_json_response({}, {
            'Content-Type': 'application/manifest+json',
        })
