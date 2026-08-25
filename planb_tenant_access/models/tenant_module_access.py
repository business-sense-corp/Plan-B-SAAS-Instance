# -*- coding: utf-8 -*-
from odoo import fields, models


class PlanBTenantModuleAccess(models.Model):
    _name = 'planb.tenant.module.access'
    _description = 'Plan B Tenant Package Module Access'
    _order = 'name, id'

    name = fields.Char(required=True, readonly=True)
    technical_name = fields.Char(required=True, readonly=True, index=True)
    user_group_xmlids = fields.Text(readonly=True)
    manager_group_xmlids = fields.Text(readonly=True)
    root_menu_xmlids = fields.Text(readonly=True)
    active = fields.Boolean(default=True, readonly=True)

    _sql_constraints = [
        (
            'planb_tenant_module_access_technical_name_uniq',
            'unique(technical_name)',
            'The tenant module technical name must be unique.',
        ),
    ]

    @staticmethod
    def _split_xmlids(value):
        if not value:
            return []
        normalized = value.replace('\r', '\n').replace(',', '\n')
        return list(dict.fromkeys(
            item.strip() for item in normalized.split('\n') if item.strip()
        ))

    def get_user_group_xmlids(self):
        self.ensure_one()
        return self._split_xmlids(self.user_group_xmlids)

    def get_manager_group_xmlids(self):
        self.ensure_one()
        return self._split_xmlids(self.manager_group_xmlids)

    def get_root_menu_xmlids(self):
        self.ensure_one()
        return self._split_xmlids(self.root_menu_xmlids)