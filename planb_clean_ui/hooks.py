# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Clean UI post-init migration: disable tours, close onboarding, and migrate Discuss/Bot."""
    cr = env.cr

    _logger.info("Executing planb_clean_ui post_init_hook...")

    # 1. Disable tour_enabled for all existing users
    cr.execute("UPDATE res_users SET tour_enabled = FALSE WHERE tour_enabled IS TRUE")
    _logger.info("Updated existing users tour_enabled to False.")

    # 2. Mark existing onboarding progress as closed and done
    cr.execute("""
        UPDATE onboarding_progress
        SET is_onboarding_closed = TRUE,
            onboarding_state = 'done'
        WHERE is_onboarding_closed IS NOT TRUE OR onboarding_state != 'done'
    """)
    _logger.info("Updated onboarding_progress records to closed and done.")

    # 3. If onboarding_onboarding table has is_onboarding_closed column, update it too
    cr.execute("""
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'onboarding_onboarding' AND column_name = 'is_onboarding_closed'
    """)
    if cr.fetchone():
        cr.execute("UPDATE onboarding_onboarding SET is_onboarding_closed = TRUE WHERE is_onboarding_closed IS NOT TRUE")
        _logger.info("Updated onboarding_onboarding records to closed.")

    # 4. Mark all non-custom tours as consumed for all users in database
    cr.execute("""
        SELECT 1 FROM information_schema.tables WHERE table_name = 'res_users_web_tour_tour_rel'
    """)
    if cr.fetchone():
        cr.execute("""
            INSERT INTO res_users_web_tour_tour_rel (web_tour_tour_id, res_users_id)
            SELECT t.id, u.id
            FROM web_tour_tour t
            CROSS JOIN res_users u
            WHERE t.custom IS NOT TRUE
            ON CONFLICT DO NOTHING
        """)
        _logger.info("Marked active tours as consumed across existing users.")

    # 5. Execute Discuss and Bot white-label data migrations
    migrate_discuss_records(env)


def migrate_discuss_records(env):
    """Idempotent migration for Discuss, PlanbBot, and General Channel messages."""
    _logger.info("Executing migrate_discuss_records...")

    # 1. Update General Channel install notification subject
    gen_msg = env.ref("mail.module_install_notification", raise_if_not_found=False)
    if gen_msg:
        if gen_msg.subject != "Welcome to Plan B!":
            gen_msg.sudo().write({"subject": "Welcome to Plan B!"})
            _logger.info("Updated mail.module_install_notification subject to 'Welcome to Plan B!'.")
    else:
        # Fallback to search by subject or general channel
        gen_channel = env.ref("mail.channel_all_employees", raise_if_not_found=False)
        if gen_channel:
            msgs = env["mail.message"].sudo().search([
                ("model", "=", "discuss.channel"),
                ("res_id", "=", gen_channel.id),
                ("subject", "=", "Welcome to Odoo!")
            ])
            if len(msgs) == 1:
                msgs.write({"subject": "Welcome to Plan B!"})
                _logger.info("Updated general channel message subject via fallback search.")

    # 2. Update Discuss notification security group name
    inbox_group = env.ref("mail.group_mail_notification_type_inbox", raise_if_not_found=False)
    if inbox_group and inbox_group.name != "Receive notifications in Plan B":
        inbox_group.sudo().write({"name": "Receive notifications in Plan B"})
        _logger.info("Updated mail.group_mail_notification_type_inbox name to 'Receive notifications in Plan B'.")

    # 3. Ensure bot partner and user are named PlanbBot
    bot_partner = env.ref("base.partner_root", raise_if_not_found=False)
    if bot_partner and bot_partner.name != "PlanbBot":
        bot_partner.sudo().write({"name": "PlanbBot"})
        _logger.info("Renamed base.partner_root to PlanbBot.")

    bot_user = env.ref("base.user_root", raise_if_not_found=False)
    if bot_user and bot_user.name != "PlanbBot":
        bot_user.sudo().write({"name": "PlanbBot"})
        _logger.info("Renamed base.user_root to PlanbBot.")

    # 4. Update existing bot chat messages in discuss.channel
    if bot_partner:
        bot_channels = env["discuss.channel"].sudo().search([
            ("channel_type", "=", "chat"),
            ("channel_member_ids.partner_id", "=", bot_partner.id)
        ])
        for ch in bot_channels:
            bot_msgs = env["mail.message"].sudo().search([
                ("model", "=", "discuss.channel"),
                ("res_id", "=", ch.id),
                ("author_id", "=", bot_partner.id),
            ])
            for msg in bot_msgs:
                body = msg.body or ""
                # Update old welcome messages
                if "يساعد تطبيق الدردشة في أودو" in body:
                    new_body = body.replace(
                        "يساعد تطبيق الدردشة في أودو الموظفين على التعاون بكفاءة. أنا هنا لمساعدتك على استكشاف خصائصه.",
                        "يساعد تطبيق الدردشة في Plan B الموظفين على التعاون بكفاءة. أنا هنا لمساعدتك على استكشاف خصائصه."
                    )
                    msg.write({"body": new_body})
                    _logger.info(f"Updated Bot welcome message {msg.id} in channel {ch.id} to Plan B (Arabic).")
                elif "Odoo's chat helps employees collaborate efficiently" in body:
                    new_body = body.replace(
                        "Odoo's chat helps employees collaborate efficiently. I'm here to help you discover its features.",
                        "Plan B's chat helps employees collaborate efficiently. I'm here to help you discover its features."
                    )
                    msg.write({"body": new_body})
                    _logger.info(f"Updated Bot welcome message {msg.id} in channel {ch.id} to Plan B (English).")

                # Update old fallback messages with Odoo doc/slides links
                if ("odoo.com/documentation" in body or "odoo.com/slides" in body or
                    "للأسف، أنا مجرد ذكاء اصطناعي 😞" in body or "Unfortunately, I'm just a bot" in body):
                    if "للأسف" in body or "المساعدة" in body:
                        clean_body = (
                            "<p>للأسف، أنا مجرد روبوت دردشة ولا أفهم هذه الرسالة. "
                            "إذا كنت بحاجة إلى مساعدة، يرجى التواصل مع فريق الدعم في Plan B.</p>"
                        )
                    else:
                        clean_body = (
                            "<p>Sorry, I'm just a chatbot and I didn't understand that message. "
                            "If you need help, please contact the Plan B support team.</p>"
                        )
                    msg.write({"body": clean_body})
                    _logger.info(f"Updated Bot fallback message {msg.id} in channel {ch.id} to clean Plan B fallback.")
