# -*- coding: utf-8 -*-
from odoo import models, api


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    @api.readonly
    def get_view(self, view_id=None, view_type="form", **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        if res and isinstance(res, dict) and "arch" in res and isinstance(res["arch"], str):
            res["arch"] = res["arch"].replace('sample="1"', 'sample="0"')
        return res

    @api.model
    @api.readonly
    def get_views(self, views, options=None):
        res = super().get_views(views, options=options)
        if res and isinstance(res, dict) and "views" in res:
            for v_type, v_data in res["views"].items():
                if isinstance(v_data, dict) and "arch" in v_data and isinstance(v_data["arch"], str):
                    v_data["arch"] = v_data["arch"].replace('sample="1"', 'sample="0"')
        return res
