# -*- coding: utf-8 -*-
import re

from odoo import models
from odoo.http import request

LOGIN_HARDENED_PATHS = ('/web/login', '/ar/web/login', '/en/web/login')
_SAMESITE_RE = re.compile(r';\s*samesite=', re.IGNORECASE)
_SECURE_RE = re.compile(r';\s*secure\b', re.IGNORECASE)


def _is_https_request():
    httpreq = getattr(request, 'httprequest', None)
    if not httpreq:
        return False
    if getattr(httpreq, 'is_secure', False):
        return True
    proto = (httpreq.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
    return proto == 'https'


def apply_login_security_headers(response):
    """Apply strict no-store cache headers and Vary: Cookie on login responses."""
    if not response or not getattr(response, 'headers', None):
        return response
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    vary_headers = response.headers.getlist('Vary') if hasattr(response.headers, 'getlist') else [
        response.headers.get('Vary') or ''
    ]
    vary_parts = [
        part.strip()
        for header_val in vary_headers
        for part in header_val.split(',')
        if part.strip()
    ]
    if not any(part.lower() == 'cookie' for part in vary_parts):
        vary_parts.append('Cookie')
    response.headers['Vary'] = ', '.join(vary_parts)
    return response


def harden_session_cookie_headers(response):
    """Ensure session_id Set-Cookie carries SameSite=Lax and Secure when on HTTPS."""
    if not response or not getattr(response, 'headers', None):
        return response
    cookies = response.headers.getlist('Set-Cookie') if hasattr(response.headers, 'getlist') else []
    if not cookies:
        return response

    is_https = _is_https_request()
    updated = []
    changed = False
    for cookie_val in cookies:
        if cookie_val.lstrip().startswith('session_id='):
            if not _SAMESITE_RE.search(cookie_val):
                cookie_val = f'{cookie_val}; SameSite=Lax'
                changed = True
            if is_https and not _SECURE_RE.search(cookie_val):
                cookie_val = f'{cookie_val}; Secure'
                changed = True
        updated.append(cookie_val)

    if changed:
        response.headers.setlist('Set-Cookie', updated)
    return response


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        harden_session_cookie_headers(response)
        httpreq = getattr(request, 'httprequest', None)
        if httpreq and httpreq.path in LOGIN_HARDENED_PATHS:
            apply_login_security_headers(response)
