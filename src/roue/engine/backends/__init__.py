"""Conversion backends, one per family of tools."""

from __future__ import annotations

from ..presets import Preset
from ..tools import which
from .base import Backend, JobContext, Requirements
from .command import CommandBackend
from .document import DocumentBackend
from .ffmpeg import FFmpegBackend
from .ghostscript import GhostscriptBackend
from .image import ImageBackend

BACKENDS: dict[str, Backend] = {
    "ffmpeg": FFmpegBackend(),
    "image": ImageBackend(),
    "document": DocumentBackend(),
    "ghostscript": GhostscriptBackend(),
    "command": CommandBackend(),
}


def backend_for(preset: Preset) -> Backend:
    return BACKENDS[preset.backend]


def missing_tools(preset: Preset, mime: str | None = None) -> Requirements:
    """Requirement groups that no installed tool satisfies."""
    groups = backend_for(preset).requirements(preset, mime)
    return [group for group in groups if not any(which(tool) for tool in group)]


def is_available(preset: Preset, mime: str | None = None) -> bool:
    return not missing_tools(preset, mime)


__all__ = [
    "BACKENDS",
    "Backend",
    "JobContext",
    "Requirements",
    "backend_for",
    "is_available",
    "missing_tools",
]
