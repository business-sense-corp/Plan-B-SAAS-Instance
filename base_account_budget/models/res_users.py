from odoo import models, fields

class ResUsers(models.Model):
    _inherit = "res.users"

    notification_type = fields.Selection(
        selection_add=[('inbox', 'By Notifications')],
        ondelete={'inbox': 'set default'}
    )