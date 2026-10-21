"""Install Roue into the desktop for the current user.

Packages (.deb, Flatpak) install these files system-wide. People who
installed with pipx or from source run ``roue setup`` instead, which writes
the same files under ``~/.local/share``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .. import APP_ID


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def package_data(*parts: str) -> Path:
    return Path(str(resources.files("roue").joinpath("data", *parts)))


def roue_command() -> str:
    """Absolute command to run Roue, usable from a .desktop file or hotkey."""
    argv0 = Path(sys.argv[0])
    if argv0.name == "roue" and argv0.is_absolute() and os.access(argv0, os.X_OK):
        return str(argv0)
    found = shutil.which("roue")
    if found:
        return found
    return f"{sys.executable} -m roue"


@dataclass(frozen=True)
class Installed:
    path: Path
    what: str


def _write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _render(template: str, command: str) -> str:
    text = package_data(template).read_text(encoding="utf-8")
    return text.replace("@EXEC@", command).replace("@APP_ID@", APP_ID)


def desktop_targets(base: Path | None = None) -> dict[str, Path]:
    base = base or data_home()
    return {
        "desktop": base / "applications" / f"{APP_ID}.desktop",
        "service": base / "dbus-1" / "services" / f"{APP_ID}.service",
        "icon": base / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
        "symbolic": base / "icons" / "hicolor" / "symbolic" / "apps" / f"{APP_ID}-symbolic.svg",
        "nautilus": base / "nautilus-python" / "extensions" / "roue_nautilus.py",
    }


def install_desktop_files(
    command: str | None = None, base: Path | None = None, *, refresh: bool = True
) -> list[Installed]:
    command = command or roue_command()
    targets = desktop_targets(base)
    _write(targets["desktop"], _render(f"{APP_ID}.desktop.in", command))
    _write(targets["service"], _render(f"{APP_ID}.service.in", command))
    for key, name in (("icon", f"{APP_ID}.svg"), ("symbolic", f"{APP_ID}-symbolic.svg")):
        targets[key].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package_data("icons", name), targets[key])
    if refresh:
        _refresh_caches(base or data_home())
    return [
        Installed(targets["desktop"], "app launcher"),
        Installed(targets["service"], "D-Bus service (instant panel, Files menu)"),
        Installed(targets["icon"], "icon"),
    ]


def nautilus_python_available() -> bool:
    """True if the Files (Nautilus) Python extension host is installed."""
    candidates = [
        Path(lib) / "nautilus" / folder / "libnautilus-python.so"
        for lib in (
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib/aarch64-linux-gnu",
            "/usr/lib64",
            "/usr/lib",
        )
        # extensions-4 since Nautilus 43, extensions-3.0 in Nautilus 42 (Ubuntu 22.04)
        for folder in ("extensions-4", "extensions-3.0")
    ]
    return any(p.exists() for p in candidates)


def install_nautilus_extension(command: str | None = None, base: Path | None = None) -> Installed:
    target = desktop_targets(base)["nautilus"]
    text = package_data("nautilus", "roue_nautilus.py").read_text(encoding="utf-8")
    _write(target, text.replace("@ROUE_COMMAND@", command or roue_command()))
    return Installed(target, "Files right-click menu")


#: Where the .deb puts the same files. ``roue setup`` skips what's already there.
SYSTEM_DATA = Path("/usr/share")
#: The APT source the .deb (or the install script) adds for updates.
UPDATE_CHANNEL = Path("/etc/apt/sources.list.d/roue.sources")


def system_installed(key: str) -> bool:
    return desktop_targets(SYSTEM_DATA)[key].exists()


def _boot_time() -> float:
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("btime "):
            return float(line.split()[1])
    return 0.0


def nautilus_started_before(moment: float) -> bool:
    """True if Files is running and started before ``moment`` (a timestamp).

    Files loads extensions when it starts, so it needs a restart to show a
    menu installed after that.
    """
    try:
        boot = _boot_time()
        ticks = os.sysconf("SC_CLK_TCK")
        entries = list(Path("/proc").iterdir())
    except (OSError, ValueError):
        return False
    uid = os.getuid()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid or (entry / "comm").read_text().strip() != "nautilus":
                continue
            # Field 22 of /proc/PID/stat: start time in clock ticks after boot.
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            started = boot + int(fields[19]) / ticks
        except (OSError, IndexError, ValueError):
            continue
        if started < moment:
            return True
    return False


def restart_nautilus() -> None:
    if shutil.which("nautilus"):
        subprocess.run(["nautilus", "-q"], capture_output=True, timeout=10, check=False)


def uninstall(base: Path | None = None) -> list[Path]:
    removed = []
    for path in desktop_targets(base).values():
        if path.exists():
            path.unlink()
            removed.append(path)
    _refresh_caches(base or data_home())
    return removed


def _refresh_caches(base: Path) -> None:
    for cmd in (
        ["update-desktop-database", str(base / "applications")],
        ["gtk-update-icon-cache", "-qtf", str(base / "icons" / "hicolor")],
    ):
        if shutil.which(cmd[0]) and Path(cmd[-1]).exists():
            subprocess.run(cmd, capture_output=True, timeout=30, check=False)


def call_app_action(action: str) -> bool:
    """Activate a parameterless action on the running app, via gdbus."""
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False
    object_path = "/" + APP_ID.replace(".", "/")
    proc = subprocess.run(
        [
            gdbus,
            "call",
            "--session",
            "--dest",
            APP_ID,
            "--object-path",
            object_path,
            "--method",
            "org.gtk.Actions.Activate",
            action,
            "[]",
            "{}",
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    return proc.returncode == 0
