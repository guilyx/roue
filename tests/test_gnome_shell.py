"""The GNOME Shell helper: packaging and state parsing (no GNOME needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from roue.integrations import gnome_shell
from roue.integrations.desktop import package_data


def test_extension_metadata_matches_its_folder() -> None:
    folder = package_data("gnome-shell", gnome_shell.UUID)
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["uuid"] == gnome_shell.UUID
    # GNOME refuses extensions that don't list the running version.
    assert {"46", "50"} <= set(meta["shell-version"])
    assert (folder / "extension.js").read_text().startswith("// Roue")


def test_install_and_uninstall(tmp_path: Path) -> None:
    item = gnome_shell.install(base=tmp_path)
    assert sorted(p.name for p in item.path.iterdir()) == ["extension.js", "metadata.json"]
    assert gnome_shell.uninstall(base=tmp_path) == [item.path]
    assert not item.path.exists()


@pytest.mark.parametrize(
    ("info", "state"),
    [
        ("roue@guilyx.github.io\n  Enabled: Yes\n  State: ACTIVE\n", gnome_shell.State.ACTIVE),
        ("  State: ENABLED\n", gnome_shell.State.ACTIVE),  # GNOME 45-46 wording
        ("  State: OUT OF DATE\n", gnome_shell.State.ERROR),
        ("  State: ERROR\n", gnome_shell.State.ERROR),
        ("  State: INACTIVE\n", None),
        ("nothing useful", None),
    ],
)
def test_parse_state(info: str, state: gnome_shell.State | None) -> None:
    assert gnome_shell.parse_state(info) == state
