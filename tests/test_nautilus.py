"""The Files (Nautilus) extension, loaded with stand-ins for Files' file objects."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

gi = pytest.importorskip("gi")
for API in ("4.1", "4.0", "3.0"):
    try:
        gi.require_version("Nautilus", API)
        break
    except ValueError:
        continue
else:
    pytest.skip("nautilus-python (a Nautilus typelib) isn't installed", allow_module_level=True)

EXTENSION = Path(__file__).parents[1] / "src" / "roue" / "data" / "nautilus" / "roue_nautilus.py"

# Nautilus 42's extension API (3.0, Ubuntu 22.04) is built on GTK 3, which can't
# load next to the GTK 4 tests. With it, this file runs again in a child process.
CHILD = "ROUE_TEST_NAUTILUS_CHILD"
OWN_PROCESS = API == "3.0" and not os.environ.get(CHILD)

if OWN_PROCESS:

    def test_files_extension_in_its_own_process() -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", __file__],
            env={**os.environ, CHILD: "1"},
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

else:
    from gi.repository import Gio, GObject, Nautilus

    class FileInfo(GObject.Object, Nautilus.FileInfo):
        """A Nautilus.FileInfo, like the ones Files hands to extensions."""

        def __init__(self, path: str, mime: str, is_dir: bool = False):
            super().__init__()
            self._file, self._mime, self._dir = Gio.File.new_for_path(path), mime, is_dir

        def do_is_directory(self) -> bool:
            return self._dir

        def do_get_location(self) -> Gio.File:
            return self._file

        def do_get_mime_type(self) -> str:
            return self._mime

        def do_get_uri(self) -> str:
            return str(self._file.get_uri())

    @pytest.fixture
    def extension() -> ModuleType:
        spec = importlib.util.spec_from_file_location("roue_nautilus", EXTENSION)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def menu(module: ModuleType, files: list[Any]) -> list[str]:
        return [item.props.label for item in module.RoueMenuProvider().get_file_items(files)]

    def test_one_item_opens_the_wheel_for_a_photo(extension: ModuleType) -> None:
        photo = FileInfo("/tmp/IMG.heic", "image/heif")
        assert menu(extension, [photo]) == ["Convert with Roue…"]
        [item] = extension.RoueMenuProvider().get_file_items([photo])
        assert item.props.tip.startswith("9 ways to convert: JPG")

    def test_nautilus_42_passes_the_window_too(extension: ModuleType) -> None:
        photo = FileInfo("/tmp/IMG.heic", "image/heif")
        [item] = extension.RoueMenuProvider().get_file_items(None, [photo])
        assert item.props.label == "Convert with Roue…"

    def test_pdfs_get_the_item_too(extension: ModuleType) -> None:
        assert menu(extension, [FileInfo("/tmp/a.pdf", "application/pdf")]) == [
            "Convert with Roue…"
        ]

    def test_no_menu_for_mixed_or_folders(extension: ModuleType) -> None:
        mixed = [FileInfo("/tmp/a.png", "image/png"), FileInfo("/tmp/b.mp4", "video/mp4")]
        assert menu(extension, mixed) == []
        assert menu(extension, [FileInfo("/tmp", "inode/directory", True)]) == []
        assert menu(extension, [FileInfo("/tmp/a.zip", "application/zip")]) == []

    def test_platform_data_is_safe_without_an_installed_app(
        extension: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The GDK of the Files process: GTK 3 for Nautilus 42, GTK 4 after.
        gdk = "3.0" if API == "3.0" else "4.0"
        assert gdk == extension.GDK_VERSION
        # The .deb may have installed the real desktop file: look up one that can't exist.
        monkeypatch.setattr(extension, "APP_ID", "io.github.guilyx.Roue.NotInstalled")
        assert extension._platform_data() == {}

    def test_ctrl_shift_right_click_is_about_the_clicked_file(extension: ModuleType) -> None:
        a, b, c = (FileInfo(f"/tmp/{n}.jpg", "image/jpeg") for n in "abc")
        before = [a.get_uri()]
        # Files 42 adds the clicked file to the selection, newer Files replace it.
        assert extension._clicked(before, [a, c]) == [c]
        assert extension._clicked(before, [c]) == [c]
        # A file that was already selected: the whole selection, as with the menu.
        assert extension._clicked([a.get_uri(), b.get_uri()], [a, b]) == [a, b]

    class Window:
        """Just enough of a Files window."""

        def __init__(self, active: bool):
            self.active = active

        def get_property(self, name: str) -> bool:
            assert name == "is-active"
            return self.active

    def test_hotkey_gets_the_selection_of_files_in_front(
        extension: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = extension._Files()
        window = Window(active=True)
        key = hash(window)
        files._windows[key] = window
        files._selection[key] = [FileInfo("/tmp/a.jpg", "image/jpeg")]
        files._active = (key, 0.0)
        assert files.front_selection() == ["/tmp/a.jpg"]
        # The hotkey's key grab takes the focus from Files for a moment (X11).
        window.active = False
        now = 1000.0
        monkeypatch.setattr(extension.time, "monotonic", lambda: now)
        files._active = (key, now - 0.2)
        assert files.front_selection() == ["/tmp/a.jpg"]
        # Files was left a while ago: the hotkey is for something else.
        files._active = (key, now - 5)
        assert files.front_selection() == []
        # Folders and files nothing can convert don't count.
        files._active = (key, 0.0)
        window.active = True
        files._selection[key] = [FileInfo("/tmp", "inode/directory", True)]
        assert files.front_selection() == []

    def test_outside_files_the_extension_hooks_nothing(extension: ModuleType) -> None:
        files = extension._Files()
        files.start()  # not inside Files: no windows to watch, nothing on the bus
        files.remember(None, [FileInfo("/tmp/a.jpg", "image/jpeg")])
        assert files._windows == {} and files._selection == {} and not files._exported
