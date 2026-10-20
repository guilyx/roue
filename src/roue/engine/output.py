"""Where results go. The one hard rule: never overwrite anything.

Tools write into a hidden scratch folder created next to the final
destination (same filesystem, so moving is instant). Results are then
committed with ``os.link`` or exclusive-create, which fail instead of
replacing a file that appeared in the meantime.
"""

from __future__ import annotations

import contextlib
import errno
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from .errors import RoueError

_MAX_ATTEMPTS = 10_000


def candidate_names(stem: str, ext: str) -> Iterator[str]:
    """``photo.jpg``, ``photo (2).jpg``, ``photo (3).jpg``..."""
    dot_ext = f".{ext}" if ext else ""
    yield f"{stem}{dot_ext}"
    for n in range(2, _MAX_ATTEMPTS):
        yield f"{stem} ({n}){dot_ext}"


def user_dir(name: str, fallback: str) -> Path:
    """An XDG user directory such as DOWNLOAD, read from user-dirs.dirs."""
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "user-dirs.dirs"
    with contextlib.suppress(OSError):
        for line in config.read_text(encoding="utf-8").splitlines():
            match = re.match(rf'^XDG_{name}_DIR="(.*)"$', line.strip())
            if match:
                return Path(match.group(1).replace("$HOME", str(home)))
    return home / fallback


def is_writable_dir(directory: Path) -> bool:
    return directory.is_dir() and os.access(directory, os.W_OK | os.X_OK)


def destination_dir(source: Path, out_dir: Path | None = None) -> tuple[Path, bool]:
    """Folder for the result of ``source``.

    Returns ``(folder, fell_back)``. When the source's folder is read-only
    (a camera, a mounted ISO...), results go to the Downloads folder.
    """
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        if not is_writable_dir(out_dir):
            raise RoueError(f"Can't write to {out_dir}.", hint="Pick another output folder.")
        return out_dir, False
    parent = source.parent
    if is_writable_dir(parent):
        return parent, False
    downloads = user_dir("DOWNLOAD", "Downloads")
    for fallback in (downloads, Path.home()):
        if is_writable_dir(fallback):
            return fallback, True
    raise RoueError(
        "There's nowhere to save the result: the file's folder is read-only.",
        hint="Use 'roue convert --output-dir' to choose a folder.",
    )


@contextlib.contextmanager
def scratch_dir(destination: Path) -> Iterator[Path]:
    """A hidden temporary folder inside ``destination``, always removed."""
    try:
        path = Path(tempfile.mkdtemp(prefix=".roue-", dir=destination))
    except OSError:
        path = Path(tempfile.mkdtemp(prefix="roue-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _place_file(tmp: Path, target: Path) -> bool:
    """Move ``tmp`` to ``target`` unless ``target`` exists. True on success."""
    try:
        os.link(tmp, target)
    except FileExistsError:
        return False
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EMLINK):
            raise
        # No hard links here (FAT, some network shares) or a different
        # filesystem: copy into an exclusively created file instead.
        try:
            with tmp.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        except FileExistsError:
            return False
        shutil.copystat(tmp, target)
    tmp.unlink(missing_ok=True)
    return True


def commit_file(tmp: Path, directory: Path, stem: str, ext: str) -> Path:
    """Move a finished temp file to the first free name in ``directory``."""
    for name in candidate_names(stem, ext):
        target = directory / name
        if target.exists() or target.is_symlink():
            continue
        if _place_file(tmp, target):
            return target
    raise RoueError(f"Couldn't find a free file name for {stem}.{ext}.")


def commit_folder(tmp_dir: Path, directory: Path, name: str) -> Path:
    """Move the files of ``tmp_dir`` into a new folder named after ``name``."""
    for candidate in candidate_names(name, ""):
        target = directory / candidate
        try:
            target.mkdir()
        except FileExistsError:
            continue
        for item in sorted(tmp_dir.iterdir()):
            commit_file(item, target, item.stem, item.suffix.lstrip("."))
        return target
    raise RoueError(f"Couldn't find a free folder name for {name}.")
