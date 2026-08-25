# Part of Odoo. See LICENSE file for full copyright and licensing details.


from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _post_logout(cls):
        super()._post_logout()
        request.future_response.set_cookie("color_scheme", max_age=0)

    def color_scheme(self):
        cookie_scheme = request.httprequest.cookies.get("color_scheme")
        scheme = cookie_scheme if cookie_scheme else super().color_scheme()
        if user := request.env.user:
            if user._is_public():
                return super().color_scheme()
            if user_scheme := user.res_users_settings_id.color_scheme:
                if user_scheme in ("light", "dark"):
                    return user_scheme
        return scheme
