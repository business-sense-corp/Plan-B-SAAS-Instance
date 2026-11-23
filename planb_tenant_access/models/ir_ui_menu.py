# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _planb_menu_and_descendant_ids(self, root_ids):
        """Return root menu ids plus all their descendants."""
        result = set(root_ids)
        pending = set(root_ids)

        while pending:
            children = self.sudo().search([
                ('parent_id', 'in', list(pending)),
            ])
            new_ids = set(children.ids) - result
            result.update(new_ids)
            pending = new_ids

        return result

    def _load_menus_blacklist(self):
        """Subtract dangerous subtrees (Apps, Users & Companies, Technical)
        for non-internal identities when settings lock is active.
        """
        res = super()._load_menus_blacklist()
        user = self.env.user
        if not user._planb_is_internal_admin() and user._planb_lock_active():
            dangerous_xmlids = [
                'base.menu_management',
                'base.menu_apps',
                'base.menu_users',
                'base.menu_custom',
            ]
            dangerous_roots = []
            for xmlid in dangerous_xmlids:
                menu = self.env.ref(xmlid, raise_if_not_found=False)
                if menu:
                    dangerous_roots.append(menu.id)
            if dangerous_roots:
                res.extend(self._planb_menu_and_descendant_ids(dangerous_roots))
        return list(set(res))

    def get_user_roots(self):
        """Ensure blacklisted root menus are also excluded when loading user root menus."""
        roots = super().get_user_roots()
        blacklist = set(self._load_menus_blacklist())
        if blacklist:
            roots = roots.filtered(lambda m: m.id not in blacklist)
        return roots

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible_ids = set(super()._visible_menu_ids(debug=debug))
        user = self.env.user

        # Plan B internal/system administrators keep the normal Odoo menus.
        if user.has_group('base.group_system'):
            return frozenset(visible_ids)

        # Restrict only licensed tenant users (customer admin + user2..N).
        slot = self.env['planb.tenant.user.slot'].sudo().search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ], limit=1)

        if not slot:
            return frozenset(visible_ids)

        # Hide Apps completely for tenant users.
        apps_menu = self.env.ref(
            'base.menu_apps',
            raise_if_not_found=False
        )

        if apps_menu:
            visible_ids -= self._planb_menu_and_descendant_ids(
                {apps_menu.id}
            )

        # Hide package modules not allowed for this user.
        all_modules = self.env[
            'planb.tenant.module.access'
        ].sudo().search([
            ('active', '=', True),
        ])

        allowed_modules = slot._selected_modules()
        denied_modules = all_modules - allowed_modules

        denied_root_menu_ids = set()

        for module in denied_modules:
            for xmlid in module.get_root_menu_xmlids():
                menu = self.env.ref(
                    xmlid,
                    raise_if_not_found=False
                )

                if menu and menu._name == 'ir.ui.menu':
                    denied_root_menu_ids.add(menu.id)

        if denied_root_menu_ids:
            visible_ids -= self._planb_menu_and_descendant_ids(
                denied_root_menu_ids
            )

        return frozenset(visible_ids)