"""Run conversions: a parallel job queue shared by the panel, the CLI and
the file-manager menu.

Callbacks (``on_update``, ``on_batch_done``) are called from worker
threads. GUI code must hop back to its main loop before touching widgets.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .backends import backend_for, missing_tools
from .backends.base import JobContext
from .detect import mime_type, noun_for
from .errors import Cancelled, ConversionError, MissingToolError, NothingToDo, RoueError
from .output import commit_file, commit_folder, destination_dir, scratch_dir
from .presets import Preset
from .tools import install_hint, label

log = logging.getLogger(__name__)


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self not in (JobState.QUEUED, JobState.RUNNING)


_ids = itertools.count(1)


@dataclass(eq=False)
class Job:
    """One file going through one preset."""

    source: Path
    preset: Preset
    id: int = field(default_factory=lambda: next(_ids))
    state: JobState = JobState.QUEUED
    progress: float | None = 0.0
    outputs: list[Path] = field(default_factory=list)
    message: str = ""
    error: RoueError | None = None
    input_bytes: int = 0
    output_bytes: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    _ctx: JobContext | None = field(default=None, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self._cancel.set()
        if self._ctx:
            self._ctx.cancel()

    @property
    def mime(self) -> str:
        return mime_type(self.source)

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass(eq=False)
class Batch:
    """The jobs started by one drop (or one CLI call)."""

    preset: Preset
    jobs: list[Job]
    created_at: float = field(default_factory=time.time)
    _done: threading.Event = field(default_factory=threading.Event, repr=False)
    _remaining: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _futures: list[Future[None]] = field(default_factory=list, repr=False)

    def wait(self, timeout: float | None = None) -> Batch:
        self._done.wait(timeout)
        return self

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def cancel(self) -> None:
        for job in self.jobs:
            job.cancel()

    def count(self, state: JobState) -> int:
        return sum(1 for job in self.jobs if job.state == state)

    @property
    def outputs(self) -> list[Path]:
        return [path for job in self.jobs for path in job.outputs]

    @property
    def bytes_saved(self) -> int:
        done = [j for j in self.jobs if j.state == JobState.DONE]
        return sum(j.input_bytes for j in done) - sum(j.output_bytes for j in done)

    def summary(self) -> str:
        """One line for notifications: '12 files converted · 212 MB saved'."""
        done, failed = self.count(JobState.DONE), self.count(JobState.FAILED)
        skipped = self.count(JobState.SKIPPED)
        cancelled = self.count(JobState.CANCELLED)
        parts = []
        if done:
            parts.append(f"{done} file{'s' if done != 1 else ''} converted")
            if self.bytes_saved > 0 and done > 1:
                parts.append(f"{human_size(self.bytes_saved)} saved")
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} skipped")
        if cancelled:
            parts.append(f"{cancelled} cancelled")
        return " · ".join(parts) or "Nothing to convert"

    def _job_finished(self) -> bool:
        with self._lock:
            self._remaining -= 1
            last = self._remaining == 0
        if last:
            self._done.set()
        return last


def human_size(num: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if abs(num) < 1000 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "bytes" else f"{num:.1f} {unit}"
        num /= 1000
    return f"{num:.1f} TB"


def expand_inputs(paths: Iterable[Path], *, recursive: bool = False) -> list[Path]:
    """Replace folders by the (non-hidden) files they contain."""
    result: list[Path] = []
    for path in map(Path.absolute, paths):
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            result.extend(
                sorted(
                    p
                    for p in path.glob(pattern)
                    if p.is_file()
                    and not any(part.startswith(".") for part in p.relative_to(path).parts)
                )
            )
        else:
            result.append(path)
    return result


def default_workers() -> int:
    return max(1, os.cpu_count() or 1)


class Runner:
    """Runs batches of jobs on a thread pool."""

    def __init__(
        self,
        *,
        max_workers: int | None = None,
        on_update: Callable[[Job], None] | None = None,
        on_batch_done: Callable[[Batch], None] | None = None,
    ):
        workers = max_workers or default_workers()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="roue-job")
        # Video encoders already use every core: run fewer of them at once.
        self._video_slots = threading.BoundedSemaphore(max(1, workers // 4))
        self.on_update = on_update
        self.on_batch_done = on_batch_done
        self._active: set[Batch] = set()
        self._lock = threading.Lock()

    def submit(
        self,
        preset: Preset,
        paths: Iterable[Path],
        *,
        recursive: bool = False,
        out_dir: Path | None = None,
    ) -> Batch:
        files = expand_inputs(paths, recursive=recursive)
        batch = Batch(preset=preset, jobs=[Job(source=p, preset=preset) for p in files])
        batch._remaining = len(batch.jobs)
        if not batch.jobs:
            batch._done.set()
            self._batch_done(batch)
            return batch
        with self._lock:
            self._active.add(batch)
        for job in batch.jobs:
            batch._futures.append(self._pool.submit(self._execute, batch, job, out_dir))
        return batch

    def run(self, preset: Preset, paths: Iterable[Path], **kwargs: object) -> Batch:
        """Submit and wait. Convenience for scripts and tests."""
        return self.submit(preset, paths, **kwargs).wait()  # type: ignore[arg-type]

    def cancel_all(self) -> None:
        with self._lock:
            batches = list(self._active)
        for batch in batches:
            batch.cancel()

    def shutdown(self, *, cancel: bool = False) -> None:
        if cancel:
            self.cancel_all()
        self._pool.shutdown(wait=True, cancel_futures=cancel)

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._active)

    # -- internals -------------------------------------------------------

    def _notify(self, job: Job) -> None:
        if self.on_update:
            try:
                self.on_update(job)
            except Exception:
                log.exception("on_update callback failed")

    def _batch_done(self, batch: Batch) -> None:
        with self._lock:
            self._active.discard(batch)
        if self.on_batch_done:
            try:
                self.on_batch_done(batch)
            except Exception:
                log.exception("on_batch_done callback failed")

    def _execute(self, batch: Batch, job: Job, out_dir: Path | None) -> None:
        job.started_at = time.time()
        if job._cancel.is_set():
            self._finish(batch, job, JobState.CANCELLED, "Cancelled.")
            return
        job.state = JobState.RUNNING
        job.progress = None
        self._notify(job)
        try:
            if job.preset.backend == "ffmpeg":
                with self._video_slots:
                    self._convert(job, out_dir)
            else:
                self._convert(job, out_dir)
        except Cancelled:
            self._finish(batch, job, JobState.CANCELLED, "Cancelled.")
        except NothingToDo as exc:
            self._finish(batch, job, JobState.SKIPPED, exc.message)
        except RoueError as exc:
            job.error = exc
            self._finish(batch, job, JobState.FAILED, exc.message)
        except Exception as exc:
            log.exception("Unexpected error converting %s", job.source)
            job.error = RoueError(
                "Something unexpected went wrong. This is a bug, please report it.",
                details="".join(traceback.format_exception(exc)),
            )
            self._finish(batch, job, JobState.FAILED, job.error.message)
        else:
            self._finish(batch, job, JobState.DONE, "")

    def _finish(self, batch: Batch, job: Job, state: JobState, message: str) -> None:
        job.state = state
        job.message = message or job.message
        job.finished_at = time.time()
        if state == JobState.DONE:
            job.progress = 1.0
        job._ctx = None
        self._notify(job)
        if batch._job_finished():
            self._batch_done(batch)

    def _convert(self, job: Job, out_dir: Path | None) -> None:
        source, preset = job.source, job.preset
        if not source.exists():
            raise RoueError("This file doesn't exist anymore.")
        if not source.is_file():
            raise RoueError("This isn't a regular file.")
        mime = job.mime
        if not preset.accepts_mime(mime):
            raise NothingToDo(f"'{preset.name}' doesn't work on this {noun_for(mime)}.")
        missing = missing_tools(preset, mime)
        if missing:
            group = missing[0]
            raise MissingToolError(tuple(label(t) for t in group), hint=install_hint(group))
        job.input_bytes = source.stat().st_size
        destination, fell_back = destination_dir(source, out_dir)
        ext = preset.output_extension(source)
        with scratch_dir(destination) as work:
            ctx = JobContext(
                source=source,
                preset=preset,
                mime=mime,
                workdir=work,
                output=work / f"result.{ext}",
                cancel_event=job._cancel,
                on_progress=lambda fraction: self._progress(job, fraction),
            )
            job._ctx = ctx
            backend_for(preset).run(ctx)
            ctx.check_cancelled()
            stem = source.stem + preset.suffix
            if preset.output == "folder":
                produced = work / "out"
                if not produced.is_dir() or not any(produced.iterdir()):
                    raise ConversionError("The conversion finished but produced nothing.")
                job.output_bytes = sum(p.stat().st_size for p in produced.iterdir())
                job.outputs = [commit_folder(produced, destination, stem)]
            else:
                if not ctx.output.is_file() or ctx.output.stat().st_size == 0:
                    raise ConversionError("The conversion finished but produced an empty file.")
                size = ctx.output.stat().st_size
                if preset.only_if_smaller and size >= job.input_bytes:
                    raise NothingToDo("Already as small as it gets: the original was kept.")
                job.output_bytes = size
                job.outputs = [commit_file(ctx.output, destination, stem, ext)]
        if fell_back:
            job.message = f"Saved to {destination} because the original folder is read-only."

    def _progress(self, job: Job, fraction: float | None) -> None:
        job.progress = fraction
        self._notify(job)
