"""Presets: what a drop tile does, described as data (YAML).

A preset file holds either one preset (a mapping) or several under a
``presets:`` key. Built-in presets ship in ``roue/presets``; people add or
override presets in ``$XDG_CONFIG_HOME/roue/presets``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .detect import kind_of, mime_matches, mime_type
from .errors import PresetError

GROUPS: dict[str, str] = {
    "image": "Images",
    "video": "Video",
    "audio": "Audio",
    "document": "Documents",
    "custom": "Custom",
}

BACKENDS = ("ffmpeg", "image", "document", "ghostscript", "command")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_EXT_RE = re.compile(r"^[a-z0-9]{1,10}$")


@dataclass(frozen=True)
class Preset:
    """One conversion target, shown as a tile."""

    id: str
    name: str
    group: str
    backend: str
    accepts: tuple[str, ...]
    output_ext: str
    description: str = ""
    icon: str = ""
    rejects: tuple[str, ...] = ()
    suffix: str = ""
    output: str = "file"  # "file" or "folder"
    only_if_smaller: bool = False
    keywords: tuple[str, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    source: Path | None = None
    builtin: bool = False

    def accepts_mime(self, mime: str) -> bool:
        return mime_matches(mime, self.accepts) and not mime_matches(mime, self.rejects)

    def accepts_file(self, path: Path) -> bool:
        return self.accepts_mime(mime_type(path))

    def output_extension(self, source: Path) -> str:
        if self.output_ext == "same":
            return source.suffix.lstrip(".").lower() or "out"
        return self.output_ext

    @property
    def group_label(self) -> str:
        return GROUPS.get(self.group, self.group.title())

    def matches_query(self, query: str) -> bool:
        haystack = " ".join((self.id, self.name, self.description, *self.keywords)).lower()
        return all(word in haystack for word in query.lower().split())


def _as_tuple(value: Any, *, key: str, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    raise PresetError(f"{where}: '{key}' must be a string or a list of strings.")


def parse_preset(data: Mapping[str, Any], *, source: Path | None = None) -> Preset:
    """Build a Preset from a mapping, with friendly validation errors."""
    where = str(source) if source else "preset"
    if not isinstance(data, Mapping):
        raise PresetError(f"{where}: a preset must be a mapping of keys to values.")
    missing = [k for k in ("id", "name", "backend", "accepts", "output_ext") if k not in data]
    if missing:
        raise PresetError(f"{where}: missing required key(s): {', '.join(missing)}.")
    preset_id = str(data["id"])
    where = f"{where} ({preset_id})"
    if not _ID_RE.match(preset_id):
        raise PresetError(
            f"{where}: id must use lowercase letters, digits and dashes (like 'video-to-gif')."
        )
    backend = str(data["backend"])
    if backend not in BACKENDS:
        raise PresetError(
            f"{where}: unknown backend '{backend}'. Use one of {', '.join(BACKENDS)}."
        )
    output_ext = str(data["output_ext"]).lower().lstrip(".")
    if output_ext != "same" and not _EXT_RE.match(output_ext):
        raise PresetError(f"{where}: output_ext must be an extension like 'mp4' or 'same'.")
    output = str(data.get("output", "file"))
    if output not in ("file", "folder"):
        raise PresetError(f"{where}: output must be 'file' or 'folder'.")
    params = data.get("params") or {}
    if not isinstance(params, Mapping):
        raise PresetError(f"{where}: params must be a mapping.")
    if backend == "command":
        command = params.get("command")
        if not command or not isinstance(command, (str, list)):
            raise PresetError(f"{where}: the command backend needs params.command.")
    accepts = _as_tuple(data["accepts"], key="accepts", where=where)
    if not accepts:
        raise PresetError(f"{where}: accepts must list at least one MIME type, like 'image/*'.")
    suffix = str(data.get("suffix", ""))
    if "/" in suffix or "\0" in suffix:
        raise PresetError(f"{where}: suffix can't contain '/'.")
    return Preset(
        id=preset_id,
        name=str(data["name"]),
        group=str(data.get("group", "custom")),
        backend=backend,
        accepts=accepts,
        rejects=_as_tuple(data.get("rejects"), key="rejects", where=where),
        output_ext=output_ext,
        description=str(data.get("description", "")),
        icon=str(data.get("icon", "")),
        suffix=suffix,
        output=output,
        only_if_smaller=bool(data.get("only_if_smaller", False)),
        keywords=_as_tuple(data.get("keywords"), key="keywords", where=where),
        params=dict(params),
        source=source,
    )


def load_preset_file(path: Path, *, builtin: bool = False) -> list[Preset]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PresetError(f"{path}: this isn't valid YAML.", details=str(exc)) from exc
    except OSError as exc:
        raise PresetError(f"{path}: couldn't read the file ({exc.strerror}).") from exc
    if data is None:
        return []
    entries = data.get("presets") if isinstance(data, dict) and "presets" in data else [data]
    if not isinstance(entries, list):
        raise PresetError(f"{path}: 'presets' must be a list.")
    presets = [parse_preset(entry, source=path) for entry in entries]
    return [replace(p, builtin=builtin) for p in presets]


def builtin_preset_dir() -> Path:
    return Path(str(resources.files("roue") / "presets"))


def user_preset_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "roue" / "presets"


class PresetRegistry:
    """An ordered collection of presets with lookup and matching."""

    def __init__(self, presets: Iterable[Preset] = (), *, problems: list[str] | None = None):
        self._presets: dict[str, Preset] = {}
        for preset in presets:
            # Later definitions (user presets) replace earlier ones with the same id.
            self._presets[preset.id] = preset
        self.problems: list[str] = problems or []

    def __iter__(self) -> Iterator[Preset]:
        return iter(self.ordered())

    def __len__(self) -> int:
        return len(self._presets)

    def __contains__(self, preset_id: object) -> bool:
        return preset_id in self._presets

    def get(self, preset_id: str) -> Preset:
        try:
            return self._presets[preset_id]
        except KeyError:
            close = [p for p in self._presets if preset_id in p or p in preset_id][:3]
            hint = f"Did you mean: {', '.join(close)}?" if close else "Run 'roue list' to see them."
            raise PresetError(f"There's no preset called '{preset_id}'.", hint=hint) from None

    def ordered(self) -> list[Preset]:
        order = list(GROUPS)
        position = {pid: i for i, pid in enumerate(self._presets)}
        return sorted(
            self._presets.values(),
            key=lambda p: (
                order.index(p.group) if p.group in order else len(order),
                position[p.id],
            ),
        )

    def by_group(self) -> dict[str, list[Preset]]:
        groups: dict[str, list[Preset]] = {}
        for preset in self.ordered():
            groups.setdefault(preset.group, []).append(preset)
        return groups

    def matching(self, mimes: Iterable[str]) -> list[Preset]:
        """Presets that accept every given MIME type, most relevant first."""
        mimes = list(mimes)
        if not mimes:
            return []
        kinds = [kind_of(m) for m in mimes]
        main_kind = max(set(kinds), key=kinds.count)
        found = [p for p in self.ordered() if all(p.accepts_mime(m) for m in mimes)]
        return sorted(found, key=lambda p: p.group != main_kind)

    def matching_files(self, paths: Iterable[Path]) -> list[Preset]:
        return self.matching(mime_type(p) for p in paths)

    def without(self, preset_ids: Iterable[str]) -> PresetRegistry:
        hidden = set(preset_ids)
        return PresetRegistry(
            (p for p in self._presets.values() if p.id not in hidden), problems=self.problems
        )


def load_presets(
    dirs: Iterable[Path] | None = None, *, include_user: bool = True
) -> PresetRegistry:
    """Load built-in presets, then user presets (which may override them).

    Invalid user preset files don't stop the app: they are reported in
    ``registry.problems`` instead. Invalid built-in presets raise, because
    that's a bug.
    """
    presets: list[Preset] = []
    problems: list[str] = []
    builtin_dir = builtin_preset_dir()
    for path in sorted(builtin_dir.glob("*.yaml")):
        presets.extend(load_preset_file(path, builtin=True))
    extra = list(dirs) if dirs is not None else []
    if include_user:
        extra.append(user_preset_dir())
    for directory in extra:
        if not directory.is_dir():
            continue
        for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
            try:
                presets.extend(load_preset_file(path))
            except PresetError as exc:
                problems.append(exc.message)
    return PresetRegistry(presets, problems=problems)
