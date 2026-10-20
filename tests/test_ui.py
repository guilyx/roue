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


def test_floating_wheel_without_files_shows_a_starter_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def check(app: RoueApplication, results: dict[str, object]) -> None:
        wheel = app.show_wheel()
        results["overlay"] = wheel.overlay
        results["ids"] = [s.preset.id if s.preset else None for s in wheel.view.slices]

    results = run_app(check, monkeypatch)
    assert results["overlay"] is False
    assert results["ids"] == ["jpg", "webp", "mp4", "gif", "share-10mb", "mp3", "pdf", None]


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

        app.show_welcome()
        dialog = app.panel.get_visible_dialog() if app.panel else None
        assert isinstance(dialog, Adw.Dialog)
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
