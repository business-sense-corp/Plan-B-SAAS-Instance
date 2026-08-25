from odoo import models, api
from odoo.exceptions import AccessError


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.user.has_group(
                "planb_tenant_access.group_planb_customer_admin_no_user_crud"
            )
            and not self.env.context.get("skip_user_create_restriction")
        ):
            raise AccessError(
                "You are not allowed to create users."
            )

        return super().create(vals_list)

    def unlink(self):
        if (
            self.env.user.has_group(
                "planb_tenant_access.group_planb_customer_admin_no_user_crud"
            )
            and not self.env.context.get("skip_user_create_restriction")
        ):
            raise AccessError(
                "You are not allowed to delete users."
            )

        return super().unlink()