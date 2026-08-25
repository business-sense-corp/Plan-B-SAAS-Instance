# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Rename OdooBot partner and user."""
    partner = env.ref("base.partner_root", raise_if_not_found=False)
    if partner:
        partner.write({"name": "PlanbBot"})

    user = env.ref("base.user_root", raise_if_not_found=False)
    if user:
        user.write({"name": "PlanbBot"})