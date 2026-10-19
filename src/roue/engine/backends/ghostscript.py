"""PDFs with Ghostscript.

Modes (``params.mode``):

- ``compress``: rewrite with ``/ebook``-like settings (``params.quality``).
- ``images``: one PNG per page in a folder (``params.dpi``).
- ``text``: extract the text layer.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .. import tools
from ..errors import ConversionError
from ..presets import Preset
from .base import JobContext, Requirements

_QUALITY = {"screen", "ebook", "printer", "prepress", "default"}
_TOTAL_RE = re.compile(r"Processing pages \d+ through (\d+)")
_PAGE_RE = re.compile(r"^Page (\d+)")


def page_progress(report: Callable[[float | None], None]) -> Callable[[str], None]:
    total = 0

    def on_line(line: str) -> None:
        nonlocal total
        if match := _TOTAL_RE.search(line):
            total = int(match.group(1))
        elif (match := _PAGE_RE.match(line)) and total:
            report((int(match.group(1)) - 1) / total)

    return on_line


class GhostscriptBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        return [("ghostscript",)]

    def run(self, ctx: JobContext) -> None:
        exe = tools.require("ghostscript")
        mode = str(ctx.params.get("mode", "compress"))
        base = [exe, "-dNOPAUSE", "-dBATCH", "-dSAFER"]
        if mode == "compress":
            quality = str(ctx.params.get("quality", "ebook"))
            if quality not in _QUALITY:
                raise ConversionError(f"Unknown PDF quality '{quality}'.")
            cmd = [
                *base,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.5",
                f"-dPDFSETTINGS=/{quality}",
                "-dDetectDuplicateImages=true",
                f"-sOutputFile={ctx.output}",
                str(ctx.source),
            ]
        elif mode == "images":
            dpi = int(ctx.params.get("dpi", 150))
            pattern = ctx.output_folder / f"page-%03d.{ctx.preset.output_ext}"
            device = {"png": "png16m", "jpg": "jpeg"}.get(ctx.preset.output_ext, "png16m")
            cmd = [
                *base,
                f"-sDEVICE={device}",
                f"-r{dpi}",
                "-dTextAlphaBits=4",
                "-dGraphicsAlphaBits=4",
                f"-sOutputFile={pattern}",
                str(ctx.source),
            ]
        elif mode == "text":
            cmd = [*base, "-sDEVICE=txtwrite", f"-sOutputFile={ctx.output}", str(ctx.source)]
        else:
            raise ConversionError(f"Unknown ghostscript mode '{mode}'.")
        ctx.progress(None)
        ctx.run(
            cmd,
            failure="Ghostscript couldn't read this PDF. It may be damaged or password-protected.",
            on_line=page_progress(ctx.progress),
        )
        ctx.progress(1.0)
