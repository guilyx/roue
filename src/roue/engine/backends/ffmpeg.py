"""Video and audio with FFmpeg.

Modes (``params.mode``):

- ``transcode`` (default): re-encode to the preset's container and codecs.
- ``gif``: palette-optimised animated GIF.
- ``target-size``: two-pass encode that fits under ``target_size_mb``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import tools
from ..detect import MediaInfo, noun_for
from ..errors import ConversionError, NothingToDo
from ..presets import Preset
from .base import JobContext, Requirements

# Leave headroom for container overhead and rate-control drift.
_SIZE_SAFETY = 0.94
_MIN_VIDEO_KBPS = 90


def _even_scale(max_height: int | None) -> str:
    if max_height:
        return f"scale=-2:'trunc(min({int(max_height)},ih)/2)*2'"
    # H.264 in yuv420p needs even dimensions.
    return "scale='trunc(iw/2)*2':'trunc(ih/2)*2'"


def progress_parser(
    duration: float | None,
    report: Callable[[float | None], None],
    start: float = 0.0,
    span: float = 1.0,
) -> Callable[[str], None]:
    """Turn ``-progress pipe:1`` lines into fractions."""

    def on_line(line: str) -> None:
        key, _, value = line.partition("=")
        if key == "out_time_us" and duration:
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                return
            report(start + span * min(1.0, seconds / duration))
        elif key == "progress" and value == "end":
            report(start + span)

    return on_line


class FFmpegBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        return [("ffmpeg",), ("ffprobe",)]

    def run(self, ctx: JobContext) -> None:
        mode = str(ctx.params.get("mode", "transcode"))
        info = ctx.probe()
        wants_video = bool(ctx.params.get("video", True))
        wants_audio = not ctx.params.get("mute", False) and mode != "gif"
        if mode == "transcode" and not wants_video and not info.has_audio:
            raise ConversionError(
                f"This {noun_for(ctx.mime)} has no audio track to extract.",
            )
        needs_video = mode in ("gif", "target-size") or (mode == "transcode" and wants_video)
        if needs_video and not info.has_video:
            raise ConversionError(f"This {noun_for(ctx.mime)} has no video to convert.")
        if mode == "gif":
            self._gif(ctx)
        elif mode == "target-size":
            self._target_size(ctx)
        elif mode == "transcode":
            self._transcode(ctx, wants_video=wants_video, wants_audio=wants_audio)
        else:
            raise ConversionError(f"Unknown ffmpeg mode '{mode}' in preset {ctx.preset.id}.")

    # -- helpers ---------------------------------------------------------

    def _base(self, ctx: JobContext) -> list[str]:
        return [
            tools.require("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(ctx.source),
            "-sn",
            "-dn",
            "-map_metadata",
            "0",
        ]

    def _tail(self, ctx: JobContext, out: Path) -> list[str]:
        extra = [str(a) for a in ctx.params.get("extra_args", [])]
        return [*extra, "-progress", "pipe:1", "-nostats", str(out)]

    def _audio_args(self, params: Any, info: MediaInfo, wants_audio: bool) -> list[str]:
        if not wants_audio or not info.has_audio:
            return ["-an"]
        args: list[str] = []
        if params.get("normalize"):
            args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
            if not params.get("sample_rate"):
                # loudnorm works at 192 kHz internally: go back to the original rate.
                args += ["-ar", str(info.sample_rate or 48000)]
        if params.get("audio_codec"):
            args += ["-c:a", str(params["audio_codec"])]
        if params.get("audio_quality") is not None:
            args += ["-q:a", str(params["audio_quality"])]
        elif params.get("audio_bitrate"):
            args += ["-b:a", str(params["audio_bitrate"])]
        if params.get("sample_rate"):
            args += ["-ar", str(params["sample_rate"])]
        return args

    def _video_args(self, params: Any) -> list[str]:
        args: list[str] = []
        codec = params.get("video_codec", "libx264")
        args += ["-c:v", str(codec)]
        if codec == "copy":
            return args
        filters = [_even_scale(params.get("max_height"))]
        if params.get("fps"):
            filters.append(f"fps={params['fps']}")
        args += ["-vf", ",".join(filters)]
        if params.get("crf") is not None:
            args += ["-crf", str(params["crf"])]
            if str(codec).startswith("libvpx"):
                args += ["-b:v", "0"]
        if params.get("speed"):
            args += ["-preset", str(params["speed"])]
        if params.get("pix_fmt", "yuv420p"):
            args += ["-pix_fmt", str(params.get("pix_fmt", "yuv420p"))]
        return args

    # -- modes -----------------------------------------------------------

    def _transcode(self, ctx: JobContext, *, wants_video: bool, wants_audio: bool) -> None:
        info = ctx.probe()
        cmd = self._base(ctx)
        if wants_video:
            cmd += self._video_args(ctx.params)
        else:
            cmd += ["-vn"]
        cmd += self._audio_args(ctx.params, info, wants_audio)
        if ctx.output.suffix.lower() in (".mp4", ".m4a", ".mov"):
            cmd += ["-movflags", "+faststart"]
        cmd += self._tail(ctx, ctx.output)
        ctx.run(
            cmd,
            failure=f"FFmpeg couldn't convert this {noun_for(ctx.mime)}.",
            on_line=progress_parser(info.duration, ctx.progress),
        )

    def _gif(self, ctx: JobContext) -> None:
        info = ctx.probe()
        fps = int(ctx.params.get("fps", 15))
        width = int(ctx.params.get("max_width", 720))
        graph = (
            f"fps={fps},scale='min({width},iw)':-1:flags=lanczos,split[a][b];"
            "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
        )
        cmd = [*self._base(ctx), "-an", "-vf", graph, "-loop", "0", *self._tail(ctx, ctx.output)]
        ctx.run(
            cmd,
            failure="FFmpeg couldn't turn this video into a GIF.",
            on_line=progress_parser(info.duration, ctx.progress),
        )

    def _target_size(self, ctx: JobContext) -> None:
        info = ctx.probe()
        target_mb = float(ctx.params["target_size_mb"])
        target_bytes = target_mb * 1_000_000
        if ctx.source.stat().st_size <= target_bytes and ctx.source.suffix.lower() == ".mp4":
            raise NothingToDo(f"Already under {target_mb:g} MB, nothing to do.")
        if not info.duration:
            raise ConversionError("Couldn't read how long this video is, so it can't be sized.")
        audio_kbps = int(ctx.params.get("audio_kbps", 96)) if info.has_audio else 0
        max_height = int(ctx.params.get("max_height", 720))
        max_video_kbps = int(ctx.params.get("max_video_kbps", 2500 if max_height <= 720 else 5000))
        factor = _SIZE_SAFETY
        for _attempt in range(3):
            total_kbps = target_bytes * 8 * factor / info.duration / 1000
            # Short clips don't need a huge bitrate just because the budget allows it.
            video_kbps = min(int(total_kbps - audio_kbps), max_video_kbps)
            if video_kbps < _MIN_VIDEO_KBPS and audio_kbps > 48:
                audio_kbps, max_height = 48, min(max_height, 480)
                video_kbps = int(total_kbps - audio_kbps)
            if video_kbps < _MIN_VIDEO_KBPS:
                needed = (_MIN_VIDEO_KBPS + audio_kbps) * info.duration / 8 / 1000
                raise ConversionError(
                    f"This video is too long to fit in {target_mb:g} MB "
                    f"(it would need about {needed:.0f} MB to stay watchable).",
                    hint="Trim it first, or pick a bigger size preset.",
                )
            self._two_pass(ctx, video_kbps, audio_kbps, max_height)
            if ctx.output.stat().st_size <= target_bytes:
                return
            factor *= 0.85
        raise ConversionError(f"Couldn't get this video under {target_mb:g} MB.")

    def _two_pass(self, ctx: JobContext, video_kbps: int, audio_kbps: int, max_height: int) -> None:
        info = ctx.probe()
        passlog = str(ctx.workdir / "pass")
        common = [
            "-c:v",
            "libx264",
            "-b:v",
            f"{video_kbps}k",
            "-maxrate",
            f"{int(video_kbps * 1.5)}k",
            "-bufsize",
            f"{video_kbps * 2}k",
            "-vf",
            _even_scale(max_height),
            "-pix_fmt",
            "yuv420p",
            "-preset",
            str(ctx.params.get("speed", "medium")),
            "-passlogfile",
            passlog,
        ]
        first = [
            *self._base(ctx),
            *common,
            "-pass",
            "1",
            "-an",
            "-f",
            "mp4",
            "-progress",
            "pipe:1",
            "-nostats",
            "/dev/null",
        ]
        ctx.run(
            first,
            failure="FFmpeg couldn't analyse this video.",
            on_line=progress_parser(info.duration, ctx.progress, 0.0, 0.5),
            cwd=ctx.workdir,
        )
        audio = ["-c:a", "aac", "-b:a", f"{audio_kbps}k"] if audio_kbps else ["-an"]
        second = [
            *self._base(ctx),
            *common,
            "-pass",
            "2",
            *audio,
            "-movflags",
            "+faststart",
            *self._tail(ctx, ctx.output),
        ]
        ctx.run(
            second,
            failure="FFmpeg couldn't compress this video.",
            on_line=progress_parser(info.duration, ctx.progress, 0.5, 0.5),
            cwd=ctx.workdir,
        )
