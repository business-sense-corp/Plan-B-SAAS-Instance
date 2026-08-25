from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

# Paths that must NEVER be rewritten - system/technical routes.
# Add here any prefix used by installed addons that already serves
# its own bare routes (e.g. 'shop', 'blog', 'payment' if website is installed).
RESERVED_PREFIXES = {
    'web', 'website', 'static', 'odoo', 'longpolling',
    'mail', 'discuss', 'report', 'my', 'shop', 'payment',
}


class CustomUrlRewrite(http.Controller):

    @http.route(
        '/<string:segment>',
        type='http', auth='user', website=False, sitemap=False,
    )
    def bare_root_redirect(self, segment, **kw):
        """
        Handles the top-level bare path only, e.g. /sales, /inventory.
        Odoo's router prioritizes more specific literal routes automatically,
        so this only fires when nothing else claims the path first.
        """
        if segment in RESERVED_PREFIXES:
            raise NotFound()
        return request.redirect(f'/odoo/{segment}', code=302)

    @http.route(
        '/<string:segment>/<path:rest>',
        type='http', auth='user', website=False, sitemap=False,
    )
    def bare_subpath_redirect(self, segment, rest, **kw):
        """Handles deeper paths, e.g. /sales/123, /inventory/new."""
        if segment in RESERVED_PREFIXES:
            raise NotFound()
        return request.redirect(f'/odoo/{segment}/{rest}', code=302)
