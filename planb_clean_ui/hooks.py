# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Clean UI post-init migration: disable tours and close onboarding globally."""
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
