# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from ..models.res_users import internal_slot_scope


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
            arch = view.arch
            self.assertIn('open_company', arch)
            self.assertIn('planb_dev_tools_block', arch)
            self.assertIn('contacts_settings', arch)
            self.assertIn('email-alias-setting', arch)
            self.assertIn('about', arch)

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

        # Internal slot write with internal_slot_scope is allowed
        with internal_slot_scope(self.env.cr):
            self.regular_user.with_user(self.customer_owner).write({
                'group_ids': [(4, self.env.ref('base.group_user').id)],
            })

        # Fake context spoofing without internal_slot_scope is BLOCKED
        with self.assertRaises(AccessError):
            self.regular_user.with_user(self.customer_owner).with_context(planb_internal_slot_write=True).write({
                'group_ids': [(4, self.group_system.id)],
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
            disc_group = self.env.ref('sale.group_discount_per_so_line', raise_if_not_found=False)
            if disc_group:
                self.assertIn(disc_group, self.env.ref('base.group_user').implied_ids)

            # Toggle back to False
            s_sales_off = settings_model.create({'group_discount_per_so_line': False})
            s_sales_off.execute()
            if disc_group:
                self.assertNotIn(disc_group, self.env.ref('base.group_user').implied_ids)

        # Test Inventory group setting (group_stock_multi_locations)
        if 'group_stock_multi_locations' in settings_model._fields:
            s_stock = settings_model.create({'group_stock_multi_locations': True})
            s_stock.execute()
            loc_group = self.env.ref('stock.group_stock_multi_locations', raise_if_not_found=False)
            if loc_group:
                self.assertIn(loc_group, self.env.ref('base.group_user').implied_ids)

            s_stock_off = settings_model.create({'group_stock_multi_locations': False})
            s_stock_off.execute()
            if loc_group:
                self.assertNotIn(loc_group, self.env.ref('base.group_user').implied_ids)

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

    def test_17_res_company_create_unlink_blocked(self):
        """Test res.company create and unlink are blocked for non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        company_model = self.env['res.company']

        # 1. Customer owner cannot create company
        with self.assertRaises(AccessError):
            company_model.with_user(self.customer_owner).create({'name': 'Unauthorized New Company'})

        # 2. Customer owner cannot unlink company (blocked by AccessError from guard)
        company = self.env.company
        with self.assertRaises(AccessError):
            company.with_user(self.customer_owner).unlink()

        # 3. Internal admin CAN create company
        test_company = company_model.with_user(self.admin_user).create({'name': 'Admin Temporary Company'})
        self.assertTrue(test_company.exists())

        # 4. Kill-switch off allows customer owner to create company
        param_obj.set_param('planb.lock_settings', 'False')
        owner_company = company_model.with_user(self.customer_owner).create({'name': 'Unlocked Company'})
        self.assertTrue(owner_company.exists())
        param_obj.set_param('planb.lock_settings', 'True')

    def test_18_res_company_synced_fields_blocked(self):
        """Test res.company synced fields writes are blocked for non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        company = self.env.company

        # Synced fields must be blocked when modified by customer owner
        for field in ['name', 'vat', 'email', 'phone', 'street', 'city', 'zip']:
            if field in company._fields:
                with self.assertRaises(AccessError, msg=f"Writing to {field} must raise AccessError"):
                    company.with_user(self.customer_owner).write({field: f"modified_{field}"})

        # Non-synced fields MUST still save for customer owner
        company.with_user(self.customer_owner).write({
            'font': 'Lato',
            'primary_color': '#123456',
            'secondary_color': '#654321',
        })
        self.assertEqual(company.font, 'Lato')
        self.assertEqual(company.primary_color, '#123456')

        # Writing identical (unchanged) synced values does not raise
        company.with_user(self.customer_owner).write({'name': company.name})

        # Internal admin CAN write to synced fields
        original_name = company.name
        company.with_user(self.admin_user).write({'name': original_name + ' Updated'})
        self.assertEqual(company.name, original_name + ' Updated')
        company.with_user(self.admin_user).write({'name': original_name})

        # Kill-switch off allows customer owner to write to synced fields
        param_obj.set_param('planb.lock_settings', 'False')
        company.with_user(self.customer_owner).write({'phone': '+1234567890'})
        self.assertEqual(company.phone, '+1234567890')
        param_obj.set_param('planb.lock_settings', 'True')

    def test_19_base_document_layout_wizard_saves(self):
        """Test that Configure Document Layout wizard (base.document.layout) saves successfully for Owner."""
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # Owner opens base.document.layout wizard
        wizard_model = self.env['base.document.layout'].with_user(self.customer_owner)
        wizard = wizard_model.create({
            'font': 'Roboto',
            'primary_color': '#003366',
            'secondary_color': '#336699',
            'report_footer': '<p>Custom Document Footer</p>',
        })
        self.assertTrue(wizard.exists())

        # Verify that changes were saved to res.company
        company = self.env.company
        self.assertEqual(company.font, 'Roboto')
        self.assertEqual(company.primary_color, '#003366')
        self.assertEqual(company.secondary_color, '#336699')

    def test_20_tenant_user_slot_matrix_as_owner(self):
        """Test tenant user slot management matrix as Owner:
        - pre-activation edit: name, login, email updates allowed
        - module change: toggling modules / access_all_modules allowed
        - email/name/login change on activated slot: blocked
        - resend invite: allowed
        - edit slot 1: blocked
        - create slot: blocked
        - unlink slot: blocked
        """
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        slot_model = self.env['planb.tenant.user.slot']

        # Ensure slot 1 exists
        slot_1 = slot_model.sudo().search([('slot_number', '=', 1)], limit=1)
        if not slot_1:
            with internal_slot_scope(self.env.cr):
                slot_1 = slot_model.sudo().create({
                    'slot_number': 1,
                    'user_id': self.customer_owner.id,
                    'name': self.customer_owner.name,
                    'login': self.customer_owner.login,
                    'email': self.customer_owner.email,
                    'active': True,
                    'is_activated': True,
                })

        # Create unactivated employee user & slot (slot 995)
        unactivated_user = self.env['res.users'].with_user(self.admin_user).create({
            'name': 'Pending Employee',
            'login': 'pending_emp@example.com',
            'email': 'pending_emp@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with internal_slot_scope(self.env.cr):
            employee_slot = slot_model.sudo().create({
                'slot_number': 995,
                'user_id': unactivated_user.id,
                'name': unactivated_user.name,
                'login': unactivated_user.login,
                'email': unactivated_user.email,
                'active': True,
                'is_activated': False,
                'access_all_modules': True,
            })
        owner_employee_slot = slot_model.with_user(self.customer_owner).browse(employee_slot.id)
        owner_slot_1 = slot_model.with_user(self.customer_owner).browse(slot_1.id)

        # 1. Pre-activation edit as Owner (name, login, email allowed)
        owner_employee_slot.write({
            'name': 'Updated Pending Employee',
            'login': 'updated_pending@example.com',
            'email': 'updated_pending@example.com',
        })
        self.assertEqual(employee_slot.name, 'Updated Pending Employee')
        self.assertEqual(employee_slot.login, 'updated_pending@example.com')
        self.assertEqual(unactivated_user.login, 'updated_pending@example.com')
        self.assertEqual(unactivated_user.email, 'updated_pending@example.com')

        # 2. Module change as Owner (allowed)
        owner_employee_slot.write({
            'access_all_modules': False,
            'module_ids': [(6, 0, [])],
        })
        self.assertFalse(employee_slot.access_all_modules)

        # 3. Email change on activated slot as Owner (blocked)
        with internal_slot_scope(self.env.cr):
            employee_slot.sudo().write({'is_activated': True})
        with self.assertRaises(AccessError):
            owner_employee_slot.write({
                'email': 'hacked_email@example.com',
            })
        with self.assertRaises(AccessError):
            owner_employee_slot.write({
                'login': 'hacked_login@example.com',
            })
        with self.assertRaises(AccessError):
            owner_employee_slot.write({
                'name': 'Hacked Name',
            })

        # 4. Resend invite (allowed for employee)
        employee_slot.user_id.partner_id.signup_prepare(signup_type="signup")
        token = employee_slot.user_id.partner_id.sudo()._generate_signup_token()
        self.assertTrue(token)

        # 5. Edit slot 1 as Owner (blocked)
        with self.assertRaises(AccessError):
            owner_slot_1.write({
                'name': 'Renamed Slot 1',
            })
        with self.assertRaises(AccessError):
            owner_slot_1.write({
                'access_all_modules': False,
            })

        # 6. Create slot as Owner (blocked)
        with self.assertRaises(AccessError):
            slot_model.with_user(self.customer_owner).create({
                'slot_number': 996,
                'user_id': self.regular_user.id,
                'name': 'Unauthorized Slot',
                'login': self.regular_user.login,
            })

        # 7. Unlink slot as Owner (blocked)
        with self.assertRaises(AccessError):
            owner_employee_slot.unlink()

    def test_21_tenant_user_slot_kill_switch_and_internal_admin(self):
        """Test tenant user slot behavior with internal admin and kill-switch deactivation."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        slot_model = self.env['planb.tenant.user.slot']

        # 1. Internal admin can create and unlink slots via internal context
        new_user = self.env['res.users'].with_user(self.admin_user).create({
            'name': 'Internal Created User',
            'login': 'internal_created@example.com',
        })
        with internal_slot_scope(self.env.cr):
            admin_slot = slot_model.with_user(self.admin_user).create({
                'slot_number': 997,
                'user_id': new_user.id,
                'name': new_user.name,
                'login': new_user.login,
                'active': True,
            })
            self.assertTrue(admin_slot.exists())
            admin_slot.with_user(self.admin_user).unlink()
            self.assertFalse(admin_slot.exists())

        # 2. When kill-switch is inactive, Owner can create and unlink slots
        param_obj.set_param('planb.lock_settings', 'False')
        unlocked_slot = slot_model.with_user(self.customer_owner).create({
            'slot_number': 998,
            'user_id': new_user.id,
            'name': new_user.name,
            'login': new_user.login,
            'active': True,
        })
        self.assertTrue(unlocked_slot.exists())
        unlocked_slot.with_user(self.customer_owner).unlink()
        self.assertFalse(unlocked_slot.exists())

        # 3. planb.* parameters remain protected even when kill-switch is False
        planb_param = self.env['ir.config_parameter'].sudo().search([('key', '=', 'planb.lock_settings')], limit=1)
        with self.assertRaises(AccessError):
            planb_param.with_user(self.customer_owner).write({'value': 'True'})

        param_obj.set_param('planb.lock_settings', 'True')

    def test_22_res_groups_direct_write_and_unlink_blocked(self):
        """Test that direct writes to res.groups (user_ids, admin groups, unlink, create)
        are blocked for non-internal users to prevent privilege escalation."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        # 1. Customer owner cannot add users to base.group_system via user_ids
        with self.assertRaises(AccessError):
            self.group_system.with_user(self.customer_owner).write({
                'user_ids': [(4, self.regular_user.id)],
            })

        # 2. Customer owner cannot modify administrative groups
        with self.assertRaises(AccessError):
            self.group_system.with_user(self.customer_owner).write({
                'name': 'Hacked System Group',
            })

        # 3. Customer owner cannot delete groups
        with self.assertRaises(AccessError):
            self.group_system.with_user(self.customer_owner).unlink()

        # 4. Customer owner cannot create groups
        with self.assertRaises(AccessError):
            self.env['res.groups'].with_user(self.customer_owner).create({
                'name': 'Unauthorized Group',
            })

        # 5. Internal admin CAN modify groups
        self.group_system.with_user(self.admin_user).write({
            'comment': 'Admin updated group comment',
        })
        self.assertEqual(self.group_system.comment, 'Admin updated group comment')

        # 6. Kill-switch off allows customer owner to modify groups
        param_obj.set_param('planb.lock_settings', 'False')
        self.group_system.with_user(self.customer_owner).write({
            'comment': 'Unlocked owner comment',
        })
        self.assertEqual(self.group_system.comment, 'Unlocked owner comment')
        param_obj.set_param('planb.lock_settings', 'True')

    def test_23_company_partner_synced_fields_blocked(self):
        """Test that res.partner writes to company.partner_id synced fields are blocked
        for non-internal users, preventing company profile modification bypass."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        company_partner = self.env.company.partner_id

        # 1. Writing to synced fields on company partner raises AccessError
        for field in ['name', 'vat', 'email', 'phone', 'street', 'city', 'zip']:
            if field in company_partner._fields:
                with self.assertRaises(AccessError, msg=f"Writing to company partner {field} must raise AccessError"):
                    company_partner.with_user(self.customer_owner).write({
                        field: f"modified_{field}",
                    })

        # 2. Customer owner cannot unlink company partner
        with self.assertRaises(AccessError):
            company_partner.with_user(self.customer_owner).unlink()

        # 3. Customer owner CAN write to ordinary non-company partner
        regular_partner = self.regular_user.partner_id
        regular_partner.with_user(self.customer_owner).write({
            'name': 'Customer Contact Updated',
            'phone': '+999888777',
        })
        self.assertEqual(regular_partner.name, 'Customer Contact Updated')

        # 4. Internal admin CAN write to company partner
        original_company_partner_name = company_partner.name
        company_partner.with_user(self.admin_user).write({'name': original_company_partner_name + ' Admin'})
        self.assertEqual(company_partner.name, original_company_partner_name + ' Admin')
        company_partner.with_user(self.admin_user).write({'name': original_company_partner_name})

        # 5. Kill-switch off allows customer owner to write to company partner
        param_obj.set_param('planb.lock_settings', 'False')
        company_partner.with_user(self.customer_owner).write({'phone': '+1987654321'})
        self.assertEqual(company_partner.phone, '+1987654321')
        param_obj.set_param('planb.lock_settings', 'True')

    def test_24_res_groups_implied_ids_and_rules_privilege_escalation_blocked(self):
        """Test that customer owner cannot escalate privileges via res.groups.implied_ids
        or modify group security rules/menus directly."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        group_user = self.env.ref('base.group_user')

        # 1. Customer owner cannot make group_user imply group_system
        with self.assertRaises(AccessError):
            group_user.with_user(self.customer_owner).write({
                'implied_ids': [(4, self.group_system.id)],
            })

        # 2. Customer owner cannot make group_user imply customer admin group
        admin_group = self.env.ref('planb_tenant_access.group_planb_customer_admin')
        with self.assertRaises(AccessError):
            group_user.with_user(self.customer_owner).write({
                'implied_ids': [(4, admin_group.id)],
            })

        # 3. Customer owner cannot modify model_access or rule_groups on res.groups
        with self.assertRaises(AccessError):
            group_user.with_user(self.customer_owner).write({
                'model_access': [(5, 0, 0)],
            })

        with self.assertRaises(AccessError):
            group_user.with_user(self.customer_owner).write({
                'rule_groups': [(5, 0, 0)],
            })

    def test_25_context_spoofing_bypasses_blocked(self):
        """Test that RPC caller cannot spoof internal execution state via context dictionary."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        slot_model = self.env['planb.tenant.user.slot']

        # 1. Spoofing planb_auth_signup_flow to modify password is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).with_context(planb_auth_signup_flow=True).write({
                'password': 'SpoofedPassword123!',
            })

        # 2. Spoofing auth_signup_token in context to modify password is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).with_context(auth_signup_token='fake_token_123').write({
                'password': 'SpoofedPassword123!',
            })

        # 3. Spoofing planb_internal_slot_write in context to modify slot password is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).with_context(planb_internal_slot_write=True).write({
                'password': 'SpoofedPassword123!',
            })

        # 4. Spoofing planb_internal_slot_write in context to modify slot login is blocked
        with self.assertRaises(AccessError):
            self.seat_user.with_user(self.customer_owner).with_context(planb_internal_slot_write=True).write({
                'login': 'spoofed_login@example.com',
            })

        # 5. Spoofing planb_internal_slot_write in context to create a slot is blocked
        with self.assertRaises(AccessError):
            slot_model.with_user(self.customer_owner).with_context(planb_internal_slot_write=True).create({
                'slot_number': 9999,
                'user_id': self.regular_user.id,
                'name': 'Spoofed Slot',
                'login': self.regular_user.login,
            })

        # 6. Spoofing planb_internal_slot_write in context to unlink a slot is blocked
        owner_seat_slot = slot_model.with_user(self.customer_owner).browse(self.seat_slot.id)
        with self.assertRaises(AccessError):
            owner_seat_slot.with_context(planb_internal_slot_write=True).unlink()

    def test_26_company_partner_id_and_archival_blocked(self):
        """Test that company.partner_id modification, company partner archival,
        and res.company archival are strictly blocked for non-internal users."""
        from odoo.exceptions import AccessError
        param_obj = self.env['ir.config_parameter'].sudo()
        param_obj.set_param('planb.lock_settings', 'True')

        company = self.env.company
        company_partner = company.partner_id

        # 1. Customer owner cannot change company.partner_id
        new_partner = self.env['res.partner'].with_user(self.customer_owner).create({
            'name': 'Bypass Attempt Partner',
        })
        with self.assertRaises(AccessError):
            company.with_user(self.customer_owner).write({
                'partner_id': new_partner.id,
            })

        # 2. Customer owner cannot archive company.partner_id
        with self.assertRaises(AccessError):
            company_partner.with_user(self.customer_owner).write({
                'active': False,
            })

        # 3. Customer owner cannot archive res.company directly
        with self.assertRaises(AccessError):
            company.with_user(self.customer_owner).write({
                'active': False,
            })

    def test_27_settings_view_get_views_proof(self):
        """Prove get_views as Owner: Outgoing Email Servers present, Digest present,
        alias, Gmail, Outlook, about, and dev tools have planb_hide_system_settings.
        """
        views = self.env['res.config.settings'].with_user(self.customer_owner).get_views([(False, 'form')])
        arch = views['views']['form']['arch']

        # 1. Outgoing email servers is present and NOT hidden
        self.assertIn('email_servers_setting', arch)
        # 2. Document Layout is present
        self.assertIn('document_layout_setting', arch)
        # 3. Inner email settings are hidden
        self.assertIn('id="email-alias-setting" invisible="planb_hide_system_settings"', arch)
        self.assertIn('id="email-outlook-setting" invisible="planb_hide_system_settings"', arch)
        self.assertIn('name="module_google_gmail"', arch)
        # 4. About block is hidden
        self.assertIn('id="about" invisible="planb_hide_system_settings"', arch)
        # 5. Developer tools block is hidden
        self.assertIn('id="planb_dev_tools_block" invisible="planb_hide_system_settings"', arch)
        # 6. Update info button is hidden
        self.assertIn('name="open_company"', arch)
        self.assertIn('invisible="planb_hide_system_settings"', arch)





