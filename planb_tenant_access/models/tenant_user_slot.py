# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


_logger = logging.getLogger(__name__)


class PlanBTenantUserSlot(models.Model):
    _name = 'planb.tenant.user.slot'
    _description = 'Plan B Licensed Tenant User Slot'
    _order = 'slot_number, id'

    slot_number = fields.Integer(required=True, readonly=True, index=True)
    user_id = fields.Many2one(
        'res.users',
        required=True,
        readonly=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(required=True)
    login = fields.Char(required=True)
    email = fields.Char()
    access_all_modules = fields.Boolean(
        string='Access All Package Modules',
        default=True,
        help=(
            'When enabled, the user automatically receives every current and '
            'future module in the subscribed package.'
        ),
    )
    module_ids = fields.Many2many(
        'planb.tenant.module.access',
        'planb_tenant_slot_module_rel',
        'slot_id',
        'module_id',
        string='Allowed Package Modules',
    )
    active = fields.Boolean(default=True, readonly=True)
    is_activated = fields.Boolean(
        string='Is Activated',
        default=False,
        help='Indicates whether this user has an active portal invitation or custom password.',
    )

    _sql_constraints = [
        (
            'planb_tenant_user_slot_number_uniq',
            'unique(slot_number)',
            'The licensed slot number must be unique.',
        ),
        (
            'planb_tenant_user_slot_user_uniq',
            'unique(user_id)',
            'A tenant user can only be linked to one licensed slot.',
        ),
    ]

    def _is_customer_admin_request(self):
        return (
            self.env.user.has_group(
                'planb_tenant_access.group_planb_customer_admin'
            )
            and not self.env.user.has_group('base.group_system')
        )

    @api.model
    def _xmlids_to_group_ids(self, xmlids):
        group_ids = []
        for xmlid in list(dict.fromkeys(filter(None, xmlids or []))):
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record and record._name == 'res.groups':
                group_ids.append(record.id)
            else:
                _logger.warning(
                    'Tenant access group XML ID was not found: %s', xmlid
                )
        return list(dict.fromkeys(group_ids))

    @api.model
    def _protected_group_ids(self):
        xmlids = ['base.group_system', 'base.group_erp_manager']
        return set(self._xmlids_to_group_ids(xmlids))

    @api.model
    def _managed_module_group_ids(self):
        records = self.env['planb.tenant.module.access'].sudo().with_context(
            active_test=False
        ).search([])
        xmlids = []
        for module in records:
            xmlids.extend(module.get_user_group_xmlids())
            xmlids.extend(module.get_manager_group_xmlids())
        return set(self._xmlids_to_group_ids(xmlids))

    @api.model
    def _customer_admin_group_id(self):
        group = self.env.ref(
            'planb_tenant_access.group_planb_customer_admin',
            raise_if_not_found=False,
        )
        return group.id if group else False

    def _validate_customer_login(self, login):
        login = (login or '').strip()
        if not login:
            raise ValidationError(_('User login cannot be empty.'))

        reserved = {
            (
                self.env['ir.config_parameter'].sudo().get_param(
                    'planb.internal_admin_login', 'admin'
                )
                or 'admin'
            ).strip(),
            (
                self.env['ir.config_parameter'].sudo().get_param(
                    'planb.service_login', 'saas_system'
                )
                or 'saas_system'
            ).strip(),
        }
        if login in reserved:
            raise ValidationError(
                _('This login is reserved for Plan B administration.')
            )

        duplicate = self.env['res.users'].sudo().with_context(
            active_test=False
        ).search([
            ('login', '=', login),
            ('id', '!=', self.user_id.id),
        ], limit=1)
        if duplicate:
            raise ValidationError(_('Another user already uses this login.'))

    def _apply_profile_to_user(self):
        for slot in self:
            slot._validate_customer_login(slot.login)
            slot.user_id.sudo().write({
                'name': slot.name,
                'login': slot.login.strip(),
                'email': (slot.email or '').strip() or False,
                'share': False,
            })

    def _selected_modules(self):
        self.ensure_one()
        active_modules = self.env['planb.tenant.module.access'].sudo().search([
            ('active', '=', True),
        ])
        if self.slot_number == 1 or self.access_all_modules:
            return active_modules
        return self.module_ids.filtered('active')

    def _apply_module_access(self):
        for slot in self:
            user = slot.user_id.sudo()
            selected_modules = slot._selected_modules()

            managed_group_ids = slot._managed_module_group_ids()
            protected_group_ids = slot._protected_group_ids()
            customer_admin_group_id = slot._customer_admin_group_id()

            existing_ids = set(user.group_ids.ids)
            remove_ids = managed_group_ids | protected_group_ids
            if customer_admin_group_id:
                remove_ids.add(customer_admin_group_id)
            final_ids = existing_ids - remove_ids

            xmlids = ['base.group_user']
            for module in selected_modules:
                xmlids.extend(module.get_user_group_xmlids())
                if slot.slot_number == 1:
                    xmlids.extend(module.get_manager_group_xmlids())

            final_ids.update(slot._xmlids_to_group_ids(xmlids))
            if slot.slot_number == 1 and customer_admin_group_id:
                final_ids.add(customer_admin_group_id)

            user.write({
                'group_ids': [(6, 0, sorted(final_ids))],
                'share': False,
                'active': True,
            })

        # Odoo caches loaded menus by user. Package/module changes must be
        # visible immediately without requiring a server restart.
        self.env.registry.clear_cache()

    @api.model
    def _definition_text(self, values):
        if not values:
            return False
        return '\n'.join(list(dict.fromkeys(filter(None, values))))

    @api.model
    def sync_from_saas(
        self,
        module_definitions,
        slots,
        internal_admin_login='admin',
        service_login='saas_system',
    ):
        """Synchronize paid modules/slots from the management database."""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only the SaaS service may synchronize slots.'))

        config = self.env['ir.config_parameter'].sudo()
        config.set_param('planb.internal_admin_login', internal_admin_login)
        config.set_param('planb.service_login', service_login)

        module_model = self.env['planb.tenant.module.access'].sudo().with_context(
            active_test=False
        )
        active_module_ids = []
        for definition in module_definitions or []:
            technical_name = (definition.get('technical_name') or '').strip()
            if not technical_name:
                continue
            module = module_model.search([
                ('technical_name', '=', technical_name),
            ], limit=1)
            values = {
                'name': definition.get('name') or technical_name,
                'technical_name': technical_name,
                'user_group_xmlids': self._definition_text(
                    definition.get('user_group_xmlids')
                ),
                'manager_group_xmlids': self._definition_text(
                    definition.get('manager_group_xmlids')
                ),
                'root_menu_xmlids': self._definition_text(
                    definition.get('root_menu_xmlids')
                ),
                'active': True,
            }
            if module:
                module.write(values)
            else:
                module = module_model.create(values)
            active_module_ids.append(module.id)

        stale_modules = module_model.search([
            ('id', 'not in', active_module_ids or [0]),
            ('active', '=', True),
        ])
        if stale_modules:
            stale_modules.write({'active': False})

        active_modules = module_model.browse(active_module_ids).filtered('active')
        active_slot_numbers = []
        synced_slots = self.sudo().browse()

        for payload in slots or []:
            slot_number = int(payload.get('slot_number') or 0)
            user_id = int(payload.get('user_id') or 0)
            if slot_number <= 0 or not user_id:
                continue

            user = self.env['res.users'].sudo().with_context(
                active_test=False
            ).browse(user_id).exists()
            if not user:
                continue

            slot = self.sudo().with_context(active_test=False).search([
                ('slot_number', '=', slot_number),
            ], limit=1)

            values = {
                'user_id': user.id,
                'name': payload.get('name') or user.name,
                'login': payload.get('login') or user.login,
                'email': payload.get('email') or user.email or False,
                'active': True,
            }
            if 'is_activated' in payload:
                values['is_activated'] = bool(payload.get('is_activated'))

            if not slot:
                values.update({
                    'slot_number': slot_number,
                    'access_all_modules': True,
                    'module_ids': [(6, 0, active_modules.ids)],
                })
                slot = self.sudo().create(values)
            else:
                if slot_number == 1 or slot.access_all_modules:
                    values['module_ids'] = [(6, 0, active_modules.ids)]
                    values['access_all_modules'] = True
                else:
                    selected_ids = slot.module_ids.filtered(
                        lambda module: module.id in active_modules.ids
                    ).ids
                    values['module_ids'] = [(6, 0, selected_ids)]
                slot.sudo().write(values)

            active_slot_numbers.append(slot_number)
            synced_slots |= slot

        stale_slots = self.sudo().with_context(active_test=False).search([
            ('slot_number', 'not in', active_slot_numbers or [0]),
            ('active', '=', True),
        ])
        if stale_slots:
            stale_slots.write({'active': False})

        # Apply package-manager access to slot 1 and the saved per-user module
        # selections to employee slots. No employee selection is overwritten.
        synced_slots._apply_module_access()
        return True

    def write(self, vals):
        if self.env.context.get('planb_internal_slot_write'):
            return super().write(vals)

        customer_admin_request = self._is_customer_admin_request()
        if customer_admin_request:
            forbidden = set(vals) - {
                'name',
                'login',
                'email',
                'access_all_modules',
                'module_ids',
            }
            if forbidden:
                raise AccessError(
                    _('You can only edit the licensed user profile and modules.')
                )
            if any(slot.slot_number <= 1 or not slot.active for slot in self):
                raise AccessError(
                    _('You can only manage active employee slots in your plan.')
                )
            if any(slot.is_activated for slot in self) and {'name', 'login', 'email'} & set(vals):
                raise AccessError(
                    _('This user account has been activated. Changes to username, login, or email must be made through Plan B SaaS Portal.')
                )

        result = super().write(vals)

        if 'module_ids' in vals or 'access_all_modules' in vals:
            for slot in self:
                invalid_modules = slot.module_ids.filtered(
                    lambda module: not module.active
                )
                if invalid_modules:
                    raise ValidationError(
                        _('Only modules in the current package can be assigned.')
                    )
                if slot.access_all_modules:
                    active_modules = self.env[
                        'planb.tenant.module.access'
                    ].sudo().search([('active', '=', True)])
                    slot.with_context(
                        planb_internal_slot_write=True
                    ).write({
                        'module_ids': [(6, 0, active_modules.ids)],
                    })
            self._apply_module_access()

        if {'name', 'login', 'email'} & set(vals):
            self._apply_profile_to_user()

        return result