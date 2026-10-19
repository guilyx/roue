from __future__ import annotations

import json
from pathlib import Path

import pytest

from roue import __version__
from roue.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Images" in out and "share-10mb" in out


def test_list_json_for_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--json", "--for", "a.mov"]) == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    ids = [p["id"] for p in data]
    assert ids[0] == "mp4" and "jpg" not in ids
    assert {"accepts", "rejects", "available"} <= data[0].keys()


def test_disabled_presets_are_hidden(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    from roue.engine.settings import Settings

    Settings(disabled_presets=["gif"]).save()
    main(["list", "--json"])
    assert "gif" not in [p["id"] for p in json.loads(capsys.readouterr().out)]
    main(["list", "--json", "--all"])
    assert "gif" in [p["id"] for p in json.loads(capsys.readouterr().out)]


def test_info(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    note = tmp_path / "n.md"
    note.write_text("# hi")
    assert main(["info", str(note)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "text/markdown" in out and "html" in out


def test_unknown_preset_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert main(["convert", "nope", str(f)]) == EXIT_USAGE
    assert "no preset called 'nope'" in capsys.readouterr().err


def test_shorthand_convert_and_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset_dir = tmp_path / "config" / "roue" / "presets"
    preset_dir.mkdir(parents=True)
    (preset_dir / "upper.yaml").write_text(
        "id: upper\nname: Upper\nbackend: command\naccepts: text/*\noutput_ext: txt\n"
        "suffix: ' (up)'\n"
        "params: {command: [sh, -c, 'tr a-z A-Z < \"$0\" > \"$1\"', '{in}', '{out}']}\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    f = tmp_path / "a.txt"
    f.write_text("hey")
    assert main(["upper", str(f), "--json"]) == EXIT_OK
    result = json.loads(capsys.readouterr().out)
    assert result["jobs"][0]["state"] == "done"
    assert Path(result["jobs"][0]["outputs"][0]).read_text() == "HEY"
    # And it shows up in history, and undo trashes it.
    assert main(["history"]) == EXIT_OK
    assert "Upper" in capsys.readouterr().out
    assert main(["undo"]) == EXIT_OK
    assert not (tmp_path / "a (up).txt").exists()
    assert f.exists()


def test_failed_conversion_exit_code(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["convert", "jpg", str(tmp_path / "missing.png")]) == EXIT_FAILED
    assert "doesn't exist" in capsys.readouterr().err


def test_doctor_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Tools" in out and "Presets:" in out and "Desktop" in out
