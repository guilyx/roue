"""The external command-line tools Roue drives, and how to install them."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .errors import MissingToolError


@dataclass(frozen=True)
class Tool:
    """A command-line program Roue can use."""

    id: str
    label: str
    executables: tuple[str, ...]
    purpose: str
    packages: dict[str, str] = field(default_factory=dict)
    homepage: str = ""


TOOLS: dict[str, Tool] = {
    tool.id: tool
    for tool in (
        Tool(
            "ffmpeg",
            "FFmpeg",
            ("ffmpeg",),
            "Video and audio conversions",
            {"apt": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg", "zypper": "ffmpeg"},
            "https://ffmpeg.org",
        ),
        Tool(
            "ffprobe",
            "FFprobe",
            ("ffprobe",),
            "Reading video and audio details",
            {"apt": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg", "zypper": "ffmpeg"},
            "https://ffmpeg.org",
        ),
        Tool(
            "vips",
            "libvips",
            ("vips",),
            "Fast image conversions (HEIC, AVIF, WebP...)",
            {"apt": "libvips-tools", "dnf": "vips-tools", "pacman": "libvips", "zypper": "vips"},
            "https://www.libvips.org",
        ),
        Tool(
            "imagemagick",
            "ImageMagick",
            ("magick", "convert"),
            "Image conversions when libvips is missing",
            {
                "apt": "imagemagick",
                "dnf": "ImageMagick",
                "pacman": "imagemagick",
                "zypper": "ImageMagick",
            },
            "https://imagemagick.org",
        ),
        Tool(
            "libreoffice",
            "LibreOffice",
            ("soffice", "libreoffice"),
            "Office documents to PDF",
            {
                "apt": "libreoffice-writer libreoffice-calc libreoffice-impress",
                "dnf": "libreoffice",
                "pacman": "libreoffice-fresh",
                "zypper": "libreoffice",
            },
            "https://www.libreoffice.org",
        ),
        Tool(
            "pandoc",
            "Pandoc",
            ("pandoc",),
            "Markdown to HTML, DOCX and PDF",
            {"apt": "pandoc", "dnf": "pandoc", "pacman": "pandoc", "zypper": "pandoc"},
            "https://pandoc.org",
        ),
        Tool(
            "ghostscript",
            "Ghostscript",
            ("gs",),
            "PDF compression, PDF to images and text",
            {
                "apt": "ghostscript",
                "dnf": "ghostscript",
                "pacman": "ghostscript",
                "zypper": "ghostscript",
            },
            "https://www.ghostscript.com",
        ),
    )
}

#: Programs pandoc can use to write PDF files, best first.
PDF_ENGINES = ("typst", "weasyprint", "wkhtmltopdf", "tectonic", "xelatex", "pdflatex")


@cache
def which(tool_id: str) -> str | None:
    """Return the path of the first installed executable for ``tool_id``.

    ``tool_id`` can be a known tool id or a plain executable name. Set
    ``ROUE_DISABLE_TOOLS=vips,pandoc`` to pretend tools are missing (handy
    for testing fallbacks).
    """
    disabled = {t.strip() for t in os.environ.get("ROUE_DISABLE_TOOLS", "").split(",")}
    if tool_id in disabled:
        return None
    tool = TOOLS.get(tool_id)
    for exe in tool.executables if tool else (tool_id,):
        if exe in disabled:
            continue
        found = shutil.which(exe)
        if found:
            return found
    return None


def require(*alternatives: str) -> str:
    """Return the executable of the first installed tool, or raise."""
    for tool_id in alternatives:
        found = which(tool_id)
        if found:
            return found
    raise MissingToolError(tuple(label(t) for t in alternatives), hint=install_hint(alternatives))


def label(tool_id: str) -> str:
    tool = TOOLS.get(tool_id)
    return tool.label if tool else tool_id


def package_manager() -> str | None:
    """Best guess of the system package manager."""
    for manager, exe in (
        ("apt", "apt"),
        ("dnf", "dnf"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
    ):
        if shutil.which(exe):
            return manager
    return None


_INSTALL_COMMANDS = {
    "apt": "sudo apt install {}",
    "dnf": "sudo dnf install {}",
    "pacman": "sudo pacman -S {}",
    "zypper": "sudo zypper install {}",
}


def install_command(
    tool_ids: tuple[str, ...] | list[str], manager: str | None = None
) -> str | None:
    """Shell command that installs the given tools, or None if unknown."""
    manager = manager or package_manager()
    if manager not in _INSTALL_COMMANDS:
        return None
    packages: list[str] = []
    for tool_id in tool_ids:
        tool = TOOLS.get(tool_id)
        pkg = tool.packages.get(manager) if tool else None
        if pkg and pkg not in packages:
            packages.append(pkg)
    if not packages:
        return None
    return _INSTALL_COMMANDS[manager].format(" ".join(packages))


def install_hint(alternatives: tuple[str, ...]) -> str | None:
    # Suggest installing the first (preferred) alternative.
    cmd = install_command(alternatives[:1])
    return f"Install it with: {cmd}" if cmd else None


def pdf_engine() -> str | None:
    """First PDF engine pandoc can use, if any."""
    for engine in PDF_ENGINES:
        if which(engine):
            return engine
    return None


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
