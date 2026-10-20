"""The GTK application.

One instance per session, reachable on D-Bus as ``io.github.guilyx.Roue``.
Actions exposed over ``org.gtk.Actions`` (used by the Files extension and
the hotkey):

- ``show-wheel``: the wheel as a small window to drop files on (the hotkey)
- ``wheel-files`` (``as``): the wheel at the pointer for these files (Files menu)
- ``show-panel``
- ``stage-files`` (``as``): open the panel with files ready to convert
- ``run-preset`` (``(sas)``): convert files right away
- ``open-file`` / ``show-in-folder`` (``s``, a file URI)
- ``preferences``, ``history``, ``undo``, ``about``, ``quit``
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, ISSUES_URL, WEBSITE, __version__
from ..engine import tools
from ..engine.history import History
from ..engine.presets import Preset, PresetRegistry, load_presets
from ..engine.runner import Batch, JobState, Runner, human_size
from ..engine.settings import Settings
from ..integrations import session, x11_drag
from ..integrations.desktop import package_data
from .panel import DropPanel
from .wheel import WheelWindow

log = logging.getLogger(__name__)


class _TokenLaunchContext(Gio.AppLaunchContext):
    """Hands a Wayland activation token on to the app we launch, so it may
    come to the front (GNOME otherwise just says "… is ready")."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def do_get_startup_notify_id(self, _info: Any, _files: Any) -> str:
        return self._token


class RoueApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE | Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.settings = Settings.load()
        self.registry: PresetRegistry = load_presets()
        self.history = History()
        self.runner = self._make_runner()
        self.panel: DropPanel | None = None
        self.wheel: WheelWindow | None = None
        #: Files last taken from the clipboard, so they aren't offered twice.
        self.clipboard_seen: tuple[str, ...] = ()
        self._background_hold = False
        self._watcher: x11_drag.ShiftDragWatcher | None = None
        self._drag_started_at = 0.0
        self._last_drop = 0.0
        self._opened_by_drag = False
        #: Token GNOME sent with the last activation (e.g. a notification click).
        self._activation_token: str | None = None

    # -- lifecycle ------------------------------------------------------------

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display:
            provider = Gtk.CssProvider()
            provider.load_from_path(str(Path(__file__).with_name("style.css")))
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            # Lets the icon show up when running from a checkout.
            Gtk.IconTheme.get_for_display(display).add_search_path(str(package_data("icons")))
        Gtk.Window.set_default_icon_name(APP_ID)
        self._install_actions()
        self._apply_background_setting()
        self._start_shift_drag()
        GLib.idle_add(self._prewarm)

    def _prewarm(self) -> bool:
        """Build the panel hidden, so the first hotkey press only has to map it."""
        if self.panel is None:
            self.panel = DropPanel(self)
            self.panel.realize()
        return GLib.SOURCE_REMOVE

    def do_activate(self) -> None:
        self.show_panel()
        self._welcome_once()

    def do_open(self, files: list[Gio.File], _n_files: int, _hint: str) -> None:
        self.show_panel()
        paths = [Path(p) for f in files if (p := f.get_path())]
        if paths and self.panel:
            self.panel.stage(paths)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict().end().unpack()
        cwd = Path(command_line.get_cwd() or ".")
        args = [a for a in command_line.get_arguments()[1:] if not a.startswith("--")]
        files = [cwd / a for a in args]
        if options.get("wheel"):
            self.show_wheel(files, overlay=bool(files))
            return 0
        self.show_panel()
        if files and self.panel:
            self.panel.stage(files)
        if options.get("preferences"):
            self.show_preferences()
        elif not files:
            self._welcome_once()
        return 0

    def do_shutdown(self) -> None:
        if self._watcher:
            self._watcher.stop()
        self.runner.shutdown(cancel=True)
        Adw.Application.do_shutdown(self)

    # -- settings ---------------------------------------------------------------

    def _make_runner(self) -> Runner:
        return Runner(
            max_workers=self.settings.max_jobs or None,
            on_update=lambda job: GLib.idle_add(self._on_job_update, job),
            on_batch_done=lambda batch: GLib.idle_add(self._on_batch_done, batch),
        )

    def visible_presets(self) -> dict[str, list[Preset]]:
        return self.registry.without(self.settings.disabled_presets).by_group()

    def settings_changed(self) -> None:
        """Called by Preferences after each change."""
        if not self.runner.busy:
            self.runner.shutdown()
            self.runner = self._make_runner()
        self._apply_background_setting()
        if self._watcher and not self.settings.shift_drag:
            self._watcher.stop()
            self._watcher = None
        elif not self._watcher:
            self._start_shift_drag()
        if self.panel:
            self.panel.rebuild()

    def tools_changed(self) -> None:
        """Called after installing tools: presets may have become ready."""
        tools.which.cache_clear()
        if self.panel:
            self.panel.rebuild()

    def reload_presets(self) -> None:
        self.registry = load_presets()
        if self.panel:
            self.panel.rebuild()

    def _apply_background_setting(self) -> None:
        if self.settings.stay_in_background and not self._background_hold:
            self.hold()
            self._background_hold = True
        elif not self.settings.stay_in_background and self._background_hold:
            self.release()
            self._background_hold = False

    # -- actions ----------------------------------------------------------------

    def _install_actions(self) -> None:
        simple = {
            "show-wheel": lambda *_: self.show_wheel(),
            "show-panel": lambda *_: self.show_panel(),
            "preferences": lambda *_: self.show_preferences(),
            "welcome": lambda *_: self.show_welcome(),
            "history": lambda *_: self.show_history(),
            "undo": lambda *_: self.undo(),
            "about": lambda *_: self.show_about(),
            "quit": lambda *_: self.quit_app(),
            "reload-presets": lambda *_: self.reload_presets(),
        }
        for name, callback in simple.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        typed: dict[str, tuple[str, Any]] = {
            "wheel-files": ("as", self._on_wheel_files),
            "stage-files": ("as", self._on_stage_files),
            "run-preset": ("(sas)", self._on_run_preset),
            "open-file": ("s", self._on_open_file),
            "show-in-folder": ("s", self._on_show_in_folder),
        }
        for name, (signature, callback) in typed.items():
            action = Gio.SimpleAction.new(name, GLib.VariantType(signature))
            action.connect("activate", callback)
            self.add_action(action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.preferences", ["<Control>comma"])
        self.set_accels_for_action("app.undo", ["<Control>z"])

    def show_panel(self) -> DropPanel:
        if self.panel is None:
            self.panel = DropPanel(self)
        self.panel.present()
        return self.panel

    def show_wheel(
        self,
        files: list[Path] | None = None,
        *,
        overlay: bool = False,
        pointer: tuple[int, int] | None = None,
    ) -> WheelWindow:
        """Show the wheel: at the pointer over everything (overlay), or as a
        small window to drop files on."""
        if self.wheel is not None:
            self.wheel.dismiss()
        x11 = session.session_type() == "x11"
        if pointer is None and x11:
            pointer = x11_drag.pointer_position()
        wheel = WheelWindow(self, files=files, overlay=overlay, pointer=pointer)
        wheel.connect("close-request", self._on_wheel_closed)
        self.wheel = wheel
        wheel.present()
        if not wheel.overlay and not files:
            wheel.paste_files()
        if x11:
            centre = None if wheel.overlay else pointer
            GLib.timeout_add(60, self._keep_above, wheel, centre)
        return wheel

    def _on_wheel_closed(self, wheel: WheelWindow) -> bool:
        if self.wheel is wheel:
            self.wheel = None
        return False

    def _keep_above(self, window: Gtk.Window, centre: tuple[int, int] | None) -> bool:
        """X11 only: keep the window on top, centred on ``centre`` if given."""
        try:
            import gi

            gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11

            surface = window.get_surface()
            if isinstance(surface, GdkX11.X11Surface):
                x, y = centre if centre else (None, None)
                width, height = window.get_default_size()
                x11_drag.keep_above_near(
                    surface.get_xid(),
                    x,
                    y,
                    window.get_width() or width,
                    window.get_height() or height,
                    center=True,
                )
        except Exception as exc:  # placement is a nicety; never break the wheel
            log.debug("Couldn't place the wheel: %s", exc)
        return GLib.SOURCE_REMOVE

    def show_welcome(self) -> None:
        from .welcome import WelcomeDialog

        WelcomeDialog(self).present(self.show_panel())

    def _welcome_once(self) -> None:
        if not self.settings.welcome_done:
            self.show_welcome()

    def show_preferences(self) -> None:
        from .preferences import PreferencesDialog

        PreferencesDialog(self).present(self.show_panel())

    def show_history(self) -> None:
        from .history import HistoryDialog

        HistoryDialog(self.history).present(self.show_panel())

    def show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=__version__,
            developer_name="Erwin Lejeune and contributors",
            comments="Drop a file, get the file you wanted.\nEverything runs on your computer.",
            website=WEBSITE,
            issue_url=ISSUES_URL,
            license_type=Gtk.License.GPL_3_0,
            developers=["Erwin Lejeune https://github.com/guilyx"],
        )
        about.add_credit_section(
            "Powered by",
            ["FFmpeg", "libvips", "ImageMagick", "LibreOffice", "Pandoc", "Ghostscript"],
        )
        about.present(self.show_panel())

    def undo(self) -> None:
        result = self.history.undo_last()
        panel = self.show_panel()
        if result is None:
            panel.toast("Nothing to undo.")
            return
        entry, trashed = result
        files = "file" if len(trashed) == 1 else "files"
        panel.toast(f"Moved {len(trashed)} {files} from “{entry.preset_name}” to the trash.")

    def quit_app(self) -> None:
        if self.runner.busy:
            self.runner.cancel_all()
        self.quit()

    def _on_wheel_files(self, _action: Gio.SimpleAction, param: GLib.Variant) -> None:
        self.show_wheel([Path(p) for p in param.unpack()], overlay=True)

    def _on_stage_files(self, _action: Gio.SimpleAction, param: GLib.Variant) -> None:
        panel = self.show_panel()
        panel.stage([Path(p) for p in param.unpack()])

    def _on_run_preset(self, _action: Gio.SimpleAction, param: GLib.Variant) -> None:
        preset_id, paths = param.unpack()
        try:
            preset = self.registry.get(preset_id)
        except Exception as exc:  # unknown id from an old menu entry
            log.warning("run-preset: %s", exc)
            return
        self.convert(preset, [Path(p) for p in paths])

    def do_before_emit(self, platform_data: GLib.Variant) -> None:
        Adw.Application.do_before_emit(self, platform_data)
        token = platform_data.lookup_value("activation-token", GLib.VariantType("s"))
        self._activation_token = token.unpack() if token else None

    def _take_activation_token(self) -> str | None:
        token, self._activation_token = self._activation_token, None
        return token

    def _visible_panel(self) -> DropPanel | None:
        return self.panel if self.panel and self.panel.get_visible() else None

    def _on_open_file(self, _action: Gio.SimpleAction, param: GLib.Variant) -> None:
        uri = param.unpack()
        token = self._take_activation_token()
        if token and not self._visible_panel():
            try:
                Gio.AppInfo.launch_default_for_uri(uri, _TokenLaunchContext(token))
                return
            except GLib.Error as exc:
                log.debug("Couldn't open %s with a token: %s", uri, exc.message)
        launcher = Gtk.FileLauncher(file=Gio.File.new_for_uri(uri))
        launcher.launch(self._visible_panel(), None, None)

    def _on_show_in_folder(self, _action: Gio.SimpleAction, param: GLib.Variant) -> None:
        uri = param.unpack()
        token = self._take_activation_token()

        def fallback() -> None:
            launcher = Gtk.FileLauncher(file=Gio.File.new_for_uri(uri))
            launcher.open_containing_folder(self._visible_panel(), None, None)

        bus = self.get_dbus_connection()
        if not token or bus is None or self._visible_panel():
            fallback()
            return

        def done(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                conn.call_finish(result)
            except GLib.Error as exc:
                log.debug("ShowItems failed (%s), using the file launcher", exc.message)
                fallback()

        # The call GTK makes too, plus the token so the file manager comes forward.
        bus.call(
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            "ShowItems",
            GLib.Variant("(ass)", ([uri], token)),
            None,
            Gio.DBusCallFlags.NONE,
            5000,
            None,
            done,
        )

    # -- conversions ------------------------------------------------------------

    def convert(self, preset: Preset, paths: list[Path]) -> Batch:
        self.hold()  # finish conversions even if the panel closes
        batch = self.runner.submit(
            preset,
            paths,
            recursive=self.settings.recursive_folders,
            out_dir=self.settings.output_path,
        )
        if self.panel:
            self.panel.batch_started(batch)
        return batch

    def _on_job_update(self, job: Any) -> bool:
        if self.panel:
            self.panel.job_updated(job)
        return GLib.SOURCE_REMOVE

    def _on_batch_done(self, batch: Batch) -> bool:
        try:
            self.history.record(batch)
        except OSError as exc:
            log.warning("Couldn't save history: %s", exc)
        if self.panel:
            self.panel.batch_done(batch)
        panel_in_view = bool(self.panel and self.panel.get_visible() and self.panel.is_active())
        if self.settings.notifications and not panel_in_view and batch.jobs:
            self._notify(batch)
        self.release()
        return GLib.SOURCE_REMOVE

    def _notify(self, batch: Batch) -> None:
        done = [j for j in batch.jobs if j.state == JobState.DONE]
        failed = [j for j in batch.jobs if j.state == JobState.FAILED]
        if failed and not done:
            title = (
                f"Couldn't convert {failed[0].source.name}"
                if len(failed) == 1
                else f"{len(failed)} files couldn't be converted"
            )
            body = failed[0].message
        elif done:
            title = f"{batch.preset.name}: {batch.summary()}"
            if len(done) == 1:
                job = done[0]
                title = f"{job.outputs[0].name} is ready"
                body = f"{human_size(job.input_bytes)} → {human_size(job.output_bytes)}"
            else:
                body = ", ".join(p.name for p in batch.outputs[:3])
        else:
            title = f"{batch.preset.name}: {batch.summary()}"
            body = next((j.message for j in batch.jobs if j.message), "")
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        if batch.outputs:
            uri = GLib.Variant("s", batch.outputs[0].as_uri())
            notification.set_default_action_and_target("app.show-in-folder", uri)
            if len(batch.outputs) == 1:
                notification.add_button_with_target("Open", "app.open-file", uri)
            notification.add_button_with_target("Show in Folder", "app.show-in-folder", uri)
        self.send_notification(f"batch-{id(batch)}", notification)

    # -- X11 Shift-drag -----------------------------------------------------------

    def note_drop(self) -> None:
        self._last_drop = time.monotonic()

    def _start_shift_drag(self) -> None:
        if (
            session.session_type() != "x11"
            or not self.settings.shift_drag
            or not x11_drag.available()
        ):
            return
        self._watcher = x11_drag.ShiftDragWatcher(
            on_shift_drag=lambda x, y: GLib.idle_add(self._on_shift_drag, x, y),
            on_drag_end=lambda: GLib.idle_add(self._on_drag_end),
        )
        self._watcher.start()
        log.info("Shift-drag is on: hold Shift while dragging a file to open the wheel")

    def _on_shift_drag(self, x: int, y: int) -> bool:
        """X11: a drag started with Shift held. Open the wheel around the pointer."""
        if self.panel and self.panel.get_visible() and self.panel.is_active():
            return GLib.SOURCE_REMOVE  # already dragging onto the panel
        self._drag_started_at = time.monotonic()
        self._opened_by_drag = True
        self.show_wheel(overlay=True, pointer=(x, y))
        return GLib.SOURCE_REMOVE

    def _on_drag_end(self) -> bool:
        if self._opened_by_drag:
            GLib.timeout_add(450, self._hide_if_unused)
        return GLib.SOURCE_REMOVE

    def _hide_if_unused(self) -> bool:
        """Released somewhere else: put the wheel away again."""
        dropped = self._last_drop >= self._drag_started_at
        if self.wheel and not dropped:
            self.wheel.dismiss()
        self._opened_by_drag = False
        return GLib.SOURCE_REMOVE


def main(argv: list[str]) -> int:
    from .launcher import main as launch

    return launch(argv)
