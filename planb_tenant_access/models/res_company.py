# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import AccessError

SYNCED_COMPANY_FIELDS = {
    'name',
    'vat',
    'company_registry',
    'email',
    'phone',
    'mobile',
    'street',
    'street2',
    'city',
    'zip',
    'country_id',
    'state_id',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                "Creating companies directly in the tenant is not allowed. "
                "Please manage company profiles in the Plan B SaaS Portal."
            ))
        return super().create(vals_list)

    def unlink(self):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            raise AccessError(_(
                "Deleting companies directly in the tenant is not allowed. "
                "Please manage company profiles in the Plan B SaaS Portal."
            ))
        return super().unlink()

    def write(self, vals):
        if self.env.user._planb_lock_active() and not self.env.user._planb_is_internal_admin():
            if 'active' in vals and not vals['active']:
                raise AccessError(_(
                    "Archiving companies directly in the tenant is not allowed. "
                    "Please manage company profiles in the Plan B SaaS Portal."
                ))
            if 'partner_id' in vals:
                raise AccessError(_(
                    "Modifying company partner directly in the tenant is not allowed. "
                    "Please manage company profiles in the Plan B SaaS Portal."
                ))
            for field in SYNCED_COMPANY_FIELDS:
                if field in vals and field in self._fields:
                    for company in self:
                        current_val = company[field]
                        new_val = vals[field]
                        if hasattr(current_val, 'id'):
                            current_val = current_val.id or False
                            new_val = new_val or False
                        else:
                            current_val = (current_val or '').strip() if isinstance(current_val, str) else (current_val or False)
                            new_val = (new_val or '').strip() if isinstance(new_val, str) else (new_val or False)
                        if current_val != new_val:
                            raise AccessError(_(
                                "Modifying company details (%s) directly in the tenant is not allowed. "
                                "These fields are synchronized from your Plan B SaaS Portal. "
                                "Please update your company details in the portal."
                            ) % field)
        return super().write(vals)
