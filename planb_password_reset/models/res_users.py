# -*- coding: utf-8 -*-
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _planb_reset_ttl(self):
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(
                'planb.reset.otp_ttl_minutes', 10))
        except (TypeError, ValueError):
            return 10

    def action_planb_send_reset_code(self):
        """Back-office: e-mail a verification code to this user (Flow C).

        The code is sent synchronously because an operator clicked the button
        and expects an immediate result. It is never displayed in the UI and
        never written to the log.
        """
        self.ensure_one()
        if not self.partner_id.email:
            raise UserError(_(
                'This user has no e-mail address, so a verification code '
                'cannot be sent. Set the address on the contact first.'))
        if not self.active:
            raise UserError(_('The user is archived; reactivate it first.'))

        ttl = self._planb_reset_ttl()
        record, code = self.env['planb.password.reset']._open_request(
            self, self.login, self.partner_id.email, ttl=ttl)

        mail = self.env['mail.mail'].sudo().create({
            # Never in the subject: it would leak through lock-screen previews
            # and mail-gateway logs.
            'subject': _('Your Plan B verification code'),
            'body_html': record._build_otp_body(code, ttl),
            'email_to': self.partner_id.email,
            'email_from': self.env.company.email_formatted or self.env.company.email,
            'auto_delete': False,
        })
        record.write({'mail_id': mail.id})

        try:
            mail.send(raise_exception=True)
        except Exception as exc:
            _logger.exception('Password reset: back-office send failed for user %s', self.id)
            raise UserError(_(
                'The verification e-mail could not be sent: %s') % exc) from exc

        _logger.info(
            'Password reset: back-office code sent for user_id=%s login=%s',
            self.id, self.login)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Verification code sent'),
                'message': _('A 6-digit code was sent to %s. It expires in %s minutes.')
                           % (self.partner_id.email, ttl),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
