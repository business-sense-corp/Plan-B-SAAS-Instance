# -*- coding: utf-8 -*-

from html import escape
from urllib.parse import urlencode, urlsplit, urlunsplit

from odoo import http
from odoo.http import request


class PlanBCustomerPortalController(http.Controller):
    """Open the management portal login for the tenant owner."""

    @http.route(
        '/planb/customer_portal',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    def open_customer_portal(self, **kwargs):
        parameters = request.env['ir.config_parameter'].sudo()

        portal_url = (
            parameters.get_param('planb.customer_portal_url') or ''
        ).strip()
        portal_email = (
            parameters.get_param('planb.customer_portal_email')
            or request.env.company.email
            or ''
        ).strip().lower()

        if not portal_url:
            return self._configuration_error(
                "Customer Portal URL is not configured for this database. "
                "Please synchronize the company information from the SaaS "
                "management database."
            )

        if not portal_email:
            return self._configuration_error(
                "The database owner's email is not configured. Please add "
                "the customer email in the SaaS management database and "
                "synchronize the company information."
            )

        parsed_url = urlsplit(portal_url)
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            return self._configuration_error(
                "The configured Customer Portal URL is invalid."
            )

        login_path = '%s/web/login' % parsed_url.path.rstrip('/')
        login_query = urlencode({
            'login': portal_email,
            'redirect': '/my/home',
        })
        login_url = urlunsplit((
            parsed_url.scheme,
            parsed_url.netloc,
            login_path,
            login_query,
            '',
        ))

        return request.redirect(login_url, local=False)

    @staticmethod
    def _configuration_error(message):
        escaped_message = escape(message)
        body = """
            <!DOCTYPE html>
            <html>
                <head>
                    <meta charset="utf-8"/>
                    <meta name="viewport" content="width=device-width, initial-scale=1"/>
                    <title>Customer Portal</title>
                    <style>
                        body {
                            margin: 0;
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-family: Arial, sans-serif;
                            background: #f5f6f8;
                            color: #212529;
                        }
                        .message {
                            width: min(620px, calc(100%% - 32px));
                            padding: 28px;
                            border: 1px solid #dee2e6;
                            border-radius: 12px;
                            background: #fff;
                            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
                        }
                        h1 {
                            margin: 0 0 12px;
                            font-size: 24px;
                        }
                        p {
                            margin: 0;
                            line-height: 1.6;
                        }
                    </style>
                </head>
                <body>
                    <main class="message">
                        <h1>Customer Portal</h1>
                        <p>%s</p>
                    </main>
                </body>
            </html>
        """ % escaped_message
        return request.make_response(
            body,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
            status=503,
        )