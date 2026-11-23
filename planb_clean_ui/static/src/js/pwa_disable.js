/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

// 1. Intercept beforeinstallprompt at window level to prevent any native install prompt
if (typeof window !== "undefined") {
    window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault();
        return false;
    });
}

// 2. Patch PWA service to ensure canPromptToInstall and isAvailable stay false
const serviceRegistry = registry.category("services");
const pwaService = serviceRegistry.get("pwa");

if (pwaService) {
    patch(pwaService, {
        start(env, deps) {
            const state = super.start(env, deps);
            state.canPromptToInstall = false;
            state.isAvailable = false;
            state.isSupportedOnBrowser = false;
            state.show = async () => {};
            state.getManifest = async () => null;
            return state;
        },
    });
}
