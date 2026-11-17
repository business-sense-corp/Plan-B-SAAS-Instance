/** @odoo-module **/

import { View } from "@web/views/view";
import { SampleServer } from "@web/model/sample_server";
import { patch } from "@web/core/utils/patch";

// 1. Framework-level view patch: force useSampleModel to false across all views
patch(View.prototype, {
    async loadView(props) {
        const res = await super.loadView(...arguments);
        if (this.componentProps) {
            this.componentProps.useSampleModel = false;
        }
        return res;
    },
});

// 2. Defense-in-depth: guarantees SampleServer returns empty structures if queried
patch(SampleServer.prototype, {
    mockRpc(params) {
        const method = params.method || params.route;
        if (method === "web_search_read" || method === "read") {
            return { records: [], length: 0 };
        }
        if (
            method === "web_read_group" ||
            method === "formatted_read_group" ||
            method === "formatted_read_grouping_sets"
        ) {
            return { groups: [], length: 0 };
        }
        if (method === "read_progress_bar") {
            return {};
        }
        return super.mockRpc(...arguments);
    },
});
