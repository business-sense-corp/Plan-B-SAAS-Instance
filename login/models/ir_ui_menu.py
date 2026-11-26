from odoo import models

class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _register_hook(self):
        res = super()._register_hook()
        menu = self.env.ref('account.menu_finance', raise_if_not_found=False)
        if menu:
            active_langs = set(self.env['res.lang'].sudo().search([
                ('code', 'in', ['ar_001']),
                ('active', '=', True),
            ]).mapped('code'))
            for lang_code in active_langs:
                menu_ar = menu.with_context(lang=lang_code)
                if menu_ar.name != 'المحاسبة':
                    menu_ar.write({'name': 'المحاسبة'})
        return res