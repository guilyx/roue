"""What kind of desktop session we're running in."""

from __future__ import annotations

import os


def session_type() -> str:
    """'wayland', 'x11' or 'tty'."""
    kind = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if kind in ("wayland", "x11"):
        return kind
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "tty"


def desktops() -> list[str]:
    """Lower-case desktop names, e.g. ['ubuntu', 'gnome']."""
    return [d.lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d]


def is_gnome() -> bool:
    return any(d in ("gnome", "ubuntu", "pop", "gnome-classic") for d in desktops())


def has_display() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def trigger_explanation() -> str:
    """One line telling people how they'll open the wheel in this session."""
    kind = session_type()
    if kind == "x11":
        return "Hold Shift while dragging a file to open the wheel, or press the hotkey."
    if kind == "wayland":
        return "Right-click files in Files > Convert with Roue…, or press the hotkey and drop."
    return "No desktop session detected: use 'roue convert' from the terminal."
