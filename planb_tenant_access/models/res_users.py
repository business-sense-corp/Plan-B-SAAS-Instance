# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _planb_is_internal_admin(self):
        """Check if self is an internal Plan B administrator (OdooBot / root or Administrator).
        Identity is strictly based on base.user_admin and base.user_root.
        Execution state (env.su / sudo) is NOT identity.
        """
        admin_user = self.env.ref('base.user_admin', raise_if_not_found=False)
        root_user = self.env.ref('base.user_root', raise_if_not_found=False)
        internal_ids = {u.id for u in (admin_user, root_user) if u}
        if not internal_ids:
            internal_ids = {1, 2}
        return bool(self) and all(user.id in internal_ids for user in self)

    @api.model
    def _planb_lock_active(self):
        """Check if the tenant settings lock kill-switch is active.
        Defaults to True (fail-closed) if the parameter is absent or True.
        """
        val = self.env['ir.config_parameter'].sudo().get_param('planb.lock_settings', default='True')
        return str(val).strip().lower() not in ('false', '0', 'no', 'off')

    def _planb_is_customer_admin(self):
        return (
            self.env.user.has_group(
                'planb_tenant_access.group_planb_customer_admin'
            )
            and self.env.user.has_group('base.group_system')
        )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Creating users directly in the tenant is not allowed. '
                'Please manage user seats from the Plan B SaaS Portal.'
            ))
        return super().create(vals_list)

    def unlink(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Deleting users directly in the tenant is not allowed. '
                'Please manage user seats from the Plan B SaaS Portal.'
            ))
        return super().unlink()

    def action_change_password_wizard(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing user passwords from within the tenant is disabled. '
                'Please manage user passwords through the Plan B SaaS Portal.'
            ))
        return super().action_change_password_wizard()

    def preference_change_password(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing your password from within the tenant is disabled. '
                'Please change your password through the Plan B SaaS Portal.'
            ))
        return super().preference_change_password()

    @api.model
    def signup(self, values, token=None):
        if token:
            return super(ResUsers, self.with_context(planb_auth_signup_flow=True)).signup(values, token=token)
        return super().signup(values, token=token)

    @api.model
    def _planb_administrative_group_ids(self):
        """Return IDs of administrative, technical, and package-managed groups."""
        xmlids = [
            'base.group_system',
            'base.group_erp_manager',
            'planb_tenant_access.group_planb_customer_admin',
        ]
        group_ids = set()
        for xmlid in xmlids:
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec and rec._name == 'res.groups':
                group_ids.add(rec.id)
        if 'planb.tenant.user.slot' in self.env:
            group_ids.update(self.env['planb.tenant.user.slot']._managed_module_group_ids())
        return group_ids

    def write(self, vals):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            # 1. Protect internal admin accounts from any non-internal writes
            if any(user._planb_is_internal_admin() for user in self):
                raise AccessError(_(
                    'Modifying Plan B internal administrator accounts is not allowed.'
                ))

            # 2. Block user archival (active=False)
            if 'active' in vals and not vals['active']:
                raise AccessError(_(
                    'Archiving users directly in the tenant is not allowed. '
                    'Please manage user seats from the Plan B SaaS Portal.'
                ))

            # 3. Block direct group_ids writes to administrative/technical groups (unless via internal slot management)
            group_field_val = vals.get('group_ids') or vals.get('groups_id')
            if group_field_val is not None and not self.env.context.get('planb_internal_slot_write'):
                admin_group_ids = self._planb_administrative_group_ids()
                # Parse commands from group_field_val
                affected_group_ids = set()
                has_clear_command = False
                for cmd in group_field_val:
                    if isinstance(cmd, (tuple, list)) and len(cmd) >= 2:
                        code = cmd[0]
                        if code in (1, 2, 3, 4):
                            affected_group_ids.add(cmd[1])
                        elif code == 5:
                            has_clear_command = True
                        elif code == 6 and len(cmd) >= 3 and isinstance(cmd[2], (list, tuple, set)):
                            affected_group_ids.update(cmd[2])
                            has_clear_command = True

                # If clear command is used, check if existing users had administrative groups
                if has_clear_command:
                    for user in self:
                        if set(user.group_ids.ids) & admin_group_ids:
                            affected_group_ids.update(admin_group_ids)
                            break

                if affected_group_ids & admin_group_ids:
                    raise AccessError(_(
                        'Modifying administrative or technical user groups directly is not allowed. '
                        'Please assign module permissions via Licensed User Slots.'
                    ))

            # 4. Block login, email, password on slot-managed users (unless internal slot write or valid auth signup token)
            if not self.env.context.get('planb_internal_slot_write'):
                valid_signup_partner = getattr(self.env.cr, 'planb_valid_signup_partner', None)
                partner_ids = set(self.mapped('partner_id.id'))
                is_valid_token_signup = valid_signup_partner is not None and valid_signup_partner in partner_ids
                if is_valid_token_signup:
                    self.env.cr.planb_valid_signup_partner = None

                slot_user_ids = set(self.env['planb.tenant.user.slot'].sudo().search([
                    ('user_id', 'in', self.ids),
                    ('active', '=', True),
                ]).mapped('user_id.id'))
                if slot_user_ids:
                    slot_users = self.filtered(lambda u: u.id in slot_user_ids)
                    if 'login' in vals and any(vals['login'] != u.login for u in slot_users):
                        raise AccessError(_(
                            'Modifying login for slot-managed users is not allowed. '
                            'Please use the Plan B SaaS Portal.'
                        ))
                    if 'email' in vals and any((vals['email'] or False) != (u.email or False) for u in slot_users):
                        raise AccessError(_(
                            'Modifying email for slot-managed users is not allowed. '
                            'Please use the Plan B SaaS Portal.'
                        ))
                    if 'password' in vals and not is_valid_token_signup and not self.env.context.get('planb_auth_signup_flow') and not self.env.context.get('auth_signup_token'):
                        raise AccessError(_(
                            'Modifying password for slot-managed users directly is not allowed. '
                            'Please use the Plan B SaaS Portal.'
                        ))

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


class ChangePasswordWizard(models.TransientModel):
    _inherit = 'change.password.wizard'

    @api.model
    def default_get(self, fields_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing user passwords from within the tenant is disabled. '
                'Please manage user passwords through the Plan B SaaS Portal.'
            ))
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing user passwords from within the tenant is disabled. '
                'Please manage user passwords through the Plan B SaaS Portal.'
            ))
        return super().create(vals_list)

    def change_password_button(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing user passwords from within the tenant is disabled. '
                'Please manage user passwords through the Plan B SaaS Portal.'
            ))
        return super().change_password_button()


class ChangePasswordOwn(models.TransientModel):
    _inherit = 'change.password.own'

    @api.model
    def default_get(self, fields_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing your password from within the tenant is disabled. '
                'Please change your password through the Plan B SaaS Portal.'
            ))
        return super().default_get(fields_list)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing your password from within the tenant is disabled. '
                'Please change your password through the Plan B SaaS Portal.'
            ))
        return super().create(vals_list)

    def change_password(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                'Changing your password from within the tenant is disabled. '
                'Please change your password through the Plan B SaaS Portal.'
            ))
        return super().change_password()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        if 'signup_type' in vals and not vals['signup_type']:
            for partner in self:
                partner.env.cr.planb_valid_signup_partner = partner.id
        return super().write(vals)
