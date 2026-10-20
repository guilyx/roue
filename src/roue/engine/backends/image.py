"""Images with libvips, falling back to ImageMagick.

Params:

- ``quality`` (1-100): lossy quality for JPG, WebP, AVIF, HEIC.
- ``width``: shrink to this width (never enlarges).
- ``scale``: resize factor, like 0.5 or 2.
- ``strip``: drop metadata (EXIF, GPS, camera details).
- ``tool``: force ``vips`` or ``imagemagick``.
"""

from __future__ import annotations

from pathlib import Path

from .. import tools
from ..presets import Preset
from .base import JobContext, Requirements

_LOSSY = {"jpg", "jpeg", "webp", "avif", "heic", "heif", "jxl"}
_NO_ALPHA = {"jpg", "jpeg"}


def _safe_input(ctx: JobContext) -> Path:
    """Both tools read ``[...]`` in file names as options, so use a plain link."""
    link = ctx.workdir / f"input{ctx.source.suffix.lower()}"
    if not link.exists():
        link.symlink_to(ctx.source.resolve())
    return link


class ImageBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        forced = preset.params.get("tool")
        if forced:
            return [(str(forced),)]
        return [("vips", "imagemagick")]

    def run(self, ctx: JobContext) -> None:
        forced = ctx.params.get("tool")
        tool = str(forced) if forced else ("vips" if tools.which("vips") else "imagemagick")
        ctx.progress(None)
        if tool == "vips":
            self._vips(ctx)
        else:
            self._magick(ctx)
        ctx.progress(1.0)

    def _save_options(self, ctx: JobContext, *, vips: bool) -> list[str]:
        ext = ctx.output.suffix.lstrip(".").lower()
        opts: list[str] = []
        quality = ctx.params.get("quality")
        if quality is not None and ext in _LOSSY:
            opts.append(f"Q={int(quality)}" if vips else str(int(quality)))
        return opts

    def _vips(self, ctx: JobContext) -> None:
        exe = tools.require("vips")
        src = _safe_input(ctx)
        params = ctx.params
        ext = ctx.output.suffix.lstrip(".").lower()
        opts = self._save_options(ctx, vips=True)
        if params.get("strip"):
            opts.append("strip")
        if ext in _NO_ALPHA:
            opts.append("background=255")  # transparent areas become white, not black
        out = f"{ctx.output}[{','.join(opts)}]" if opts else str(ctx.output)
        failure = "libvips couldn't convert this image."
        width = params.get("width")
        scale = params.get("scale")
        if width:
            cmd = [exe, "thumbnail", str(src), out, str(int(width))]
            cmd += ["--height", "10000000", "--size", "down"]
            ctx.run(cmd, failure=failure)
            return
        if params.get("strip"):
            # Metadata carries the orientation: apply it before dropping it.
            stage = ctx.workdir / "upright.v"
            ctx.run([exe, "autorot", str(src), str(stage)], failure=failure)
            src = stage
        if scale and float(scale) != 1.0:
            if ctx.source.suffix.lower() in (".svg", ".svgz") and float(scale) > 1:
                # Render vectors at the target size instead of upscaling pixels.
                cmd = [exe, "copy", f"{src}[scale={float(scale)}]", out]
            else:
                cmd = [exe, "resize", str(src), out, str(float(scale))]
        else:
            cmd = [exe, "copy", str(src), out]
        ctx.run(cmd, failure=failure)

    def _magick(self, ctx: JobContext) -> None:
        exe = tools.require("imagemagick")
        src = _safe_input(ctx)
        params = ctx.params
        ext = ctx.output.suffix.lstrip(".").lower()
        cmd = [exe, f"{src}[0]", "-auto-orient"]
        if params.get("width"):
            cmd += ["-resize", f"{int(params['width'])}x>"]
        elif params.get("scale") and float(params["scale"]) != 1.0:
            cmd += ["-resize", f"{float(params['scale']) * 100:g}%"]
        if params.get("strip"):
            cmd += ["-strip"]
        if ext in _NO_ALPHA:
            cmd += ["-background", "white", "-flatten"]
        quality = self._save_options(ctx, vips=False)
        if quality:
            cmd += ["-quality", quality[0]]
        cmd.append(f"{ext}:{ctx.output}")
        ctx.run(cmd, failure="ImageMagick couldn't convert this image.")
