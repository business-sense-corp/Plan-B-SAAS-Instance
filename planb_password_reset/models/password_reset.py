# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: States a reset request can be in.
#:   pending  - code sent, waiting for the user
#:   verified - the code was accepted; only the password step is left
#:   used     - the password was changed successfully
#:   expired  - TTL passed (set lazily, not by a cron)
#:   cancelled - superseded by a newer request, or refused by the rate limiter
STATE_SELECTION = [
    ('pending', 'Pending'),
    ('verified', 'Code verified'),
    ('used', 'Used'),
    ('expired', 'Expired'),
    ('cancelled', 'Cancelled'),
]


class PlanbPasswordReset(models.Model):
    """One password-reset attempt, identified by an opaque request token.

    The one-time code itself is never stored: only ``sha256(salt + code)`` is.
    A record is created for *every* request, whether or not the e-mail address
    matches a real user, so that the amount of database work performed by the
    controller does not depend on whether the account exists.
    """

    _name = 'planb.password.reset'
    _description = 'Password Reset One-Time Code'
    _order = 'create_date desc'
    _rec_name = 'login'

    user_id = fields.Many2one(
        'res.users', string='User', ondelete='cascade', index=True,
        help='Empty when the requested address does not match an active user.',
    )
    login = fields.Char(
        string='Requested address', required=True, index=True,
        help='The address exactly as typed by the user, lower-cased and stripped.',
    )
    email = fields.Char(
        string='Destination e-mail', index=True,
        help='The address the code was actually sent to (the partner e-mail).',
    )
    request_token = fields.Char(
        string='Request token', required=True, index=True,
        help='Opaque identifier returned to the browser. Never the code itself.',
    )
    salt = fields.Char(string='Salt', required=True)
    code_hash = fields.Char(string='Code hash', required=True)
    db_uuid = fields.Char(
        string='Database UUID', required=True, index=True,
        help='Binds the request to the database that issued it.',
    )
    state = fields.Selection(STATE_SELECTION, default='pending', required=True, index=True)
    expires_at = fields.Datetime(string='Expires at', required=True)
    attempts = fields.Integer(string='Failed attempts', default=0)
    max_attempts = fields.Integer(string='Maximum attempts', default=5)
    used_at = fields.Datetime(string='Used at')
    ip_address = fields.Char(string='Source IP')
    user_agent = fields.Char(string='User agent')
    mail_id = fields.Many2one('mail.mail', string='Notification e-mail', ondelete='set null')
    notify_mail_id = fields.Many2one(
        'mail.mail', string='Password-changed notice', ondelete='set null',
        help='Copy of the "your password was changed" e-mail, kept for audit.')

    # --- second step ---------------------------------------------------
    #: Random secret handed to the browser only after the code was accepted.
    #: Without it /web/forgot-password/reset refuses the request, so the
    #: password step cannot be reached by skipping the code.
    verify_token = fields.Char(
        string='Verification token', index=True, copy=False,
        help='Set when the code is accepted; cleared as soon as it is used.')
    session_hash = fields.Char(
        string='Browser binding', copy=False,
        help='SHA-256 of the session that verified the code. A token copied '
             'to another browser is refused.')
    verified_at = fields.Datetime(string='Verified at')
    verified_until = fields.Datetime(string='Verification valid until')
    password_attempts = fields.Integer(string='Password step attempts', default=0)


    # Odoo 19: the legacy `_sql_constraints` attribute is deprecated.
    _request_token_uniq = models.Constraint(
        'unique (request_token)',
        'The request token must be unique.',
    )

    # ------------------------------------------------------------------
    # Code generation and comparison
    # ------------------------------------------------------------------
    @api.model
    def _generate_code(self):
        """A 6-digit numeric code, uniformly distributed (000000-999999)."""
        return '%06d' % secrets.randbelow(1_000_000)

    @api.model
    def _generate_token(self):
        """256 bits of entropy, URL-safe."""
        return secrets.token_urlsafe(32)

    @api.model
    def _generate_salt(self):
        return secrets.token_hex(16)

    @staticmethod
    def _hash_code(salt, code):
        return hashlib.sha256(('%s:%s' % (salt, code)).encode('utf-8')).hexdigest()

    def _code_matches(self, code):
        """Constant-time comparison of a candidate code against the stored hash."""
        self.ensure_one()
        candidate = self._hash_code(self.salt, code or '')
        return hmac.compare_digest(candidate, self.code_hash or '')

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _cancel_pending_for_user(self, user):
        """A new request supersedes every older unfinished request of that user.

        ``verified`` is included on purpose: a code that was already accepted
        but whose password step was never completed must not survive a new
        request, otherwise two valid second-step tokens would exist at once.
        """
        if user:
            self.search([
                ('user_id', '=', user.id),
                ('state', 'in', ('pending', 'verified')),
            ]).write({'state': 'cancelled'})

    def _mark_used(self):
        self.ensure_one()
        self.write({
            'state': 'used',
            'used_at': fields.Datetime.now(),
            'verify_token': False,
            'session_hash': False,
        })

    # ------------------------------------------------------------------
    # Second step: from "code accepted" to "password may be set"
    # ------------------------------------------------------------------
    @staticmethod
    def _session_fingerprint(sid):
        """Non-reversible fingerprint of the browser session.

        The raw session id is itself a credential, so only its digest is
        stored: a database dump does not hand an attacker a usable session,
        while the controller can still tell two browsers apart.
        """
        return hashlib.sha256(
            ('planb-reset:%s' % (sid or '')).encode('utf-8')).hexdigest()

    def _mark_verified(self, verify_token, sid, window_minutes):
        """Promote a pending request to ``verified`` and mint the step-2 token."""
        self.ensure_one()
        now = fields.Datetime.now()
        self.write({
            'state': 'verified',
            'verify_token': verify_token,
            'session_hash': self._session_fingerprint(sid),
            'verified_at': now,
            'verified_until': now + timedelta(minutes=window_minutes),
        })

    def _verification_matches(self, verify_token, sid):
        """Constant-time check of everything the password step depends on.

        Three independent conditions must hold: the row is in ``verified``,
        the token matches, and the request comes from the same browser session
        that accepted the code. A token leaked through a screenshot, a proxy
        log or a shared URL is therefore useless in another browser.
        """
        self.ensure_one()
        if self.state != 'verified' or not self.verify_token:
            return False
        if not hmac.compare_digest(self.verify_token or '', verify_token or ''):
            return False
        expected = self._session_fingerprint(sid)
        return hmac.compare_digest(self.session_hash or '', expected)

    def _mark_expired(self):
        self.ensure_one()
        self.write({'state': 'expired'})

    # ------------------------------------------------------------------
    # Service used by the controller and by the back-office action
    # ------------------------------------------------------------------
    @api.model
    def _build_otp_body(self, code, ttl):
        """HTML body of the notification e-mail (English + Arabic)."""
        from markupsafe import Markup, escape

        safe_code = escape(code)
        return Markup("""
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;
            padding:28px;border:1px solid #e5e7eb;border-radius:10px;background:#ffffff">
  <h2 style="margin:0 0 6px;color:#111827;font-size:20px">Plan B &mdash; Password reset</h2>
  <p style="color:#374151;font-size:14px">Use the verification code below to set a new password.</p>
  <div style="text-align:center;margin:26px 0">
    <span style="display:inline-block;font-size:34px;font-weight:700;letter-spacing:10px;
                 padding:12px 18px;border-radius:8px;background:#f3f4f6;color:#111827">%s</span>
  </div>
  <p style="color:#6b7280;font-size:13px;margin:0">
    This code expires in %s minutes. If you did not request it, ignore this e-mail:
    your password will not change.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:22px 0"/>
  <div dir="rtl" style="color:#374151;font-size:14px;line-height:1.9">
    <p style="margin:0 0 6px">استخدم رمز التحقق أعلاه لتعيين كلمة مرور جديدة.</p>
    <p style="margin:0">تنتهي صلاحية الرمز خلال %s دقيقة. إذا لم تطلب هذا الرمز فتجاهل هذه الرسالة.</p>
  </div>
</div>
""") % (safe_code, ttl, ttl)

    @api.model
    def _build_changed_body(self, login, when, ip, user_agent):
        """HTML body of the "your password was changed" notice.

        The notice must never contain the new password, the code, or any
        token: it is a security *alert*, not a delivery channel. Every value
        is escaped because the address and the User-Agent are attacker
        controlled.
        """
        from markupsafe import Markup, escape

        return Markup("""
<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;
            padding:28px;border:1px solid #e5e7eb;border-radius:10px;background:#ffffff">
  <h2 style="margin:0 0 6px;color:#111827;font-size:20px">Plan B &mdash; Your password was changed</h2>
  <p style="color:#374151;font-size:14px">
    The password for <strong>%s</strong> was changed on <strong>%s</strong>.
  </p>
  <table style="border-collapse:collapse;font-size:13px;color:#374151;margin:14px 0">
    <tr><td style="padding:2px 12px 2px 0;color:#6b7280">Time (UTC)</td><td>%s</td></tr>
    <tr><td style="padding:2px 12px 2px 0;color:#6b7280">Source IP</td><td>%s</td></tr>
    <tr><td style="padding:2px 12px 2px 0;color:#6b7280">Device</td><td>%s</td></tr>
  </table>
  <p style="color:#374151;font-size:14px">
    If you made this change, no further action is needed and you can sign in
    with your new password.
  </p>
  <p style="color:#b91c1c;font-size:14px">
    If you did not change it, someone else may have access to your account.
    Reset the password again immediately and contact your administrator.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:22px 0"/>
  <div dir="rtl" style="color:#374151;font-size:14px;line-height:1.9">
    <p style="margin:0 0 6px">
      تم تغيير كلمة المرور الخاصة بالحساب <strong>%s</strong> بتاريخ <strong>%s</strong>.
    </p>
    <p style="margin:0 0 6px">
      إذا كنت أنت من قام بالتغيير فلا حاجة لأي إجراء، ويمكنك تسجيل الدخول بكلمة المرور الجديدة.
    </p>
    <p style="margin:0;color:#b91c1c">
      إذا لم تقم بهذا التغيير، فقد يكون حسابك مخترقًا: أعد تعيين كلمة المرور فورًا
      وتواصل مع مسؤول النظام.
    </p>
  </div>
</div>
""") % (
            escape(login), escape(when), escape(when), escape(ip or '-'),
            escape(user_agent or '-'), escape(login), escape(when),
        )

    @api.model
    def _changed_subject(self):
        return 'Your Plan B password was changed'

    @api.model
    def _open_request(self, user, login, email, ip=None, user_agent=None,
                      ttl=10, max_attempts=5):
        """Create a pending request. Returns ``(record, clear_code)``.

        The clear code is returned exactly once, to the caller that is about to
        put it in an e-mail; it is never persisted.
        """
        Record = self.sudo()
        if user:
            Record._cancel_pending_for_user(user)
        code = Record._generate_code()
        salt = Record._generate_salt()
        record = Record.create({
            'user_id': user.id if user else False,
            'login': login,
            'email': email or login,
            'request_token': Record._generate_token(),
            'salt': salt,
            'code_hash': Record._hash_code(salt, code),
            'db_uuid': self.env['ir.config_parameter'].sudo().get_param('database.uuid') or '',
            'state': 'pending',
            'expires_at': fields.Datetime.now() + timedelta(minutes=ttl),
            'max_attempts': max_attempts,
            'ip_address': ip,
            'user_agent': user_agent,
        })
        return record, code

    @api.model
    def _purge_old(self, older_than_days=30):
        """Delete old rows, so the table cannot grow without bound.

        Called opportunistically from the controller and by the scheduled
        action, because this installation runs with ``max_cron_threads = 0``
        and would otherwise never purge anything.
        """
        limit = fields.Datetime.now() - timedelta(days=older_than_days)
        stale = self.sudo().search([('create_date', '<', limit)])
        if stale:
            _logger.info('Password reset: purging %d record(s) older than %s days.',
                         len(stale), older_than_days)
            stale.unlink()
        return True

    @api.model
    def _ensure_purged(self, every=200):
        """Cheap probabilistic purge: runs on roughly one request in ``every``."""
        if secrets.randbelow(every) == 0:
            try:
                self._purge_old()
            except Exception:  # never let housekeeping break a reset request
                _logger.exception('Password reset: opportunistic purge failed.')
