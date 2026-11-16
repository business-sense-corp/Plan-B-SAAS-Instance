# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PlanBTenantUserPasswordWizard(models.TransientModel):
    _name = 'planb.tenant.user.password.wizard'
    _description = 'Change Licensed Tenant User Password'

    slot_id = fields.Many2one(
        'planb.tenant.user.slot',
        required=True,
        readonly=True,
    )
    new_password = fields.Char(required=True)
    confirm_password = fields.Char(required=True)

    def action_change_password(self):
        self.ensure_one()
        slot = self.slot_id.exists()
        if not slot or slot.slot_number <= 1 or not slot.active:
            raise AccessError(_('You cannot change this user password.'))
        if slot.is_activated:
            raise ValidationError(
                _('This user has an active account. Password changes must be performed through the invitation link or portal security.')
            )
        if not self.env.user.has_group(
            'planb_tenant_access.group_planb_customer_admin'
        ):
            raise AccessError(_('Only the customer administrator can do this.'))
        if self.new_password != self.confirm_password:
            raise ValidationError(_('The two passwords do not match.'))
        if len(self.new_password or '') < 8:
            raise ValidationError(
                _('The password must contain at least 8 characters.')
            )
        slot.user_id.sudo().write({'password': self.new_password})
        return {'type': 'ir.actions.act_window_close'}