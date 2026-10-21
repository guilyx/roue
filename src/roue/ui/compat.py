"""Fallbacks for older GTK 4 and libadwaita (Ubuntu 22.04 has GTK 4.6 and libadwaita 1.1).

Each helper uses the newer API where it exists and an older equivalent
otherwise, so the rest of the UI doesn't check versions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk


def _present_over(window: Gtk.Window, parent: Gtk.Widget | None) -> None:
    root = parent.get_root() if parent else None
    if isinstance(root, Gtk.Window):
        window.set_transient_for(root)
    Gtk.Window.present(window)


# -- dialogs and rows -----------------------------------------------------------

if hasattr(Adw, "Dialog"):  # libadwaita 1.5+
    Dialog = Adw.Dialog
else:

    class Dialog(Adw.Window):  # type: ignore[no-redef]
        """Adw.Dialog for libadwaita < 1.5: a modal window over its parent."""

        __gsignals__: ClassVar[dict[str, Any]] = {
            "closed": (GObject.SignalFlags.RUN_FIRST, None, ())
        }

        def __init__(self, *, content_width: int = -1, content_height: int = -1, **kwargs: Any):
            super().__init__(modal=True, **kwargs)
            self.set_default_size(content_width, content_height)
            self.connect("close-request", self._on_close_request)

        def _on_close_request(self, _window: Gtk.Window) -> bool:
            self.emit("closed")
            return False

        def set_child(self, child: Gtk.Widget) -> None:
            self.set_content(child)

        def set_content_width(self, width: int) -> None:
            self.set_default_size(width, self.get_default_size()[1])

        def set_content_height(self, height: int) -> None:
            self.set_default_size(self.get_default_size()[0], height)

        def present(self, parent: Gtk.Widget | None = None) -> None:
            _present_over(self, parent)


if hasattr(Adw, "PreferencesDialog"):  # libadwaita 1.5+
    PreferencesDialog = Adw.PreferencesDialog
else:

    class PreferencesDialog(Adw.PreferencesWindow):  # type: ignore[no-redef]
        """Adw.PreferencesDialog for libadwaita < 1.5."""

        def __init__(self, **kwargs: Any):
            super().__init__(modal=True, **kwargs)

        def present(self, parent: Gtk.Widget | None = None) -> None:
            _present_over(self, parent)


if hasattr(Adw, "SwitchRow"):  # libadwaita 1.4+
    SwitchRow = Adw.SwitchRow
else:

    class SwitchRow(Adw.ActionRow):  # type: ignore[no-redef]
        """Adw.SwitchRow for libadwaita < 1.4: a row with a switch."""

        active = GObject.Property(type=bool, default=False)

        def __init__(self, **kwargs: Any):
            super().__init__(**kwargs)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            self.add_suffix(switch)
            self.set_activatable_widget(switch)
            flags = GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
            self.bind_property("active", switch, "active", flags)

        def get_active(self) -> bool:
            return bool(self.props.active)

        def set_active(self, active: bool) -> None:
            self.props.active = active


if hasattr(Adw, "SpinRow"):  # libadwaita 1.4+
    SpinRow = Adw.SpinRow
else:

    class SpinRow(Adw.ActionRow):  # type: ignore[no-redef]
        """Adw.SpinRow for libadwaita < 1.4: a row with a spin button."""

        value = GObject.Property(type=float, default=0.0)

        def __init__(self, **kwargs: Any):
            super().__init__(**kwargs)
            self._spin = Gtk.SpinButton(valign=Gtk.Align.CENTER, numeric=True)
            self.add_suffix(self._spin)
            self.set_activatable_widget(self._spin)
            flags = GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE
            self.bind_property("value", self._spin, "value", flags)

        @classmethod
        def new_with_range(cls, lower: float, upper: float, step: float) -> SpinRow:
            row = cls()
            row._spin.set_range(lower, upper)
            row._spin.set_increments(step, step * 10)
            return row

        def get_value(self) -> float:
            return float(self._spin.get_value())

        def set_value(self, value: float) -> None:
            self._spin.set_value(value)


def toolbar_view(
    top: Gtk.Widget | None, content: Gtk.Widget, bottom: Gtk.Widget | None = None
) -> Gtk.Widget:
    """Bars above and below some content: Adw.ToolbarView (libadwaita 1.4+), or a box."""
    if hasattr(Adw, "ToolbarView"):
        view = Adw.ToolbarView()
        if top:
            view.add_top_bar(top)
        view.set_content(content)
        if bottom:
            view.add_bottom_bar(bottom)
        return view
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    content.set_vexpand(True)
    for child in (top, content, bottom):
        if child:
            box.append(child)
    return box


def spinner() -> Gtk.Widget:
    if hasattr(Adw, "Spinner"):  # libadwaita 1.6+
        return Adw.Spinner()
    return Gtk.Spinner(spinning=True)


def show_about(parent: Gtk.Window, credits: tuple[str, list[str]], **props: Any) -> None:
    """The About window. ``props`` are Adw.AboutDialog's properties."""
    if hasattr(Adw, "AboutDialog"):  # libadwaita 1.5+
        dialog = Adw.AboutDialog(**props)
        dialog.add_credit_section(*credits)
        dialog.present(parent)
        return
    if hasattr(Adw, "AboutWindow"):  # libadwaita 1.2+
        window = Adw.AboutWindow(transient_for=parent, modal=True, **props)
    else:  # GTK's own: no developer name or issue link
        window = Gtk.AboutDialog(
            transient_for=parent,
            modal=True,
            program_name=props["application_name"],
            logo_icon_name=props["application_icon"],
            version=props["version"],
            comments=props["comments"],
            website=props["website"],
            license_type=props["license_type"],
            authors=props["developers"],
        )
    window.add_credit_section(*credits)
    window.present()


def foreground_color(widget: Gtk.Widget) -> Gdk.RGBA:
    """The widget's CSS colour."""
    if hasattr(widget, "get_color"):  # GTK 4.10+
        return widget.get_color()
    return widget.get_style_context().get_color()


# -- files and links --------------------------------------------------------------

#: GTK 4.6 doesn't keep native file choosers alive while they're open.
_open_choosers: set[Gtk.NativeDialog] = set()


def _run_chooser(chooser: Gtk.FileChooserNative, on_accept: Callable[[Any], None]) -> None:
    def response(dialog: Gtk.FileChooserNative, response_id: int) -> None:
        _open_choosers.discard(dialog)
        if response_id == Gtk.ResponseType.ACCEPT:
            on_accept(dialog)
        dialog.destroy()

    _open_choosers.add(chooser)
    chooser.connect("response", response)
    chooser.show()


def _items(model: Gio.ListModel) -> list[Gio.File]:
    return [model.get_item(i) for i in range(model.get_n_items())]


def choose_files(
    parent: Gtk.Window | None,
    title: str,
    on_chosen: Callable[[list[Gio.File]], None],
    file_filter: Gtk.FileFilter | None = None,
) -> None:
    """Let people pick files. ``on_chosen`` isn't called if they cancel."""
    if hasattr(Gtk, "FileDialog"):  # GTK 4.10+
        dialog = Gtk.FileDialog(title=title)
        if file_filter:
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(file_filter)
            dialog.set_filters(filters)
            dialog.set_default_filter(file_filter)

        def done(d: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                files = d.open_multiple_finish(result)
            except GLib.Error:
                return  # cancelled
            on_chosen(_items(files))

        dialog.open_multiple(parent, None, done)
        return
    chooser = Gtk.FileChooserNative(
        title=title,
        transient_for=parent,
        modal=True,
        action=Gtk.FileChooserAction.OPEN,
        select_multiple=True,
    )
    if file_filter:
        chooser.add_filter(file_filter)
        chooser.set_filter(file_filter)
    _run_chooser(chooser, lambda c: on_chosen(_items(c.get_files())))


def choose_folder(
    parent: Gtk.Window | None, title: str, on_chosen: Callable[[Gio.File], None]
) -> None:
    """Let people pick a folder. ``on_chosen`` isn't called if they cancel."""
    if hasattr(Gtk, "FileDialog"):  # GTK 4.10+
        dialog = Gtk.FileDialog(title=title)

        def done(d: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                folder = d.select_folder_finish(result)
            except GLib.Error:
                return
            if folder:
                on_chosen(folder)

        dialog.select_folder(parent, None, done)
        return
    chooser = Gtk.FileChooserNative(
        title=title, transient_for=parent, modal=True, action=Gtk.FileChooserAction.SELECT_FOLDER
    )
    _run_chooser(chooser, lambda c: c.get_file() and on_chosen(c.get_file()))


def launch(parent: Gtk.Window | None, uri: str) -> None:
    """Open a file or folder with its default app, or a web page in the browser."""
    if hasattr(Gtk, "FileLauncher"):  # GTK 4.10+
        if uri.startswith("file:"):
            Gtk.FileLauncher(file=Gio.File.new_for_uri(uri)).launch(parent, None, None)
        else:
            Gtk.UriLauncher(uri=uri).launch(parent, None, None)
        return
    Gtk.show_uri(parent, uri, Gdk.CURRENT_TIME)


def show_in_folder(parent: Gtk.Window | None, uri: str) -> None:
    """Show a file, selected, in the file manager."""
    if hasattr(Gtk, "FileLauncher"):  # GTK 4.10+
        Gtk.FileLauncher(file=Gio.File.new_for_uri(uri)).open_containing_folder(parent, None, None)
        return
    # What GTK 4.10 does: ask the file manager over D-Bus, else open the folder.
    folder = Gio.File.new_for_uri(uri).get_parent()

    def open_folder() -> None:
        if folder:
            Gtk.show_uri(parent, folder.get_uri(), Gdk.CURRENT_TIME)

    def done(bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error:
            open_folder()

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        open_folder()
        return
    bus.call(
        "org.freedesktop.FileManager1",
        "/org/freedesktop/FileManager1",
        "org.freedesktop.FileManager1",
        "ShowItems",
        GLib.Variant("(ass)", ([uri], "")),
        None,
        Gio.DBusCallFlags.NONE,
        5000,
        None,
        done,
    )
