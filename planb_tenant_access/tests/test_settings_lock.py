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

        # Create a test seat user with an active licensed slot
        cls.seat_user = cls.env['res.users'].create({
            'name': 'Seat User Test',
            'login': 'seat_user_test@example.com',
            'email': 'seat_user_test@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        # Link customer owner to slot 991 and seat user to slot 992
        cls.owner_slot = cls.env['planb.tenant.user.slot'].create({
            'slot_number': 991,
            'user_id': cls.customer_owner.id,
            'name': cls.customer_owner.name,
            'login': cls.customer_owner.login,
            'email': cls.customer_owner.email,
            'active': True,
            'is_activated': True,
        })
        cls.seat_slot = cls.env['planb.tenant.user.slot'].create({
            'slot_number': 992,
            'user_id': cls.seat_user.id,
            'name': cls.seat_user.name,
            'login': cls.seat_user.login,
            'email': cls.seat_user.email,
            'active': True,
            'is_activated': True,
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

    def test_08_res_users_create_unlink_blocked_for_customer(self):
        """Test res.users create and unlink are blocked for customer owner when lock is active."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Customer owner cannot create users
        with self.assertRaises(AccessError):
            self.env['res.users'].with_user(self.customer_owner).create({
                'name': 'Unauthorized User',
                'login': 'unauthorized@example.com',
            })

        # 2. Customer owner cannot unlink users
        with self.assertRaises(AccessError):
            self.regular_user.with_user(self.customer_owner).unlink()

        # 3. Internal admin CAN create and unlink users
        test_user = self.env['res.users'].with_user(self.admin_user).create({
            'name': 'Admin Created User',
            'login': 'admin_created_user@example.com',
        })
        self.assertTrue(test_user.exists())
        test_user.with_user(self.admin_user).unlink()
        self.assertFalse(test_user.exists())

        # 4. When kill-switch is inactive, customer owner can create and unlink
        param_obj.set_param('planb.lock_settings', 'False')
        owner_created = self.env['res.users'].with_user(self.customer_owner).create({
            'name': 'Unlocked Creation',
            'login': 'unlocked_creation@example.com',
        })
        self.assertTrue(owner_created.exists())
        owner_created.with_user(self.customer_owner).unlink()
        param_obj.set_param('planb.lock_settings', 'True')

    def test_09_res_users_archive_blocked_for_customer(self):
        """Test res.users archival (active=False) is blocked for customer owner."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Customer owner cannot archive regular user
        with self.assertRaises(AccessError):
            self.regular_user.with_user(self.customer_owner).write({'active': False})

        # 2. Customer owner cannot archive own user
        with self.assertRaises(AccessError):
            self.customer_owner.with_user(self.customer_owner).write({'active': False})

        # 3. Internal admin CAN archive a user
        self.regular_user.with_user(self.admin_user).write({'active': False})
        self.assertFalse(self.regular_user.active)
        self.regular_user.with_user(self.admin_user).write({'active': True})
        self.assertTrue(self.regular_user.active)

        # 4. When kill-switch is inactive, customer owner can archive
        param_obj.set_param('planb.lock_settings', 'False')
        self.regular_user.with_user(self.customer_owner).write({'active': False})
        self.assertFalse(self.regular_user.active)
        self.regular_user.with_user(self.customer_owner).write({'active': True})
        param_obj.set_param('planb.lock_settings', 'True')

    def test_10_res_users_internal_admin_protected(self):
        """Test that Plan B internal admin records cannot be written to by non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # Customer owner cannot modify base.user_admin or base.user_root
        with self.assertRaises(AccessError):
            self.admin_user.with_user(self.customer_owner).write({'name': 'Hacked Admin'})

        with self.assertRaises(AccessError):
            self.root_user.with_user(self.customer_owner).write({'name': 'Hacked Root'})

        # Even if kill switch is deactivated, internal admin records remain protected
        # Wait: kill-switch off checks _planb_lock_active()
        # Internal admin can write to itself
        self.admin_user.with_user(self.admin_user).write({'tz': 'UTC'})

    def test_11_res_users_group_ids_blocked_direct(self):
        """Test that non-internal users cannot directly write group_ids."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # Customer owner direct group_ids write is blocked
        with self.assertRaises(AccessError):
            self.regular_user.with_user(self.customer_owner).write({
                'group_ids': [(4, self.group_system.id)],
            })

        # Direct write with groups_id is also blocked
        with self.assertRaises(AccessError):
            self.regular_user.with_user(self.customer_owner).write({
                'groups_id': [(4, self.group_system.id)],
            })

        # Internal slot write with context is allowed
        self.regular_user.with_user(self.customer_owner).with_context(planb_internal_slot_write=True).write({
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })

        # Internal admin direct write is allowed
        self.regular_user.with_user(self.admin_user).write({
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })

    def test_12_res_users_slot_managed_credentials_blocked(self):
        """Test that login, email, password on slot-managed users are blocked for non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Login write on slot-managed user is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).write({
                'login': 'new_seat_login@example.com',
            })

        # 2. Email write on slot-managed user is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).write({
                'email': 'new_seat_email@example.com',
            })

        # 3. Password direct write on slot-managed user is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).write({
                'password': 'NewPassword123!',
            })

        # 4. Password direct write on own user is also blocked
        with self.assertRaises(AccessError):
            self.customer_owner.with_user(self.customer_owner).write({
                'password': 'NewPassword123!',
            })

        # 5. Internal admin CAN write login/email/password
        self.seat_user.with_user(self.admin_user).write({
            'email': 'seat_user_updated@example.com',
        })
        self.assertEqual(self.seat_user.email, 'seat_user_updated@example.com')

    def test_13_res_users_preferences_preservation(self):
        """Test that own-record Preferences save successfully for Owner and seat user."""
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Customer Owner updating own preferences (lang, tz, signature)
        self.customer_owner.with_user(self.customer_owner).write({
            'tz': 'Europe/Paris',
            'signature': '<p>Owner Signature</p>',
        })
        self.assertEqual(self.customer_owner.tz, 'Europe/Paris')
        self.assertIn('Owner Signature', self.customer_owner.signature)

        # 2. Seat user updating own preferences
        self.seat_user.with_user(self.seat_user).write({
            'tz': 'America/New_York',
            'signature': '<p>Seat Signature</p>',
        })
        self.assertEqual(self.seat_user.tz, 'America/New_York')
        self.assertIn('Seat Signature', self.seat_user.signature)

    def test_14_owner_toggling_group_settings_in_sales_inventory(self):
        """Test that Owner toggling group_* settings in Sales and Inventory still saves."""
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        settings_model = self.env['res.config.settings'].with_user(self.customer_owner)

        # Test Sales group setting (group_discount_per_so_line)
        if 'group_discount_per_so_line' in settings_model._fields:
            s_sales = settings_model.create({'group_discount_per_so_line': True})
            s_sales.execute()

        # Test Inventory group setting (group_stock_multi_locations)
        if 'group_stock_multi_locations' in settings_model._fields:
            s_stock = settings_model.create({'group_stock_multi_locations': True})
            s_stock.execute()

    def test_15_change_password_wizards_blocked(self):
        """Test that change.password.wizard and change.password.own are blocked for non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Customer owner calling action_change_password_wizard raises AccessError
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).action_change_password_wizard()

        # 2. Customer owner calling preference_change_password raises AccessError
        with self.assertRaises(AccessError):
            self.customer_owner.with_user(self.customer_owner).preference_change_password()

        # 3. Direct instantiation / create of change.password.wizard is blocked
        with self.assertRaises(AccessError):
            self.env['change.password.wizard'].with_user(self.customer_owner).default_get(['user_ids'])

        with self.assertRaises(AccessError):
            self.env['change.password.wizard'].with_user(self.customer_owner).create({})

        # 4. Direct instantiation / create of change.password.own is blocked
        with self.assertRaises(AccessError):
            self.env['change.password.own'].with_user(self.customer_owner).default_get(['new_password'])

        with self.assertRaises(AccessError):
            self.env['change.password.own'].with_user(self.customer_owner).create({
                'new_password': 'NewPassword123!',
                'confirm_password': 'NewPassword123!',
            })

        # 5. Internal admin CAN use change.password.own and change.password.wizard
        own_wizard = self.env['change.password.own'].with_user(self.admin_user).create({
            'new_password': 'AdminPassChange123!',
            'confirm_password': 'AdminPassChange123!',
        })
        self.assertTrue(own_wizard.exists())
        own_wizard.unlink()

        # 6. Kill-switch off allows customer owner to access wizards
        param_obj.set_param('planb.lock_settings', 'False')
        own_unlocked = self.env['change.password.own'].with_user(self.customer_owner).create({
            'new_password': 'UnlockedPass123!',
            'confirm_password': 'UnlockedPass123!',
        })
        self.assertTrue(own_unlocked.exists())
        own_unlocked.unlink()
        param_obj.set_param('planb.lock_settings', 'True')

    def test_16_portal_invitation_and_reset_flows(self):
        """Test that portal invitation, password reset, and credential rotation by uid 2 still work."""
        from odoo import fields
        from dateutil.relativedelta import relativedelta
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        public_user = self.env.ref('base.public_user')

        # 1. Credential rotation by uid 2 (admin_user)
        self.seat_user.with_user(self.admin_user).write({'password': 'AdminRotatedPass123!'})
        cred_admin = {'type': 'password', 'login': self.seat_user.login, 'password': 'AdminRotatedPass123!'}
        auth_admin = self.env['res.users'].authenticate(cred_admin, {})
        self.assertEqual(auth_admin['uid'], self.seat_user.id)

        # 2. Portal invitation token flow (auth_signup token on partner)
        self.seat_user.partner_id.signup_prepare(signup_type="signup")
        invitation_token = self.seat_user.partner_id.sudo()._generate_signup_token()
        self.assertTrue(invitation_token)

        # Unauthenticated / public user signs up with the valid token (as done by auth_signup controller)
        self.env['res.users'].with_user(public_user).sudo().signup({'password': 'InvitedUserPass123!'}, token=invitation_token)
        cred_invited = {'type': 'password', 'login': self.seat_user.login, 'password': 'InvitedUserPass123!'}
        auth_invited = self.env['res.users'].authenticate(cred_invited, {'interactive': False})
        self.assertEqual(auth_invited['uid'], self.seat_user.id)

        # 3. Password reset token flow
        self.seat_user.partner_id.signup_prepare(signup_type="reset")
        reset_token = self.seat_user.partner_id.sudo()._generate_signup_token()
        self.assertTrue(reset_token)

        self.env['res.users'].with_user(public_user).sudo().signup({'password': 'ResetUserPass123!'}, token=reset_token)
        cred_reset = {'type': 'password', 'login': self.seat_user.login, 'password': 'ResetUserPass123!'}
        auth_reset = self.env['res.users'].authenticate(cred_reset, {'interactive': False})
        self.assertEqual(auth_reset['uid'], self.seat_user.id)




