"""Roue for Files (Nautilus): right-click any files > Convert to…

Installed by ``roue setup`` (per user) or by the .deb (system-wide). Needs
nautilus-python (``python3-nautilus`` on Debian/Ubuntu).

Jobs run in the Roue app over D-Bus, so progress and notifications are
shared with the panel. If the app can't be reached, the ``roue`` command
runs instead and shows a notification when it's done.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import gi

gi.require_version("Nautilus", "4.0")
from gi.repository import Gio, GLib, GObject, Nautilus  # noqa: E402

APP_ID = "io.github.guilyx.Roue"
OBJECT_PATH = "/io/github/guilyx/Roue"
# Filled in at install time with the absolute path of the roue command.
ROUE_COMMAND = "@ROUE_COMMAND@"
MAX_ITEMS = 6
CACHE_SECONDS = 20


def _command() -> list[str]:
    if not ROUE_COMMAND.startswith("@"):
        return ROUE_COMMAND.split()
    found = shutil.which("roue")
    return [found] if found else []


def _kind(mime: str) -> str:
    top = mime.split("/", 1)[0]
    return top if top in ("image", "video", "audio") else "document"


class _Catalog:
    """Presets, read through the roue package when importable, else the CLI."""

    def __init__(self) -> None:
        self._presets: list[dict[str, Any]] = []
        self._loaded = -CACHE_SECONDS
        self._mime_type: Any = None

    def presets(self) -> list[dict[str, Any]]:
        if time.monotonic() - self._loaded > CACHE_SECONDS:
            self._reload()
        return self._presets

    def _reload(self) -> None:
        self._loaded = time.monotonic()
        try:
            from roue.engine.backends import is_available
            from roue.engine.detect import mime_type
            from roue.engine.presets import load_presets
            from roue.engine.settings import Settings

            registry = load_presets().without(Settings.load().disabled_presets)
            self._presets = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "group": p.group,
                    "accepts": list(p.accepts),
                    "rejects": list(p.rejects),
                    "available": is_available(p),
                }
                for p in registry
            ]
            self._mime_type = mime_type
            return
        except Exception:  # not importable from this Python: ask the CLI
            self._mime_type = None
        command = _command()
        if not command:
            self._presets = []
            return
        try:
            out = subprocess.run(
                [*command, "list", "--json"], capture_output=True, text=True, timeout=5, check=True
            )
            self._presets = json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            self._presets = []

    def mime(self, info: Nautilus.FileInfo, path: str) -> str:
        if self._mime_type is not None:
            return str(self._mime_type(Path(path)))
        return str(info.get_mime_type())

    def matching(self, mimes: list[str]) -> list[dict[str, Any]]:
        def accepts(preset: dict[str, Any], mime: str) -> bool:
            return any(fnmatchcase(mime, p) for p in preset["accepts"]) and not any(
                fnmatchcase(mime, p) for p in preset.get("rejects", [])
            )

        found = [
            p
            for p in self.presets()
            if p.get("available", True) and all(accepts(p, m) for m in mimes)
        ]
        kinds = [_kind(m) for m in mimes]
        main = max(set(kinds), key=kinds.count)
        return sorted(found, key=lambda p: p.get("group") != main)


_catalog = _Catalog()


def _spawn(args: list[str]) -> None:
    command = _command()
    if command:
        subprocess.Popen(
            [*command, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _activate(action: str, parameter: GLib.Variant, fallback: list[str]) -> None:
    """Ask the Roue app to run an action, starting it if needed."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        _spawn(fallback)
        return

    def done(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error:
            _spawn(fallback)

    bus.call(
        APP_ID,
        OBJECT_PATH,
        "org.gtk.Actions",
        "Activate",
        GLib.Variant("(sava{sv})", (action, [parameter], {})),
        None,
        Gio.DBusCallFlags.NONE,
        15000,
        None,
        done,
    )


class RoueMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files: list[Nautilus.FileInfo]) -> list[Nautilus.MenuItem]:
        if not files:
            return []
        paths: list[str] = []
        mimes: list[str] = []
        for info in files:
            if info.is_directory():
                return []
            location = info.get_location()
            path = location.get_path() if location else None
            if not path:
                return []  # not a local file (network share without a mount...)
            paths.append(path)
            mimes.append(_catalog.mime(info, path))
        presets = _catalog.matching(mimes)
        if not presets:
            return []

        top = Nautilus.MenuItem(name="Roue::Convert", label="Convert to…", tip="Convert with Roue")
        submenu = Nautilus.Menu()
        top.set_submenu(submenu)
        for preset in presets[:MAX_ITEMS]:
            item = Nautilus.MenuItem(
                name=f"Roue::{preset['id']}",
                label=preset["name"],
                tip=preset.get("description", ""),
            )
            item.connect("activate", self._run, preset["id"], paths)
            submenu.append_item(item)
        if len(presets) > MAX_ITEMS:
            more = Nautilus.MenuItem(
                name="Roue::More", label="More…", tip="Open the Roue panel with these files"
            )
            more.connect("activate", self._stage, paths)
            submenu.append_item(more)
        return [top]

    def _run(self, _item: Nautilus.MenuItem, preset_id: str, paths: list[str]) -> None:
        _activate(
            "run-preset",
            GLib.Variant("(sas)", (preset_id, paths)),
            ["convert", "--notify", preset_id, *paths],
        )

    def _stage(self, _item: Nautilus.MenuItem, paths: list[str]) -> None:
        _activate("stage-files", GLib.Variant("as", paths), ["panel", *paths])
