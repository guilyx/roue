"""Settings, history/undo and the hotkey helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from roue.engine import history as history_mod
from roue.engine.history import History
from roue.engine.presets import parse_preset
from roue.engine.runner import Batch, Job, JobState
from roue.engine.settings import Settings
from roue.integrations import hotkey


def test_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    Settings(disabled_presets=["gif"], max_jobs=2, notifications=False).save(path)
    loaded = Settings.load(path)
    assert loaded.disabled_presets == ["gif"] and loaded.max_jobs == 2 and not loaded.notifications


def test_settings_ignore_bad_values(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("max_jobs: lots\nnotifications: 1\nunknown: true\nshift_drag: false\n")
    loaded = Settings.load(path)
    assert loaded.max_jobs == 0 and loaded.notifications is True and loaded.shift_drag is False
    path.write_text(": not yaml [")
    assert Settings.load(path) == Settings()


def _batch(tmp_path: Path, name: str) -> Batch:
    preset = parse_preset(
        {"id": "p", "name": "P", "backend": "image", "accepts": "image/*", "output_ext": "png"}
    )
    out = tmp_path / f"{name}.png"
    out.write_bytes(b"x")
    job = Job(source=tmp_path / f"{name}.jpg", preset=preset, state=JobState.DONE, outputs=[out])
    return Batch(preset=preset, jobs=[job])


def test_history_and_undo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the built-in trash implementation (no gio in tests).
    monkeypatch.setattr(history_mod.shutil, "which", lambda _: None)
    history = History(tmp_path / "h.jsonl")
    history.record(_batch(tmp_path, "first"))
    history.record(_batch(tmp_path, "second"))
    assert [Path(e.outputs[0]).stem for e in history.entries()] == ["second", "first"]

    result = history.undo_last()
    assert result is not None
    entry, trashed = result
    assert Path(entry.outputs[0]).stem == "second" and trashed
    assert not (tmp_path / "second.png").exists()
    trash = Path(history_mod.os.environ["XDG_DATA_HOME"]) / "Trash"
    assert (trash / "files" / "second.png").exists()
    assert "Path=" in (trash / "info" / "second.png.trashinfo").read_text()

    # Second undo goes one step further back.
    assert history.undo_last() is not None
    assert not (tmp_path / "first.png").exists()
    assert history.undo_last() is None


def test_history_is_capped(tmp_path: Path) -> None:
    history = History(tmp_path / "h.jsonl")
    for i in range(history_mod.MAX_ENTRIES + 5):
        history.record(_batch(tmp_path, f"f{i}"))
    assert len(history.entries()) == history_mod.MAX_ENTRIES


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [("@as []", []), ("['/a/', '/b/']", ["/a/", "/b/"]), ("garbage", [])],
)
def test_parse_gsettings_arrays(raw: str, parsed: list[str]) -> None:
    assert hotkey.parse_string_array(raw) == parsed


def test_hotkey_install_and_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[tuple[str, str], str] = {
        (hotkey._SCHEMA, "custom-keybindings"): "['/existing/']",
    }

    def fake(*args: str) -> str:
        if args[0] == "get":
            return store.get((args[1], args[2]), "''")
        if args[0] == "set":
            store[(args[1], args[2])] = args[3]
        if args[0] == "reset":
            store.pop((args[1], args[2]), None)
        return ""

    monkeypatch.setattr(hotkey, "_gsettings", fake)
    monkeypatch.setattr(hotkey, "can_install", lambda: True)
    hotkey.install("/usr/bin/roue panel")
    paths = hotkey.parse_string_array(store[(hotkey._SCHEMA, "custom-keybindings")])
    assert paths == ["/existing/", hotkey._PATH]
    assert hotkey.current_binding() == hotkey.DEFAULT_BINDING
    assert hotkey.remove()
    assert hotkey.parse_string_array(store[(hotkey._SCHEMA, "custom-keybindings")]) == [
        "/existing/"
    ]
    assert hotkey.current_binding() is None
