/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleActionHelper } from "@sale/js/sale_action_helper/sale_action_helper";

patch(SaleActionHelper.prototype, {
    openVideoPreview() {
        // Suppress video preview dialog globally
        return;
    },
});
