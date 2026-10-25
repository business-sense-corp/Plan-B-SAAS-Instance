# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _planb_is_customer_admin(self):
        return (
            self.env.user.has_group(
                'planb_tenant_access.group_planb_customer_admin'
            )
            and self.env.user.has_group('base.group_system')
        )

    @api.model_create_multi
    def create(self, vals_list):
        if self._planb_is_customer_admin():
            raise AccessError(_(
                'Your subscription administrator cannot create additional '
                'users. Add user slots from the subscription portal first.'
            ))
        return super().create(vals_list)

    def unlink(self):
        if self._planb_is_customer_admin():
            raise AccessError(_(
                'Licensed tenant users cannot be deleted by the customer '
                'administrator.'
            ))
        return super().unlink()

    def write(self, vals):
        res = super().write(vals)
        if vals.get('password'):
            for user in self:
                with self.env.cr.savepoint():
                    try:
                        if 'res.device' in self.env:
                            devices = self.env['res.device'].sudo().search([('user_id', '=', user.id)])
                            devices.filtered(lambda d: not d.is_current)._revoke()
                    except Exception as e:
                        _logger.warning("Could not revoke devices for tenant user %s: %s", user.id, e)
        return res
