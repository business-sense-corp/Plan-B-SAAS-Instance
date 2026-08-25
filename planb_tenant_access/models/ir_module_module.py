# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import AccessError


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _planb_check_module_operation_allowed(self):
        """Never let a licensed customer slot modify installed applications.

        The internal Plan B ``admin`` and ``saas_system`` accounts are not
        licensed slots, so provisioning and Plan B administration continue to
        work normally.  This is intentionally independent of Odoo groups: if a
        customer slot is accidentally granted a powerful group later, module
        installation is still blocked here.
        """
        slot = self.env['planb.tenant.user.slot'].sudo().search([
            ('user_id', '=', self.env.user.id),
            ('active', '=', True),
        ], limit=1)
        if slot:
            raise AccessError(_(
                'Installing, upgrading, or uninstalling applications is '
                'managed by Plan B and is not available to tenant users.'
            ))

    def button_install(self):
        self._planb_check_module_operation_allowed()
        return super().button_install()

    def button_immediate_install(self):
        self._planb_check_module_operation_allowed()
        return super().button_immediate_install()

    def button_upgrade(self):
        self._planb_check_module_operation_allowed()
        return super().button_upgrade()

    def button_immediate_upgrade(self):
        self._planb_check_module_operation_allowed()
        return super().button_immediate_upgrade()

    def button_uninstall(self):
        self._planb_check_module_operation_allowed()
        return super().button_uninstall()

    def button_immediate_uninstall(self):
        self._planb_check_module_operation_allowed()
        return super().button_immediate_uninstall()

    def button_uninstall_wizard(self):
        self._planb_check_module_operation_allowed()
        return super().button_uninstall_wizard()