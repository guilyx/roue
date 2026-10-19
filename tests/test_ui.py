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
