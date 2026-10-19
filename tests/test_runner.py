"""Runner behaviour, using tiny shell-command presets so no media tools are needed."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from roue.engine.presets import Preset, parse_preset
from roue.engine.runner import Job, JobState, Runner, expand_inputs, human_size


def command_preset(command: str, **extra: Any) -> Preset:
    data = {
        "id": "test",
        "name": "Test",
        "backend": "command",
        "accepts": ["text/*"],
        "output_ext": "txt",
        "params": {"command": ["sh", "-c", command, "sh", "{in}", "{out}"]},
    }
    data.update(extra)
    return parse_preset(data)


UPPER = command_preset('tr a-z A-Z < "$1" > "$2"', suffix=" (upper)")


def write(path: Path, text: str = "hello") -> Path:
    path.write_text(text)
    return path


def test_converts_next_to_the_original(workdir: Path) -> None:
    src = write(workdir / "note.txt")
    batch = Runner().run(UPPER, [src])
    [job] = batch.jobs
    assert job.state == JobState.DONE, job.message
    assert job.outputs == [workdir / "note (upper).txt"]
    assert job.outputs[0].read_text() == "HELLO"
    assert job.progress == 1.0
    # No scratch folders left behind.
    assert not [p for p in workdir.iterdir() if p.name.startswith(".roue-")]


def test_failure_has_a_plain_message_and_keeps_details(workdir: Path) -> None:
    preset = command_preset('echo "boom: disk on fire" >&2; exit 3')
    [job] = Runner().run(preset, [write(workdir / "a.txt")]).jobs
    assert job.state == JobState.FAILED
    assert job.message == "The command for 'Test' failed."
    assert job.error and "disk on fire" in (job.error.details or "")


def test_known_tool_errors_are_translated(workdir: Path) -> None:
    preset = command_preset('echo "write error: No space left on device" >&2; exit 1')
    [job] = Runner().run(preset, [write(workdir / "a.txt")]).jobs
    assert job.message == "The disk is full."


def test_wrong_kind_of_file_is_skipped(workdir: Path) -> None:
    [job] = Runner().run(UPPER, [write(workdir / "pic.png")]).jobs
    assert job.state == JobState.SKIPPED
    assert "doesn't work on this image" in job.message


def test_missing_tool(workdir: Path) -> None:
    preset = parse_preset(
        {
            "id": "nope",
            "name": "Nope",
            "backend": "command",
            "accepts": "text/*",
            "output_ext": "txt",
            "params": {"command": "definitely-not-installed-tool {in} {out}"},
        }
    )
    [job] = Runner().run(preset, [write(workdir / "a.txt")]).jobs
    assert job.state == JobState.FAILED
    assert "isn't installed" in job.message


def test_missing_file(workdir: Path) -> None:
    [job] = Runner().run(UPPER, [workdir / "gone.txt"]).jobs
    assert job.state == JobState.FAILED and "doesn't exist" in job.message


def test_empty_output_is_an_error(workdir: Path) -> None:
    preset = command_preset(': > "$2"')
    [job] = Runner().run(preset, [write(workdir / "a.txt")]).jobs
    assert job.state == JobState.FAILED and "empty" in job.message


def test_only_if_smaller_keeps_the_original(workdir: Path) -> None:
    preset = command_preset('cat "$1" "$1" > "$2"', only_if_smaller=True, suffix=" (small)")
    [job] = Runner().run(preset, [write(workdir / "a.txt")]).jobs
    assert job.state == JobState.SKIPPED
    assert sorted(p.name for p in workdir.iterdir()) == ["a.txt"]


def test_folder_output(workdir: Path) -> None:
    preset = parse_preset(
        {
            "id": "split",
            "name": "Split",
            "backend": "command",
            "accepts": "text/*",
            "output_ext": "txt",
            "output": "folder",
            "suffix": " (lines)",
            "params": {"command": ["split", "-l", "1", "{in}", "{outdir}/line-"]},
        }
    )
    [job] = Runner().run(preset, [write(workdir / "a.txt", "1\n2\n3\n")]).jobs
    assert job.state == JobState.DONE, job.message
    [folder] = job.outputs
    assert folder.name == "a (lines)" and len(list(folder.iterdir())) == 3


def test_cancel_stops_the_tool(workdir: Path) -> None:
    preset = command_preset("sleep 30")
    runner = Runner()
    batch = runner.submit(preset, [write(workdir / "a.txt")])
    deadline = time.time() + 5
    while batch.jobs[0].state != JobState.RUNNING and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.2)
    started = time.time()
    batch.cancel()
    batch.wait(10)
    assert batch.jobs[0].state == JobState.CANCELLED
    assert time.time() - started < 5
    assert sorted(p.name for p in workdir.iterdir()) == ["a.txt"]


def test_parallel_batch_summary_and_callbacks(workdir: Path) -> None:
    files = [write(workdir / f"f{i}.txt", "abc" * 100) for i in range(6)]
    seen: list[JobState] = []
    lock = threading.Lock()
    done: list[int] = []

    def on_update(job: Job) -> None:
        with lock:
            seen.append(job.state)

    preset = command_preset('head -c 10 "$1" > "$2"', suffix=" (short)")
    runner = Runner(
        max_workers=3, on_update=on_update, on_batch_done=lambda b: done.append(len(b.jobs))
    )
    batch = runner.run(preset, files)
    assert batch.count(JobState.DONE) == 6
    assert batch.summary() == f"6 files converted · {human_size(6 * 300 - 6 * 10)} saved"
    assert JobState.RUNNING in seen and seen.count(JobState.DONE) == 6
    assert done == [6]


def test_mixed_drop_converts_what_fits(workdir: Path) -> None:
    files = [write(workdir / "a.txt"), write(workdir / "b.png")]
    batch = Runner().run(UPPER, files)
    assert [j.state for j in batch.jobs] == [JobState.DONE, JobState.SKIPPED]
    assert batch.summary() == "1 file converted · 1 skipped"


def test_expand_inputs(workdir: Path) -> None:
    sub = workdir / "sub"
    sub.mkdir()
    write(workdir / "a.txt")
    write(workdir / ".hidden.txt")
    write(sub / "b.txt")
    flat = expand_inputs([workdir])
    deep = expand_inputs([workdir], recursive=True)
    assert [p.name for p in flat] == ["a.txt"]
    assert sorted(p.name for p in deep) == ["a.txt", "b.txt"]


def test_output_dir_option(workdir: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    [job] = Runner().run(UPPER, [write(workdir / "a.txt")], out_dir=out).jobs
    assert job.outputs == [out / "a (upper).txt"]


@pytest.mark.parametrize(
    ("size", "text"), [(512, "512 bytes"), (1_500, "1.5 KB"), (212_000_000, "212.0 MB")]
)
def test_human_size(size: int, text: str) -> None:
    assert human_size(size) == text
