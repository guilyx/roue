"""What Roue can convert with the tools installed, and installing the rest.

On apt systems (Ubuntu, Debian) the app installs missing tools itself with
``pkexec apt-get install``: the desktop asks for the password first.
Elsewhere it shows the command to copy.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from ..engine import tools


@dataclass(frozen=True)
class Capability:
    """Something Roue can do once one of ``tools`` is installed."""

    title: str
    detail: str
    tools: tuple[str, ...]  # any one of these is enough
    install: str  # the tool to install when none is there


CAPABILITIES = (
    Capability("Video and audio", "MP4, GIF, MP3, Under 10 MB…", ("ffmpeg",), "ffmpeg"),
    Capability("Images", "JPG, PNG, WebP, AVIF, iPhone photos", ("vips", "imagemagick"), "vips"),
    Capability("PDF tools", "Compress PDFs, pages to images", ("ghostscript",), "ghostscript"),
    Capability("Markdown", "Markdown to Word and web pages", ("pandoc",), "pandoc"),
    Capability(
        "Office documents to PDF",
        "Word, Excel and PowerPoint to PDF · LibreOffice, a large download",
        ("libreoffice",),
        "libreoffice",
    ),
)


def missing() -> list[Capability]:
    return [c for c in CAPABILITIES if not any(tools.which(t) for t in c.tools)]


def can_install() -> bool:
    """True if the app can install packages itself (apt, with a password prompt)."""
    return (
        tools.package_manager() == "apt"
        and shutil.which("pkexec") is not None
        and shutil.which("apt-get") is not None
    )


def apt_packages(tool_ids: list[str] | tuple[str, ...]) -> list[str]:
    names: list[str] = []
    for tool_id in tool_ids:
        tool = tools.TOOLS.get(tool_id)
        for name in tool.packages.get("apt", "").split() if tool else []:
            if name not in names:
                names.append(name)
    return names


def install_argv(packages: list[str]) -> list[str]:
    """The command that installs ``packages``. It asks for the password itself."""
    # The lock timeout covers the update check that runs right after login.
    return ["pkexec", "apt-get", "install", "--yes", "-o", "DPkg::Lock::Timeout=300", *packages]
