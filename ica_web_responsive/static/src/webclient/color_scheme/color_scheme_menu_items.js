import { markup } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export function switchColorSchemeItem(env) {
    const { setUserColorScheme, userColorScheme } = env.services.color_scheme;
    return {
        type: "item",
        id: "color_scheme.switch_theme",
        description: markup`
            <div class="d-flex align-items-center justify-content-between gap-3 w-100">
                <span>${_t("Theme")}</span>
                <div class="btn-group">
                    <button class="btn btn-secondary btn-sm ${
                        userColorScheme === "system" ? "active" : ""
                    }" data-color-scheme="system">
                        <span class="visually-hidden">${_t("System")}</span>
                        <i class="fa fa-fw fa-desktop" data-tooltip="${_t("System")}"></i>
                    </button>
                    <button class="btn btn-secondary btn-sm ${
                        userColorScheme === "light" ? "active" : ""
                    }" data-color-scheme="light">
                        <span class="visually-hidden">${_t("Light")}</span>
                        <i class="fa fa-fw fa-sun-o" data-tooltip="${_t("Light")}"></i>
                    </button>
                    <button class="btn btn-secondary btn-sm ${
                        userColorScheme === "dark" ? "active" : ""
                    }" data-color-scheme="dark">
                        <span class="visually-hidden">${_t("Dark")}</span>
                        <i class="fa fa-fw fa-moon-o" data-tooltip="${_t("Dark")}"></i>
                    </button>
                </div>
            </div>`,
        callback: async (ev) => {
            const target = ev.target.matches("[data-color-scheme]")
                ? ev.target
                : ev.target.closest("[data-color-scheme]");
            if (target) {
                await setUserColorScheme(target.dataset.colorScheme);
            }
        },
        sequence: 30,
    };
}
