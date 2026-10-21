"""Recent conversions and undo.

History is a small JSON-lines file in ``$XDG_STATE_HOME/roue``. Undo moves
the outputs of the last batch to the trash; it never deletes anything.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .runner import Batch

MAX_ENTRIES = 50


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "roue"


@dataclass(frozen=True)
class HistoryEntry:
    time: float
    preset_id: str
    preset_name: str
    summary: str
    sources: list[str]
    outputs: list[str]
    undone: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "preset_id": self.preset_id,
            "preset_name": self.preset_name,
            "summary": self.summary,
            "sources": self.sources,
            "outputs": self.outputs,
            "undone": self.undone,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            time=float(data["time"]),
            preset_id=str(data["preset_id"]),
            preset_name=str(data.get("preset_name", data["preset_id"])),
            summary=str(data.get("summary", "")),
            sources=[str(s) for s in data.get("sources", [])],
            outputs=[str(s) for s in data.get("outputs", [])],
            undone=bool(data.get("undone", False)),
        )


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or state_dir() / "history.jsonl"

    def entries(self) -> list[HistoryEntry]:
        """Most recent first."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        entries = []
        for line in lines:
            with contextlib.suppress(ValueError, KeyError, TypeError):
                entries.append(HistoryEntry.from_json(json.loads(line)))
        return list(reversed(entries))

    def _write(self, newest_first: list[HistoryEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        oldest_first = reversed(newest_first[:MAX_ENTRIES])
        tmp.write_text(
            "".join(json.dumps(e.to_json()) + "\n" for e in oldest_first), encoding="utf-8"
        )
        tmp.replace(self.path)

    def record(self, batch: Batch) -> HistoryEntry | None:
        if not batch.jobs:
            return None
        entry = HistoryEntry(
            time=batch.created_at,
            preset_id=batch.preset.id,
            preset_name=batch.preset.name,
            summary=batch.summary(),
            sources=[str(j.source) for j in batch.jobs],
            outputs=[str(p) for p in batch.outputs],
        )
        self._write([entry, *self.entries()])
        return entry

    def undo_last(self) -> tuple[HistoryEntry, list[Path]] | None:
        """Trash the outputs of the most recent batch that has any left."""
        entries = self.entries()
        for index, entry in enumerate(entries):
            if entry.undone or not entry.outputs:
                continue
            trashed = [p for p in map(Path, entry.outputs) if p.exists() and trash(p)]
            entries[index] = HistoryEntry(**{**entry.to_json(), "undone": True})
            self._write(entries)
            return entry, trashed
        return None


def trash(path: Path) -> bool:
    """Move a file or folder to the trash. Returns False if that failed."""
    gio = shutil.which("gio")
    if gio:
        result = subprocess.run(
            [gio, "trash", "--", str(path)], capture_output=True, timeout=30, check=False
        )
        if result.returncode == 0:
            return True
    return _home_trash(path)


def _home_trash(path: Path) -> bool:
    """Minimal freedesktop.org trash for the home trash folder."""
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    trash_dir = Path(data) / "Trash"
    files, info = trash_dir / "files", trash_dir / "info"
    try:
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        name = path.name
        for n in range(1, 10_000):
            try:
                fd = os.open(info / f"{name}.trashinfo", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                name = f"{path.stem}.{n}{path.suffix}"
        else:
            return False
        stamp = datetime.fromtimestamp(time.time(), tz=timezone.utc).astimezone()
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                "[Trash Info]\n"
                f"Path={quote(str(path.resolve()))}\n"
                f"DeletionDate={stamp.strftime('%Y-%m-%dT%H:%M:%S')}\n"
            )
        shutil.move(str(path), files / name)
    except OSError:
        return False
    return True
