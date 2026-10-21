"""The GNOME Shell helper: packaging and state parsing (no GNOME needed)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from roue.integrations import gnome_shell

UUID = gnome_shell.UUID


@pytest.mark.parametrize(
    ("legacy", "versions"), [(False, {"45", "46", "50"}), (True, {"42", "43", "44"})]
)
def test_extension_metadata_matches_its_folder(legacy: bool, versions: set[str]) -> None:
    folder = gnome_shell.source_dir(legacy=legacy)
    meta = json.loads((folder / "metadata.json").read_text())
    assert folder.name == meta["uuid"] == UUID
    # GNOME refuses extensions that don't list the running version.
    assert versions <= set(meta["shell-version"])
    assert gnome_shell.is_legacy(folder) is legacy
    code = (folder / "extension.js").read_text()
    assert code.startswith("// Roue")
    # GNOME 45 loads extensions as ES modules; 42-44 call init().
    assert ("export default class" in code) is not legacy
    assert ("function init()" in code) is legacy


def test_install_and_uninstall(tmp_path: Path) -> None:
    item = gnome_shell.install(base=tmp_path)
    assert sorted(p.name for p in item.path.iterdir()) == ["extension.js", "metadata.json"]
    assert not gnome_shell.is_legacy(item.path)  # packages ship the GNOME 45+ copy
    assert gnome_shell.uninstall(base=tmp_path) == [item.path]
    assert not item.path.exists()


@pytest.fixture
def system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A system data folder with the package's copy of the helper."""
    folder = tmp_path / "usr-share"
    monkeypatch.setattr(gnome_shell, "SYSTEM_DATA", folder)
    gnome_shell.install(base=folder)
    return folder


@pytest.mark.parametrize(
    ("version", "legacy"), [(42, True), (44, True), (46, False), (None, False)]
)
def test_your_copy_matches_your_gnome(
    system: Path, monkeypatch: pytest.MonkeyPatch, version: int | None, legacy: bool
) -> None:
    monkeypatch.setattr(gnome_shell, "shell_version", lambda: version)
    # The package's copy is enough from GNOME 45 on; 42-44 need a copy of their own.
    assert gnome_shell.installed() is not legacy
    item = gnome_shell.install()
    assert item.path == gnome_shell.extension_dir()  # yours wins over the system's
    assert gnome_shell.is_legacy(item.path) is legacy
    assert gnome_shell.installed()


def test_an_old_copy_after_upgrading_gnome_is_replaced(
    system: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gnome_shell, "shell_version", lambda: 42)
    gnome_shell.install()
    monkeypatch.setattr(gnome_shell, "shell_version", lambda: 46)  # Ubuntu 22.04 -> 24.04
    assert not gnome_shell.installed()  # GNOME 46 would load your old copy, and refuse it
    assert not gnome_shell.is_legacy(gnome_shell.install().path)


def test_a_session_still_on_the_package_copy_waits_for_the_next_login(
    system: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # GNOME 42 found the package's copy (for GNOME 45+) when the session started.
    # Your own copy, in GNOME 42's format, loads at the next login.
    monkeypatch.setattr(gnome_shell, "shell_version", lambda: 42)
    gnome_shell.install()
    package_copy = gnome_shell.extension_dir(system)
    replies = {
        ("gnome-extensions", "info"): f"{UUID}\n  Path: {package_copy}\n  State: OUT OF DATE\n",
        ("gsettings", "get"): f"['{UUID}']\n",
    }

    def run(*args: str) -> subprocess.CompletedProcess[str] | None:
        reply = replies.get(args[:2])
        return None if reply is None else subprocess.CompletedProcess(args, 0, reply, "")

    monkeypatch.setattr(gnome_shell, "_run", run)
    assert gnome_shell.state() is gnome_shell.State.PENDING
    replies[("gnome-extensions", "info")] = (
        f"{UUID}\n  Path: {gnome_shell.extension_dir()}\n  State: ENABLED\n"
    )
    assert gnome_shell.state() is gnome_shell.State.ACTIVE


# Runs the GNOME 42-44 helper in gjs with stand-ins for GNOME Shell's objects.
LEGACY_DRIVER = """
const source = %s;
const calls = [];
const handlers = {};
const shell = {
    display: {
        connect: (signal, callback) => { handlers[signal] = callback; return 7; },
        disconnect: id => calls.push(['disconnect', id]),
        get_current_monitor: () => 0,
    },
    get_pointer: () => [100, 50],
};
const gi = {Meta: {WindowClientType: {WAYLAND: 0, X11: 1}}};
const init = new Function('imports', 'global', `${source}\nreturn init;`)({gi}, shell);
let shown = null;
const wheel = {
    connect: (signal, callback) => { calls.push(['connect', signal]); shown = callback; return 3; },
    disconnect: id => calls.push(['window-disconnect', id]),
    get_client_type: () => 0,
    get_gtk_application_id: () => 'io.github.guilyx.Roue',
    get_wm_class: () => null,
    get_title: () => 'Convert with Roue',
    make_above: () => calls.push(['make_above']),
    get_maximized: () => 0,
    is_fullscreen: () => false,
    get_work_area_for_monitor: () => ({x: 0, y: 32, width: 1280, height: 768}),
    get_frame_rect: () => ({width: 300, height: 300}),
    move_frame: (user, x, y) => calls.push(['move_frame', user, x, y]),
};
const extension = init();
extension.enable();
handlers['window-created'](null, wheel);
shown();
extension.disable();
print(JSON.stringify(calls));
"""


@pytest.mark.skipif(not shutil.which("gjs"), reason="needs gjs")
def test_legacy_helper_keeps_the_wheel_on_top_at_the_pointer(tmp_path: Path) -> None:
    code = (gnome_shell.source_dir(legacy=True) / "extension.js").read_text()
    driver = tmp_path / "driver.js"
    driver.write_text(LEGACY_DRIVER % json.dumps(code))
    proc = subprocess.run(["gjs", str(driver)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [
        ["connect", "shown"],
        ["window-disconnect", 3],
        ["make_above"],
        ["move_frame", True, 0, 32],  # centred on the pointer, kept below the top bar
        ["disconnect", 7],
    ]


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


def test_parse_path() -> None:
    info = f"{UUID}\n  Name: Roue\n  Path: /usr/share/gnome-shell/extensions/{UUID}\n"
    assert gnome_shell.parse_path(info) == Path(f"/usr/share/gnome-shell/extensions/{UUID}")
    assert gnome_shell.parse_path("nothing useful") is None
