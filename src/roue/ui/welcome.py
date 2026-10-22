"""First-run setup: how to open the wheel, and the tools conversions need.

Shown the first time Roue opens from the app grid, and from the main menu
(Set Up Roue…) after that. Every row shows what is already done, and offers
one button for what isn't.
"""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Callable
from typing import TYPE_CHECKING

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ..engine import tools
from ..integrations import desktop, gnome_shell, hotkey, packages, session, x11_drag
from . import compat

if TYPE_CHECKING:
    from .application import RoueApplication


class WelcomeDialog(compat.Dialog):
    def __init__(self, app: RoueApplication):
        super().__init__(title="Set Up Roue", content_width=560, content_height=680)
        self.app = app
        self._busy = False
        self.toasts = Adw.ToastOverlay()
        self.page = Adw.PreferencesPage()
        done = Gtk.Button(label="Done", halign=Gtk.Align.CENTER, margin_top=12, margin_bottom=12)
        done.add_css_class("pill")
        done.add_css_class("suggested-action")
        done.connect("clicked", lambda _b: self.close())
        self.toasts.set_child(compat.toolbar_view(Adw.HeaderBar(), self.page, done))
        self.set_child(self.toasts)
        self._groups: list[Adw.PreferencesGroup] = []
        self.refresh()
        self.connect("closed", self._on_closed)

    def _on_closed(self, _dialog: Gtk.Widget) -> None:
        if not self.app.settings.welcome_done:
            self.app.settings.welcome_done = True
            self.app.settings.save()

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text)))

    # -- content ----------------------------------------------------------------

    def refresh(self) -> None:
        for group in self._groups:
            self.page.remove(group)
        self._groups = [self._intro(), self._opening(), self._tools()]
        for group in self._groups:
            self.page.add(group)

    def _intro(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon = Gtk.Image.new_from_icon_name(self.app.get_application_id())
        icon.set_pixel_size(64)
        box.append(icon)
        title = Gtk.Label(label="Welcome to Roue")
        title.add_css_class("title-1")
        box.append(title)
        text = Gtk.Label(
            label="Convert files from a wheel of presets. Set up how you'll open it, "
            "and the tools the conversions use.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        text.add_css_class("dim-label")
        box.append(text)
        group.add(box)
        return group

    def _opening(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Open the Wheel")
        files = self._files_row()
        if files:
            group.add(files)
        group.add(self._hotkey_row())
        if gnome_shell.wanted():
            group.add(self._helper_row())
        if session.session_type() == "x11":
            group.add(self._shift_drag_row())
        return group

    def _tools(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Conversion Tools",
            description="Roue drives these programs. Everything runs on this computer.",
        )
        missing = packages.missing()
        if not missing:
            group.add(self._row("Everything is installed", "Every preset is ready.", done=True))
            return group
        installable = packages.can_install()
        for capability in missing:
            row = self._row(capability.title, capability.detail)
            if installable:
                names = packages.apt_packages([capability.install])
                row.add_suffix(self._button("Install", lambda b, n=names: self._install(b, n)))
            group.add(row)
        if not installable:
            command = tools.install_command([c.install for c in missing])
            if command:
                row = Adw.ActionRow(
                    title=command, title_selectable=True, subtitle="Run in a terminal"
                )
                row.add_css_class("monospace")
                row.add_suffix(self._button("Copy", lambda _b, c=command: self._copy(c)))
                group.add(row)
        return group

    # -- rows -----------------------------------------------------------------------

    def _row(self, title: str, subtitle: str, *, done: bool = False) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        if done:
            icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            icon.add_css_class("success")
            icon.set_tooltip_text("Done")
            row.add_suffix(icon)
        return row

    def _button(self, label: str, callback: Callable[[Gtk.Button], None]) -> Gtk.Button:
        button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
        button.connect("clicked", callback)
        return button

    def _files_row(self) -> Adw.ActionRow | None:
        title = "Right-click in Files"
        if not shutil.which("nautilus"):
            return None
        if not desktop.nautilus_python_available():
            row = self._row(title, "Needs the Files extension host, python3-nautilus")
            if packages.can_install():
                row.add_suffix(
                    self._button("Install", lambda b: self._install(b, ["python3-nautilus"]))
                )
            return row
        menu = desktop.desktop_targets(
            desktop.SYSTEM_DATA if desktop.system_installed("nautilus") else None
        )["nautilus"]
        if not menu.exists():
            row = self._row(title, "Adds Convert with Roue… to the right-click menu")
            row.add_suffix(self._button("Add", self._add_files_menu))
            return row
        if desktop.nautilus_started_before(menu.stat().st_mtime):
            row = self._row(title, "Files needs a restart to show the menu (its windows close)")
            row.add_suffix(self._button("Restart Files", self._restart_files))
            return row
        return self._row(
            title, "Ctrl+Shift+right-click files, or right-click > Convert with Roue…", done=True
        )

    def _hotkey_row(self) -> Adw.ActionRow:
        binding = hotkey.current_binding()
        if binding:
            accel = Gtk.accelerator_get_label(*Gtk.accelerator_parse(binding)[1:])
            return self._row("Keyboard shortcut", f"{accel} opens the wheel", done=True)
        if not hotkey.can_install():
            return self._row(
                "Keyboard shortcut",
                "Add a shortcut running “roue wheel” in your keyboard settings",
            )
        row = self._row("Keyboard shortcut", "Open the wheel from anywhere, drop files on it")
        row.add_suffix(self._button("Set Super+Shift+D", self._set_hotkey))
        return row

    def _helper_row(self) -> Adw.ActionRow:
        title = "Wheel on top, at the pointer"
        state = gnome_shell.state()
        if state is gnome_shell.State.ACTIVE:
            return self._row(title, "The Roue GNOME extension is on", done=True)
        if state is gnome_shell.State.PENDING:
            return self._row(title, "Starts after you log out and back in", done=True)
        if state is gnome_shell.State.ERROR:
            return self._row(title, "GNOME couldn't load the Roue extension")
        row = self._row(title, "A small GNOME extension that keeps the wheel above other windows")
        row.add_suffix(self._button("Turn On", self._enable_helper))
        return row

    def _shift_drag_row(self) -> Adw.ActionRow:
        title = "Shift-drag"
        if not x11_drag.available():
            row = self._row(title, "Needs python3-xlib")
            if packages.can_install():
                install = self._button("Install", lambda b: self._install(b, ["python3-xlib"]))
                row.add_suffix(install)
            return row
        return self._row(title, "Hold Shift while dragging a file to open the wheel", done=True)

    # -- actions --------------------------------------------------------------------

    def _add_files_menu(self, _button: Gtk.Button) -> None:
        desktop.install_nautilus_extension()
        self.refresh()

    def _restart_files(self, _button: Gtk.Button) -> None:
        desktop.restart_nautilus()
        self.toast("Files restarted")
        GLib.timeout_add(600, lambda: self.refresh() or GLib.SOURCE_REMOVE)

    def _set_hotkey(self, _button: Gtk.Button) -> None:
        try:
            hotkey.install(f"{desktop.roue_command()} wheel")
        except hotkey.HotkeyError as exc:
            self.toast(str(exc))
        self.refresh()

    def _enable_helper(self, _button: Gtk.Button) -> None:
        if not gnome_shell.installed():
            gnome_shell.install()
        state = gnome_shell.enable()
        if state is gnome_shell.State.PENDING:
            self.toast("It starts after you log out and back in")
        elif state is not gnome_shell.State.ACTIVE:
            self.toast("Couldn't turn on the GNOME extension")
        self.refresh()

    def _copy(self, text: str) -> None:
        display = Gdk.Display.get_default()
        if display:
            display.get_clipboard().set(text)
            self.toast("Copied")

    def _install(self, button: Gtk.Button, names: list[str]) -> None:
        if self._busy or not names:
            return
        self._busy = True
        button.set_sensitive(False)
        button.set_child(compat.spinner())
        try:
            proc = Gio.Subprocess.new(packages.install_argv(names), Gio.SubprocessFlags.NONE)
        except GLib.Error as exc:
            self._busy = False
            self.toast(f"Couldn't start the installer: {exc.message}")
            self.refresh()
            return

        def finished(p: Gio.Subprocess, result: Gio.AsyncResult) -> None:
            self._busy = False
            with contextlib.suppress(GLib.Error):
                p.wait_finish(result)
            status = p.get_exit_status() if p.get_if_exited() else -1
            if status == 0:
                self.toast(f"Installed {', '.join(names)}")
            else:  # 126: password dialog dismissed, 127: not allowed
                self.toast(f"Not installed. In a terminal: sudo apt install {' '.join(names)}")
            tools.which.cache_clear()
            self.app.tools_changed()
            self.refresh()

        proc.wait_async(None, finished)
