/** @odoo-module **/

// This patches the browser's native History API (pushState / replaceState)
// so that whenever Odoo's web client writes a URL starting with "/odoo",
// the address bar shows the path without that prefix.
//
// We deliberately patch at the native History level instead of Odoo's
// internal router module: Odoo still thinks the URL is "/odoo/sales"
// internally (state, breadcrumbs, deep links keep working), only what
// the user SEES in the address bar changes. This makes the patch
// resistant to internal refactors between Odoo point releases.

function stripOdooPrefix(url) {
    if (!url) return url;
    try {
        const isAbsolute = /^https?:\/\//i.test(url);
        const base = isAbsolute ? undefined : window.location.origin;
        const parsed = new URL(url, base);
        if (parsed.pathname === '/odoo' || parsed.pathname === '/odoo/') {
            parsed.pathname = '/';
        } else if (parsed.pathname.startsWith('/odoo/')) {
            parsed.pathname = parsed.pathname.replace('/odoo/', '/');
        } else {
            return url;
        }
        return isAbsolute ? parsed.toString() : parsed.pathname + parsed.search + parsed.hash;
    } catch (e) {
        return url;
    }
}

const nativePushState = window.history.pushState.bind(window.history);
const nativeReplaceState = window.history.replaceState.bind(window.history);

window.history.pushState = function (state, title, url) {
    return nativePushState(state, title, stripOdooPrefix(url));
};

window.history.replaceState = function (state, title, url) {
    return nativeReplaceState(state, title, stripOdooPrefix(url));
};

// Handle direct load / refresh: if the page loaded on a bare path like
// /sales because our server-side redirect already sent the browser
// there, nothing else to do here - the controller in main.py handled it.
