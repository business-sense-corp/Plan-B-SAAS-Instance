import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { user } from "@web/core/user";

import { switchColorSchemeItem } from "./color_scheme_menu_items";

const serviceRegistry = registry.category("services");
const userMenuRegistry = registry.category("user_menuitems");

export function systemColorScheme() {
    return browser.matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light";
}

export function currentColorScheme() {
    return cookie.get("color_scheme");
}

export const colorSchemeService = {
    dependencies: ["ui"],

    start(env, { ui }) {
        userMenuRegistry.add("color_scheme.switch", switchColorSchemeItem);

        const setCurrentColorScheme = (scheme) => {
            let newColorScheme = systemColorScheme();
            if (["light", "dark"].includes(scheme)) {
                newColorScheme = scheme;
            }
            const current = currentColorScheme();
            if (!current) {
                cookie.set("color_scheme", newColorScheme);
                if (newColorScheme === "dark") {
                    ui.block();
                    this.reload();
                }
            } else if (newColorScheme !== current) {
                cookie.set("color_scheme", newColorScheme);
                ui.block();
                this.reload();
            }
        };

        setCurrentColorScheme(user.settings.color_scheme);

        return {
            get systemColorScheme() {
                return systemColorScheme();
            },
            get currentColorScheme() {
                return currentColorScheme();
            },
            get userColorScheme() {
                return user.settings.color_scheme;
            },
            setUserColorScheme: async (color_scheme) => {
                await user.setUserSettings("color_scheme", color_scheme);
                setCurrentColorScheme(color_scheme);
            },
            switchToColorScheme: (scheme) => {
                setCurrentColorScheme(scheme);
            },
        };
    },
    reload() {
        browser.location.reload();
    },
};
serviceRegistry.add("color_scheme", colorSchemeService);
