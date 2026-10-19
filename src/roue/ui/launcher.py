"""Start the panel, or hand the request to the copy that's already running.

Importing GTK and libadwaita costs a few hundred milliseconds. When Roue is
already running in the background (the usual case), this forwards the
command line over D-Bus using only Gio, so the hotkey feels instant.
"""

from __future__ import annotations

import logging

from .. import APP_ID


def _add_options(app: object) -> None:
    from gi.repository import GLib

    app.add_main_option(  # type: ignore[attr-defined]
        "preferences", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Open preferences", None
    )


def _is_running() -> bool:
    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (APP_ID,)),
            GLib.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            500,
            None,
        )
    except GLib.Error:
        return False
    return bool(reply.unpack()[0])


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="roue: %(message)s")
    from gi.repository import Gio

    if "--gapplication-service" not in argv and _is_running():
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.HANDLES_OPEN
        forwarder = Gio.Application(application_id=APP_ID, flags=flags)
        _add_options(forwarder)
        return int(forwarder.run(argv))

    from .application import RoueApplication

    app = RoueApplication()
    _add_options(app)
    return int(app.run(argv))
