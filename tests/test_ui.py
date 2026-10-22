"""Smoke tests for the GTK panel. They need a display: CI runs them under xvfb-run."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    pytest.skip("needs a display (run with xvfb-run)", allow_module_level=True)

gi = pytest.importorskip("gi")
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
except ValueError:
    pytest.skip("GTK 4 / libadwaita typelibs are missing", allow_module_level=True)

from gi.repository import Gio, GLib  # noqa: E402

from roue.ui.application import RoueApplication  # noqa: E402


def run_app(check: object, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("GSK_RENDERER", "cairo")
    app = RoueApplication()
    app.settings.welcome_done = True  # tests open the setup dialog themselves
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    results: dict[str, object] = {}

    def later() -> bool:
        try:
            check(app, results)  # type: ignore[operator]
        finally:
            app.quit()
        return GLib.SOURCE_REMOVE

    # The app handles its command line (no "activate"): check once it's up.
    app.connect("startup", lambda *_: GLib.timeout_add(300, later))
    GLib.timeout_add_seconds(20, lambda: app.quit() or GLib.SOURCE_REMOVE)  # never hang
    app.run(["roue"])
    return results


def test_panel_shows_every_enabled_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    def check(app: RoueApplication, results: dict[str, object]) -> None:
        results["tiles"] = set(app.panel.tiles) if app.panel else set()
        results["expected"] = {p.id for group in app.visible_presets().values() for p in group}

    results = run_app(check, monkeypatch)
    assert results["tiles"] == results["expected"]
    assert len(results["tiles"]) >= 25  # type: ignore[arg-type]


def test_staging_dims_tiles_that_cannot_take_the_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"not really a photo")

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        assert app.panel
        app.panel.stage([photo])
        tiles = app.panel.tiles
        results["jpg"] = tiles["jpg"].compatible
        results["mp4"] = tiles["mp4"].compatible
        results["staged"] = app.panel.staged_revealer.get_reveal_child()

    results = run_app(check, monkeypatch)
    assert results == {"jpg": True, "mp4": False, "staged": True}


def test_search_filters_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    def check(app: RoueApplication, results: dict[str, object]) -> None:
        assert app.panel
        app.panel.search.set_text("discord")
        app.panel._apply_filter()
        results["visible"] = [
            pid for pid, tile in app.panel.tiles.items() if tile.get_parent().get_visible()
        ]

    assert run_app(check, monkeypatch)["visible"] == ["share-10mb"]


def test_preferences_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def check(app: RoueApplication, results: dict[str, object]) -> None:
        app.show_preferences()
        results["ok"] = True

    assert run_app(check, monkeypatch) == {"ok": True}


def test_history_and_about_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def check(app: RoueApplication, results: dict[str, object]) -> None:
        app.show_history()
        app.show_about()
        results["ok"] = True

    assert run_app(check, monkeypatch) == {"ok": True}


def test_preference_rows_report_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch and number rows behave the same with older libadwaita."""

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        from roue.ui import compat

        seen: list[object] = []
        switch = compat.SwitchRow(title="Notifications")
        switch.connect("notify::active", lambda row, _p: seen.append(row.get_active()))
        switch.set_active(True)
        spin = compat.SpinRow.new_with_range(0, 64, 1)
        spin.connect("notify::value", lambda row, _p: seen.append(row.get_value()))
        spin.set_value(3)
        results["seen"] = seen

    assert run_app(check, monkeypatch)["seen"] == [True, 3.0]


def test_wheel_with_files_offers_the_best_presets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"not really a photo")

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        wheel = app.show_wheel([photo], overlay=True)
        results["titles"] = [s.title for s in wheel.view.slices]
        results["overlay"] = wheel.overlay

    results = run_app(check, monkeypatch)
    titles = results["titles"]
    assert titles[0] == "JPG" and titles[-1] == "More…" and len(titles) == 8  # type: ignore[index,arg-type]


def test_picking_a_slice_converts_and_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"x")
    calls: list[tuple[str, list[Path]]] = []

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        monkeypatch.setattr(app, "convert", lambda preset, paths: calls.append((preset.id, paths)))
        wheel = app.show_wheel([photo], overlay=True)
        wheel.choose(0)
        results["chosen"] = wheel.view.chosen

    results = run_app(check, monkeypatch)
    assert calls == [("jpg", [photo])]
    assert results["chosen"] == 0


def test_more_opens_the_panel_with_the_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"x")

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        wheel = app.show_wheel([photo], overlay=True)
        wheel.choose(len(wheel.view.slices) - 1)
        assert app.panel
        results["staged"] = app.panel.staged
        results["panel"] = app.panel.get_visible()

    results = run_app(check, monkeypatch)
    assert results == {"staged": [photo], "panel": True}


def test_floating_wheel_without_files_is_an_empty_ring(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"x")

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        wheel = app.show_wheel()
        results["overlay"] = wheel.overlay
        results["empty"] = [s.title for s in wheel.view.slices]
        results["hub"] = wheel.view.hub_title.get_text()
        wheel.stage([photo])  # dropped, pasted or chosen: now it shows what fits
        results["photo"] = [s.preset.id if s.preset else None for s in wheel.view.slices][:2]

    results = run_app(check, monkeypatch)
    assert results["overlay"] is False
    assert results["empty"] == []
    assert results["hub"] == "Drop files"
    assert results["photo"] == ["jpg", "png"]


class FilesOnTheBus:
    """Stands in for the session bus, answering for Roue's extension in Files."""

    def __init__(self, selection: list[str] | None):
        self.selection = selection  # None: Files isn't running
        self.asked: list[tuple[str, str]] = []

    def call(self, name: str, _path: str, _iface: str, method: str, *args: object) -> None:
        self.asked.append((name, method))
        args[-1](self, None)  # type: ignore[operator]

    def call_finish(self, _result: object) -> GLib.Variant:
        if self.selection is None:
            raise GLib.Error("org.freedesktop.DBus.Error.ServiceUnknown")
        return GLib.Variant("(as)", (self.selection,))


@pytest.mark.parametrize("case", ["photo", "nothing selected", "Files not running", "file gone"])
def test_hotkey_opens_the_wheel_for_what_is_selected_in_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    photo = tmp_path / "IMG_0001.heic"
    photo.write_bytes(b"x")
    selection = {
        "photo": [str(photo)],
        "nothing selected": [],
        "Files not running": None,
        "file gone": [str(tmp_path / "gone.jpg")],
    }[case]
    bus = FilesOnTheBus(selection)

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        monkeypatch.setattr(app, "get_dbus_connection", lambda: bus)
        app.activate_action("show-wheel", None)
        assert app.wheel
        results["files"] = app.wheel.files
        results["slices"] = len(app.wheel.view.slices)

    results = run_app(check, monkeypatch)
    assert bus.asked == [("org.gnome.Nautilus", "GetSelection")]
    if case == "photo":  # the wheel at the pointer, with what fits the photo
        assert results["files"] == [photo]
        assert results["slices"]
    else:  # the empty ring to drop files on
        assert results == {"files": [], "slices": 0}


def test_empty_wheel_takes_keys_and_clicks(monkeypatch: pytest.MonkeyPatch) -> None:
    from gi.repository import Gdk

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        wheel = app.show_wheel()
        asked: list[str] = []
        monkeypatch.setattr(wheel, "choose_files", lambda: asked.append("choose"))
        handled = [
            wheel._on_key(None, key, 0, 0)  # type: ignore[arg-type]
            for key in (Gdk.KEY_Right, Gdk.KEY_1, Gdk.KEY_Return)
        ]
        size = wheel.view.geometry.size
        wheel._on_click(None, 1, size / 2 + 100, size / 2)  # type: ignore[arg-type]
        results["handled"], results["asked"] = handled, asked

    results = run_app(check, monkeypatch)
    assert results["handled"] == [False, False, True]
    assert results["asked"] == ["choose", "choose"]


def test_notifications_are_built_without_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Conversions started from the wheel report back through notifications."""
    from roue.engine.presets import parse_preset
    from roue.engine.runner import Batch, Job, JobState

    preset = parse_preset(
        {"id": "p", "name": "P", "backend": "image", "accepts": "image/*", "output_ext": "png"}
    )
    out = tmp_path / "out.png"
    out.write_bytes(b"x")
    done = Job(source=tmp_path / "a.jpg", preset=preset, state=JobState.DONE, outputs=[out])
    failed = Job(source=tmp_path / "b.jpg", preset=preset, state=JobState.FAILED, message="Nope.")
    sent: list[str] = []

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        monkeypatch.setattr(app, "send_notification", lambda key, n: sent.append(key))
        app._notify(Batch(preset=preset, jobs=[done]))
        app._notify(Batch(preset=preset, jobs=[failed]))
        app._notify(Batch(preset=preset, jobs=[done, failed]))

    run_app(check, monkeypatch)
    assert len(sent) == 3


def test_setup_dialog_lists_missing_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from roue.engine import tools

    monkeypatch.setenv("ROUE_DISABLE_TOOLS", "libreoffice,ghostscript")
    tools.which.cache_clear()

    def check(app: RoueApplication, results: dict[str, object]) -> None:
        from gi.repository import Adw

        dialog = app.show_welcome()
        assert dialog.get_visible()
        if hasattr(Adw, "Dialog"):  # libadwaita 1.5+ shows it inside the panel
            assert app.panel and app.panel.get_visible_dialog() is dialog
        titles = []
        for group in dialog._groups:  # type: ignore[attr-defined]
            row = group.get_first_child()
            stack = [row]
            while stack:
                widget = stack.pop()
                if widget is None:
                    continue
                if isinstance(widget, Adw.PreferencesRow):
                    titles.append(widget.get_title())
                stack.extend([widget.get_first_child(), widget.get_next_sibling()])
        results["titles"] = titles
        dialog.close()
        results["done"] = app.settings.welcome_done

    results = run_app(check, monkeypatch)
    assert "Office documents to PDF" in results["titles"]  # type: ignore[operator]
    assert "PDF tools" in results["titles"]  # type: ignore[operator]
    assert "Keyboard shortcut" in results["titles"]  # type: ignore[operator]
    assert results["done"] is True
