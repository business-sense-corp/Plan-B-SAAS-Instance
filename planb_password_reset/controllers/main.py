# -*- coding: utf-8 -*-
"""Self-service password recovery with a one-time code (OTP).

Design notes (see changes/10-forgot-password/ for the long version):

* The one-time code is 6 digits, generated with ``secrets``, and only its
  salted SHA-256 is stored.
* The flow is three pages: e-mail address -> code -> new password. The code is
  checked *before* the password is asked for, so a request can only reach the
  password page by presenting the single-use ``verify_token`` minted when the
  code is accepted. That token is bound to the browser session and expires on
  its own window.
* Every successful change sends the customer a "your password was changed"
  notice (time, source IP, device) with no secret in it.
* Every request creates a ``planb.password.reset`` row, even when the e-mail
  address matches nobody, so the database work does not depend on whether the
  account exists.
* A new request cancels all older pending requests of the same user.
* The row is bound to ``database.uuid``: a code minted in tenant A is rejected
  in tenant B and in the management database.
* E-mail delivery is scheduled *after* the transaction commits, on a daemon
  thread, so an SMTP round-trip never inflates the response time (which would
  leak whether the account exists).
"""

import logging
import re
import threading
from datetime import timedelta

from odoo import _, fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

RESET_MODEL = 'planb.password.reset'

P_TTL = 'planb.reset.otp_ttl_minutes'
P_MAX_ATTEMPTS = 'planb.reset.max_attempts'
P_RATE_EMAIL_HOUR = 'planb.reset.rate_email_per_hour'
P_RATE_IP_HOUR = 'planb.reset.rate_ip_per_hour'
P_RATE_DB_HOUR = 'planb.reset.rate_db_per_hour'
P_MIN_LENGTH = 'planb.reset.min_password_length'
P_VERIFY_WINDOW = 'planb.reset.verify_window_minutes'
P_PASSWORD_ATTEMPTS = 'planb.reset.max_password_attempts'
P_DEBUG = 'planb.reset.debug'

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MAX_EMAIL_LEN = 254


def _msg_sent():
    """Generic 'we sent you a code' text. A function, not a constant: Odoo
    translates at call time and there is no language context at import."""
    return _(
        'If an account exists for that address, a 6-digit verification code has '
        'been sent to it. The code expires in a few minutes.'
    )


def _msg_bad_code():
    return _(
        'That code is invalid or has expired. Please check the code, or request a '
        'new one.'
    )


def _ilike_literal(value):
    """Escape LIKE metacharacters so an address is matched literally.

    Odoo's ``=ilike`` operator forwards the value to PostgreSQL ``ILIKE``
    untouched, so an address such as ``john_smith@example.com`` would also
    match ``johnXsmith@example.com`` ('_' is "any one character") and a '%'
    would match anything.  Escaping the three metacharacters keeps the lookup
    case-insensitive without turning the address into a pattern.
    """
    return (
        value.replace('\\', '\\\\')
        .replace('%', '\\%')
        .replace('_', '\\_')
    )


def _int_param(env, key, default):
    value = env['ir.config_parameter'].sudo().get_param(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_param(env, key, default=False):
    value = env['ir.config_parameter'].sudo().get_param(key, None)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _spawn_mail_send(db_name, mail_id):
    """Send one ``mail.mail`` on a daemon thread with its own cursor.

    Called from ``cr.postcommit``, i.e. after the request transaction is
    committed, so the thread is guaranteed to see the row.
    """

    def _run():
        import odoo
        from odoo.modules.registry import Registry

        registry = Registry(db_name)
        try:
            with registry.cursor() as cr:
                env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                mail = env['mail.mail'].browse(mail_id)
                if mail.exists():
                    mail.send(raise_exception=False)
        except Exception:
            # `mail.mail.send()` hands the message to the SMTP server *before*
            # it records the new state, so an error here never means "not
            # delivered" and must not be retried (that would duplicate the
            # e-mail). A typical cause is a SerializationFailure when the row
            # was deleted while the SMTP round-trip was in flight, which is
            # what happens during a maintenance purge; that is expected, so it
            # is reported at debug level.
            try:
                with registry.cursor() as cr:
                    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                    if not env['mail.mail'].browse(mail_id).exists():
                        _logger.debug(
                            'Password reset: mail %s was purged after delivery',
                            mail_id)
                        return
            except Exception:
                pass
            _logger.exception(
                'Password reset: asynchronous delivery failed for mail %s', mail_id)

    threading.Thread(
        target=_run, name='planb-otp-mail-%s' % mail_id, daemon=True).start()


class PlanbPasswordResetController(http.Controller):
    """HTTP endpoints for the OTP password reset."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _db_uuid(self):
        return request.env['ir.config_parameter'].sudo().get_param('database.uuid') or ''

    def _client_ip(self):
        forwarded = request.httprequest.headers.get('X-Forwarded-For')
        if forwarded:
            # First hop is the real client when a trusted reverse proxy is used.
            return forwarded.split(',')[0].strip()[:64]
        return (request.httprequest.remote_addr or '')[:64]

    def _session_sid(self):
        """The browser session id, used to bind the second step to its browser.

        Public pages still have a session (it carries the CSRF token), so this
        is always available; the defensive ``getattr`` keeps the flow working
        if a future Odoo version renames the attribute.
        """
        return getattr(request.session, 'sid', '') or ''

    def _user_agent(self):
        return (request.httprequest.headers.get('User-Agent') or '')[:250]

    def _rate_limited(self, login, ip):
        """Return a reason string when the request must be refused, else None.

        Counting is done on the reset table itself, so it survives restarts and
        works with ``workers = 0``.
        """
        env = request.env
        Record = env[RESET_MODEL].sudo()
        since = fields.Datetime.now() - timedelta(hours=1)

        if ip:
            limit_ip = _int_param(env, P_RATE_IP_HOUR, 10)
            if Record.search_count([('ip_address', '=', ip), ('create_date', '>=', since)]) >= limit_ip:
                return 'ip'
        if login:
            limit_email = _int_param(env, P_RATE_EMAIL_HOUR, 3)
            if Record.search_count([('login', '=', login), ('create_date', '>=', since)]) >= limit_email:
                return 'email'
        limit_db = _int_param(env, P_RATE_DB_HOUR, 100)
        if Record.search_count([('create_date', '>=', since)]) >= limit_db:
            return 'database'
        return None

    def _find_user(self, login):
        """Resolve an address to an active internal/portal user, or empty."""
        needle = _ilike_literal(login)
        return request.env['res.users'].sudo().with_context(active_test=False).search([
            '|',
            ('login', '=ilike', needle),
            ('partner_id.email', '=ilike', needle),
        ], limit=1)

    def _from_address(self):
        company = request.env.company.sudo()
        return company.email_formatted or company.email or 'no-reply@planb-hub.com'

    def _render(self, template, values=None):
        """Render one of our pages with the context the layout needs.

        Every page of the flow can contain a token or an e-mail address, so it
        is explicitly non-cacheable and no-referrer: a shared proxy must not
        keep it, and an outbound link must not leak the URL.
        """
        values = dict(values or {})
        values.setdefault('db', request.db)
        response = request.render(template, values)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def _send_code(self, record, code, ttl):
        """Create the notification e-mail and schedule its delivery."""
        # The code is deliberately kept out of the subject: subjects appear on
        # lock screens, in notification previews and in mail-gateway logs.
        subject = _('Your Plan B verification code')
        mail = request.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': record._build_otp_body(code, ttl),
            'email_to': record.email,
            'email_from': self._from_address(),
            'auto_delete': False,
        })
        record.write({'mail_id': mail.id})

        db_name = request.env.cr.dbname
        request.env.cr.postcommit.add(lambda: _spawn_mail_send(db_name, mail.id))

        if _bool_param(request.env, P_DEBUG, False):
            _logger.warning(
                'Password reset DEBUG: code %s for %s (db=%s)',
                code, record.email, db_name)

    def _send_changed_notice(self, record, user):
        """Queue the “your password was changed” alert, after the commit.

        Deliberately contains no code and no password: e-mail is a
        notification channel, never a secret channel. It goes to the same
        mailbox that received the code, and it is the customer's only signal
        if somebody else completed a reset.
        """
        when = fields.Datetime.now().strftime('%Y-%m-%d %H:%M')
        mail = request.env['mail.mail'].sudo().create({
            'subject': record._changed_subject(),
            'body_html': record._build_changed_body(
                record.login, when, self._client_ip(), self._user_agent()),
            'email_to': record.email or record.login,
            'email_from': self._from_address(),
            'auto_delete': False,
        })
        record.write({'notify_mail_id': mail.id})

        db_name = request.env.cr.dbname
        request.env.cr.postcommit.add(lambda: _spawn_mail_send(db_name, mail.id))

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route('/web/forgot-password', type='http', auth='public',
                methods=['GET'], csrf=False, sitemap=False)
    def forgot_password_form(self, **kw):
        return self._render('planb_password_reset.forgot_password_form', {
            'error': kw.get('error'),
            'email': kw.get('email') or '',
        })

    @http.route('/web/forgot-password', type='http', auth='public',
                methods=['POST'], csrf=True, sitemap=False)
    def forgot_password_send(self, email=None, **kw):
        env = request.env
        login = (email or '').strip().lower()[:MAX_EMAIL_LEN]

        if not login or not EMAIL_RE.match(login):
            return self._render('planb_password_reset.forgot_password_form', {
                'error': _('Please enter a valid e-mail address.'),
                'email': login,
            })

        ip = self._client_ip()
        user_agent = (request.httprequest.headers.get('User-Agent') or '')[:250]

        # Rate limiting is evaluated before any row is written, so an attacker
        # cannot use it to fill the table. The response is identical either way.
        limited = self._rate_limited(login, ip)
        Record = env[RESET_MODEL].sudo()
        Record._ensure_purged()

        if limited:
            _logger.warning(
                'Password reset: rate limit hit (%s) for %s from %s', limited, login, ip)
            return self._render('planb_password_reset.forgot_password_verify', {
                'message': _msg_sent(),
                'error': None,
                'email': login,
                'request_token': '',
                'ttl': _int_param(env, P_TTL, 10),
                'max_attempts': _int_param(env, P_MAX_ATTEMPTS, 5),
                'blocked': True,
            })

        user = self._find_user(login)
        if user and not user.active:
            # Archived accounts are treated exactly like unknown addresses.
            user = env['res.users']

        ttl = _int_param(env, P_TTL, 10)
        max_attempts = _int_param(env, P_MAX_ATTEMPTS, 5)

        record, code = Record._open_request(
            user,
            login,
            (user.partner_id.email or login) if user else login,
            ip=ip,
            user_agent=user_agent,
            ttl=ttl,
            max_attempts=max_attempts,
        )
        token = record.request_token

        if user:
            self._send_code(record, code, ttl)

        return self._render('planb_password_reset.forgot_password_verify', {
            'message': _msg_sent(),
            'error': None,
            'email': login,
            'request_token': token,
            'ttl': ttl,
            'max_attempts': max_attempts,
            'blocked': False,
        })

    @http.route('/web/forgot-password/verify', type='http', auth='public',
                methods=['POST'], csrf=True, sitemap=False)
    def forgot_password_verify(self, request_token=None, code=None, **kw):
        """Step 2 — check the code only.

        The password is deliberately not accepted here any more: a request
        reaches the password step only by presenting the single-use
        ``verify_token`` minted below, bound to this browser session.
        """
        env = request.env
        ttl = _int_param(env, P_TTL, 10)
        window = _int_param(env, P_VERIFY_WINDOW, 10)
        Record = env[RESET_MODEL].sudo()

        record = Record.search([
            ('request_token', '=', request_token or ''),
            ('db_uuid', '=', self._db_uuid()),
        ], limit=1)

        def rerender(error, state='pending', show_form=True, email=None):
            return self._render('planb_password_reset.forgot_password_verify', {
                'message': None,
                'error': error,
                'email': email or (record.login if record else ''),
                'request_token': request_token if show_form else '',
                'ttl': ttl,
                'max_attempts': record.max_attempts if record else 5,
                'blocked': not show_form,
                'state': state,
            })

        if not record:
            return rerender(_msg_bad_code(), show_form=False)

        if record.state != 'pending':
            return rerender(_msg_bad_code(), state=record.state, show_form=False)

        if record.expires_at < fields.Datetime.now():
            record._mark_expired()
            return rerender(_msg_bad_code(), state='expired', show_form=False)

        if record.attempts >= record.max_attempts:
            record.write({'state': 'cancelled'})
            return rerender(_msg_bad_code(), state='cancelled', show_form=False)

        if not record._code_matches(code):
            record.write({'attempts': record.attempts + 1})
            remaining = record.max_attempts - record.attempts
            if remaining <= 0:
                record.write({'state': 'cancelled'})
                return rerender(_msg_bad_code(), state='cancelled', show_form=False)
            return rerender(
                _('That code is not correct. %s attempt(s) left.') % remaining)

        # Correct code. Mint the step-2 secret; the code itself is now spent
        # and can never be replayed, even while it is still in the mailbox.
        verify_token = Record._generate_token()
        record._mark_verified(verify_token, self._session_sid(), window)

        _logger.info('Password reset: code verified for login=%s from %s',
                     record.login, self._client_ip())

        return self._render('planb_password_reset.forgot_password_new_password', {
            'request_token': record.request_token,
            'verify_token': verify_token,
            'email': record.email or record.login,
            'ttl': window,
            'error': None,
            'max_attempts': _int_param(env, P_PASSWORD_ATTEMPTS, 5),
            'min_length': _int_param(env, P_MIN_LENGTH, 8),
        })

    @http.route('/web/forgot-password/reset', type='http', auth='public',
                methods=['POST'], csrf=True, sitemap=False)
    def forgot_password_reset(self, request_token=None, verify_token=None,
                              new_password=None, confirm_password=None, **kw):
        """Step 3 — set the password, only for a verified request.

        Refuses everything that did not come through step 2: unknown request,
        wrong token, another browser session, expired window, already used
        request. The refusals are intentionally indistinguishable.
        """
        env = request.env
        Record = env[RESET_MODEL].sudo()
        max_password_attempts = _int_param(env, P_PASSWORD_ATTEMPTS, 5)

        record = Record.search([
            ('request_token', '=', request_token or ''),
            ('db_uuid', '=', self._db_uuid()),
        ], limit=1)

        def abandon():
            """Generic dead end: no hint about which condition failed."""
            return self._render('planb_password_reset.forgot_password_verify', {
                'message': None,
                'error': _msg_bad_code(),
                'email': record.login if record else '',
                'request_token': '',
                'ttl': _int_param(env, P_TTL, 10),
                'max_attempts': record.max_attempts if record else 5,
                'blocked': True,
            })

        def ask_again(error, remaining_minutes):
            return self._render('planb_password_reset.forgot_password_new_password', {
                'request_token': record.request_token,
                'verify_token': verify_token,
                'email': record.email or record.login,
                'ttl': remaining_minutes,
                'error': error,
                'max_attempts': max_password_attempts,
                'min_length': _int_param(env, P_MIN_LENGTH, 8),
            })

        if not record or not record._verification_matches(
                verify_token, self._session_sid()):
            return abandon()

        now = fields.Datetime.now()
        if not record.verified_until or record.verified_until < now:
            record._mark_expired()
            return abandon()

        if record.password_attempts >= max_password_attempts:
            record.write({'state': 'cancelled', 'verify_token': False})
            return abandon()

        user = record.user_id
        if not user or not user.active:
            record.write({'state': 'cancelled', 'verify_token': False})
            return abandon()

        remaining_minutes = max(
            1, int((record.verified_until - now).total_seconds() // 60))

        min_length = _int_param(env, P_MIN_LENGTH, 8)
        policy_error = None
        if not new_password or len(new_password) < min_length:
            policy_error = _(
                'The password must be at least %s characters long.') % min_length
        elif new_password != confirm_password:
            policy_error = _('The two passwords do not match.')

        if policy_error:
            record.write({'password_attempts': record.password_attempts + 1})
            if record.password_attempts >= max_password_attempts:
                record.write({'state': 'cancelled', 'verify_token': False})
                return abandon()
            return ask_again(policy_error, remaining_minutes)

        try:
            user.sudo().write({'password': new_password})
        except Exception:
            _logger.exception(
                'Password reset: could not set the password for user %s', user.id)
            return ask_again(
                _('The password could not be changed. Please contact your '
                  'administrator.'),
                remaining_minutes)

        record._mark_used()
        Record._cancel_pending_for_user(user)

        # Notify the customer. A failure to queue the notice must never undo
        # a password that was already changed.
        try:
            self._send_changed_notice(record, user)
        except Exception:
            _logger.exception(
                'Password reset: could not queue the change notice for user %s',
                user.id)

        _logger.info(
            'Password reset completed for user_id=%s login=%s from %s',
            user.id, user.login, self._client_ip())

        return self._render('planb_password_reset.forgot_password_done', {
            'login': user.login,
            'notified': bool(record.notify_mail_id),
        })
