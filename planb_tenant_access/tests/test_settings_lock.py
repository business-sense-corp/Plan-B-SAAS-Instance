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
