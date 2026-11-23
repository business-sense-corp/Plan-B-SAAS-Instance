# -*- coding: utf-8 -*-
import re
from markupsafe import Markup
from odoo import models, _


class MailBot(models.AbstractModel):
    _inherit = 'mail.bot'

    @staticmethod
    def _get_style_dict():
        """Ensure all required style keys exist without external Odoo hyperlinks."""
        return {
            "new_line": Markup("<br>"),
            "bold_start": Markup("<b>"),
            "bold_end": Markup("</b>"),
            "command_start": Markup("<span class='o_odoobot_command'>"),
            "command_end": Markup("</span>"),
            "document_link_start": Markup(""),
            "document_link_end": Markup(""),
            "slides_link_start": Markup(""),
            "slides_link_end": Markup(""),
            "paperclip_icon": Markup("<i class='fa fa-paperclip' aria-hidden='true'/>"),
        }

    def _get_answer(self, channel, body, values, command=False):
        odoobot = self.env.ref("base.partner_root")

        # Intercept when Bot is in direct chat with user and help is requested
        if channel.channel_type == "chat" and odoobot.id in channel.channel_member_ids.partner_id.ids:
            if self._is_help_requested(body):
                return self.env._(
                    "Sorry, I'm just a chatbot and I didn't understand that message. "
                    "If you need help, please contact the Plan B support team."
                )

        # Call super to handle onboarding steps, canned responses, and commands
        answer = super()._get_answer(channel, body, values, command=command)

        if not answer:
            return answer

        if isinstance(answer, list):
            return [self._sanitize_bot_answer(ans) for ans in answer]
        return self._sanitize_bot_answer(answer)

    def _sanitize_bot_answer(self, text):
        """Sanitize Bot response to eliminate remaining Odoo product references while preserving Markup."""
        if not text:
            return text

        import html
        is_markup = isinstance(text, Markup)
        s = str(text)
        s_clean = html.unescape(s).lower()

        # Replace random fallback responses if any leaked through super
        fallback_keywords = [
            "unfortunately, i'm just a bot",
            "unfortunately",
            "للأسف، أنا مجرد",
            "للأسف",
            "i'm not smart enough",
            "smart enough",
            "لست ذكياً",
            "لست ذكي",
            "i'm afraid i don't understand",
            "afraid",
            "أخشى أنني لا أفهم",
            "أخشى",
            "sorry i'm sleepy",
            "sleepy",
            "عذراً، أشعر بالنعاس",
            "نعاس",
            "hmmm...",
            "hmmm",
            "هممم...",
            "هممم",
            "unawareness",
            "documentation",
            "slides",
            "odoo.com",
        ]
        if any(k in s_clean for k in fallback_keywords):
            return self.env._(
                "Sorry, I'm just a chatbot and I didn't understand that message. "
                "If you need help, please contact the Plan B support team."
            )

        # 1. Replace @OdooBot ping instruction with @PlanbBot
        s = s.replace("@OdooBot", "@PlanbBot")

        # 2. Replace 'Enjoy exploring Odoo!' / 'Enjoy discovering Odoo!'
        s = re.sub(r'Enjoy\s+(?:exploring|discovering)\s+Odoo!?', 'Enjoy exploring Plan B!', s, flags=re.IGNORECASE)
        s = s.replace("استمتع باستكشاف أودو!", "استمتع باستكشاف Plan B!")
        s = s.replace("استمتع باستكشاف أودو", "استمتع باستكشاف Plan B")

        # 3. Replace any other user-facing 'Odoo' references in discuss text
        s = s.replace("Odoo's chat", "Plan B's chat")
        s = s.replace("تطبيق الدردشة في أودو", "تطبيق الدردشة في Plan B")

        return Markup(s) if is_markup else s
