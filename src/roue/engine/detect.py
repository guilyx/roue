"""Work out what a file is: MIME type, kind, and media details."""

from __future__ import annotations

import json
import mimetypes
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from . import tools
from .errors import ConversionError

# Extensions the stdlib table misses or gets wrong on some systems.
_EXTRA_TYPES: dict[str, str] = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".webp": "image/webp",
    ".jxl": "image/jxl",
    ".svg": "image/svg+xml",
    ".svgz": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
    ".3gp": "video/3gpp",
    ".mts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".mp3": "audio/mpeg",
    ".wav": "audio/x-wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".wma": "audio/x-ms-wma",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".rst": "text/x-rst",
    ".org": "text/org",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".rtf": "application/rtf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".csv": "text/csv",
    ".epub": "application/epub+zip",
}

#: MIME patterns that make up each file kind. Used for grouping and wording.
KIND_PATTERNS: dict[str, tuple[str, ...]] = {
    "image": ("image/*",),
    "video": ("video/*",),
    "audio": ("audio/*",),
    "document": (
        "application/pdf",
        "application/rtf",
        "application/msword",
        "application/vnd.ms-*",
        "application/vnd.openxmlformats-officedocument.*",
        "application/vnd.oasis.opendocument.*",
        "application/epub+zip",
        "text/*",
    ),
}

KIND_NOUNS = {
    "image": "image",
    "video": "video",
    "audio": "audio file",
    "document": "document",
    "other": "file",
}


def mime_type(path: Path) -> str:
    """MIME type of ``path``, from its extension, then from its content."""
    suffix = path.suffix.lower()
    if suffix in _EXTRA_TYPES:
        return _EXTRA_TYPES[suffix]
    guess, _ = mimetypes.guess_type(path.name, strict=False)
    if guess:
        return guess
    return _sniff(path) or "application/octet-stream"


def _sniff(path: Path) -> str | None:
    exe = tools.which("file")
    if not exe or not path.is_file():
        return None
    try:
        out = subprocess.run(
            [exe, "--brief", "--mime-type", "--", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    result = out.stdout.strip()
    return result if "/" in result else None


def mime_matches(mime: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """True if ``mime`` matches any glob pattern such as ``image/*``."""
    return any(fnmatchcase(mime, pattern) for pattern in patterns)


def kind_of(mime: str) -> str:
    for kind, patterns in KIND_PATTERNS.items():
        if mime_matches(mime, patterns):
            return kind
    return "other"


def noun_for(mime: str) -> str:
    return KIND_NOUNS[kind_of(mime)]


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe tells us about a video or audio file."""

    duration: float | None
    has_video: bool
    has_audio: bool
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    sample_rate: int | None = None


def probe(path: Path) -> MediaInfo:
    """Read duration and streams of a media file with ffprobe."""
    exe = tools.require("ffprobe")
    proc = subprocess.run(
        [
            exe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "--",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise ConversionError(
            "This file couldn't be read. It may be damaged or not a real media file.",
            details=proc.stderr.strip(),
        )
    return parse_probe(json.loads(proc.stdout or "{}"))


def parse_probe(data: dict[str, Any]) -> MediaInfo:
    streams = data.get("streams") or []
    # Cover art in audio files shows up as a one-frame video stream.
    videos = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    duration: float | None = None
    for candidate in [
        data.get("format", {}).get("duration"),
        *(s.get("duration") for s in streams),
    ]:
        try:
            value = float(candidate) if candidate is not None else None
        except (TypeError, ValueError):
            value = None
        if value and value > 0:
            duration = value
            break
    video = videos[0] if videos else {}
    audio = audios[0] if audios else {}
    return MediaInfo(
        duration=duration,
        has_video=bool(videos),
        has_audio=bool(audios),
        width=video.get("width"),
        height=video.get("height"),
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name"),
        sample_rate=int(audio["sample_rate"])
        if str(audio.get("sample_rate", "")).isdigit()
        else None,
    )
