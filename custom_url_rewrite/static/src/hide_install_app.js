/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

// إيقاف PWA Service من إضافة زرار التثبيت
const pwaService = registry.category("services").get("pwa");
if (pwaService) {
    patch(pwaService, {
        start() {
            const api = super.start(...arguments);
            api.canInstall = false; // إلغاء إمكانية التثبيت
            return api;
        },
    });
}