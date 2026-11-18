# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _handle_debug(cls):
        super()._handle_debug()
        if request and hasattr(request, 'session') and request.session.debug:
            try:
                user = request.env.user
                if user and not user._planb_is_internal_admin() and user._planb_lock_active():
                    request.session.debug = ''
            except Exception:
                pass

    def session_info(self):
        user = self.env.user
        if not user._planb_is_internal_admin() and user._planb_lock_active():
            if request and hasattr(request, 'session'):
                request.session.debug = ''
        res = super().session_info()
        if not user._planb_is_internal_admin() and user._planb_lock_active():
            if isinstance(res, dict) and 'bundle_params' in res:
                res['bundle_params'].pop('debug', None)
        return res
