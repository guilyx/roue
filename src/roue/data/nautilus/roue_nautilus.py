"""Roue for Files (Nautilus): right-click any files > Convert with Roue…

The wheel opens at the pointer with the presets that fit the selection.
Ctrl+Shift+right-click opens it straight away, without the menu. Installed by
``roue setup`` (per user) or by the .deb (system-wide). Needs nautilus-python
(``python3-nautilus`` on Debian/Ubuntu).

The menu talks to the Roue app over D-Bus (starting it if needed), so the
wheel, progress and notifications all come from one place. If the app
can't be reached, the ``roue`` command runs instead. The other way round, the
app asks Files for its selection when the hotkey is pressed (``GetSelection``
on ``/io/github/guilyx/Roue/Files``, in the Files process).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import gi

# Nautilus 43-48 ship the 4.0 extension API, Nautilus 49+ (Ubuntu 25.10+) ship 4.1,
# Nautilus 42 (Ubuntu 22.04) ships 3.0, which runs on GTK 3.
for _version in ("4.1", "4.0", "3.0"):
    try:
        gi.require_version("Nautilus", _version)
        break
    except ValueError:  # not installed, or the host already loaded another one
        continue
from gi.repository import Gio, GLib, GObject, Nautilus  # noqa: E402

# The GDK of the Files process: GTK 3 with the 3.0 API, GTK 4 after.
GDK_VERSION = "3.0" if Nautilus._version == "3.0" else "4.0"
try:
    gi.require_version("Gtk", GDK_VERSION)
    gi.require_version("Gdk", GDK_VERSION)
    from gi.repository import Gdk, Gtk
except (ValueError, ImportError):  # another GTK is loaded: no Ctrl+Shift+right-click
    Gdk = Gtk = None

APP_ID = "io.github.guilyx.Roue"
OBJECT_PATH = "/io/github/guilyx/Roue"
# Filled in at install time with the absolute path of the roue command.
ROUE_COMMAND = "@ROUE_COMMAND@"
CACHE_SECONDS = 20

FILES_OBJECT_PATH = "/io/github/guilyx/Roue/Files"
FILES_INTERFACE = """
<node>
  <interface name="io.github.guilyx.Roue.Files">
    <method name="GetSelection">
      <arg name="paths" type="as" direction="out"/>
    </method>
  </interface>
</node>
"""
#: The hotkey's key grab takes focus from Files for a moment on X11.
FOCUS_GRACE_SECONDS = 1.0


def _command() -> list[str]:
    if not ROUE_COMMAND.startswith("@"):
        return ROUE_COMMAND.split()
    found = shutil.which("roue")
    return [found] if found else []


def _kind(mime: str) -> str:
    top = mime.split("/", 1)[0]
    return top if top in ("image", "video", "audio") else "document"


class _Catalog:
    """Presets, read through the roue package when importable, else the CLI."""

    def __init__(self) -> None:
        self._presets: list[dict[str, Any]] = []
        self._loaded = -CACHE_SECONDS
        self._mime_type: Any = None

    def presets(self) -> list[dict[str, Any]]:
        if time.monotonic() - self._loaded > CACHE_SECONDS:
            self._reload()
        return self._presets

    def _reload(self) -> None:
        self._loaded = time.monotonic()
        try:
            from roue.engine.backends import is_available
            from roue.engine.detect import mime_type
            from roue.engine.presets import load_presets
            from roue.engine.settings import Settings

            registry = load_presets().without(Settings.load().disabled_presets)
            self._presets = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "group": p.group,
                    "accepts": list(p.accepts),
                    "rejects": list(p.rejects),
                    "available": is_available(p),
                }
                for p in registry
            ]
            self._mime_type = mime_type
            return
        except Exception:  # not importable from this Python: ask the CLI
            self._mime_type = None
        command = _command()
        if not command:
            self._presets = []
            return
        try:
            out = subprocess.run(
                [*command, "list", "--json"], capture_output=True, text=True, timeout=5, check=True
            )
            self._presets = json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            self._presets = []

    def mime(self, info: Nautilus.FileInfo, path: str) -> str:
        if self._mime_type is not None:
            return str(self._mime_type(Path(path)))
        return str(info.get_mime_type())

    def matching(self, mimes: list[str]) -> list[dict[str, Any]]:
        def accepts(preset: dict[str, Any], mime: str) -> bool:
            return any(fnmatchcase(mime, p) for p in preset["accepts"]) and not any(
                fnmatchcase(mime, p) for p in preset.get("rejects", [])
            )

        found = [
            p
            for p in self.presets()
            if p.get("available", True) and all(accepts(p, m) for m in mimes)
        ]
        kinds = [_kind(m) for m in mimes]
        main = max(set(kinds), key=kinds.count)
        return sorted(found, key=lambda p: p.get("group") != main)


_catalog = _Catalog()


def _spawn(args: list[str]) -> None:
    command = _command()
    if command:
        subprocess.Popen(
            [*command, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _platform_data() -> dict[str, GLib.Variant]:
    """An activation token, so the desktop lets the wheel take focus."""
    try:
        gi.require_version("Gdk", GDK_VERSION)
        from gi.repository import Gdk

        try:  # GLib >= 2.80 moved it to GioUnix; Gio.DesktopAppInfo is deprecated
            gi.require_version("GioUnix", "2.0")
            from gi.repository import GioUnix

            desktop_app_info: Any = GioUnix.DesktopAppInfo
        except (ValueError, ImportError):
            desktop_app_info = Gio.DesktopAppInfo
        info = desktop_app_info.new(f"{APP_ID}.desktop")
        display = Gdk.Display.get_default()
        if info is None or display is None:
            return {}
        token = display.get_app_launch_context().get_startup_notify_id(info, [])
    except (ValueError, TypeError, GLib.Error):
        return {}
    if not token:
        return {}
    return {
        "activation-token": GLib.Variant("s", token),
        "desktop-startup-id": GLib.Variant("s", token),
    }


def _activate(action: str, parameter: GLib.Variant, fallback: list[str]) -> None:
    """Ask the Roue app to run an action, starting it if needed."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        _spawn(fallback)
        return

    def done(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error:
            _spawn(fallback)

    bus.call(
        APP_ID,
        OBJECT_PATH,
        "org.gtk.Actions",
        "Activate",
        GLib.Variant("(sava{sv})", (action, [parameter], _platform_data())),
        None,
        Gio.DBusCallFlags.NONE,
        15000,
        None,
        done,
    )


def _convertible(files: list[Nautilus.FileInfo]) -> tuple[list[str], list[dict[str, Any]]]:
    """The files' paths and the presets that take them all, or nothing."""
    paths: list[str] = []
    mimes: list[str] = []
    for info in files:
        if info.is_directory():
            return [], []
        location = info.get_location()
        path = location.get_path() if location else None
        if not path:
            return [], []  # not a local file (network share without a mount...)
        paths.append(path)
        mimes.append(_catalog.mime(info, path))
    presets = _catalog.matching(mimes) if paths else []
    return (paths, presets) if presets else ([], [])


def _open_wheel(paths: list[str]) -> None:
    _activate("wheel-files", GLib.Variant("as", paths), ["wheel", *paths])


def _clicked(before: list[str], after: list[Nautilus.FileInfo]) -> list[Nautilus.FileInfo]:
    """The files a Ctrl+Shift+right-click was about, from the selection around it.

    Clicking a file that isn't selected yet selects it: Files 42 adds it to
    the selection (that's what Ctrl and Shift do there), newer Files replace
    the selection with it. Either way the newly selected file is the one
    clicked. Clicking a selected file keeps the selection, as a menu would.
    """
    added = [info for info in after if info.get_uri() not in before]
    return added or after


class _Files:
    """What's selected in each Files window, and Ctrl+Shift+right-click.

    Files asks menu providers for items whenever the selection changes, and
    again right before it shows a context menu, so the selection stays
    current. Files has no API for mouse shortcuts: the extension listens to
    right-clicks on its windows before Files does (the capture phase), lets
    Files select the clicked file as usual, then closes Files' menu and opens
    the wheel instead.
    """

    def __init__(self) -> None:
        self._selection: dict[int, list[Nautilus.FileInfo]] = {}
        self._windows: dict[int, Any] = {}
        self._active: tuple[int, float] | None = None  # last focused window, when it lost focus
        self._clicked_window: Any = None  # during a Ctrl+Shift+right-click
        self._exported = False

    def start(self) -> None:
        app = self._app()
        if app is None:
            return
        app.connect("window-added", lambda _app, window: self.watch(window))
        for window in app.get_windows():
            self.watch(window)
        self._export(app)

    @staticmethod
    def _app() -> Any:
        """The Files app, when running inside Files."""
        app = Gio.Application.get_default()
        if Gtk is None or not isinstance(app, Gtk.Application):
            return None
        return app if (app.get_application_id() or "").startswith("org.gnome.Nautilus") else None

    # -- the selection ----------------------------------------------------------

    def remember(self, window: Any, files: list[Nautilus.FileInfo]) -> None:
        app = self._app()
        if app is None:
            return
        if window is None:  # Nautilus 43+ doesn't say which window: the clicked or focused one
            window = self._clicked_window or app.get_active_window()
        if window is not None:
            self.watch(window)
            self._selection[hash(window)] = list(files)

    def selected(self, window: Any) -> list[Nautilus.FileInfo]:
        return self._selection.get(hash(window), [])

    def front_selection(self) -> list[str]:
        """Paths Roue can convert, selected in the Files window in front."""
        if self._active is None:
            return []
        key, since = self._active
        window = self._windows.get(key)
        if window is None:
            return []
        if not window.get_property("is-active") and time.monotonic() - since > FOCUS_GRACE_SECONDS:
            return []
        return _convertible(self.selected(window))[0]

    # -- windows --------------------------------------------------------------------

    def watch(self, window: Any) -> None:
        key = hash(window)
        if key in self._windows or Gtk is None or not isinstance(window, Gtk.Window):
            return
        self._windows[key] = window
        if GDK_VERSION == "3.0":
            gesture = Gtk.GestureMultiPress.new(window)
            window.roue_gesture = gesture  # GTK 3 gestures don't belong to their widget
        else:
            gesture = Gtk.GestureClick()
            window.add_controller(gesture)
        gesture.set_button(Gdk.BUTTON_SECONDARY)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("pressed", self._on_right_press, window)
        window.connect("notify::is-active", self._on_focus)
        window.connect("destroy", self._forget)
        if window.get_property("is-active"):
            self._active = (key, 0.0)
        app = self._app()
        if app is not None:
            self._export(app)  # in case Files wasn't on the bus yet at start()

    def _forget(self, window: Any) -> None:
        key = hash(window)
        self._windows.pop(key, None)
        self._selection.pop(key, None)
        if self._active and self._active[0] == key:
            self._active = None

    def _on_focus(self, window: Any, _pspec: Any) -> None:
        key = hash(window)
        if window.get_property("is-active"):
            self._active = (key, 0.0)
        elif self._active and self._active[0] == key:
            self._active = (key, time.monotonic())

    # -- Ctrl+Shift+right-click -----------------------------------------------------

    def _on_right_press(self, gesture: Any, _n: int, _x: float, _y: float, window: Any) -> None:
        if GDK_VERSION == "3.0":
            known, state = Gtk.get_current_event_state()
            if not known:
                return
        else:
            state = gesture.get_current_event_state()
        wanted = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if state & wanted != wanted:
            return
        before = [info.get_uri() for info in self.selected(window)]
        self._clicked_window = window
        # Before Files' menu is drawn, after Files has handled the click.
        GLib.idle_add(self._after_right_click, window, before, priority=GLib.PRIORITY_HIGH_IDLE)

    def _after_right_click(self, window: Any, before: list[str]) -> bool:
        self._clicked_window = None
        paths, _presets = _convertible(_clicked(before, self.selected(window)))
        if paths:  # else it's empty space or nothing to convert: Files' menu stays
            self._close_menus(window)
            _open_wheel(paths)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _close_menus(window: Any) -> None:
        if GDK_VERSION == "3.0":
            for toplevel in Gtk.Window.list_toplevels():
                menu = toplevel.get_child()
                if toplevel.get_visible() and isinstance(menu, Gtk.Menu):
                    menu.cancel()
            return
        pending = [window]
        while pending:
            widget = pending.pop()
            if isinstance(widget, Gtk.PopoverMenu) and widget.get_visible():
                widget.popdown()
            child = widget.get_first_child()
            while child is not None:
                pending.append(child)
                child = child.get_next_sibling()

    # -- D-Bus ------------------------------------------------------------------------

    def _export(self, app: Any) -> None:
        connection = app.get_dbus_connection()
        if connection is None or self._exported:
            return
        interface = Gio.DBusNodeInfo.new_for_xml(FILES_INTERFACE).interfaces[0]
        try:
            connection.register_object(FILES_OBJECT_PATH, interface, self._on_call, None, None)
        except GLib.Error:  # another copy of this extension got there first
            return
        self._exported = True

    def _on_call(self, *args: Any) -> None:
        # (connection, sender, object path, interface, method, parameters, invocation)
        method, invocation = args[4], args[6]
        if method == "GetSelection":
            invocation.return_value(GLib.Variant("(as)", (self.front_selection(),)))
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)


_files = _Files()
_files.start()


class RoueMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, *args: Any) -> list[Nautilus.MenuItem]:
        # Nautilus 43+ passes the files, Nautilus 42 (window, files).
        files: list[Nautilus.FileInfo] = args[-1]
        _files.remember(args[0] if len(args) > 1 else None, files)
        paths, presets = _convertible(files)
        if not paths:
            return []

        item = Nautilus.MenuItem(
            name="Roue::Wheel",
            label="Convert with Roue…",
            tip=f"{len(presets)} ways to convert: " + ", ".join(p["name"] for p in presets[:4]),
        )
        item.connect("activate", self._wheel, paths)
        return [item]

    def _wheel(self, _item: Nautilus.MenuItem, paths: list[str]) -> None:
        _open_wheel(paths)
