"""Recent conversions, with a button to show each result."""

from __future__ import annotations

import time
from pathlib import Path

from gi.repository import Adw, GLib, Gtk

from ..engine.history import History


class HistoryDialog(Adw.Dialog):
    def __init__(self, history: History):
        super().__init__(title="Recent Conversions")
        self.set_content_width(520)
        self.set_content_height(560)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        entries = history.entries()
        if not entries:
            view.set_content(
                Adw.StatusPage(
                    icon_name="document-open-recent-symbolic",
                    title="Nothing Yet",
                    description="Conversions show up here.",
                )
            )
            self.set_child(view)
            return
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        for entry in entries:
            when = time.strftime("%d %b, %H:%M", time.localtime(entry.time))
            subtitle = f"{when} · {entry.summary}" + (" · undone" if entry.undone else "")
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(entry.preset_name),
                subtitle=GLib.markup_escape_text(subtitle),
            )
            existing = [p for p in map(Path, entry.outputs) if p.exists()]
            if existing:
                button = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
                button.add_css_class("flat")
                button.set_tooltip_text("Show in folder")
                button.set_action_name("app.show-in-folder")
                button.set_action_target_value(GLib.Variant("s", existing[0].as_uri()))
                row.add_suffix(button)
            group.add(row)
        page.add(group)
        view.set_content(page)
        self.set_child(view)
