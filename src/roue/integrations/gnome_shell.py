"""Roue's GNOME Shell helper extension.

On GNOME Wayland the app can't keep the wheel above other windows or open it
at the pointer: the compositor decides. A tiny Shell extension does both. It
is optional; without it the wheel still works.

The .deb installs it under /usr/share; ``roue setup`` copies it to
``~/.local/share`` for other installs. GNOME only discovers new extensions
when it starts, so a fresh install becomes active after the next login.
"""

from __future__ import annotations

import enum
import re
import shutil
import subprocess
from pathlib import Path

from .desktop import SYSTEM_DATA, Installed, data_home, package_data
from .hotkey import parse_string_array
from .session import is_gnome, session_type

UUID = "roue@guilyx.github.io"
_SCHEMA = "org.gnome.shell"
_FILES = ("metadata.json", "extension.js")


class State(enum.Enum):
    ACTIVE = "active"  # loaded and running
    PENDING = "pending"  # turned on, starts at the next login
    OFF = "off"  # installed, not turned on
    ERROR = "error"  # GNOME refused it (error or unsupported GNOME version)
    MISSING = "missing"  # not installed


def wanted() -> bool:
    """True where the helper makes a difference: GNOME on Wayland."""
    return is_gnome() and session_type() == "wayland"


def extension_dir(base: Path | None = None) -> Path:
    return (base or data_home()) / "gnome-shell" / "extensions" / UUID


def installed() -> bool:
    return any((extension_dir(b) / "extension.js").exists() for b in (SYSTEM_DATA, None))


def install(base: Path | None = None) -> Installed:
    target = extension_dir(base)
    target.mkdir(parents=True, exist_ok=True)
    for name in _FILES:
        shutil.copyfile(package_data("gnome-shell", UUID, name), target / name)
    return Installed(target, "GNOME helper (wheel on top, at the pointer)")


def uninstall(base: Path | None = None) -> list[Path]:
    target = extension_dir(base)
    if not target.exists():
        return []
    shutil.rmtree(target)
    return [target]


def _run(*args: str) -> subprocess.CompletedProcess[str] | None:
    if not shutil.which(args[0]):
        return None
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _enabled_in_settings() -> bool:
    proc = _run("gsettings", "get", _SCHEMA, "enabled-extensions")
    return bool(proc and proc.returncode == 0 and UUID in parse_string_array(proc.stdout))


def parse_state(info: str) -> State | None:
    """Read the state from ``gnome-extensions info`` output."""
    match = re.search(r"^\s*State:\s*(.+?)\s*$", info, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).upper()
    if value in ("ACTIVE", "ENABLED"):
        return State.ACTIVE
    if value in ("ERROR", "OUT OF DATE"):
        return State.ERROR
    return None  # INACTIVE, DISABLED, INITIALIZED...: decided by the setting


def state() -> State:
    if not installed():
        return State.MISSING
    proc = _run("gnome-extensions", "info", UUID)
    if proc and proc.returncode == 0:
        return parse_state(proc.stdout) or State.OFF
    # This GNOME session started before it was installed, so it doesn't know it.
    return State.PENDING if _enabled_in_settings() else State.OFF


def enable() -> State:
    """Turn the helper on. Returns PENDING when it starts at the next login."""
    if not installed():
        return State.MISSING
    proc = _run("gnome-extensions", "enable", UUID)
    if proc and proc.returncode == 0 and state() is State.ACTIVE:
        return State.ACTIVE
    # GNOME hasn't seen it yet: list it so it starts with the next session.
    current = _run("gsettings", "get", _SCHEMA, "enabled-extensions")
    if current is None or current.returncode != 0:
        return State.OFF
    uuids = parse_string_array(current.stdout)
    if UUID not in uuids:
        uuids.append(UUID)
        value = "[" + ", ".join(repr(u) for u in uuids) + "]"
        done = _run("gsettings", "set", _SCHEMA, "enabled-extensions", value)
        if done is None or done.returncode != 0:
            return State.OFF
    return state()


def disable() -> None:
    _run("gnome-extensions", "disable", UUID)
    current = _run("gsettings", "get", _SCHEMA, "enabled-extensions")
    if current and current.returncode == 0:
        uuids = parse_string_array(current.stdout)
        if UUID in uuids:
            uuids.remove(UUID)
            value = "[" + ", ".join(repr(u) for u in uuids) + "]"
            _run("gsettings", "set", _SCHEMA, "enabled-extensions", value)


def describe(current: State) -> str:
    return {
        State.ACTIVE: "on",
        State.PENDING: "turned on: starts after you log out and back in",
        State.OFF: "off",
        State.ERROR: "GNOME couldn't load it (unsupported GNOME version?)",
        State.MISSING: "not installed",
    }[current]
