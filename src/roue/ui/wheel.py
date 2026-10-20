"""The wheel: Roue's radial menu.

It comes in two forms, sharing one view:

- **overlay**: a transparent full-screen layer with the wheel centred on the
  pointer. Used when the files are already known (Files > Convert with
  Roue…) and for Shift-drag on X11. Clicking outside the wheel closes it.
- **floating**: a small round window to drop files on (the hotkey). It also
  picks up files copied with Ctrl+C.

Up to seven presets fit the files best; the last slice, "More…", opens the
full panel.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cairo
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from ..engine.detect import mime_type
from ..engine.presets import Preset
from ..radial import DEFAULT, choose_presets, clamp_center, slice_anchor, slice_at, slice_span

if TYPE_CHECKING:
    from .application import RoueApplication

GROUP_RGB = {
    "image": (0.149, 0.635, 0.412),
    "video": (0.878, 0.106, 0.141),
    "audio": (0.569, 0.255, 0.675),
    "document": (0.110, 0.443, 0.847),
    "custom": (0.902, 0.380, 0.0),
    "more": (0.369, 0.361, 0.392),
}
FALLBACK_ICONS = {
    "image": "image-x-generic-symbolic",
    "video": "video-x-generic-symbolic",
    "audio": "audio-x-generic-symbolic",
    "document": "x-office-document-symbolic",
}
OPEN_SECONDS = 0.14
POP = 8.0  # how far the hovered slice grows
SLICE_WIDTH = 92  # label width inside a slice


@dataclass(frozen=True)
class Slice:
    preset: Preset | None  # None is "More…"
    title: str
    subtitle: str
    icon: str
    group: str

    @classmethod
    def for_preset(cls, preset: Preset) -> Slice:
        if preset.output == "folder":
            sub = "folder"
        elif preset.output_ext == "same":
            sub = "same format"
        else:
            sub = f".{preset.output_ext}"
        return cls(preset, preset.name, sub, preset.icon, preset.group)

    @classmethod
    def more(cls) -> Slice:
        return cls(None, "More…", "all presets", "view-more-horizontal-symbolic", "more")


def files_label(files: list[Path]) -> str:
    if not files:
        return "Drop a file"
    if len(files) == 1:
        return files[0].name
    return f"{len(files)} files"


class WheelView(Gtk.Overlay):
    """Draws the wheel and its labels. The window decides what clicks mean."""

    def __init__(self) -> None:
        super().__init__()
        self.geometry = DEFAULT
        self.slices: list[Slice] = []
        self.center: tuple[float, float] | None = None
        self._requested: tuple[float, float] | None = None
        self.hover: int | None = None
        self.chosen: int | None = None
        self.dim = 0.0
        self._open = 0.0
        self._open_start = 0
        self._buttons: list[Gtk.Button] = []

        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_draw_func(self._draw)
        self.area.connect("resize", lambda *_: self._recenter())
        self.set_child(self.area)
        self.fixed = Gtk.Fixed(can_target=False)
        self.add_overlay(self.fixed)

        # Gtk.Fixed hands children their minimum size, so give labels real widths.
        self.hub = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.hub.set_size_request(int(2 * (self.geometry.inner - 12)), -1)
        self.hub.add_css_class("wheel-hub")
        self.hub_title = Gtk.Label(justify=Gtk.Justification.CENTER, ellipsize=3)
        self.hub_title.set_max_width_chars(12)
        self.hub_title.add_css_class("hub-title")
        self.hub_text = Gtk.Label(justify=Gtk.Justification.CENTER, wrap=True, lines=3)
        self.hub_text.set_ellipsize(3)
        self.hub_text.set_max_width_chars(14)
        self.hub_text.add_css_class("hub-text")
        self.hub.append(self.hub_title)
        self.hub.append(self.hub_text)
        self.fixed.put(self.hub, 0, 0)
        self.add_tick_callback(self._animate)

    # -- content ---------------------------------------------------------------

    def set_slices(self, slices: list[Slice], activate: Callable[[int], None]) -> None:
        for button in self._buttons:
            self.fixed.remove(button)
        self._buttons = []
        self.slices = slices
        self.hover = self.chosen = None
        for index, item in enumerate(slices):
            button = Gtk.Button(can_target=False)
            button.set_size_request(SLICE_WIDTH, -1)
            button.add_css_class("wheel-slice")
            button.add_css_class(f"group-{item.group}")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            image = Gtk.Image.new_from_icon_name(self._icon(item))
            image.set_pixel_size(22)
            box.append(image)
            title = Gtk.Label(label=item.title, justify=Gtk.Justification.CENTER)
            title.set_wrap(True)
            title.set_lines(2)
            title.set_ellipsize(3)
            title.set_max_width_chars(10)
            title.add_css_class("slice-title")
            box.append(title)
            sub = Gtk.Label(label=item.subtitle)
            sub.add_css_class("slice-sub")
            box.append(sub)
            button.set_child(box)
            description = item.preset.description if item.preset else "Open the full panel"
            button.update_property([Gtk.AccessibleProperty.LABEL], [f"{item.title}: {description}"])
            button.connect("clicked", lambda _b, i=index: activate(i))
            focus = Gtk.EventControllerFocus()
            focus.connect("enter", lambda _c, i=index: self.set_hover(i))
            button.add_controller(focus)
            self.fixed.put(button, 0, 0)
            self._buttons.append(button)
        self._layout()
        self.area.queue_draw()

    def _icon(self, item: Slice) -> str:
        display = self.get_display()
        theme = Gtk.IconTheme.get_for_display(display) if display else None
        if theme and theme.has_icon(item.icon):
            return item.icon
        return FALLBACK_ICONS.get(item.group, "system-run-symbolic")

    def set_hub(self, title: str, text: str) -> None:
        self.hub_title.set_text(title)
        self.hub_text.set_text(text)
        self._place(self.hub, 0.0, 0.0)

    def set_center(self, x: float, y: float) -> None:
        """Centre the wheel on a point (kept on screen), and start opening it."""
        if self._requested is None:
            self._open_start = 0
        self._requested = (x, y)
        self._recenter()

    def _recenter(self) -> None:
        if self._requested is None:
            return
        width, height = self.area.get_width(), self.area.get_height()
        x, y = self._requested
        if width > 0 and height > 0:
            x, y = clamp_center(x, y, width, height, self.geometry)
        self.center = (x, y)
        self._layout()
        self.area.queue_draw()

    def set_hover(self, index: int | None) -> None:
        if index == self.hover:
            return
        if self.hover is not None and self.hover < len(self._buttons):
            self._buttons[self.hover].remove_css_class("hot")
        self.hover = index
        if index is not None:
            self._buttons[index].add_css_class("hot")
        self._layout()
        self.area.queue_draw()

    def slice_at_point(self, x: float, y: float) -> int | None:
        if self.center is None:
            return None
        return slice_at(x - self.center[0], y - self.center[1], len(self.slices), self.geometry)

    def in_wheel(self, x: float, y: float) -> bool:
        if self.center is None:
            return False
        dist = math.hypot(x - self.center[0], y - self.center[1])
        return dist <= self.geometry.outer + self.geometry.reach

    def focus_slice(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].grab_focus()
            self.set_hover(index)

    # -- layout and drawing ------------------------------------------------------

    def _place(self, widget: Gtk.Widget, dx: float, dy: float) -> None:
        if self.center is None:
            return
        width = widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        height = widget.measure(Gtk.Orientation.VERTICAL, width)[0]
        self.fixed.move(widget, self.center[0] + dx - width / 2, self.center[1] + dy - height / 2)

    def _layout(self) -> None:
        g = self.geometry
        count = len(self._buttons)
        for index, button in enumerate(self._buttons):
            radius = (g.inner + g.outer) / 2 + (POP / 2 if index == self.hover else 0) + 4
            dx, dy = slice_anchor(index, count, radius)
            self._place(button, dx, dy)
        self._place(self.hub, 0.0, 0.0)
        self.fixed.set_visible(self.center is not None)

    def _animate(self, _widget: Gtk.Widget, clock: Gdk.FrameClock) -> bool:
        if self.center is None or self._open >= 1.0:
            return GLib.SOURCE_CONTINUE
        now = clock.get_frame_time()
        if not self._open_start:
            self._open_start = now
        t = min(1.0, (now - self._open_start) / 1e6 / OPEN_SECONDS)
        self._open = 1 - (1 - t) ** 3  # ease out
        self.fixed.set_opacity(self._open)
        self.area.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int) -> None:
        if self.dim:
            cr.set_source_rgba(0, 0, 0, self.dim * self._open)
            cr.paint()
        if self.center is None or not self.slices:
            return
        g = self.geometry
        cx, cy = self.center
        scale = 0.88 + 0.12 * self._open
        dark = Adw.StyleManager.get_default().get_dark()
        alpha = self._open

        shadow = cairo.RadialGradient(
            cx, cy + 10, g.outer * scale * 0.85, cx, cy + 10, (g.outer + 30) * scale
        )
        shadow.add_color_stop_rgba(0, 0, 0, 0, 0.32 * alpha)
        shadow.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(shadow)
        cr.arc(cx, cy + 10, (g.outer + 30) * scale, 0, 2 * math.pi)
        cr.fill()

        base = (0.19, 0.19, 0.21) if dark else (1.0, 1.0, 1.0)
        count = len(self.slices)
        for index, item in enumerate(self.slices):
            start, end = slice_span(index, count)
            start += g.gap / 2
            end -= g.gap / 2
            hot = index in (self.hover, self.chosen)
            outer = (g.outer + (POP if hot else 0)) * scale
            inner = g.inner * scale
            cr.new_path()
            cr.arc(cx, cy, outer, start, end)
            cr.arc_negative(cx, cy, inner, end, start)
            cr.close_path()
            if hot:
                r, gr, b = GROUP_RGB.get(item.group, GROUP_RGB["more"])
                cr.set_source_rgba(r, gr, b, alpha)
            else:
                cr.set_source_rgba(*base, 0.97 * alpha)
            cr.fill_preserve()
            edge = 1.0 if dark else 0.0
            cr.set_source_rgba(edge, edge, edge, 0.08 * alpha)
            cr.set_line_width(1)
            cr.stroke()

        hub = (g.inner - 6) * scale
        cr.arc(cx, cy, hub, 0, 2 * math.pi)
        cr.set_source_rgba(0.14, 0.14, 0.16, alpha)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.14 * alpha)
        cr.set_line_width(3)
        cr.stroke()


class WheelWindow(Gtk.Window):
    """A wheel on screen. ``files`` are converted when a slice is picked."""

    def __init__(
        self,
        app: RoueApplication,
        *,
        files: list[Path] | None = None,
        overlay: bool = False,
        pointer: tuple[float, float] | None = None,
    ):
        super().__init__(application=app, title="Convert with Roue", decorated=False)
        self.app = app
        self.files: list[Path] = list(files or [])
        self._dragged: list[Path] = []  # files hovering over the wheel in a drag
        self.overlay = overlay
        self._closing = False
        self.add_css_class("roue-wheel")
        if not self._transparent_ok():
            self.overlay = overlay = False
            self.add_css_class("opaque")

        self.view = WheelView()
        self.view.dim = 0.10 if overlay else 0.0
        self.set_child(self.view)
        self._rebuild()

        if overlay:
            monitor = self._monitor_at(pointer) if pointer else None
            if monitor is not None and pointer is not None:
                geo = monitor.get_geometry()
                self.set_default_size(geo.width, geo.height)
                self.fullscreen_on_monitor(monitor)
                self.view.set_center(pointer[0] - geo.x, pointer[1] - geo.y)
            else:
                self.fullscreen()
                # On Wayland the pointer position arrives with the first enter
                # event; if it never does (keyboard use), centre on screen.
                GLib.timeout_add(220, self._center_fallback)
        else:
            size = self.view.geometry.size
            self.set_default_size(size, size)
            self.set_resizable(False)
            self.view.set_center(size / 2, size / 2)
        self._install_controllers()

    # -- setup ------------------------------------------------------------------

    def _transparent_ok(self) -> bool:
        display = self.get_display() or Gdk.Display.get_default()
        return bool(display and display.is_composited())

    def _monitor_at(self, point: tuple[float, float]) -> Gdk.Monitor | None:
        display = self.get_display() or Gdk.Display.get_default()
        if display is None:
            return None
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            g = monitor.get_geometry()
            if g.x <= point[0] < g.x + g.width and g.y <= point[1] < g.y + g.height:
                return monitor
        return None

    def _center_fallback(self) -> bool:
        if self.view.center is None:
            self.view.set_center(self.view.get_width() / 2, self.view.get_height() / 2)
        return GLib.SOURCE_REMOVE

    def _install_controllers(self) -> None:
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_motion)
        motion.connect("motion", self._on_motion)
        self.view.add_controller(motion)

        click = Gtk.GestureClick(button=0)
        click.connect("released", self._on_click)
        self.view.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        target = Gtk.DropTarget.new(
            Gdk.FileList.__gtype__, Gdk.DragAction.COPY | Gdk.DragAction.MOVE
        )
        target.set_preload(True)
        target.connect("notify::value", self._on_drag_value)
        target.connect("motion", self._on_drag_motion)
        target.connect("leave", self._on_drag_leave)
        target.connect("drop", self._on_drop)
        self.view.add_controller(target)

    # -- content ------------------------------------------------------------------

    def _rebuild(self, mimes: list[str] | None = None) -> None:
        if mimes is None:
            mimes = [mime_type(p) for p in self.files]
        registry = self.app.registry.without(self.app.settings.disabled_presets)
        presets, more = choose_presets(registry, mimes)
        slices = [Slice.for_preset(p) for p in presets]
        if more or not slices:
            slices.append(Slice.more())
        self.view.set_slices(slices, self.choose)
        self._refresh_hub()

    def _refresh_hub(self, text: str | None = None) -> None:
        view = self.view
        if view.chosen is not None:
            return
        if view.hover is not None:
            item = view.slices[view.hover]
            detail = item.preset.description if item.preset else "Open the full panel."
            view.set_hub(item.title, text or detail)
            return
        if self.files:
            hint = "Pick a slice" if self.overlay else "Click a slice"
            view.set_hub(files_label(self.files), text or hint)
        elif self._dragged:
            view.set_hub(files_label(self._dragged), text or "Drop on a slice")
        else:
            view.set_hub("Drop a file", text or "on a slice. Or copy files first.")

    def stage(self, files: list[Path]) -> None:
        self.files = [p for p in files if p.exists()]
        self._rebuild()

    def paste_files(self) -> None:
        """Use files copied in Files, unless they were already used once."""
        clipboard = self.get_clipboard()
        if not clipboard.get_formats().contain_gtype(Gdk.FileList.__gtype__):
            return

        def done(cb: Gdk.Clipboard, result: Gio.AsyncResult) -> None:
            try:
                value = cb.read_value_finish(result)
            except GLib.Error:
                return
            paths = [Path(p) for f in value.get_files() if (p := f.get_path())] if value else []
            signature = tuple(str(p) for p in paths)
            if paths and signature != self.app.clipboard_seen and not self.files:
                self.app.clipboard_seen = signature
                self.stage(paths)

        clipboard.read_value_async(Gdk.FileList.__gtype__, GLib.PRIORITY_DEFAULT, None, done)

    # -- picking --------------------------------------------------------------------

    def choose(self, index: int, files: list[Path] | None = None) -> None:
        if self._closing or not 0 <= index < len(self.view.slices):
            return
        item = self.view.slices[index]
        files = files if files is not None else self.files
        if item.preset is None:
            panel = self.app.show_panel()
            if files:
                panel.stage(files)
            self.dismiss()
            return
        if not files:
            self._pick_files(item.preset)
            return
        matching = [p for p in files if item.preset.accepts_file(p)]
        if not matching:
            self._refresh_hub(f"{item.title} can't take these files.")
            return
        self.app.convert(item.preset, matching)
        self.app.clipboard_seen = tuple(str(p) for p in files)
        self.view.chosen = index
        self.view.set_hub(item.title, "Converting… You'll get a notification.")
        self.view.area.queue_draw()
        self._closing = True
        GLib.timeout_add(320, self._close_now)

    def _pick_files(self, preset: Preset) -> None:
        dialog = Gtk.FileDialog(title=f"Convert to {preset.name}")
        file_filter = Gtk.FileFilter(name=f"Files {preset.name} can take")
        for pattern in preset.accepts:
            file_filter.add_mime_type(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)

        def done(d: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                picked = d.open_multiple_finish(result)
            except GLib.Error:
                return
            paths = [
                Path(p) for i in range(picked.get_n_items()) if (p := picked.get_item(i).get_path())
            ]
            if paths:
                self.app.convert(preset, paths)
                self.dismiss()

        dialog.open_multiple(self, None, done)

    def dismiss(self) -> None:
        self._closing = True
        self.close()

    def _close_now(self) -> bool:
        self.close()
        return GLib.SOURCE_REMOVE

    # -- events -----------------------------------------------------------------------

    def _on_motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        if self.view.center is None and self.overlay:
            self.view.set_center(x, y)
            return
        self.view.set_hover(self.view.slice_at_point(x, y))
        self._refresh_hub()

    def _on_click(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        index = self.view.slice_at_point(x, y)
        if index is not None:
            self.choose(index)
        elif self.overlay and not self.view.in_wheel(x, y):
            self.dismiss()

    def _on_key(self, _c: Gtk.EventControllerKey, keyval: int, _code: int, state: int) -> bool:
        count = len(self.view.slices)
        current = self.view.hover
        if keyval == Gdk.KEY_Escape:
            self.dismiss()
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_Down, Gdk.KEY_Tab):
            self.view.focus_slice(0 if current is None else (current + 1) % count)
            self._refresh_hub()
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab):
            self.view.focus_slice(count - 1 if current is None else (current - 1) % count)
            self._refresh_hub()
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space) and current is not None:
            self.choose(current)
        elif Gdk.KEY_1 <= keyval <= Gdk.KEY_9 and keyval - Gdk.KEY_1 < count:
            self.choose(keyval - Gdk.KEY_1)
        elif keyval in (Gdk.KEY_v, Gdk.KEY_V) and state & Gdk.ModifierType.CONTROL_MASK:
            self.app.clipboard_seen = ()
            self.paste_files()
        else:
            return False
        return True

    @staticmethod
    def _offers_copy(target: Gtk.DropTarget) -> bool:
        drop = target.get_current_drop()
        return bool(drop and drop.get_actions() & Gdk.DragAction.COPY)

    def _on_drag_value(self, target: Gtk.DropTarget, _pspec: object) -> None:
        value = target.get_value()
        if value is None or self.files:
            return
        paths = [Path(p) for f in value.get_files() if (p := f.get_path())]
        if paths:
            self._dragged = paths
            self._rebuild([mime_type(p) for p in paths])

    def _on_drag_leave(self, _target: Gtk.DropTarget) -> None:
        self._dragged = []
        self.view.set_hover(None)
        self._refresh_hub()

    def _on_drag_motion(self, target: Gtk.DropTarget, x: float, y: float) -> Gdk.DragAction:
        if self.view.center is None:
            self.view.set_center(x, y)
        index = self.view.slice_at_point(x, y)
        self.view.set_hover(index)
        if not self._offers_copy(target):
            # Never accept a move: the source app could then delete the original.
            self._refresh_hub("Release Shift to drop.")
            return Gdk.DragAction(0)
        self._refresh_hub()
        return Gdk.DragAction.COPY if index is not None else Gdk.DragAction(0)

    def _on_drop(self, target: Gtk.DropTarget, value: Gdk.FileList, x: float, y: float) -> bool:
        if not self._offers_copy(target):
            self._refresh_hub("Release Shift before dropping.")
            return False
        paths = [Path(p) for f in value.get_files() if (p := f.get_path())]
        index = self.view.slice_at_point(x, y)
        if not paths or index is None:
            return False
        self.app.note_drop()
        self.choose(index, paths)
        return True
