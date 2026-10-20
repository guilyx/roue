from __future__ import annotations

from pathlib import Path

import pytest

from roue.engine import output
from roue.engine.errors import RoueError


def test_candidate_names() -> None:
    names = output.candidate_names("photo", "jpg")
    assert [next(names) for _ in range(3)] == ["photo.jpg", "photo (2).jpg", "photo (3).jpg"]


def test_commit_never_overwrites(tmp_path: Path) -> None:
    existing = tmp_path / "photo.jpg"
    existing.write_bytes(b"precious")
    tmp = tmp_path / "result.jpg"
    tmp.write_bytes(b"new")
    final = output.commit_file(tmp, tmp_path, "photo", "jpg")
    assert final.name == "photo (2).jpg"
    assert existing.read_bytes() == b"precious"
    assert final.read_bytes() == b"new"
    assert not tmp.exists()


def test_commit_skips_dangling_symlinks(tmp_path: Path) -> None:
    (tmp_path / "a.png").symlink_to(tmp_path / "missing")
    tmp = tmp_path / "t"
    tmp.write_bytes(b"x")
    assert output.commit_file(tmp, tmp_path, "a", "png").name == "a (2).png"


def test_commit_folder(tmp_path: Path) -> None:
    (tmp_path / "doc (pages)").mkdir()
    produced = tmp_path / "produced"
    produced.mkdir()
    (produced / "page-001.png").write_bytes(b"1")
    (produced / "page-002.png").write_bytes(b"2")
    final = output.commit_folder(produced, tmp_path, "doc (pages)")
    assert final.name == "doc (pages) (2)"
    assert sorted(p.name for p in final.iterdir()) == ["page-001.png", "page-002.png"]


def test_scratch_dir_is_hidden_and_cleaned(tmp_path: Path) -> None:
    with output.scratch_dir(tmp_path) as scratch:
        assert scratch.parent == tmp_path and scratch.name.startswith(".roue-")
        (scratch / "junk").write_text("x")
    assert not scratch.exists()


def test_read_only_folder_falls_back_to_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir, downloads = tmp_path / "camera", tmp_path / "Downloads"
    source_dir.mkdir()
    downloads.mkdir()
    monkeypatch.setattr(output, "user_dir", lambda *_: downloads)
    monkeypatch.setattr(output, "is_writable_dir", lambda d: d != source_dir)
    folder, fell_back = output.destination_dir(source_dir / "IMG.heic")
    assert folder == downloads and fell_back


def test_explicit_output_dir_is_created(tmp_path: Path) -> None:
    target = tmp_path / "out" / "nested"
    folder, fell_back = output.destination_dir(tmp_path / "a.png", target)
    assert folder == target and target.is_dir() and not fell_back


def test_nowhere_to_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output, "is_writable_dir", lambda d: False)
    with pytest.raises(RoueError, match="read-only"):
        output.destination_dir(tmp_path / "a.png")


def test_user_dirs_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "cfg"
    config.mkdir()
    (config / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Téléchargements"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    assert output.user_dir("DOWNLOAD", "Downloads") == Path.home() / "Téléchargements"
