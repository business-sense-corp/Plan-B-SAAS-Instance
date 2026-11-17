# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import AccessError


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    def _planb_check_param_access(self, keys):
        if self.env.su or self.env.user._planb_is_internal_admin():
            return
        for key in keys:
            if key and key.startswith('planb.'):
                raise AccessError(_("Modifying Plan B configuration parameters is not allowed."))

    @api.model_create_multi
    def create(self, vals_list):
        keys = [vals.get('key', '') for vals in vals_list if 'key' in vals]
        self._planb_check_param_access(keys)
        records = super().create(vals_list)
        if any(k == 'planb.lock_settings' for k in keys):
            self.env.registry.clear_cache()
        return records

    def write(self, vals):
        target_keys = set(self.mapped('key'))
        if 'key' in vals:
            target_keys.add(vals['key'])
        self._planb_check_param_access(target_keys)
        res = super().write(vals)
        if 'planb.lock_settings' in target_keys:
            self.env.registry.clear_cache()
        return res

    def unlink(self):
        target_keys = set(self.mapped('key'))
        self._planb_check_param_access(target_keys)
        res = super().unlink()
        if 'planb.lock_settings' in target_keys:
            self.env.registry.clear_cache()
        return res
