"""What every backend gets to work with: the job context and a safe runner."""

from __future__ import annotations

import collections
import os
import signal
import subprocess
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..detect import MediaInfo, noun_for, probe
from ..errors import Cancelled, ConversionError
from ..presets import Preset

#: Each entry is a group of alternatives: ``("vips", "imagemagick")`` means
#: "either one". All groups must be satisfied.
Requirements = list[tuple[str, ...]]

ProgressCallback = Callable[[float | None], None]


class Backend(Protocol):
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements: ...

    def run(self, ctx: JobContext) -> None: ...


_FRIENDLY_FAILURES: tuple[tuple[str, str], ...] = (
    # libheif without codec plugins (they're separate packages on Debian/Ubuntu).
    (
        "heifsave: Unsupported compression",
        "Saving this format needs an encoder that isn't installed. "
        "For AVIF install libheif-plugin-aomenc, for HEIC libheif-plugin-x265.",
    ),
    (
        "Unsupported codec",
        "Opening this image needs a decoder that isn't installed. "
        "For HEIC photos install libheif-plugin-libde265.",
    ),
    ("No space left on device", "The disk is full."),
    ("Permission denied", "Roue isn't allowed to read or write one of the files."),
    ("Invalid data found when processing input", "This file seems damaged or isn't a real {noun}."),
    ("moov atom not found", "This video is incomplete or damaged."),
    ("not a known image format", "This image format isn't supported by the installed tools."),
    ("no decode delegate", "This image format isn't supported by your ImageMagick."),
    ("no encode delegate", "Your ImageMagick can't write this format. Installing libvips helps."),
    ("is not a known file format", "This image format isn't supported by the installed tools."),
    ("password", "This file is password-protected."),
    ("Encrypted", "This file is password-protected."),
)


def friendly_failure(output: str, default: str, mime: str = "") -> str:
    noun = noun_for(mime) if mime else "file"
    for needle, message in _FRIENDLY_FAILURES:
        if needle.lower() in output.lower():
            return message.format(noun=noun)
    return default


@dataclass
class JobContext:
    """Everything a backend needs to convert one file."""

    source: Path
    preset: Preset
    mime: str
    workdir: Path
    output: Path
    cancel_event: threading.Event = field(default_factory=threading.Event)
    on_progress: ProgressCallback | None = None
    _probe: MediaInfo | None = None
    _proc: subprocess.Popen[str] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def params(self) -> Mapping[str, Any]:
        return self.preset.params

    @property
    def output_folder(self) -> Path:
        """Where folder presets (one file per page...) write their files."""
        folder = self.workdir / "out"
        folder.mkdir(exist_ok=True)
        return folder

    def progress(self, fraction: float | None) -> None:
        if self.on_progress:
            self.on_progress(None if fraction is None else max(0.0, min(1.0, fraction)))

    def probe(self) -> MediaInfo:
        if self._probe is None:
            self._probe = probe(self.source)
        return self._probe

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()

    def run(
        self,
        cmd: list[str],
        *,
        failure: str,
        on_line: Callable[[str], None] | None = None,
        parse: str = "stdout",
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> str:
        """Run a tool, feed lines of ``parse`` to ``on_line``, and return its output.

        Raises ConversionError with ``failure`` (or a better guess from the
        tool's output) when the tool fails, and Cancelled when cancelled.
        """
        self.check_cancelled()
        full_env = {**os.environ, "LC_ALL": "C", **(env or {})}
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            env=full_env,
            cwd=cwd,
            start_new_session=True,
        )
        with self._lock:
            self._proc = proc
        tail: collections.deque[str] = collections.deque(maxlen=60)
        streams = {"stdout": proc.stdout, "stderr": proc.stderr}
        watched = streams.pop(parse)
        other = next(iter(streams.values()))

        def drain() -> None:
            assert other is not None
            for line in other:
                tail.append(line)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        assert watched is not None
        for line in watched:
            tail.append(line)
            if on_line:
                on_line(line.rstrip("\n"))
        proc.wait()
        reader.join(timeout=5)
        with self._lock:
            self._proc = None
        self.check_cancelled()
        output = "".join(tail)
        if proc.returncode != 0:
            raise ConversionError(
                friendly_failure(output, failure, self.mime), details=output.strip()
            )
        return output
