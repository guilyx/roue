"""Several files into one PDF: PDFs, images and documents, in the order given.

Each file becomes PDF pages first:

- PDFs are used as they are.
- Images become pages through :mod:`..pdfimages`. JPEGs go in untouched;
  other images are decoded with libvips (or ImageMagick) and stored
  losslessly, except photo formats like HEIC and AVIF, which become JPEGs
  at quality 90 so the PDF stays a sensible size.
- Documents (Word, LibreOffice, Markdown...) go through the document backend.

Then qpdf, pdfunite or Ghostscript joins the pieces, in that order of
preference: the first two copy pages as they are, Ghostscript rewrites them.
Images alone need none of them: Roue writes that PDF itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import tools
from ..detect import mime_type
from ..errors import ConversionError
from ..pdfimages import PageImage, PdfWriter, jpeg_page, pnm_page
from ..presets import Preset
from .base import JobContext, Requirements
from .document import DocumentBackend

#: Tools that join PDFs, best first.
PDF_JOINERS = ("qpdf", "pdfunite", "ghostscript")
#: Images stored as JPEG in the PDF: lossless pages would make it huge.
PHOTO_FORMATS = ("image/jpeg", "image/heic", "image/heif", "image/avif", "image/webp", "image/jxl")
_FAILURE = "Couldn't merge these PDFs. One of them may be damaged or password-protected."
_DECODE_FAILURE = "Couldn't read {name} as an image."


class MergeBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        if mime is None or mime == "application/pdf":
            return [PDF_JOINERS]
        if mime == "image/jpeg":
            return []
        if mime.startswith("image/"):
            return [("vips", "imagemagick")]
        return [*DocumentBackend().requirements(preset, mime), PDF_JOINERS]

    def run(self, ctx: JobContext) -> None:
        inputs = ctx.inputs or [ctx.source]
        steps = len(inputs) + 1
        pieces: list[Path] = []
        writer: PdfWriter | None = None  # images in a row share one PDF
        try:
            for index, path in enumerate(inputs):
                ctx.check_cancelled()
                ctx.progress(index / steps)
                mime = mime_type(path)
                if mime.startswith("image/"):
                    if writer is None:
                        pieces.append(ctx.workdir / f"part-{len(pieces):03d}.pdf")
                        writer = PdfWriter(pieces[-1])
                    writer.add(self._page(ctx, path, mime, index))
                    continue
                if writer is not None:
                    writer.close()
                    writer = None
                if mime == "application/pdf":
                    pieces.append(path)
                else:
                    pieces.append(self._document(ctx, path, mime, index))
            if writer is not None:
                writer.close()
                writer = None
        finally:
            if writer is not None:
                writer.abort()
        ctx.progress(len(inputs) / steps)
        self._join(ctx, pieces)
        ctx.progress(1.0)

    # -- one file at a time -------------------------------------------------------

    def _page(self, ctx: JobContext, path: Path, mime: str, index: int) -> PageImage:
        if mime == "image/jpeg":
            page = jpeg_page(path.read_bytes())
            if page:
                return page
        lossy = mime in PHOTO_FORMATS
        decoded = self._decode(ctx, path, index, lossy=lossy)
        data = decoded.read_bytes()
        if lossy:
            page = jpeg_page(data)
            if page is None:
                raise ConversionError(_DECODE_FAILURE.format(name=path.name))
            return page
        try:
            return pnm_page(data)
        except ValueError as exc:
            raise ConversionError(_DECODE_FAILURE.format(name=path.name)) from exc

    def _decode(self, ctx: JobContext, path: Path, index: int, *, lossy: bool) -> Path:
        """The image upright, on white, 8-bit: a JPEG, or a PGM/PPM when lossless."""
        # Both tools read "[...]" in file names as options, so use a plain link.
        link = ctx.workdir / f"image-{index}{path.suffix.lower()}"
        link.symlink_to(path.resolve())
        vector = path.suffix.lower() in (".svg", ".svgz")
        failure = _DECODE_FAILURE.format(name=path.name)
        if tools.which("vips"):
            return self._vips(ctx, link, index, lossy=lossy, vector=vector, failure=failure)
        exe = tools.require("vips", "imagemagick")
        out = ctx.workdir / f"image-{index}.{'jpg' if lossy else 'pnm'}"
        cmd = [exe, *(["-density", "150"] if vector else []), f"{link}[0]", "-auto-orient"]
        cmd += ["-background", "white", "-alpha", "remove", "-alpha", "off"]
        cmd += ["-colorspace", "sRGB", "-depth", "8", "-strip"]
        cmd += ["-quality", "90", f"jpg:{out}"] if lossy else [f"pnm:{out}"]
        ctx.run(cmd, failure=failure)
        return out

    def _vips(
        self, ctx: JobContext, link: Path, index: int, *, lossy: bool, vector: bool, failure: str
    ) -> Path:
        vips = tools.require("vips")
        header = shutil.which("vipsheader") or "vipsheader"
        stage = ctx.workdir / f"image-{index}"
        source = f"{link}[dpi=150]" if vector else str(link)
        ctx.run([vips, "autorot", source, f"{stage}-a.v"], failure=failure)
        info = _header(ctx.run([header, "-a", f"{stage}-a.v"], failure=failure))
        grey = info.get("interpretation") in ("b-w", "grey16") and not lossy
        ctx.run(
            [vips, "colourspace", f"{stage}-a.v", f"{stage}-b.v", "b-w" if grey else "srgb"],
            failure=failure,
        )
        bands = _header(ctx.run([header, "-a", f"{stage}-b.v"], failure=failure)).get("bands")
        current = f"{stage}-b.v"
        if bands == ("2" if grey else "4"):  # an alpha channel: put it on white
            ctx.run(
                [vips, "flatten", current, f"{stage}-c.v", "--background", "255"], failure=failure
            )
            current = f"{stage}-c.v"
        ctx.run([vips, "cast", current, f"{stage}-d.v", "uchar"], failure=failure)
        if lossy:
            out = ctx.workdir / f"image-{index}.jpg"
            ctx.run([vips, "copy", f"{stage}-d.v", f"{out}[Q=90,strip]"], failure=failure)
        else:
            out = ctx.workdir / f"image-{index}.{'pgm' if grey else 'ppm'}"
            ctx.run([vips, "copy", f"{stage}-d.v", str(out)], failure=failure)
        return out

    def _document(self, ctx: JobContext, path: Path, mime: str, index: int) -> Path:
        folder = ctx.workdir / f"document-{index}"
        folder.mkdir()
        sub = ctx.child(path, mime, folder, folder / "document.pdf")
        DocumentBackend().run(sub)
        return sub.output

    # -- all together ---------------------------------------------------------------

    def _join(self, ctx: JobContext, pieces: list[Path]) -> None:
        if len(pieces) == 1:
            piece = pieces[0]
            if piece.parent == ctx.workdir:
                piece.replace(ctx.output)
            else:
                shutil.copyfile(piece, ctx.output)
            return
        names = [str(piece) for piece in pieces]
        output = str(ctx.output)
        if exe := tools.which("qpdf"):
            # Exit code 3: done, with warnings about a slightly broken input.
            cmd = [exe, "--empty", "--pages", *names, "--", output]
            ctx.run(cmd, failure=_FAILURE, ok_codes=(0, 3))
        elif exe := tools.which("pdfunite"):
            ctx.run([exe, *names, output], failure=_FAILURE)
        else:
            exe = tools.require(*PDF_JOINERS)
            cmd = [exe, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite"]
            ctx.run([*cmd, f"-sOutputFile={output}", *names], failure=_FAILURE)


def _header(text: str) -> dict[str, str]:
    """``vipsheader -a`` output as a mapping, like ``{"bands": "3"}``."""
    fields = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields
