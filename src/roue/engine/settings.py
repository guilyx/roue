"""User settings, stored as YAML in ``$XDG_CONFIG_HOME/roue/settings.yaml``.

Kept outside GSettings on purpose: the CLI and the file-manager extension
read the same file without needing GTK.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "roue"


@dataclass
class Settings:
    #: Preset ids hidden from the panel and menus.
    disabled_presets: list[str] = field(default_factory=list)
    #: Parallel conversions. 0 means one per CPU core.
    max_jobs: int = 0
    #: Show a desktop notification when a drop finishes.
    notifications: bool = True
    #: Write results here instead of next to the original (None = next to it).
    output_dir: str | None = None
    #: Keep running in the background after the panel closes (faster reopen).
    stay_in_background: bool = True
    #: On X11, show the panel when a drag starts with Shift held.
    shift_drag: bool = True
    #: Convert everything inside dropped folders, not just the top level.
    recursive_folders: bool = False
    #: The setup dialog was shown once (it stays in the main menu).
    welcome_done: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or config_dir() / "settings.yaml"
        data: Any = None
        with contextlib.suppress(OSError, yaml.YAMLError):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        settings = cls()
        for key, value in data.items():
            if key in known and _same_kind(getattr(settings, key), value, key):
                setattr(settings, key, value)
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "settings.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            "# Roue settings. Edit here or in Preferences.\n"
            + yaml.safe_dump(asdict(self), sort_keys=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    @property
    def output_path(self) -> Path | None:
        return Path(self.output_dir).expanduser() if self.output_dir else None


def _same_kind(default: Any, value: Any, key: str) -> bool:
    if key == "output_dir":
        return value is None or isinstance(value, str)
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(default))
