"""Preferences: how Roue opens, where results go, presets, and tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import WEBSITE
from ..engine import tools
from ..engine.backends import missing_tools
from ..engine.presets import GROUPS, user_preset_dir
from ..integrations import gnome_shell, hotkey, session, x11_drag
from ..integrations.desktop import roue_command
from . import compat

if TYPE_CHECKING:
    from .application import RoueApplication

EXAMPLE_PRESET = """\
# A custom preset. Copy this file, change it, and reopen the wheel.
# Full reference: {website}docs/custom-presets.html
id: my-webp-thumbnail
name: Thumbnail
description: 320 px wide WebP, for blog posts.
group: image
icon: image-x-generic-symbolic
accepts: ["image/*"]
output_ext: webp
suffix: " (thumb)"
backend: image
params:
  width: 320
  quality: 80
"""


class PreferencesDialog(compat.PreferencesDialog):
    def __init__(self, app: RoueApplication):
        super().__init__(title="Preferences")
        self.app = app
        self.settings = app.settings
        self.set_search_enabled(True)
        self.add(self._general_page())
        self.add(self._presets_page())
        self.add(self._tools_page())

    def _save(self) -> None:
        self.settings.save()
        self.app.settings_changed()

    def _switch(self, title: str, subtitle: str, key: str) -> Adw.ActionRow:
        row = compat.SwitchRow(title=title, subtitle=subtitle)
        row.set_active(bool(getattr(self.settings, key)))

        def changed(r: Adw.ActionRow, _pspec: object) -> None:
            setattr(self.settings, key, r.get_active())
            self._save()

        row.connect("notify::active", changed)
        return row

    # -- General ------------------------------------------------------------

    def _general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")

        opening = Adw.PreferencesGroup(
            title="Opening Roue", description=session.trigger_explanation()
        )
        self.hotkey_row = Adw.ActionRow(title="Keyboard shortcut")
        self.hotkey_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.hotkey_button.connect("clicked", self._on_hotkey_clicked)
        self.hotkey_row.add_suffix(self.hotkey_button)
        self._refresh_hotkey()
        opening.add(self.hotkey_row)

        shift = self._switch(
            "Shift-drag",
            "Hold Shift while dragging any file to open the wheel around it",
            "shift_drag",
        )
        if session.session_type() != "x11":
            shift.set_sensitive(False)
            shift.set_subtitle("Only on X11 sessions: Wayland keeps drags private")
        elif not x11_drag.available():
            shift.set_sensitive(False)
            shift.set_subtitle("Needs python3-xlib")
        opening.add(shift)
        if gnome_shell.wanted():
            self.helper_row = Adw.ActionRow(title="Wheel on top, at the pointer")
            self.helper_button = Gtk.Button(valign=Gtk.Align.CENTER)
            self.helper_button.connect("clicked", self._on_helper_clicked)
            self.helper_row.add_suffix(self.helper_button)
            self._refresh_helper()
            opening.add(self.helper_row)
        opening.add(
            self._switch(
                "Stay in the background",
                "Keeps Roue ready so the wheel opens instantly",
                "stay_in_background",
            )
        )
        page.add(opening)

        results = Adw.PreferencesGroup(title="Results")
        folder_row = Adw.ActionRow(title="Save results")
        self.folder_label = Gtk.Label(valign=Gtk.Align.CENTER, ellipsize=1)
        self.folder_label.add_css_class("dim-label")
        folder_row.add_suffix(self.folder_label)
        pick = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
        pick.set_tooltip_text("Choose a folder")
        pick.add_css_class("flat")
        pick.connect("clicked", self._on_pick_folder)
        folder_row.add_suffix(pick)
        self.reset_folder = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER)
        self.reset_folder.set_tooltip_text("Save next to the original again")
        self.reset_folder.add_css_class("flat")
        self.reset_folder.connect("clicked", self._on_reset_folder)
        folder_row.add_suffix(self.reset_folder)
        self._refresh_folder()
        results.add(folder_row)
        results.add(
            self._switch(
                "Notifications",
                "Tell me when conversions finish in the background",
                "notifications",
            )
        )
        results.add(
            self._switch(
                "Include sub-folders",
                "When a folder is dropped, convert files in its sub-folders too",
                "recursive_folders",
            )
        )
        jobs = compat.SpinRow.new_with_range(0, 64, 1)
        jobs.set_title("Parallel conversions")
        jobs.set_subtitle("0 means one per processor core")
        jobs.set_value(self.settings.max_jobs)

        def jobs_changed(row: Adw.ActionRow, _pspec: object) -> None:
            self.settings.max_jobs = int(row.get_value())
            self._save()

        jobs.connect("notify::value", jobs_changed)
        results.add(jobs)
        page.add(results)
        return page

    def _refresh_hotkey(self) -> None:
        binding = hotkey.current_binding()
        if binding:
            accel = Gtk.accelerator_get_label(*Gtk.accelerator_parse(binding)[1:])
            self.hotkey_row.set_subtitle(f"{accel} opens the wheel")
            self.hotkey_button.set_label("Remove")
        else:
            self.hotkey_row.set_subtitle("Not set")
            self.hotkey_button.set_label("Set Super+Shift+D")
        self.hotkey_button.set_sensitive(hotkey.can_install())
        if not hotkey.can_install():
            self.hotkey_row.set_subtitle(
                "Add a custom shortcut running “roue wheel” in your keyboard settings"
            )

    def _on_hotkey_clicked(self, _button: Gtk.Button) -> None:
        try:
            if hotkey.current_binding():
                hotkey.remove()
            else:
                hotkey.install(f"{roue_command()} wheel")
        except hotkey.HotkeyError as exc:
            self.add_toast(Adw.Toast(title=GLib.markup_escape_text(str(exc))))
        self._refresh_hotkey()

    def _refresh_helper(self) -> None:
        state = gnome_shell.state()
        self.helper_row.set_subtitle(f"Roue's GNOME extension: {gnome_shell.describe(state)}")
        on = state in (gnome_shell.State.ACTIVE, gnome_shell.State.PENDING)
        self.helper_button.set_label("Turn Off" if on else "Turn On")
        self.helper_button.set_sensitive(state is not gnome_shell.State.ERROR)

    def _on_helper_clicked(self, _button: Gtk.Button) -> None:
        if gnome_shell.state() in (gnome_shell.State.ACTIVE, gnome_shell.State.PENDING):
            gnome_shell.disable()
        else:
            if not gnome_shell.installed():
                gnome_shell.install()
            gnome_shell.enable()
        self._refresh_helper()

    def _refresh_folder(self) -> None:
        path = self.settings.output_path
        self.folder_label.set_text(str(path) if path else "Next to the original")
        self.reset_folder.set_visible(path is not None)

    def _on_pick_folder(self, _button: Gtk.Button) -> None:
        def chosen(folder: Gio.File) -> None:
            if folder.get_path():
                self.settings.output_dir = folder.get_path()
                self._save()
                self._refresh_folder()

        compat.choose_folder(self.get_root(), "Save Results In", chosen)

    def _on_reset_folder(self, _button: Gtk.Button) -> None:
        self.settings.output_dir = None
        self._save()
        self._refresh_folder()

    # -- Presets --------------------------------------------------------------

    def _presets_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Presets", icon_name="view-grid-symbolic")
        custom = Adw.PreferencesGroup(
            title="Your Own Presets",
            description="Presets are small YAML files. Add yours to the presets folder.",
        )
        open_row = Adw.ActionRow(title="Open presets folder", activatable=True)
        open_row.add_suffix(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        open_row.connect("activated", self._on_open_presets_folder)
        custom.add(open_row)
        docs_row = Adw.ActionRow(title="How to write a preset", activatable=True)
        docs_row.add_suffix(Gtk.Image.new_from_icon_name("adw-external-link-symbolic"))
        docs_row.connect(
            "activated",
            lambda *_: compat.launch(self.get_root(), f"{WEBSITE}docs/custom-presets.html"),
        )
        custom.add(docs_row)
        for problem in self.app.registry.problems:
            row = Adw.ActionRow(title="A preset file has a problem", subtitle=problem)
            row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
            custom.add(row)
        page.add(custom)

        for group, presets in self.app.registry.by_group().items():
            box = Adw.PreferencesGroup(title=GROUPS.get(group, group.title()))
            for preset in presets:
                row = compat.SwitchRow(title=preset.name, subtitle=preset.description)
                row.set_active(preset.id not in self.settings.disabled_presets)
                if missing_tools(preset):
                    row.set_subtitle(f"{preset.description} (needs tools, see Tools)")
                row.connect("notify::active", self._on_preset_toggled, preset.id)
                box.add(row)
            page.add(box)
        return page

    def _on_preset_toggled(self, row: Adw.ActionRow, _pspec: object, preset_id: str) -> None:
        disabled = [p for p in self.settings.disabled_presets if p != preset_id]
        if not row.get_active():
            disabled.append(preset_id)
        self.settings.disabled_presets = disabled
        self._save()

    def _on_open_presets_folder(self, _row: Adw.ActionRow) -> None:
        folder = user_preset_dir()
        folder.mkdir(parents=True, exist_ok=True)
        example = folder / "example.yaml.disabled"
        if not any(folder.iterdir()):
            example.write_text(EXAMPLE_PRESET.format(website=WEBSITE), encoding="utf-8")
        compat.launch(self.get_root(), folder.as_uri())

    # -- Tools ------------------------------------------------------------------

    def _tools_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Tools", icon_name="applications-engineering-symbolic")
        group = Adw.PreferencesGroup(
            title="Conversion Tools",
            description="Roue drives these programs. Everything runs on this computer.",
        )
        missing: list[str] = []
        for tool in tools.TOOLS.values():
            path = tools.which(tool.id)
            row = Adw.ActionRow(title=tool.label, subtitle=tool.purpose)
            icon = Gtk.Image.new_from_icon_name(
                "emblem-ok-symbolic" if path else "dialog-warning-symbolic"
            )
            icon.add_css_class("success" if path else "warning")
            row.add_suffix(icon)
            if path:
                row.set_tooltip_text(path)
            else:
                missing.append(tool.id)
            group.add(row)
        page.add(group)
        command = tools.install_command(missing) if missing else None
        if command:
            install = Adw.PreferencesGroup(
                title="Install Missing Tools", description="Run this in a terminal:"
            )
            row = Adw.ActionRow(title=command, title_selectable=True)
            row.add_css_class("monospace")
            copy = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
            copy.add_css_class("flat")
            copy.set_tooltip_text("Copy")

            def copy_command(*_args: object) -> None:
                display = Gdk.Display.get_default()
                if display:
                    display.get_clipboard().set(command)
                    self.add_toast(Adw.Toast(title="Copied"))

            copy.connect("clicked", copy_command)
            row.add_suffix(copy)
            install.add(row)
            page.add(install)
        return page
