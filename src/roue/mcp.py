"""``roue mcp``: Roue's engine as an MCP server, so AI agents can convert files.

It speaks the Model Context Protocol over stdin and stdout, one JSON-RPC
message per line, with the standard library only: the server ships in the same
package as the CLI and needs nothing else installed. Agents get the same
presets and the same rules as the wheel: results go next to the originals (or
to ``output_dir``), nothing is ever overwritten, and ``undo_last`` moves the
latest results to the trash.

Tool calls run on worker threads, so ``ping`` and cancellation keep working
while a long video converts.
"""

from __future__ import annotations

import io
import json
import os
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

from . import APP_NAME, WEBSITE, __version__
from .engine import tools
from .engine.backends import is_available, missing_tools
from .engine.detect import kind_of, mime_type
from .engine.errors import PresetError, RoueError
from .engine.history import History
from .engine.presets import GROUPS, Preset, PresetRegistry, load_presets
from .engine.runner import Batch, Job, JobState, Runner, expand_inputs
from .engine.settings import Settings

#: Protocol revisions this server speaks, newest first.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = (
    -32700,
    -32600,
    -32601,
    -32602,
    -32603,
)

INSTRUCTIONS = f"""\
{APP_NAME} converts files on this computer: images, video, audio and documents.
Nothing is uploaded. Call list_presets with the user's files to see which
presets fit them, then convert with a preset id. To join PDFs, images and
documents into one PDF, convert them together with merge-pdf. Results are written next to
the originals (or to output_dir) and never overwrite anything. undo_last moves
the latest results to the trash. If a preset says available: false,
check_tools shows the command that installs what's missing. Docs: {WEBSITE}"""

RequestId = str | int
Json = dict[str, Any]


class ToolInputError(Exception):
    """Arguments the tool can't use. Reported to the model so it can retry."""


# -- tools -------------------------------------------------------------------

_FILES = {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "description": "Absolute paths of files or folders.",
}
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

TOOLS: list[Json] = [
    {
        "name": "list_presets",
        "title": "List presets",
        "description": (
            "List Roue's conversion presets (JPG, WebP, MP4, GIF, 'Under 10 MB', MP3, PDF, "
            "merge into one PDF...). "
            "With files, only the presets that fit all of them, most relevant first. "
            "Pass a preset's id to convert."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {**_FILES, "description": "Only presets that take all these files."},
                "group": {"type": "string", "enum": list(GROUPS), "description": "Only one group."},
            },
            "additionalProperties": False,
        },
        "annotations": _READ_ONLY,
    },
    {
        "name": "file_info",
        "title": "Inspect files",
        "description": (
            "What Roue sees in files: type, size, length, codecs and resolution of "
            "videos and audio, and the ids of the presets that fit each file."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"files": {**_FILES, "description": "Absolute paths of files."}},
            "required": ["files"],
            "additionalProperties": False,
        },
        "annotations": _READ_ONLY,
    },
    {
        "name": "convert",
        "title": "Convert files",
        "description": (
            "Convert files with a preset, locally. Folders are converted file by file. "
            "Each result is written next to its original (photo.HEIC -> photo.jpg), or "
            "to output_dir, and never replaces an existing file: Roue picks a free name "
            "instead. Presets with combine: true (merge-pdf) put all the files into one "
            "result instead, in the order given. Returns the paths it wrote."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "preset": {"type": "string", "description": "A preset id from list_presets."},
                "files": _FILES,
                "output_dir": {
                    "type": "string",
                    "description": "Write results here instead of next to the originals.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Also convert files in sub-folders of folders.",
                },
            },
            "required": ["preset", "files"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
    {
        "name": "undo_last",
        "title": "Undo the last conversion",
        "description": (
            "Move the files the most recent conversion wrote to the trash. Originals are "
            "never touched. Call it again to go one more conversion back."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    },
    {
        "name": "check_tools",
        "title": "Check conversion tools",
        "description": (
            "Which conversion tools (FFmpeg, libvips, Ghostscript, Pandoc, LibreOffice...) "
            "are installed, how many presets are ready, and the command that installs "
            "what's missing."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": _READ_ONLY,
    },
]


def _check_arguments(arguments: Json, schema: Json) -> None:
    """Enough of JSON Schema for the inputs above: types, required, no extras."""
    properties: Json = schema.get("properties", {})
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise ToolInputError(
            f"Unknown argument {unknown[0]!r}. Arguments: {', '.join(properties) or 'none'}."
        )
    for key in schema.get("required", []):
        if key not in arguments:
            raise ToolInputError(f"Missing argument {key!r}.")
    for key, value in arguments.items():
        spec = properties[key]
        kind = spec["type"]
        if kind == "string" and not isinstance(value, str):
            raise ToolInputError(f"{key!r} must be a string.")
        if kind == "boolean" and not isinstance(value, bool):
            raise ToolInputError(f"{key!r} must be true or false.")
        if kind == "array":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ToolInputError(f"{key!r} must be a list of paths.")
            if not value:
                raise ToolInputError(f"{key!r} needs at least one path.")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolInputError(f"{key!r} must be one of: {', '.join(spec['enum'])}.")


def _paths(names: list[str]) -> list[Path]:
    return [Path(name).expanduser().absolute() for name in names]


def _registry() -> PresetRegistry:
    registry = load_presets()
    for problem in registry.problems:
        print(f"roue: {problem}", file=sys.stderr)
    return registry


def _needs(preset: Preset) -> list[str]:
    """What a preset is missing, like ['libvips or ImageMagick']."""
    return [" or ".join(tools.label(t) for t in group) for group in missing_tools(preset)]


def _preset_json(preset: Preset) -> Json:
    data: Json = {
        "id": preset.id,
        "name": preset.name,
        "group": preset.group,
        "description": preset.description,
        "output_ext": preset.output_ext,
        "available": is_available(preset),
    }
    if preset.combine:
        data["combine"] = True  # all the files go into one result
    if not data["available"]:
        data["needs"] = _needs(preset)
    return data


def list_presets(arguments: Json, context: Call) -> Json:
    registry = _registry()
    if "files" in arguments:
        presets = registry.matching_files(expand_inputs(_paths(arguments["files"])))
    else:
        presets = registry.ordered()
    if "group" in arguments:
        presets = [p for p in presets if p.group == arguments["group"]]
    return {"presets": [_preset_json(p) for p in presets]}


def file_info(arguments: Json, context: Call) -> Json:
    registry = _registry()
    files = []
    for path in _paths(arguments["files"]):
        mime = mime_type(path)
        info: Json = {"path": str(path), "exists": path.exists(), "type": mime}
        info["kind"] = kind_of(mime)
        if path.is_file():
            info["size_bytes"] = path.stat().st_size
            if info["kind"] in ("video", "audio") and tools.which("ffprobe"):
                info.update(_media(path))
        info["presets"] = [p.id for p in registry.matching([mime])] if path.is_file() else []
        files.append(info)
    return {"files": files}


def _media(path: Path) -> Json:
    from .engine.detect import probe

    try:
        media = probe(path)
    except RoueError as exc:
        return {"media_error": exc.message}
    data: Json = {"duration_seconds": media.duration, "audio_codec": media.audio_codec}
    if media.has_video:
        data["video"] = {"codec": media.video_codec, "width": media.width, "height": media.height}
    return data


def _job_json(job: Job) -> Json:
    data: Json = {
        "source": str(job.source),
        "state": job.state.value,
        "outputs": [str(p) for p in job.outputs],
        "message": job.message,
        "input_bytes": job.input_bytes,
        "output_bytes": job.output_bytes,
    }
    if job.preset.combine:
        data["inputs"] = [str(p) for p in job.inputs]
    if job.error and job.error.hint:
        data["hint"] = job.error.hint
    return data


def convert(arguments: Json, context: Call) -> Json:
    settings = Settings.load()
    try:
        preset = _registry().get(arguments["preset"])
    except PresetError as exc:
        close = exc.hint if exc.hint and exc.hint.startswith("Did you mean") else ""
        raise ToolInputError(f"{exc.message} {close or 'Call list_presets for the ids.'}") from None
    out_dir = settings.output_path
    if "output_dir" in arguments:
        out_dir = Path(arguments["output_dir"]).expanduser().absolute()
    progress = _Progress(context)
    runner = Runner(max_workers=settings.max_jobs or None, on_update=progress.update)
    try:
        batch = runner.submit(
            preset,
            _paths(arguments["files"]),
            recursive=arguments.get("recursive", settings.recursive_folders),
            out_dir=out_dir,
        )
        progress.total = len(batch.jobs)
        context.watch(batch)
        batch.wait()
    finally:
        runner.shutdown(cancel=context.cancelled)
    History().record(batch)
    if not batch.jobs:
        raise ToolInputError(
            "No files to convert: the folders are empty or hold only hidden files."
        )
    context.error = batch.count(JobState.FAILED) > 0
    return {
        "preset": preset.id,
        "summary": batch.summary(),
        "jobs": [_job_json(job) for job in batch.jobs],
    }


def undo_last(arguments: Json, context: Call) -> Json:
    result = History().undo_last()
    if result is None:
        return {"undone": False, "message": "Nothing to undo."}
    entry, trashed = result
    return {"undone": True, "preset": entry.preset_name, "trashed": [str(p) for p in trashed]}


def check_tools(arguments: Json, context: Call) -> Json:
    found = []
    missing = []
    for tool in tools.TOOLS.values():
        path = tools.which(tool.id)
        found.append(
            {
                "id": tool.id,
                "label": tool.label,
                "installed": bool(path),
                "path": path,
                "purpose": tool.purpose,
            }
        )
        if not path:
            missing.append(tool.id)
    registry = _registry()
    return {
        "tools": found,
        "presets_ready": sum(1 for p in registry if is_available(p)),
        "presets_total": len(registry),
        "install_command": tools.install_command(missing) if missing else None,
    }


HANDLERS: dict[str, Callable[[Json, Call], Json]] = {
    "list_presets": list_presets,
    "file_info": file_info,
    "convert": convert,
    "undo_last": undo_last,
    "check_tools": check_tools,
}
SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in TOOLS}


# -- the server --------------------------------------------------------------


class Call:
    """One tools/call in flight: its progress token, and a way to cancel it."""

    def __init__(self, server: Server, request_id: RequestId, progress_token: Any = None):
        self.server, self.request_id, self.progress_token = server, request_id, progress_token
        self.cancelled = False
        self.error = False
        self._batch: Batch | None = None
        self._lock = threading.Lock()

    def watch(self, batch: Batch) -> None:
        with self._lock:
            self._batch = batch
            if self.cancelled:
                batch.cancel()

    def cancel(self) -> None:
        with self._lock:
            self.cancelled = True
            if self._batch:
                self._batch.cancel()


class _Progress:
    """Sends notifications/progress for a conversion, if the client asked for them."""

    def __init__(self, call: Call):
        self.call = call
        self.total: int | None = None
        self.finished = 0
        self.running: dict[int, float] = {}
        self.sent = 0.0
        self.last = 0.0
        self.lock = threading.Lock()

    def update(self, job: Job) -> None:
        if self.call.progress_token is None:
            return
        with self.lock:
            if job.state.finished:
                self.finished += 1
                self.running.pop(job.id, None)
            elif job.state == JobState.RUNNING and job.progress is not None:
                self.running[job.id] = min(job.progress, 0.99)  # 1 is for when it's done
            else:
                return
            value = round(self.finished + sum(self.running.values()), 3)
            now = time.monotonic()
            # Progress must only grow; in-between updates at most twice a second.
            if value <= self.sent or (not job.state.finished and now - self.last < 0.5):
                return
            self.sent, self.last = value, now
            params: Json = {
                "progressToken": self.call.progress_token,
                "progress": value,
                "message": f"{job.label}: {job.state.value}",
            }
            if self.total is not None:
                params["total"] = self.total
            self.call.server.notify("notifications/progress", params)


class Server:
    """Reads requests line by line and writes responses to ``out``."""

    def __init__(self, out: TextIO, *, workers: int = 4):
        self.out = out
        self._write_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="roue-mcp")
        self._calls: dict[RequestId, Call] = {}
        self._calls_lock = threading.Lock()

    # writing

    def _send(self, message: Json) -> None:
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            self.out.write(line + "\n")
            self.out.flush()

    def notify(self, method: str, params: Json) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _result(self, request_id: RequestId, result: Json) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id: RequestId | None, code: int, message: str) -> None:
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        )

    # reading

    def serve(self, lines: Iterable[str]) -> None:
        """Handle messages until the input ends, then finish the calls in flight."""
        for line in lines:
            if line.strip():
                self.handle(line)
        self.close()

    def close(self, *, cancel: bool = False) -> None:
        if cancel:
            with self._calls_lock:
                calls = list(self._calls.values())
            for call in calls:
                call.cancel()
        self._pool.shutdown(wait=True)

    def handle(self, line: str) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            self._error(None, PARSE_ERROR, "Parse error: not JSON.")
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            request_id = message.get("id") if isinstance(message, dict) else None
            self._error(request_id, INVALID_REQUEST, "Expected one JSON-RPC 2.0 message.")
            return
        method = message.get("method")
        if not isinstance(method, str):
            if "result" not in message and "error" not in message:
                self._error(message.get("id"), INVALID_REQUEST, "A request needs a method.")
            return  # otherwise a response, to a request this server never sends
        params = message.get("params") or {}
        if "id" not in message:
            self._notification(method, params)
            return
        request_id = message["id"]
        if not isinstance(params, dict):
            self._error(request_id, INVALID_PARAMS, "params must be an object.")
        elif method == "initialize":
            self._result(request_id, self._initialize(params))
        elif method == "ping":
            self._result(request_id, {})
        elif method == "tools/list":
            self._result(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            self._start_call(request_id, params)
        else:
            self._error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    def _notification(self, method: str, params: Any) -> None:
        if method != "notifications/cancelled" or not isinstance(params, dict):
            return
        request_id = params.get("requestId")
        if isinstance(request_id, (str, int)):
            with self._calls_lock:
                call = self._calls.get(request_id)
            if call:
                call.cancel()

    def _initialize(self, params: Json) -> Json:
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "roue", "title": APP_NAME, "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def _start_call(self, request_id: RequestId, params: Json) -> None:
        name = params.get("name")
        if name not in HANDLERS:
            self._error(request_id, INVALID_PARAMS, f"Unknown tool: {name}")
            return
        arguments = params.get("arguments") or {}
        meta = params.get("_meta") or {}
        call = Call(self, request_id, meta.get("progressToken") if isinstance(meta, dict) else None)
        with self._calls_lock:
            self._calls[request_id] = call
        self._pool.submit(self._run_call, call, name, arguments)

    def _run_call(self, call: Call, name: str, arguments: Any) -> None:
        try:
            if not isinstance(arguments, dict):
                raise ToolInputError("arguments must be an object.")
            _check_arguments(arguments, SCHEMAS[name])
            tools.which.cache_clear()  # the user may have installed a tool meanwhile
            data = HANDLERS[name](arguments, call)
            result: Json = {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                "structuredContent": data,
                "isError": call.error,
            }
        except (ToolInputError, RoueError) as exc:
            result = _tool_error(exc)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            result = _tool_error(RuntimeError(f"{name} failed unexpectedly; see the server log."))
        finally:
            with self._calls_lock:
                self._calls.pop(call.request_id, None)
        # A cancelled request gets no response (the client has moved on).
        if not call.cancelled:
            self._result(call.request_id, result)


def _tool_error(exc: Exception) -> Json:
    text = exc.message if isinstance(exc, RoueError) else str(exc)
    if isinstance(exc, RoueError) and exc.hint:
        text += f" {exc.hint}"
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _stop(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main() -> int:
    """Serve on stdin/stdout until the client closes stdin."""
    # stdout carries the protocol only. Point file descriptor 1 at stderr so
    # stray prints, and the conversion tools Roue runs, can't corrupt it.
    out = io.TextIOWrapper(
        os.fdopen(os.dup(sys.stdout.fileno()), "wb"), encoding="utf-8", newline="\n"
    )
    sys.stdout.flush()
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    lines = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    signal.signal(signal.SIGTERM, _stop)
    server = Server(out)
    try:
        server.serve(iter(lines.readline, ""))
    except KeyboardInterrupt:  # SIGTERM or Ctrl+C: stop the conversions too
        server.close(cancel=True)
    return 0
