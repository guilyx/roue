"""The global hotkey that opens the wheel.

Wayland doesn't let apps grab keys, so on GNOME we register a regular
"custom shortcut" (the same thing Settings > Keyboard creates) that runs
``roue wheel``. Other desktops get instructions instead.
"""

from __future__ import annotations

import ast
import shutil
import subprocess

from .session import is_gnome

DEFAULT_BINDING = "<Super><Shift>d"

_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
_ENTRY_SCHEMA = f"{_SCHEMA}.custom-keybinding"
_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/roue/"


class HotkeyError(Exception):
    pass


def _gsettings(*args: str) -> str:
    exe = shutil.which("gsettings")
    if not exe:
        raise HotkeyError("gsettings isn't available, so the shortcut can't be set automatically.")
    proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=10, check=False)
    if proc.returncode != 0:
        raise HotkeyError(proc.stderr.strip() or "gsettings failed.")
    return proc.stdout.strip()


def parse_string_array(value: str) -> list[str]:
    """Parse gsettings output like ``@as []`` or ``['/a/', '/b/']``."""
    value = value.strip()
    if value.startswith("@as"):
        value = value[3:].strip()
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def _format_array(items: list[str]) -> str:
    return "[" + ", ".join(repr(i) for i in items) + "]"


def can_install() -> bool:
    if not is_gnome() or not shutil.which("gsettings"):
        return False
    try:
        return _SCHEMA in _gsettings("list-schemas").split()
    except HotkeyError:
        return False


def current_binding() -> str | None:
    """The binding Roue's shortcut uses, or None if it isn't set."""
    try:
        paths = parse_string_array(_gsettings("get", _SCHEMA, "custom-keybindings"))
        if _PATH not in paths:
            return None
        binding = _gsettings("get", f"{_ENTRY_SCHEMA}:{_PATH}", "binding")
    except HotkeyError:
        return None
    return binding.strip("'") or None


def install(command: str, binding: str = DEFAULT_BINDING) -> None:
    if not can_install():
        raise HotkeyError("Automatic shortcut setup only works on GNOME for now.")
    entry = f"{_ENTRY_SCHEMA}:{_PATH}"
    _gsettings("set", entry, "name", "Roue: open the wheel")
    _gsettings("set", entry, "command", command)
    _gsettings("set", entry, "binding", binding)
    paths = parse_string_array(_gsettings("get", _SCHEMA, "custom-keybindings"))
    if _PATH not in paths:
        _gsettings("set", _SCHEMA, "custom-keybindings", _format_array([*paths, _PATH]))


def remove() -> bool:
    if not can_install():
        return False
    paths = parse_string_array(_gsettings("get", _SCHEMA, "custom-keybindings"))
    if _PATH not in paths:
        return False
    paths.remove(_PATH)
    _gsettings("set", _SCHEMA, "custom-keybindings", _format_array(paths))
    entry = f"{_ENTRY_SCHEMA}:{_PATH}"
    for key in ("name", "command", "binding"):
        _gsettings("reset", entry, key)
    return True


def manual_instructions(command: str, binding: str = DEFAULT_BINDING) -> str:
    pretty = binding.replace("<", "").replace(">", "+").replace("+d", "+D")
    return (
        "Add a custom keyboard shortcut in your desktop's settings:\n"
        f"  Name:     Roue\n  Command:  {command}\n  Shortcut: {pretty}\n"
        "KDE: System Settings > Shortcuts > Add New > Command or Script.\n"
        "Xfce: Settings > Keyboard > Application Shortcuts > Add.\n"
        "Cinnamon/MATE: Keyboard settings > Shortcuts > Custom Shortcuts."
    )
