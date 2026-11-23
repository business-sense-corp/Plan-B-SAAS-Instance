# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import models, fields, api, _


class ResUsers(models.Model):
    _inherit = "res.users"

    tour_enabled = fields.Boolean(
        compute="_compute_tour_enabled",
        store=True,
        readonly=False,
        default=False,
        string="Onboarding",
    )

    odoobot_state = fields.Selection(
        string="PlanbBot Status",
    )

    notification_type = fields.Selection(
        selection=[
            ('email', 'By Emails'),
            ('inbox', 'In Plan B'),
        ],
        string='Notification',
        required=True,
        default='email',
        compute='_compute_notification_type',
        inverse='_inverse_notification_type',
        store=True,
        help="Policy on how to handle Chatter notifications:\n"
             "- By Emails: notifications are sent to your email address\n"
             "- In Plan B: notifications appear in your Plan B Inbox",
    )

    def _init_odoobot(self):
        self.ensure_one()
        odoobot_id = self.env['ir.model.data']._xmlid_to_res_id("base.partner_root")
        channel = self.env['discuss.channel']._get_or_create_chat([odoobot_id, self.partner_id.id])
        message = Markup("%s<br/>%s<br/><b>%s</b> <span class=\"o_odoobot_command\">:)</span>") % (
            self.env._("Hello,"),
            self.env._("Plan B's chat helps employees collaborate efficiently. I'm here to help you discover its features."),
            self.env._("Try to send me an emoji")
        )
        channel.sudo().message_post(
            author_id=odoobot_id,
            body=message,
            message_type="comment",
            silent=True,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().odoobot_state = 'onboarding_emoji'
        return channel

    @api.depends("create_date")
    def _compute_tour_enabled(self):
        for user in self:
            user.tour_enabled = False

    @api.model
    def switch_tour_enabled(self, val):
        self.env.user.sudo().tour_enabled = False
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["tour_enabled"] = False
        return super().create(vals_list)
