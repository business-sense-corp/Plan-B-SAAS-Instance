# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'planb_tenant_access')
class TestTenantSettingsLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env.ref('base.user_admin')
        cls.root_user = cls.env.ref('base.user_root')
        cls.group_system = cls.env.ref('base.group_system')

        # Create a test customer admin (Owner-like user with group_system)
        cls.customer_owner = cls.env['res.users'].create({
            'name': 'Customer Owner Test',
            'login': 'customer_owner_test@example.com',
            'email': 'customer_owner_test@example.com',
            'group_ids': [(6, 0, [cls.group_system.id])],
        })

        # Create a test regular user
        cls.regular_user = cls.env['res.users'].create({
            'name': 'Regular User Test',
            'login': 'regular_user_test@example.com',
            'email': 'regular_user_test@example.com',
            'group_ids': [(6, 0, [])],
        })

    def test_01_internal_admin_identity(self):
        """Test _planb_is_internal_admin identity check."""
        # base.user_admin and base.user_root must be recognized as internal admin
        self.assertTrue(self.admin_user._planb_is_internal_admin())
        self.assertTrue(self.root_user._planb_is_internal_admin())

        # Customer owner (even with base.group_system) is NOT an internal admin
        self.assertFalse(self.customer_owner._planb_is_internal_admin())

        # Regular user is NOT an internal admin
        self.assertFalse(self.regular_user._planb_is_internal_admin())

        # sudo() execution state does NOT change the user's identity
        owner_sudo = self.customer_owner.sudo()
        self.assertFalse(owner_sudo._planb_is_internal_admin())

        # Context su=True does NOT change identity
        owner_su = self.customer_owner.with_context(su=True)
        self.assertFalse(owner_su._planb_is_internal_admin())

    def test_02_lock_active_kill_switch(self):
        """Test _planb_lock_active kill-switch behavior."""
        param_obj = self.env['ir.config_parameter'].sudo()

        # Default when absent: True (fail-closed)
        existing_param = param_obj.search([('key', '=', 'planb.lock_settings')])
        if existing_param:
            existing_param.unlink()
        self.assertTrue(self.env['res.users']._planb_lock_active())

        # Explicit 'True' / '1'
        param_obj.set_param('planb.lock_settings', 'True')
        self.assertTrue(self.env['res.users']._planb_lock_active())

        param_obj.set_param('planb.lock_settings', '1')
        self.assertTrue(self.env['res.users']._planb_lock_active())

        # Explicit 'False' / '0'
        param_obj.set_param('planb.lock_settings', 'False')
        self.assertFalse(self.env['res.users']._planb_lock_active())

        param_obj.set_param('planb.lock_settings', '0')
        self.assertFalse(self.env['res.users']._planb_lock_active())

        # Clean up / reset to True
        param_obj.set_param('planb.lock_settings', 'True')

    def test_03_menu_blacklist_subtraction(self):
        """Test _load_menus_blacklist behavior for internal admin vs customer."""
        menu_model = self.env['ir.ui.menu']
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # Internal admin: blacklist is empty
        admin_blacklist = menu_model.with_user(self.admin_user)._load_menus_blacklist()
        self.assertEqual(admin_blacklist, [])

        root_blacklist = menu_model.with_user(self.root_user)._load_menus_blacklist()
        self.assertEqual(root_blacklist, [])

        # Customer owner: dangerous subtrees are in blacklist
        owner_blacklist = set(menu_model.with_user(self.customer_owner)._load_menus_blacklist())
        for xmlid in ['base.menu_apps', 'base.menu_users', 'base.menu_custom']:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertIn(menu.id, owner_blacklist, f"{xmlid} must be blacklisted for owner")

        # When kill-switch is deactivated: owner blacklist is empty
        param_obj.set_param('planb.lock_settings', 'False')
        owner_blacklist_inactive = menu_model.with_user(self.customer_owner)._load_menus_blacklist()
        self.assertEqual(owner_blacklist_inactive, [])
        param_obj.set_param('planb.lock_settings', 'True')

    def test_04_menu_loading_and_order_independence(self):
        """Test that load_menus yields different menus for admin vs owner order-independently."""
        menu_model = self.env['ir.ui.menu']
        self.env.registry.clear_cache()

        # Order 1: Admin first, then Owner
        admin_menus_1 = menu_model.with_user(self.admin_user).load_menus(False)
        owner_menus_1 = menu_model.with_user(self.customer_owner).load_menus(False)

        admin_ids_1 = set(admin_menus_1.keys()) - {'root'}
        owner_ids_1 = set(owner_menus_1.keys()) - {'root'}

        # base.menu_apps and base.menu_users are visible to admin but blacklisted for owner
        for xmlid in ['base.menu_apps', 'base.menu_users']:
            m = self.env.ref(xmlid, raise_if_not_found=False)
            if m:
                self.assertIn(m.id, admin_ids_1, f"{xmlid} must be in admin menus")
                self.assertNotIn(m.id, owner_ids_1, f"{xmlid} must NOT be in owner menus")

        # Settings root (base.menu_administration) is preserved for Owner
        settings_root = self.env.ref('base.menu_administration')
        self.assertIn(settings_root.id, owner_ids_1)

        # Order 2: Clear cache, then Owner first, then Admin
        self.env.registry.clear_cache()
        owner_menus_2 = menu_model.with_user(self.customer_owner).load_menus(False)
        admin_menus_2 = menu_model.with_user(self.admin_user).load_menus(False)

        admin_ids_2 = set(admin_menus_2.keys()) - {'root'}
        owner_ids_2 = set(owner_menus_2.keys()) - {'root'}

        self.assertEqual(admin_ids_1, admin_ids_2, "Admin menus must be order-independent")
        self.assertEqual(owner_ids_1, owner_ids_2, "Owner menus must be order-independent")

    def test_05_settings_view_field_and_inheritance(self):
        """Test res.config.settings planb_hide_system_settings field and view attributes."""
        settings_model = self.env['res.config.settings']
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # Compute field check for customer owner
        owner_settings = settings_model.with_user(self.customer_owner).new()
        self.assertTrue(owner_settings.planb_hide_system_settings)

        # Compute field check for admin
        admin_settings = settings_model.with_user(self.admin_user).new()
        self.assertFalse(admin_settings.planb_hide_system_settings)

        # When kill-switch is deactivated, owner compute field is False
        param_obj.set_param('planb.lock_settings', 'False')
        owner_settings_inactive = settings_model.with_user(self.customer_owner).new()
        self.assertFalse(owner_settings_inactive.planb_hide_system_settings)
        param_obj.set_param('planb.lock_settings', 'True')

        # Check view inheritance arch
        view = self.env.ref('planb_tenant_access.res_config_settings_view_form_inherit_planb', raise_if_not_found=False)
        if view:
            self.assertTrue(view.active)
            self.assertEqual(view.inherit_id, self.env.ref('base_setup.res_config_settings_view_form'))

    def test_06_debug_neutralization(self):
        """Test ir.http._handle_debug neutralization for non-internal identities."""
        from unittest.mock import MagicMock
        from odoo.http import _request_stack
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        mock_session = MagicMock()
        mock_session.debug = '1'

        mock_req = MagicMock()
        mock_req.session = mock_session
        mock_req.httprequest.args.get.return_value = None

        ir_http = self.env['ir.http']

        _request_stack.push(mock_req)
        try:
            # Customer owner: debug is cleared
            mock_req.env.user = self.customer_owner
            ir_http._handle_debug()
            self.assertEqual(mock_session.debug, '')

            # Internal admin: debug is preserved
            mock_session.debug = '1'
            mock_req.env.user = self.admin_user
            ir_http._handle_debug()
            self.assertEqual(mock_session.debug, '1')

            # When kill-switch is deactivated, customer owner debug is preserved
            param_obj.set_param('planb.lock_settings', 'False')
            mock_session.debug = '1'
            mock_req.env.user = self.customer_owner
            ir_http._handle_debug()
            self.assertEqual(mock_session.debug, '1')

            param_obj.set_param('planb.lock_settings', 'True')
        finally:
            _request_stack.pop()

    def test_07_ir_config_parameter_protection_and_cache_invalidation(self):
        """Test planb.* ir.config_parameter protection and cache invalidation."""
        from odoo.exceptions import AccessError
        param_model = self.env['ir.config_parameter']

        # Ensure planb.lock_settings exists
        param_model.sudo().set_param('planb.lock_settings', 'True')
        param = param_model.sudo().search([('key', '=', 'planb.lock_settings')], limit=1)
        self.assertTrue(param)

        # 1. Customer owner cannot write to planb.* parameters
        with self.assertRaises(AccessError):
            param.with_user(self.customer_owner).write({'value': 'False'})

        # Customer owner cannot unlink planb.* parameters
        with self.assertRaises(AccessError):
            param.with_user(self.customer_owner).unlink()

        # Customer owner cannot create planb.* parameters
        with self.assertRaises(AccessError):
            param_model.with_user(self.customer_owner).create({'key': 'planb.custom_key', 'value': '123'})

        # 2. Internal admin CAN write to planb.* parameters
        param.with_user(self.admin_user).write({'value': 'True'})
        self.assertEqual(param.value, 'True')

        # 3. Cache invalidation on planb.lock_settings modification
        self.env.registry.cache_invalidated.clear()
        param.with_user(self.admin_user).write({'value': 'False'})
        self.assertIn('default', self.env.registry.cache_invalidated)

        # Restore
        param.with_user(self.admin_user).write({'value': 'True'})




