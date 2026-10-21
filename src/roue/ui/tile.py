"""A preset tile: icon badge, name, output format, and a progress ring."""

from __future__ import annotations

import math

from gi.repository import GLib, Gtk

from ..engine.backends import missing_tools
from ..engine.presets import Preset
from ..engine.tools import label
from .compat import foreground_color


class ProgressRing(Gtk.DrawingArea):
    """A small circular progress indicator. ``fraction=None`` spins."""

    def __init__(self, size: int = 52):
        super().__init__()
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_can_target(False)
        self._fraction: float | None = 0.0
        self._angle = 0.0
        self._tick_id = 0
        self.set_draw_func(self._draw)

    def set_fraction(self, fraction: float | None) -> None:
        self._fraction = fraction
        if fraction is None and not self._tick_id:
            self._tick_id = self.add_tick_callback(self._spin)
        elif fraction is not None and self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0
        self.queue_draw()

    def stop(self) -> None:
        if self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _spin(self, _widget: Gtk.Widget, clock: object) -> bool:
        self._angle = (self._angle + 0.12) % (2 * math.pi)
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(self, _area: Gtk.DrawingArea, cr: object, width: int, height: int) -> None:
        color = foreground_color(self)
        line = 4.0
        radius = min(width, height) / 2 - line
        cx, cy = width / 2, height / 2
        cr.set_line_width(line)  # type: ignore[attr-defined]
        cr.set_source_rgba(color.red, color.green, color.blue, 0.15)  # type: ignore[attr-defined]
        cr.arc(cx, cy, radius, 0, 2 * math.pi)  # type: ignore[attr-defined]
        cr.stroke()  # type: ignore[attr-defined]
        cr.set_source_rgba(color.red, color.green, color.blue, 0.9)  # type: ignore[attr-defined]
        cr.set_line_cap(1)  # type: ignore[attr-defined]  # round
        if self._fraction is None:
            start = self._angle
            cr.arc(cx, cy, radius, start, start + math.pi * 0.6)  # type: ignore[attr-defined]
        else:
            start = -math.pi / 2
            end = start + 2 * math.pi * max(0.02, self._fraction)
            cr.arc(cx, cy, radius, start, end)  # type: ignore[attr-defined]
        cr.stroke()  # type: ignore[attr-defined]


class PresetTile(Gtk.Button):
    """One drop target. The panel decides what happens on click and drop."""

    def __init__(self, preset: Preset):
        super().__init__()
        self.preset = preset
        self.add_css_class("tile")
        self.add_css_class("flat")
        self.add_css_class(f"group-{preset.group}")
        self.set_tooltip_text(preset.description)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_valign(Gtk.Align.START)

        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        badge = Gtk.Box()
        badge.add_css_class("badge")
        badge.set_halign(Gtk.Align.CENTER)
        badge.set_valign(Gtk.Align.CENTER)
        self.icon = Gtk.Image.new_from_icon_name(self._icon_name())
        self.icon.set_pixel_size(24)
        self.icon.set_hexpand(True)
        self.icon.set_halign(Gtk.Align.CENTER)
        badge.append(self.icon)
        overlay.set_child(badge)

        self.ring = ProgressRing()
        self.ring.add_css_class("ring")
        self.ring.set_visible(False)
        self.ring.set_halign(Gtk.Align.CENTER)
        self.ring.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.ring)

        self.state_icon = Gtk.Image()
        self.state_icon.add_css_class("state-icon")
        self.state_icon.set_halign(Gtk.Align.END)
        self.state_icon.set_valign(Gtk.Align.START)
        self.state_icon.set_visible(False)
        overlay.add_overlay(self.state_icon)
        box.append(overlay)

        name = Gtk.Label(label=preset.name, justify=Gtk.Justification.CENTER)
        name.add_css_class("tile-name")
        name.set_wrap(True)
        name.set_lines(2)
        name.set_ellipsize(3)  # Pango.EllipsizeMode.END
        name.set_width_chars(9)
        name.set_max_width_chars(11)
        box.append(name)

        ext = (
            "folder"
            if preset.output == "folder"
            else ("same format" if preset.output_ext == "same" else f".{preset.output_ext}")
        )
        sub = Gtk.Label(label=ext)
        sub.add_css_class("tile-sub")
        sub.add_css_class("dim-label")
        box.append(sub)
        self.set_child(box)

        accessible = f"{preset.name}: {preset.description}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [accessible])

        self.compatible = True
        self.available = True
        self._reset_id = 0
        self.refresh_availability()

    def _icon_name(self) -> str:
        fallback = {
            "image": "image-x-generic-symbolic",
            "video": "video-x-generic-symbolic",
            "audio": "audio-x-generic-symbolic",
            "document": "x-office-document-symbolic",
        }.get(self.preset.group, "system-run-symbolic")
        display = self.get_display()
        theme = Gtk.IconTheme.get_for_display(display) if display else None
        if self.preset.icon and theme and theme.has_icon(self.preset.icon):
            return self.preset.icon
        return fallback

    def refresh_availability(self) -> None:
        missing = missing_tools(self.preset)
        self.available = not missing
        self.set_css_classes_state("unavailable", not self.available)
        if missing:
            needs = " + ".join(" or ".join(label(t) for t in group) for group in missing)
            self.set_tooltip_text(
                f"{self.preset.description}\nNeeds {needs}: see Preferences > Tools."
            )
        else:
            self.set_tooltip_text(self.preset.description)

    def set_css_classes_state(self, css: str, on: bool) -> None:
        if on:
            self.add_css_class(css)
        else:
            self.remove_css_class(css)

    def set_compatible(self, compatible: bool) -> None:
        self.compatible = compatible
        self.set_css_classes_state("incompatible", not compatible)

    def set_hover(self, hover: bool) -> None:
        self.set_css_classes_state("drop-hover", hover)

    def set_progress(self, fraction: float | None) -> None:
        if self._reset_id:
            GLib.source_remove(self._reset_id)
            self._reset_id = 0
        self.state_icon.set_visible(False)
        self.ring.set_visible(True)
        self.ring.set_fraction(fraction)
        self.add_css_class("busy")

    def show_result(self, ok: bool) -> None:
        self.ring.stop()
        self.ring.set_visible(False)
        self.remove_css_class("busy")
        self.state_icon.set_from_icon_name(
            "emblem-ok-symbolic" if ok else "dialog-warning-symbolic"
        )
        self.state_icon.set_css_classes(["state-icon", "success" if ok else "warning"])
        self.state_icon.set_visible(True)
        self._reset_id = GLib.timeout_add(2500, self._clear_result)

    def _clear_result(self) -> bool:
        self.state_icon.set_visible(False)
        self._reset_id = 0
        return GLib.SOURCE_REMOVE
