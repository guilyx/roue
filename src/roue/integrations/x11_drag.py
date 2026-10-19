"""Shift-drag on X11: pop the panel up when a drag starts with Shift held.

Every X11 drag-and-drop source takes ownership of the ``XdndSelection``
selection when a drag starts. XFixes tells us when that happens; we then
watch the pointer until the button is released, and fire ``on_shift_drag``
the moment Shift is held during the drag.

Wayland deliberately hides other apps' drags, so this only runs on X11.
Needs python-xlib (``python3-xlib``).
"""

from __future__ import annotations

import logging
import select
import threading
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

_POLL_SECONDS = 0.04


def available() -> bool:
    try:
        import Xlib.display  # noqa: F401
        from Xlib.ext import xfixes  # noqa: F401
    except ImportError:
        return False
    return True


class ShiftDragWatcher(threading.Thread):
    """Background thread. Callbacks run on this thread: hop to the UI loop."""

    def __init__(
        self,
        on_shift_drag: Callable[[int, int], None],
        on_drag_end: Callable[[], None],
    ):
        super().__init__(name="roue-x11-drag", daemon=True)
        self.on_shift_drag = on_shift_drag
        self.on_drag_end = on_drag_end
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._run()
        except Exception:
            log.exception("Shift-drag watcher stopped")

    def _run(self) -> None:
        from Xlib import X, display
        from Xlib.ext import xfixes

        disp: Any = display.Display()
        if not disp.has_extension("XFIXES"):
            log.warning("XFixes is missing: Shift-drag is disabled")
            return
        disp.xfixes_query_version()
        root = disp.screen().root
        selection = disp.intern_atom("XdndSelection")
        disp.xfixes_select_selection_input(
            root, selection, xfixes.XFixesSetSelectionOwnerNotifyMask
        )
        first_event = disp.query_extension("XFIXES").first_event
        notify_type = first_event + xfixes.XFixesSelectionNotify
        disp.flush()
        while not self._stop_event.is_set():
            ready, _, _ = select.select([disp.fileno()], [], [], 0.5)
            if not ready:
                continue
            while disp.pending_events():
                event = disp.next_event()
                if (
                    event.type == notify_type
                    and getattr(event, "sub_code", None) == xfixes.XFixesSetSelectionOwnerNotify
                    and event.owner
                ):
                    self._follow_drag(root, X)

    def _follow_drag(self, root: Any, x: Any) -> None:
        """Poll the pointer while the button is down; fire once if Shift is held."""
        fired = False
        while not self._stop_event.is_set():
            pointer = root.query_pointer()
            buttons = x.Button1Mask | x.Button2Mask | x.Button3Mask
            if not pointer.mask & buttons:
                break
            if not fired and pointer.mask & x.ShiftMask:
                fired = True
                self.on_shift_drag(pointer.root_x, pointer.root_y)
            time.sleep(_POLL_SECONDS)
        if fired:
            self.on_drag_end()


def pointer_position() -> tuple[int, int] | None:
    """Where the pointer is on the X screen, or None when that can't be known."""
    try:
        from Xlib import display
    except ImportError:
        return None
    try:
        disp: Any = display.Display()
    except Exception:
        return None
    try:
        pointer = disp.screen().root.query_pointer()
        return int(pointer.root_x), int(pointer.root_y)
    finally:
        disp.close()


def keep_above_near(
    xid: int,
    x: int | None,
    y: int | None,
    width: int,
    height: int,
    *,
    center: bool = False,
) -> None:
    """Keep our own window above others, moved next to (or centred on) the pointer."""
    from Xlib import X, display, protocol

    disp: Any = display.Display()
    try:
        window = disp.create_resource_object("window", xid)
        screen = disp.screen()
        if x is not None and y is not None:
            top_y = y - height // 2 if center else y + 24
            left = max(0, min(x - width // 2, screen.width_in_pixels - width))
            top = max(0, min(top_y, screen.height_in_pixels - height))
            window.configure(x=left, y=top)
        state = disp.intern_atom("_NET_WM_STATE")
        above = disp.intern_atom("_NET_WM_STATE_ABOVE")
        event = protocol.event.ClientMessage(
            window=window, client_type=state, data=(32, [1, above, 0, 1, 0])
        )
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        screen.root.send_event(event, event_mask=mask)
        disp.flush()
    finally:
        disp.close()
