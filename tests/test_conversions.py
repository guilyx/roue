"""Every built-in preset, run for real on a generated sample.

Tests skip (not fail) when the tools a preset needs aren't installed, so
`pytest` works anywhere; CI installs everything so nothing is skipped there.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from roue.engine.backends import missing_tools
from roue.engine.detect import mime_type
from roue.engine.presets import load_presets
from roue.engine.runner import JobState, Runner

from .conftest import copy_sample, have

# preset id -> (sample key, expected output name)
CASES: dict[str, tuple[str, str]] = {
    "jpg": ("png", "photo.jpg"),
    "png": ("svg", "logo.png"),
    "webp": ("png", "photo.webp"),
    "avif": ("png", "photo.avif"),
    "resize-half": ("png", "photo (50%).png"),
    "resize-1080": ("jpg", "wide (1080px).jpg"),
    "resize-double": ("svg", "logo (2x).png"),
    "compress-image": ("png", "photo (compressed).jpg"),
    "strip-metadata": ("jpg", "wide (clean).jpg"),
    "mp4": ("clip", "clip.mp4"),
    "gif": ("clip", "clip.gif"),
    "webm": ("silent", "silent.webm"),
    "share-10mb": ("clip", "clip (10MB).mp4"),
    "share-25mb": ("clip", "clip (25MB).mp4"),
    "compress-video": ("clip", "clip (small).mp4"),
    "mute": ("clip", "clip (muted).mov"),
    "mp3": ("clip", "clip.mp3"),
    "opus": ("tone", "tone.opus"),
    "wav": ("clip", "clip.wav"),
    "flac": ("tone", "tone.flac"),
    "normalize": ("tone", "tone (normalized).wav"),
    "pdf": ("md", "notes.pdf"),
    "docx": ("md", "notes.docx"),
    "html": ("md", "notes.html"),
    "compress-pdf": ("pdf", "doc (compressed).pdf"),
    "pdf-to-png": ("pdf", "doc (pages)"),
    "pdf-to-text": ("pdf", "doc.txt"),
}

REGISTRY = load_presets(include_user=False)
SLOW = {"pdf", "share-10mb", "share-25mb", "webm"}


def test_every_builtin_preset_has_a_case() -> None:
    assert sorted(CASES) == sorted(p.id for p in REGISTRY)


def ffprobe(path: Path) -> dict[str, object]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "preset_id", [pytest.param(p, marks=pytest.mark.slow) if p in SLOW else p for p in CASES]
)
def test_builtin_preset(preset_id: str, samples: dict[str, Path], workdir: Path) -> None:
    preset = REGISTRY.get(preset_id)
    sample_key, expected = CASES[preset_id]
    source = copy_sample(samples, sample_key, workdir)
    missing = missing_tools(preset, mime_type(source))
    if missing:
        pytest.skip(f"{preset_id} needs {missing}")
    [job] = Runner().run(preset, [source]).jobs
    if preset.only_if_smaller and job.state == JobState.SKIPPED:
        # Tiny synthetic samples often can't shrink: keeping the original is the design.
        assert sorted(p.name for p in workdir.iterdir()) == [source.name]
        return
    assert job.state == JobState.DONE, f"{job.message}\n{job.error and job.error.details}"
    [result] = job.outputs
    assert result == workdir / expected
    assert result.exists()
    assert source.exists(), "the original must never be touched"

    if preset.group in ("video", "audio") and have("ffprobe"):
        info = ffprobe(result)
        kinds = {s["codec_type"] for s in info["streams"]}  # type: ignore[index]
        if preset_id == "mute":
            assert kinds == {"video"}
        elif preset.group == "audio" or preset_id == "gif":
            assert kinds == ({"video"} if preset_id == "gif" else {"audio"})
        if preset_id.startswith("share-"):
            limit = preset.params["target_size_mb"] * 1_000_000
            assert result.stat().st_size <= limit
        if preset_id == "normalize":
            [stream] = info["streams"]  # type: ignore[index]
            assert stream["sample_rate"] == "44100"
    if preset_id == "resize-1080" and have("vipsheader"):
        width = subprocess.run(
            ["vipsheader", "-f", "width", str(result)], capture_output=True, text=True, check=True
        )
        assert width.stdout.strip() == "1080"
    if preset_id == "pdf-to-png":
        assert sorted(p.name for p in result.iterdir()) == ["page-001.png", "page-002.png"]
    if preset_id == "pdf-to-text":
        assert "Page 1" in result.read_text()
    if preset_id == "html":
        assert "<em>Markdown</em>" in result.read_text()


def test_compress_image_shrinks_photos(samples: dict[str, Path], workdir: Path) -> None:
    source = copy_sample(samples, "noisy", workdir)
    [job] = Runner().run(REGISTRY.get("compress-image"), [source]).jobs
    assert job.state == JobState.DONE, job.message
    assert job.output_bytes < job.input_bytes


def test_heic_to_jpg(samples: dict[str, Path], workdir: Path) -> None:
    """The classic: a phone photo that nothing opens."""
    source = copy_sample(samples, "heic", workdir)
    [job] = Runner().run(REGISTRY.get("jpg"), [source]).jobs
    if job.state == JobState.FAILED and "codec" in ((job.error and job.error.details) or ""):
        pytest.skip("libheif has no HEVC decoder plugin here")
    assert job.state == JobState.DONE, job.message
    assert job.outputs[0].suffix == ".jpg"


def test_video_without_audio_track(samples: dict[str, Path], workdir: Path) -> None:
    if not have("ffmpeg", "ffprobe"):
        pytest.skip("needs ffmpeg")
    source = copy_sample(samples, "silent", workdir)
    [job] = Runner().run(REGISTRY.get("mp3"), [source]).jobs
    assert job.state == JobState.FAILED
    assert job.message == "This video has no audio track to extract."


def test_damaged_video(workdir: Path) -> None:
    if not have("ffmpeg", "ffprobe"):
        pytest.skip("needs ffmpeg")
    broken = workdir / "broken.mp4"
    broken.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"garbage" * 100)
    [job] = Runner().run(REGISTRY.get("gif"), [broken]).jobs
    assert job.state == JobState.FAILED
    assert "damaged" in job.message or "couldn't be read" in job.message


def test_imagemagick_fallback(
    samples: dict[str, Path], workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from roue.engine import tools

    if not (have("convert") or have("magick")):
        pytest.skip("needs ImageMagick")
    monkeypatch.setenv("ROUE_DISABLE_TOOLS", "vips")
    tools.which.cache_clear()
    source = copy_sample(samples, "png", workdir)
    for preset_id in ("jpg", "resize-half", "strip-metadata"):
        [job] = Runner().run(REGISTRY.get(preset_id), [source]).jobs
        assert job.state == JobState.DONE, f"{preset_id}: {job.message}"
