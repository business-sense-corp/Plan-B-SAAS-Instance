# -*- coding: utf-8 -*-
from odoo import models, fields, api


class OnboardingOnboarding(models.Model):
    _inherit = "onboarding.onboarding"

    @api.depends_context("company")
    @api.depends(
        "progress_ids",
        "progress_ids.is_onboarding_closed",
        "progress_ids.onboarding_state",
        "progress_ids.company_id",
    )
    def _compute_current_progress(self):
        super()._compute_current_progress()
        for onboarding in self:
            onboarding.is_onboarding_closed = True
            onboarding.current_onboarding_state = "done"


class OnboardingProgress(models.Model):
    _inherit = "onboarding.progress"

    is_onboarding_closed = fields.Boolean(
        "Was panel closed?",
        default=True,
    )
