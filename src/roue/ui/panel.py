"""The drop panel: preset tiles grouped by kind, a drop target, and staging.

Ways in:
- drag files onto a tile (dims tiles that can't take them)
- copy files in Files (Ctrl+C), open the panel, click a tile
- click a tile to pick files, or press Ctrl+O
- type to search presets, Enter runs the first match
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ..engine.detect import mime_type
from ..engine.presets import GROUPS, Preset
from ..engine.runner import Batch, Job, JobState
from ..integrations import session
from . import compat
from .tile import PresetTile

if TYPE_CHECKING:
    from .application import RoueApplication


def _paths_from(files: Iterable[Gio.File]) -> list[Path]:
    return [Path(p) for f in files if (p := f.get_path())]


class DropPanel(Adw.ApplicationWindow):
    def __init__(self, app: RoueApplication):
        super().__init__(application=app, title="Roue")
        self.app = app
        self.set_default_size(800, 640)
        self.set_size_request(380, 320)
        self.add_css_class("roue-panel")
        self.tiles: dict[str, PresetTile] = {}
        self.sections: dict[str, tuple[Gtk.Widget, Gtk.FlowBox]] = {}
        self.staged: list[Path] = []
        self.staged_from_clipboard = False
        self._hover: PresetTile | None = None
        self._jobs: dict[str, dict[int, Job]] = {}
        self._running: set[Batch] = set()

        self.toasts = Adw.ToastOverlay()
        view = compat.toolbar_view(self._build_header(), self._build_body(), self._build_status())
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self._build_tiles()
        self._install_drop_target()
        self._install_shortcuts()
        self.connect("close-request", self._on_close_request)
        self.connect("notify::is-active", self._on_active_changed)
        self._update_status()

    # -- layout -------------------------------------------------------------

    def _build_header(self) -> Gtk.Widget:
        header = Adw.HeaderBar()
        self.search = Gtk.SearchEntry(placeholder_text="Search presets")
        self.search.set_hexpand(True)
        self.search.set_max_width_chars(28)
        self.search.update_property([Gtk.AccessibleProperty.LABEL], ["Search presets"])
        self.search.connect("search-changed", lambda *_: self._apply_filter())
        self.search.connect("activate", lambda *_: self._activate_first_match())
        self.search.set_key_capture_widget(self)
        header.set_title_widget(self.search)

        open_button = Gtk.Button(icon_name="document-open-symbolic")
        open_button.set_tooltip_text("Choose files to convert (Ctrl+O)")
        open_button.set_action_name("win.open-files")
        header.pack_start(open_button)

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Recent Conversions", "app.history")
        section.append("Undo Last Conversion", "app.undo")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append("Set Up Roue…", "app.welcome")
        section.append("Preferences", "app.preferences")
        section.append("About Roue", "app.about")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append("Quit", "app.quit")
        menu.append_section(None, section)
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text("Main menu")
        menu_button.set_primary(True)
        header.pack_end(menu_button)
        return header

    def _build_body(self) -> Gtk.Widget:
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.staged_revealer = Gtk.Revealer()
        bar = Gtk.Box(spacing=10)
        bar.add_css_class("staged-bar")
        bar.append(Gtk.Image.new_from_icon_name("edit-paste-symbolic"))
        self.staged_label = Gtk.Label(xalign=0, hexpand=True)
        self.staged_label.set_ellipsize(3)
        bar.append(self.staged_label)
        clear = Gtk.Button(label="Clear")
        clear.add_css_class("flat")
        clear.connect("clicked", lambda *_: self.clear_staged())
        bar.append(clear)
        self.staged_revealer.set_child(bar)
        body.append(self.staged_revealer)

        self.stack = Gtk.Stack()
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.groups_box.set_margin_start(12)
        self.groups_box.set_margin_end(12)
        self.groups_box.set_margin_bottom(12)
        clamp = Adw.Clamp(maximum_size=900, child=self.groups_box)
        scroller.set_child(clamp)
        self.scroller = scroller
        self.stack.add_named(scroller, "tiles")
        empty = Adw.StatusPage(
            icon_name="edit-find-symbolic",
            title="No Matching Presets",
            description="Try “gif”, “discord”, “pdf” or “privacy”.",
        )
        self.stack.add_named(empty, "empty")
        body.append(self.stack)
        return body

    def _build_status(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=8)
        bar.add_css_class("status-bar")
        self.status_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.status_label.add_css_class("dim-label")
        bar.append(self.status_label)
        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.add_css_class("flat")
        self.cancel_button.set_visible(False)
        self.cancel_button.connect("clicked", lambda *_: self.app.runner.cancel_all())
        bar.append(self.cancel_button)
        return bar

    def _build_tiles(self) -> None:
        child = self.groups_box.get_first_child()
        while child:
            self.groups_box.remove(child)
            child = self.groups_box.get_first_child()
        self.tiles.clear()
        self.sections.clear()
        for group, presets in self.app.visible_presets().items():
            heading = Gtk.Box(spacing=8, margin_top=16, margin_bottom=6, margin_start=8)
            dot = Gtk.Box(valign=Gtk.Align.CENTER)
            dot.add_css_class("group-dot")
            dot.add_css_class(group)
            heading.append(dot)
            title = GROUPS.get(group, group.title()).upper()
            label = Gtk.Label(label=title, xalign=0)
            label.add_css_class("group-heading")
            heading.append(label)
            flow = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE,
                homogeneous=True,
                min_children_per_line=3,
                max_children_per_line=8,
                column_spacing=2,
                row_spacing=2,
            )
            for preset in presets:
                tile = PresetTile(preset)
                tile.connect("clicked", self._on_tile_clicked)
                flow.append(tile)
                tile.get_parent().set_focusable(False)
                self.tiles[preset.id] = tile
            self.groups_box.append(heading)
            self.groups_box.append(flow)
            self.sections[group] = (heading, flow)
        self._apply_filter()

    def rebuild(self) -> None:
        self._build_tiles()
        self._refresh_compatibility()

    # -- staging --------------------------------------------------------------

    def stage(self, paths: list[Path], *, from_clipboard: bool = False) -> None:
        self.staged = [p for p in paths if p.exists()]
        self.staged_from_clipboard = from_clipboard
        if not self.staged:
            self.clear_staged()
            return
        names = ", ".join(p.name for p in self.staged[:3])
        more = f" and {len(self.staged) - 3} more" if len(self.staged) > 3 else ""
        source = "Copied" if from_clipboard else "Ready"
        self.staged_label.set_markup(
            f"<b>{source}:</b> {GLib.markup_escape_text(names + more)} · pick a tile"
        )
        self.staged_revealer.set_reveal_child(True)
        self._refresh_compatibility()

    def clear_staged(self) -> None:
        self.staged = []
        self.staged_revealer.set_reveal_child(False)
        self._refresh_compatibility()

    def _refresh_compatibility(self, mimes: list[str] | None = None) -> None:
        if mimes is None:
            mimes = [mime_type(p) for p in self.staged]
        for tile in self.tiles.values():
            tile.set_compatible(not mimes or all(tile.preset.accepts_mime(m) for m in mimes))
        self._update_status()

    def paste_files(self, *, automatic: bool = False) -> None:
        clipboard = self.get_clipboard()
        if not clipboard.get_formats().contain_gtype(Gdk.FileList.__gtype__):
            if not automatic:
                self.toast("The clipboard has no files. Copy some in Files first.")
            return

        def done(cb: Gdk.Clipboard, result: Gio.AsyncResult) -> None:
            try:
                value = cb.read_value_finish(result)
            except GLib.Error:
                return
            paths = _paths_from(value.get_files()) if value else []
            signature = tuple(str(p) for p in paths)
            if automatic and signature == self.app.clipboard_seen:
                return
            self.app.clipboard_seen = signature
            if paths:
                self.stage(paths, from_clipboard=True)

        clipboard.read_value_async(Gdk.FileList.__gtype__, GLib.PRIORITY_DEFAULT, None, done)

    # -- drag and drop --------------------------------------------------------

    def _install_drop_target(self) -> None:
        # Shift (the X11 trigger) also means "move" to drag sources, and GTK then
        # offers the drop as MOVE only. Listening for MOVE keeps the target engaged
        # so the drop works once Shift is released; we only ever accept COPY.
        target = Gtk.DropTarget.new(
            Gdk.FileList.__gtype__, Gdk.DragAction.COPY | Gdk.DragAction.MOVE
        )
        target.set_preload(True)
        target.connect("notify::value", self._on_drag_value)
        target.connect("motion", self._on_drag_motion)
        target.connect("leave", self._on_drag_leave)
        target.connect("drop", self._on_drop)
        self.add_controller(target)

    def _on_drag_value(self, target: Gtk.DropTarget, _pspec: object) -> None:
        value = target.get_value()
        if value is None:
            return
        paths = _paths_from(value.get_files())
        self._refresh_compatibility([mime_type(p) for p in paths] or None)
        first = next((t for t in self.tiles.values() if t.compatible), None)
        if first:
            self._scroll_to(first)

    def _tile_at(self, x: float, y: float) -> PresetTile | None:
        widget = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None and not isinstance(widget, PresetTile):
            widget = widget.get_parent()
        return widget

    def _set_hover(self, tile: PresetTile | None) -> None:
        if self._hover is not tile:
            if self._hover:
                self._hover.set_hover(False)
            if tile:
                tile.set_hover(True)
            self._hover = tile

    @staticmethod
    def _offers_copy(target: Gtk.DropTarget) -> bool:
        drop = target.get_current_drop()
        return bool(drop and drop.get_actions() & Gdk.DragAction.COPY)

    def _on_drag_motion(self, target: Gtk.DropTarget, x: float, y: float) -> Gdk.DragAction:
        if not self._offers_copy(target):
            # Never accept a move: the source app could then delete the original.
            self._set_hover(None)
            self.status_label.set_text("Release Shift to drop. Roue copies, never moves.")
            return Gdk.DragAction(0)
        self._update_status()
        tile = self._tile_at(x, y)
        usable = tile if tile and tile.compatible and tile.available else None
        self._set_hover(usable)
        if tile and not usable:
            return Gdk.DragAction(0)
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, _target: Gtk.DropTarget) -> None:
        self._set_hover(None)
        self._refresh_compatibility()

    def _on_drop(self, target: Gtk.DropTarget, value: Gdk.FileList, x: float, y: float) -> bool:
        self._set_hover(None)
        if not self._offers_copy(target):
            self.toast("Release Shift before dropping: Shift asks to move the file.")
            self._refresh_compatibility()
            return False
        paths = _paths_from(value.get_files())
        if not paths:
            self.toast("Only local files can be converted.")
            self._refresh_compatibility()
            return False
        self.app.note_drop()
        tile = self._tile_at(x, y)
        if tile and tile.compatible and tile.available:
            self.app.convert(tile.preset, paths)
            self._refresh_compatibility()
        else:
            self.stage(paths)
        return True

    # -- actions --------------------------------------------------------------

    def _install_shortcuts(self) -> None:
        for name, callback in (
            ("open-files", lambda *_: self.choose_files(None)),
            ("paste", lambda *_: self.paste_files()),
            ("search", lambda *_: self.search.grab_focus()),
            ("hide", lambda *_: self.close()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        app = self.app
        app.set_accels_for_action("win.open-files", ["<Control>o"])
        app.set_accels_for_action("win.paste", ["<Control>v"])
        app.set_accels_for_action("win.search", ["<Control>f"])
        app.set_accels_for_action("win.hide", ["Escape", "<Control>w"])

    def _on_tile_clicked(self, tile: PresetTile) -> None:
        if not tile.available:
            self.toast(f"{tile.preset.name} needs tools that aren't installed. See Preferences.")
            return
        if self.staged:
            matching = [p for p in self.staged if tile.preset.accepts_file(p)]
            if not matching:
                self.toast(f"{tile.preset.name} can't take these files.")
                return
            self.app.convert(tile.preset, matching)
            self.clear_staged()
            return
        self.choose_files(tile.preset)

    def _activate_first_match(self) -> None:
        for tile in self.tiles.values():
            if tile.get_parent().get_visible() and tile.compatible and tile.available:
                self._on_tile_clicked(tile)
                return

    def choose_files(self, preset: Preset | None) -> None:
        file_filter = None
        if preset:
            file_filter = Gtk.FileFilter(name=f"Files {preset.name} can take")
            for pattern in preset.accepts:
                file_filter.add_mime_type(pattern)

        def chosen(files: list[Gio.File]) -> None:
            paths = _paths_from(files)
            if preset:
                self.app.convert(preset, paths)
            else:
                self.stage(paths)

        title = f"Convert to {preset.name}" if preset else "Choose Files"
        compat.choose_files(self, title, chosen, file_filter)

    # -- jobs -----------------------------------------------------------------

    def batch_started(self, batch: Batch) -> None:
        self._running.add(batch)
        tile = self.tiles.get(batch.preset.id)
        if tile:
            tile.set_progress(None)
        self._update_status()

    def job_updated(self, job: Job) -> None:
        jobs = self._jobs.setdefault(job.preset.id, {})
        if job.state.finished:
            jobs.pop(job.id, None)
        else:
            jobs[job.id] = job
        tile = self.tiles.get(job.preset.id)
        if tile and jobs:
            fractions = [j.progress for j in jobs.values()]
            known = [f for f in fractions if f is not None]
            tile.set_progress(sum(known) / len(fractions) if len(known) == len(fractions) else None)
        self._update_status()

    def batch_done(self, batch: Batch) -> None:
        self._running.discard(batch)
        tile = self.tiles.get(batch.preset.id)
        if tile and not self._jobs.get(batch.preset.id):
            tile.show_result(batch.count(JobState.FAILED) == 0)
        self._update_status()
        self.toast_for(batch)

    def toast_for(self, batch: Batch) -> None:
        failed = [j for j in batch.jobs if j.state == JobState.FAILED]
        if failed:
            first = failed[0]
            title = f"{first.source.name}: {first.message}"
            if len(failed) > 1:
                title = f"{len(failed)} files failed. {first.source.name}: {first.message}"
            toast = Adw.Toast(title=GLib.markup_escape_text(title), timeout=8)
        elif batch.count(JobState.DONE) == 0:
            skipped = next((j for j in batch.jobs if j.message), None)
            message = skipped.message if skipped else "Nothing to convert."
            toast = Adw.Toast(title=GLib.markup_escape_text(message), timeout=5)
        else:
            outputs = batch.outputs
            title = outputs[0].name if len(outputs) == 1 else batch.summary()
            toast = Adw.Toast(title=GLib.markup_escape_text(f"✓ {title}"), timeout=5)
            toast.set_button_label("Show")
            toast.set_action_name("app.show-in-folder")
            toast.set_action_target_value(GLib.Variant("s", outputs[0].as_uri()))
        self.toasts.add_toast(toast)

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(message), timeout=4))

    def _update_status(self) -> None:
        active = [j for jobs in self._jobs.values() for j in jobs.values()]
        self.cancel_button.set_visible(bool(active))
        if active:
            total = sum(len(b.jobs) for b in self._running)
            done = sum(1 for b in self._running for j in b.jobs if j.state.finished)
            self.status_label.set_text(f"Converting {min(done + 1, total)} of {total}…")
        elif self.staged:
            self.status_label.set_text("Click a tile, or type its name and press Enter.")
        else:
            hint = "Drop files on a tile · Ctrl+V uses copied files · Esc closes"
            if session.session_type() == "x11" and self.app.settings.shift_drag:
                hint = "Drop files on a tile · Shift-drag opens this anywhere · Esc closes"
            self.status_label.set_text(hint)

    # -- search & misc --------------------------------------------------------

    def _apply_filter(self) -> None:
        query = self.search.get_text().strip()
        any_visible = False
        for _group, (heading, flow) in self.sections.items():
            group_visible = False
            child = flow.get_first_child()
            while child:
                tile = child.get_child()
                visible = not query or tile.preset.matches_query(query)
                child.set_visible(visible)
                group_visible |= visible
                child = child.get_next_sibling()
            heading.set_visible(group_visible)
            flow.set_visible(group_visible)
            any_visible |= group_visible
        self.stack.set_visible_child_name("tiles" if any_visible else "empty")

    def _scroll_to(self, tile: PresetTile) -> None:
        ok, bounds = tile.compute_bounds(self.groups_box)
        if ok:
            adjustment = self.scroller.get_vadjustment()
            adjustment.set_value(max(0, bounds.get_y() - 40))

    def _on_active_changed(self, *_args: object) -> None:
        if self.is_active():
            self.paste_files(automatic=True)

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        self.search.set_text("")
        self.clear_staged()
        if self.app.settings.stay_in_background or self.app.runner.busy:
            self.set_visible(False)
            return True  # keep the window around: reopening is instant
        return False
