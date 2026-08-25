/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

patch(UserMenu.prototype, {
    setup() {
        super.setup();
        // فلترة العناصر المترندرة واستبعاد support نهائياً
        if (this.menuItems) {
            this.menuItems = this.menuItems.filter((item) => item.id !== "support" && item.key !== "support");
        }
    },
});