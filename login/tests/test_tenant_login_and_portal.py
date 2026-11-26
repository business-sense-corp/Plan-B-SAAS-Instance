# -*- coding: utf-8 -*-
import os
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install', 'planb_login_portal')
class TestTenantLoginAndPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref('base.group_user')
        cls.test_password = 'PlanbTestLogin123!'
        cls.test_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Tenant Login Test User',
            'login': 'tenant.login.test@planb.test',
            'email': 'tenant.login.test@planb.test',
            'password': cls.test_password,
            'group_ids': [(6, 0, [internal_group.id])],
        })

    def test_01_custom_url_rewrite_does_not_depend_on_website(self):
        """custom_url_rewrite must not pull website into tenants."""
        custom_mod = self.env['ir.module.module'].search([
            ('name', '=', 'custom_url_rewrite'),
        ], limit=1)
        self.assertTrue(custom_mod)
        dep_names = set(custom_mod.dependencies_id.mapped('name'))
        self.assertNotIn('website', dep_names)

    def test_02_login_page_uses_standalone_planb_card_without_odoo_or_website_chrome(self):
        """GET /web/login?db=<db> serves clean Plan B Hub card without Odoo branding or dummy Website header."""
        resp = self.url_open(f'/web/login?db={self.env.cr.dbname}')
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        self.assertIn('planb-login-card', html)
        self.assertIn('/login/static/src/img/planb_logo.webp', html)
        self.assertIn('Powered by', html)
        self.assertIn('https://www.planb-hub.com/', html)
        self.assertIn('name="login"', html)
        self.assertIn('name="password"', html)

        css_match = re.search(r'href="(/web/assets/[^"]*web\.assets_frontend[^"]*\.css)"', html)
        js_match = re.search(r'src="(/web/assets/[^"]*web\.assets_frontend[^"]*\.js)"', html)
        self.assertIsNotNone(css_match, "Expected web.assets_frontend CSS bundle in login HTML")
        self.assertIsNotNone(js_match, "Expected web.assets_frontend JS bundle in login HTML")
        self.assertEqual(self.url_open('/login/static/src/img/planb_logo.webp').status_code, 200)
        for bundle_url in (css_match.group(1), js_match.group(1)):
            bundle_att = self.env['ir.attachment'].sudo().search([('url', '=', bundle_url)], limit=1)
            if bundle_att and bundle_att.store_fname and self.env['ir.attachment']._full_path(bundle_att.store_fname):
                if os.path.exists(self.env['ir.attachment']._full_path(bundle_att.store_fname)):
                    self.assertEqual(self.url_open(bundle_url).status_code, 200)

        self.assertNotIn('utm_source=db', html)
        self.assertNotIn('/web/database/manager', html)
        self.assertNotIn('+1 555-555-5556', html)
        self.assertNotIn('info@yourcompany.example.com', html)

        reset_mod = self.env['ir.module.module'].search([
            ('name', '=', 'planb_password_reset'),
            ('state', '=', 'installed'),
        ], limit=1)
        if reset_mod:
            self.assertIn('/web/forgot-password', html)

    def test_03_my_and_my_home_redirect_to_management_portal(self):
        """Visiting /my or /my/home on tenant redirects directly to management customer portal."""
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('planb.customer_portal_url', 'https://portal.planb-hub.test')
        params.set_param('planb.customer_portal_email', 'owner@planb-hub.test')

        self.authenticate(self.test_user.login, self.test_password)

        for route_path in ('/my', '/my/home', '/ar/my/home', '/en/my/home'):
            resp = self.url_open(route_path, allow_redirects=False)
            self.assertIn(resp.status_code, (302, 303), f"{route_path} did not redirect cleanly")
            location = resp.headers.get('Location', '')
            parsed = urlsplit(location)
            self.assertEqual(parsed.scheme, 'https')
            self.assertEqual(parsed.netloc, 'portal.planb-hub.test')
            self.assertEqual(parsed.path, '/web/login')
            qs = parse_qs(parsed.query)
            self.assertEqual(qs.get('login'), ['owner@planb-hub.test'])
            self.assertEqual(qs.get('redirect'), ['/my/home'])

        # Missing configuration fails closed with 503 instead of showing local portal
        params.set_param('planb.customer_portal_url', '')
        resp_missing = self.url_open('/my', allow_redirects=False)
        self.assertEqual(resp_missing.status_code, 503)

    def test_04_login_security_headers_and_cookie_flags(self):
        """Login returns no-store cache headers and hardened session_id cookie flags (SameSite=Lax + HTTPS Secure)."""
        resp = self.url_open(f'/web/login?db={self.env.cr.dbname}')
        self.assertEqual(resp.status_code, 200)
        cache_ctrl = resp.headers.get('Cache-Control', '').lower()
        self.assertIn('no-store', cache_ctrl)
        self.assertIn('private', cache_ctrl)
        self.assertEqual(resp.headers.get('Pragma'), 'no-cache')
        self.assertIn('cookie', resp.headers.get('Vary', '').lower())

        # Trigger cross-DB switch on plain HTTP vs HTTPS X-Forwarded-Proto
        self.url_open(f'/web/login?db={self.env.cr.dbname}')
        with patch('odoo.addons.login.controllers.web_login.http.db_filter', side_effect=lambda dbs, host=None: dbs):
            sw_http = self.url_open('/web/login?db=tenant_other_sw_http', allow_redirects=False)
            self.assertEqual(sw_http.status_code, 302)
            self.assertIn('db=tenant_other_sw_http', sw_http.headers.get('Location', ''))
            self.assertIn('_pb_sw=1', sw_http.headers.get('Location', ''))
            self.assertIn('no-store', sw_http.headers.get('Cache-Control', '').lower())
            set_cookie_http = sw_http.headers.get('Set-Cookie', '')
            self.assertIn('session_id=', set_cookie_http)
            self.assertIn('SameSite=Lax', set_cookie_http)
            self.assertNotIn('; Secure', set_cookie_http)

            # Re-pin to current DB cleanly, then test HTTPS X-Forwarded-Proto adds Secure
            self.opener.cookies.clear()
            self.url_open(f'/web/login?db={self.env.cr.dbname}')
            sw_https = self.url_open(
                '/web/login?db=tenant_other_sw_https',
                headers={'X-Forwarded-Proto': 'https'},
                allow_redirects=False,
            )
            self.assertEqual(sw_https.status_code, 302)
            set_cookie_https = sw_https.headers.get('Set-Cookie', '')
            self.assertIn('session_id=', set_cookie_https)
            self.assertIn('SameSite=Lax', set_cookie_https)
            self.assertIn('; Secure', set_cookie_https)

    def test_05_lang_prefix_login_redirect_preserves_db(self):
        """/ar/web/login and /en/web/login redirect cleanly to /web/login with ?db= intact."""
        self.url_open(f'/web/login?db={self.env.cr.dbname}')
        for prefix in ('/ar/web/login', '/en/web/login'):
            resp = self.url_open(f'{prefix}?db={self.env.cr.dbname}&redirect=%2F', allow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            loc = resp.headers.get('Location', '')
            self.assertIn('/web/login?', loc)
            self.assertNotIn('/odoo/', loc)
            self.assertIn(f'db={self.env.cr.dbname}', loc)
            self.assertIn('no-store', resp.headers.get('Cache-Control', '').lower())

    def test_06_db_switch_loop_breaker_and_hide_url_early(self):
        """Loop-breaker stops infinite 302 loops; hide_url_early normalizes /odoo? cleanly."""
        self.url_open(f'/web/login?db={self.env.cr.dbname}')
        with patch('odoo.addons.login.controllers.web_login.http.db_filter', side_effect=lambda dbs, host=None: dbs):
            resp = self.url_open('/web/login?db=tenant_loop_target&_pb_sw=1', allow_redirects=False)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('no-store', resp.headers.get('Cache-Control', '').lower())
            self.assertIn('/web/login?db=tenant_loop_target', resp.text)

        hide_view = self.env.ref('custom_url_rewrite.strip_odoo_prefix_early', raise_if_not_found=False)
        self.assertTrue(hide_view)
        self.assertIn('normalizeOdooPath', hide_view.arch_db or '')
        self.assertIn('/odoo?', hide_view.arch_db or '')

    def test_07_internal_login_redirect_never_lands_on_website_root(self):
        """Internal user POST /web/login with redirect=/ must land on /odoo, never Website /."""
        self.opener.cookies.clear()
        login_page = self.url_open(f'/web/login?db={self.env.cr.dbname}&redirect=%2F')
        self.assertEqual(login_page.status_code, 200)
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        self.assertIsNotNone(csrf_match)

        resp = self.url_open(
            f'/web/login?db={self.env.cr.dbname}&redirect=%2F',
            data={
                'csrf_token': csrf_match.group(1),
                'login': self.test_user.login,
                'password': self.test_password,
                'redirect': '/',
            },
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303))
        location = resp.headers.get('Location', '')
        parsed = urlsplit(location)
        self.assertTrue(
            parsed.path.startswith('/odoo'),
            f"Expected internal login redirect=/ to land on /odoo, got {location}",
        )
