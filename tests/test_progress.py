from __future__ import annotations

from roue.engine.backends.ffmpeg import progress_parser
from roue.engine.backends.ghostscript import page_progress


def test_ffmpeg_progress_lines() -> None:
    seen: list[float | None] = []
    on_line = progress_parser(10.0, seen.append)
    for line in (
        "frame=10",
        "out_time_us=2500000",
        "out_time_us=N/A",
        "progress=continue",
        "out_time_us=5000000",
        "progress=end",
    ):
        on_line(line)
    assert seen == [0.25, 0.5, 1.0]


def test_ffmpeg_progress_second_pass_offset() -> None:
    seen: list[float | None] = []
    on_line = progress_parser(4.0, seen.append, start=0.5, span=0.5)
    on_line("out_time_us=2000000")
    assert seen == [0.75]


def test_ghostscript_pages() -> None:
    seen: list[float | None] = []
    on_line = page_progress(seen.append)
    for line in ("GPL Ghostscript 10.02.1", "Processing pages 1 through 4.", "Page 1", "Page 3"):
        on_line(line)
    assert seen == [0.0, 0.5]
