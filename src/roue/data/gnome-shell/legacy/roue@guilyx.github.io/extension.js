// Roue's helper for GNOME 42-44 on Wayland, in the extension format those
// versions load. GNOME 45 and newer use ../../roue@guilyx.github.io/extension.js,
// which does the same: keep Roue's wheel above the window you drag from, and
// open it at the pointer. Without it Roue still works: the wheel just opens
// where GNOME puts new windows.

/* exported init */

const {Meta} = imports.gi;

const APP_ID = 'io.github.guilyx.Roue';
const WHEEL_TITLE = 'Convert with Roue';

class RoueExtension {
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
        // A Wayland window has no app id or title yet when it is created. When
        // it is first shown it has both, and GNOME has placed it. (GNOME 42
        // doesn't emit first-frame for these windows.)
        const handler = window.connect('shown', () => {
            window.disconnect(handler);
            const app = window.get_gtk_application_id() ?? window.get_wm_class();
            if (app === APP_ID && window.get_title() === WHEEL_TITLE)
                this._placeWheel(window);
        });
    }

    _placeWheel(window) {
        window.make_above();
        // The see-through layer (Files > Convert with Roue…) covers the
        // screen and finds the pointer itself.
        if (window.get_maximized() !== 0 || window.is_fullscreen())
            return;
        const [x, y] = global.get_pointer();
        const area = window.get_work_area_for_monitor(global.display.get_current_monitor());
        const frame = window.get_frame_rect();
        const left = Math.min(Math.max(x - frame.width / 2, area.x), area.x + area.width - frame.width);
        const top = Math.min(Math.max(y - frame.height / 2, area.y), area.y + area.height - frame.height);
        window.move_frame(true, Math.round(left), Math.round(top));
    }
}

function init() {
    return new RoueExtension();
}
