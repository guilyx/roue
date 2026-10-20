"""The Files (Nautilus) extension, loaded with fake file objects."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

gi = pytest.importorskip("gi")
for _version in ("4.1", "4.0"):
    try:
        gi.require_version("Nautilus", _version)
        break
    except ValueError:
        continue
else:
    pytest.skip("nautilus-python (Nautilus 4.x typelib) isn't installed", allow_module_level=True)

from gi.repository import Gio  # noqa: E402

EXTENSION = Path(__file__).parents[1] / "src" / "roue" / "data" / "nautilus" / "roue_nautilus.py"


@pytest.fixture
def extension() -> ModuleType:
    spec = importlib.util.spec_from_file_location("roue_nautilus", EXTENSION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInfo:
    def __init__(self, path: str, mime: str, is_dir: bool = False):
        self._file, self._mime, self._dir = Gio.File.new_for_path(path), mime, is_dir

    def is_directory(self) -> bool:
        return self._dir

    def get_location(self) -> Any:
        return self._file

    def get_mime_type(self) -> str:
        return self._mime


def menu(module: ModuleType, files: list[FakeInfo]) -> list[str]:
    return [item.props.label for item in module.RoueMenuProvider().get_file_items(files)]


def test_one_item_opens_the_wheel_for_a_photo(extension: ModuleType) -> None:
    assert menu(extension, [FakeInfo("/tmp/IMG.heic", "image/heif")]) == ["Convert with Roue…"]
    [item] = extension.RoueMenuProvider().get_file_items([FakeInfo("/tmp/IMG.heic", "image/heif")])
    assert item.props.tip.startswith("9 ways to convert: JPG")


def test_pdfs_get_the_item_too(extension: ModuleType) -> None:
    assert menu(extension, [FakeInfo("/tmp/a.pdf", "application/pdf")]) == ["Convert with Roue…"]


def test_no_menu_for_mixed_or_folders(extension: ModuleType) -> None:
    mixed = [FakeInfo("/tmp/a.png", "image/png"), FakeInfo("/tmp/b.mp4", "video/mp4")]
    assert menu(extension, mixed) == []
    assert menu(extension, [FakeInfo("/tmp", "inode/directory", True)]) == []
    assert menu(extension, [FakeInfo("/tmp/a.zip", "application/zip")]) == []


def test_platform_data_is_safe_without_an_installed_app(
    extension: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The .deb may have installed the real desktop file: look up one that can't exist.
    monkeypatch.setattr(extension, "APP_ID", "io.github.guilyx.Roue.NotInstalled")
    assert extension._platform_data() == {}
