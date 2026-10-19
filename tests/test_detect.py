from __future__ import annotations

from pathlib import Path

import pytest

from roue.engine.detect import kind_of, mime_matches, mime_type, parse_probe


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("IMG_0001.HEIC", "image/heic"),
        ("a.webp", "image/webp"),
        ("clip.MOV", "video/quicktime"),
        ("x.mkv", "video/x-matroska"),
        ("voice.m4a", "audio/mp4"),
        ("notes.md", "text/markdown"),
        ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("deck.odp", "application/vnd.oasis.opendocument.presentation"),
    ],
)
def test_mime_from_extension(name: str, mime: str) -> None:
    assert mime_type(Path(name)) == mime


def test_unknown_extension_sniffs_content(tmp_path: Path) -> None:
    path = tmp_path / "mystery"
    path.write_text("just some text\n")
    assert mime_type(path).startswith("text/") or mime_type(path) == "application/octet-stream"


def test_patterns_and_kinds() -> None:
    assert mime_matches("image/png", ["image/*"])
    assert not mime_matches("image/png", ["video/*", "image/jpeg"])
    assert kind_of("video/webm") == "video"
    assert kind_of("application/vnd.oasis.opendocument.text") == "document"
    assert kind_of("application/zip") == "other"


def test_probe_ignores_cover_art_and_finds_duration() -> None:
    info = parse_probe(
        {
            "format": {"duration": "N/A"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "duration": "12.5",
                    "sample_rate": "44100",
                },
                {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
            ],
        }
    )
    assert info.has_audio and not info.has_video
    assert info.duration == 12.5
    assert info.sample_rate == 44100


def test_probe_handles_empty_output() -> None:
    info = parse_probe({})
    assert info.duration is None and not info.has_audio and not info.has_video
