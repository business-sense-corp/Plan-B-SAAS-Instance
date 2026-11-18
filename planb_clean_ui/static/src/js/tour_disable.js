/** @odoo-module **/

import { tourService } from "@web_tour/js/tour_service";
import { tourState } from "@web_tour/js/tour_state";
import { patch } from "@web/core/utils/patch";

patch(tourService, {
    async start(env, deps) {
        tourState.clear();
        const noop = () => {};
        odoo.startTour = noop;
        odoo.isTourReady = async () => false;

        return {
            startTour: noop,
            startTourRecorder: noop,
        };
    },
});
