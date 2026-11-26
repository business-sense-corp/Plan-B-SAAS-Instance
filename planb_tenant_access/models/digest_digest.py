# -*- coding: utf-8 -*-
import re

from odoo import api, models

PLANB_DIGEST_NAME_EN = "Your Plan B Periodic Digest"
PLANB_DIGEST_NAME_AR = "موجزك الدوري من Plan B"

ODOO_DEFAULT_NAMES_EN = {"Your Odoo Periodic Digest"}
ODOO_DEFAULT_NAMES_AR = {"موجزك الدوري من أودو", "موجزك الدوري من أودوو"}


def _replace_odoo_brand(text):
    """Replace Odoo/أودو brand occurrences in visible text without touching URLs."""
    if not text:
        return text
    result = str(text)
    result = result.replace("@OdooBot", "@PlanbBot")
    result = result.replace("أودوو", "Plan B").replace("أودو", "Plan B")
    # Replace standalone "Odoo" word outside URLs (e.g. download.odoocdn.com won't match \bOdoo\b anyway)
    result = re.sub(r'(?<!https://www\.)\bOdoo\b(?![\w.-]*\.(?:com|org|net))', 'Plan B', result, flags=re.IGNORECASE)
    return result


class DigestDigest(models.Model):
    _inherit = 'digest.digest'

    @api.model
    def _planb_rebrand_default_digest(self):
        """Rebrand the default digest record and default tips from Odoo to Plan B.

        Safe to run repeatedly on install, upgrade, and language activation:
        only installed languages are passed to update_field_translations, and
        customer-customized digest names are preserved.
        """
        installed_langs = {code for code, _ in self.env['res.lang'].sudo().get_installed()} | {'en_US'}

        digest = self.env.ref('digest.digest_digest_default', raise_if_not_found=False)
        if digest:
            trans_list, _ctx = digest.sudo().get_field_translations('name', langs=installed_langs)
            current_map = {item['lang']: (item.get('value') or '') for item in trans_list}
            if trans_list and not current_map.get('en_US'):
                current_map['en_US'] = trans_list[0].get('source') or ''
            if not current_map.get('en_US'):
                current_map['en_US'] = digest.sudo().with_context(lang='en_US').name or ''

            updates = {}
            cur_en = current_map.get('en_US') or ''
            if not cur_en or cur_en in ODOO_DEFAULT_NAMES_EN:
                updates['en_US'] = PLANB_DIGEST_NAME_EN
            elif 'odoo' in cur_en.lower() or 'أودو' in cur_en:
                updates['en_US'] = _replace_odoo_brand(cur_en)

            for lang in installed_langs - {'en_US'}:
                cur = current_map.get(lang) or ''
                if lang.startswith('ar'):
                    if (
                        not cur
                        or cur in ODOO_DEFAULT_NAMES_AR
                        or cur in ODOO_DEFAULT_NAMES_EN
                        or cur == PLANB_DIGEST_NAME_EN
                    ):
                        updates[lang] = PLANB_DIGEST_NAME_AR
                    elif 'أودو' in cur or 'odoo' in cur.lower():
                        updates[lang] = _replace_odoo_brand(cur)
                elif 'odoo' in cur.lower() or 'أودو' in cur:
                    updates[lang] = _replace_odoo_brand(cur)

            if updates:
                digest.sudo().update_field_translations('name', updates)

        self._planb_rebrand_default_tips(installed_langs)
        return True

    @api.model
    def _planb_rebrand_default_tips(self, installed_langs):
        """Rebrand default digest.tip records referencing Odoo or @OdooBot."""
        ordered_langs = sorted(installed_langs, key=lambda code: (code != 'en_US', code))

        tip_2 = self.env.ref('digest.digest_tip_digest_2', raise_if_not_found=False)
        if tip_2:
            trans_list, _ctx = tip_2.sudo().get_field_translations('name', langs=installed_langs)
            current_map = {item['lang']: (item.get('value') or '') for item in trans_list}
            if trans_list and not current_map.get('en_US'):
                current_map['en_US'] = trans_list[0].get('source') or ''
            name_updates = {}
            for lang in installed_langs:
                cur = current_map.get(lang) or ''
                if 'odoo' in cur.lower() or 'أودو' in cur:
                    new_val = _replace_odoo_brand(cur)
                    if new_val != cur:
                        name_updates[lang] = new_val
            if name_updates:
                tip_2.sudo().update_field_translations('name', name_updates)

            for lang in ordered_langs:
                val = tip_2.sudo().with_context(lang=lang).tip_description
                val_str = str(val or '')
                if 'odoo' in val_str.lower() or 'أودو' in val_str:
                    updated = _replace_odoo_brand(val_str)
                    if updated != val_str:
                        tip_2.sudo().with_context(lang=lang).write({'tip_description': updated})

        tip_3 = self.env.ref('digest.digest_tip_digest_3', raise_if_not_found=False)
        if tip_3:
            for lang in ordered_langs:
                val = tip_3.sudo().with_context(lang=lang).tip_description
                val_str = str(val or '')
                if '@OdooBot' in val_str:
                    tip_3.sudo().with_context(lang=lang).write({
                        'tip_description': val_str.replace('@OdooBot', '@PlanbBot'),
                    })


class ResLang(models.Model):
    _inherit = 'res.lang'

    @api.model
    def _activate_lang(self, code):
        res = super()._activate_lang(code)
        if 'digest.digest' in self.env:
            self.env['digest.digest'].sudo()._planb_rebrand_default_digest()
        return res
