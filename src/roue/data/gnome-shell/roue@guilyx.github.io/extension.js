// Roue's helper for GNOME on Wayland.
//
// Wayland leaves window placement to the compositor, so the Roue app can't
// keep its wheel above the window you drag from, or open it at the pointer.
// This does both, for the wheel window only. Without it Roue still works:
// the wheel just opens where GNOME puts new windows.

import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'io.github.guilyx.Roue';
const WHEEL_TITLE = 'Convert with Roue';

export default class RoueExtension extends Extension {
    enable() {
        this._handler = global.display.connect('window-created',
            (_display, window) => this._onWindowCreated(window));
    }

    disable() {
        global.display.disconnect(this._handler);
        this._handler = null;
    }

    _onWindowCreated(window) {
        if (window.get_client_type() !== Meta.WindowClientType.WAYLAND)
            return; // on X11 the app places the wheel itself
        const actor = window.get_compositor_private();
        if (!actor)
            return;
        // A Wayland window has no app id or title yet when it is created.
        const handler = actor.connect('first-frame', () => {
            actor.disconnect(handler);
            const app = window.get_gtk_application_id() ?? window.get_wm_class();
            if (app === APP_ID && window.get_title() === WHEEL_TITLE)
                this._placeWheel(window);
        });
    }

    _placeWheel(window) {
        window.make_above();
        // The see-through layer (Files > Convert with Roue…) covers the
        // screen and finds the pointer itself.
        const maximized = window.is_maximized?.() ?? window.get_maximized() !== 0;
        if (maximized || window.is_fullscreen())
            return;
        const [x, y] = global.get_pointer();
        const area = window.get_work_area_for_monitor(global.display.get_current_monitor());
        const frame = window.get_frame_rect();
        const left = Math.min(Math.max(x - frame.width / 2, area.x), area.x + area.width - frame.width);
        const top = Math.min(Math.max(y - frame.height / 2, area.y), area.y + area.height - frame.height);
        window.move_frame(true, Math.round(left), Math.round(top));
    }
}
