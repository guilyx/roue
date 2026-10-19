"""Shared fixtures. Sample media is generated at test time so the repo stays tiny."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from roue.engine import tools


def have(*names: str) -> bool:
    return all(shutil.which(n) for n in names)


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Keep tests away from the real config, history and trash."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.delenv("ROUE_DISABLE_TOOLS", raising=False)
    tools.which.cache_clear()
    yield
    tools.which.cache_clear()


@pytest.fixture(scope="session")
def samples(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Small sample files, generated with whatever tools are installed."""
    d = tmp_path_factory.mktemp("samples")
    out: dict[str, Path] = {}
    if have("ffmpeg"):
        ff = ("ffmpeg", "-v", "error", "-y")
        run(
            *ff,
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(d / "clip.mov"),
        )
        run(
            *ff,
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=160x120:rate=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(d / "silent.mp4"),
        )
        run(*ff, "-f", "lavfi", "-i", "sine=frequency=330:duration=2", str(d / "tone.wav"))
        run(
            *ff, "-f", "lavfi", "-i", "testsrc=size=400x300", "-frames:v", "1", str(d / "photo.png")
        )
        run(
            *ff, "-f", "lavfi", "-i", "testsrc=size=1600x900", "-frames:v", "1", str(d / "wide.jpg")
        )
        run(
            *ff,
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=320x240,geq=random(1)*255:128:128",
            "-frames:v",
            "1",
            str(d / "noisy.png"),
        )
        out.update(
            noisy=d / "noisy.png",
            clip=d / "clip.mov",
            silent=d / "silent.mp4",
            tone=d / "tone.wav",
            png=d / "photo.png",
            jpg=d / "wide.jpg",
        )
    if have("vips") and "png" in out:
        try:
            run("vips", "copy", str(out["png"]), str(d / "phone.heic"))
            out["heic"] = d / "phone.heic"
        except subprocess.CalledProcessError:
            pass
    (d / "notes.md").write_text("# Notes\n\nSome *Markdown* with a [link](https://example.org).\n")
    out["md"] = d / "notes.md"
    (d / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
        '<circle cx="20" cy="20" r="18" fill="#e5484d"/></svg>'
    )
    out["svg"] = d / "logo.svg"
    if have("pandoc"):
        run("pandoc", str(out["md"]), "-o", str(d / "letter.odt"))
        out["odt"] = d / "letter.odt"
    if have("gs"):
        ps = d / "doc.ps"
        pages = "".join(
            f"/Helvetica findfont 24 scalefont setfont 72 700 moveto (Page {n}) show showpage\n"
            for n in (1, 2)
        )
        ps.write_text(pages)
        run(
            "gs",
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-sDEVICE=pdfwrite",
            f"-sOutputFile={d / 'doc.pdf'}",
            str(ps),
        )
        out["pdf"] = d / "doc.pdf"
    return out


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "work"
    d.mkdir()
    return d


def copy_sample(samples: dict[str, Path], key: str, workdir: Path) -> Path:
    if key not in samples:
        pytest.skip(f"sample '{key}' needs tools that aren't installed")
    target = workdir / samples[key].name
    shutil.copy(samples[key], target)
    return target
