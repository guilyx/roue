"""The Files (Nautilus) extension, loaded with fake file objects."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

gi = pytest.importorskip("gi")
try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pytest.skip("nautilus-python (Nautilus 4.0 typelib) isn't installed", allow_module_level=True)

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


def labels(module: ModuleType, files: list[FakeInfo]) -> list[str]:
    items = module.RoueMenuProvider().get_file_items(files)
    if not items:
        return []
    return [item.props.label for item in items[0].props.menu.get_items()]


def test_menu_for_a_photo(extension: ModuleType) -> None:
    found = labels(extension, [FakeInfo("/tmp/IMG.heic", "image/heif")])
    assert found[0] == "JPG" and found[-1] == "More…" and len(found) == 7


def test_menu_for_pdfs(extension: ModuleType) -> None:
    assert labels(extension, [FakeInfo("/tmp/a.pdf", "application/pdf")]) == [
        "Compress PDF",
        "Pages to PNG",
        "Text",
    ]


def test_no_menu_for_mixed_or_folders(extension: ModuleType) -> None:
    mixed = [FakeInfo("/tmp/a.png", "image/png"), FakeInfo("/tmp/b.mp4", "video/mp4")]
    assert labels(extension, mixed) == []
    assert labels(extension, [FakeInfo("/tmp", "inode/directory", True)]) == []
