/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const userMenuRegistry = registry.category("user_menuitems");
const customerPortalUrl = "/planb/customer_portal";

function customerPortalItem() {
    return {
        type: "item",
        id: "customer_portal",
        description: "Customer Portal",
        href: customerPortalUrl,
        callback: () => {
            browser.open(
                customerPortalUrl,
                "_blank",
                "noopener,noreferrer"
            );
        },
        sequence: 55,
    };
}

// Hide "My Odoo.com Account" using its registry key.
if (userMenuRegistry.contains("odoo_account")) {
    userMenuRegistry.remove("odoo_account");
}

userMenuRegistry.add(
    "planb_customer_portal",
    customerPortalItem
);