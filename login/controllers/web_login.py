# -*- coding: utf-8 -*-
from html import escape
from urllib.parse import urlencode

import werkzeug.exceptions

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.http import request

from ..models.ir_http import apply_login_security_headers


class PlanBWebLoginController(Home):
    """Harden /web/login against stale-cookie DB mismatches, proxy caching, and redirect loops."""

    def _login_redirect(self, uid, redirect=None):
        """Prevent internal users on legacy website-enabled tenants from landing on Website '/'."""
        clean_redirect = (redirect or '').strip()
        is_root_redirect = (
            not clean_redirect
            or clean_redirect in ('/', '/?', '/web', '/odoo?', '/ar', '/ar/', '/en', '/en/')
            or clean_redirect.startswith('/?')
        )
        if is_root_redirect and uid:
            user = request.env['res.users'].sudo().browse(uid)
            if user.exists() and user._is_internal():
                return '/odoo'
        return super()._login_redirect(uid, redirect=redirect)

    @http.route(
        '/web/login',
        type='http',
        readonly=False,
        multilang=False,
        sitemap=False,
    )
    def web_login(self, redirect=None, **kw):
        requested_db = (request.params.get('db') or '').strip()
        is_switch_retry = request.params.get('_pb_sw') == '1'

        if requested_db and requested_db in http.db_filter([requested_db]):
            if requested_db != request.session.db:
                if is_switch_retry:
                    request.session.logout(keep_db=False)
                    return self._render_cookie_loop_breaker(requested_db)

                request.session = http.root.session_store.new()
                request.session.update(http.get_default_session(), db=requested_db)
                if request.db == requested_db:
                    request.session.context['lang'] = request.default_lang()

                query_params = {'db': requested_db, '_pb_sw': '1'}
                if redirect:
                    query_params['redirect'] = redirect
                if request.params.get('login'):
                    query_params['login'] = request.params.get('login')
                target_url = f"/web/login?{urlencode(query_params)}"
                resp = request.redirect(target_url, code=302)
                return apply_login_security_headers(resp)

        try:
            response = super().web_login(redirect=redirect, **kw)
        except werkzeug.exceptions.HTTPException as exc:
            if exc.code is not None:
                raise
            resp = exc.get_response()
            return apply_login_security_headers(resp)

        if hasattr(response, 'headers'):
            apply_login_security_headers(response)
        return response

    @staticmethod
    def _render_cookie_loop_breaker(db_name):
        safe_db = escape(db_name)
        retry_href = escape(f"/web/login?{urlencode({'db': db_name})}")
        body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Workspace Session Reset | Plan B Hub</title>
    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: Arial, sans-serif;
            background: #f3f6fb;
            color: #111827;
        }}
        .card {{
            width: min(440px, calc(100% - 32px));
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 28px 24px;
            box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
            text-align: center;
        }}
        h1 {{ margin: 0 0 10px; font-size: 20px; }}
        p {{ margin: 0 0 18px; color: #4b5563; line-height: 1.55; font-size: 14px; }}
        a.btn {{
            display: inline-block;
            background: #29B6F6;
            color: #ffffff;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <main class="card">
        <h1>Unable to Switch Workspace Automatically</h1>
        <p>Please ensure browser cookies are enabled for workspace <strong>{safe_db}</strong>, then retry opening the login page.</p>
        <p dir="rtl">تعذر التبديل التلقائي إلى قاعدة البيانات <strong>{safe_db}</strong> بسبب حظر الكوكيز أو تعارض الجلسة. تأكد من تفعيل الكوكيز ثم أعد المحاولة.</p>
        <a class="btn" href="{retry_href}">Open Login / فتح تسجيل الدخول</a>
    </main>
</body>
</html>"""
        resp = request.make_response(
            body,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
            status=200,
        )
        return apply_login_security_headers(resp)
