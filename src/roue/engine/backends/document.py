"""Documents with LibreOffice (office files) and Pandoc (Markdown & co).

The output format is the preset's ``output_ext``. The route depends on the
input: office formats go through LibreOffice; Markdown, reStructuredText,
Org and HTML go through Pandoc. Markdown to PDF uses a Pandoc PDF engine
when one is installed, otherwise Pandoc writes ODT and LibreOffice prints
it to PDF.
"""

from __future__ import annotations

from pathlib import Path

from .. import tools
from ..detect import mime_matches
from ..errors import ConversionError, UnsupportedFileError
from ..presets import Preset
from .base import JobContext, Requirements

PANDOC_INPUTS: dict[str, str] = {
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "text/plain": "markdown",
    "text/x-rst": "rst",
    "text/org": "org",
    "text/html": "html",
}

OFFICE_INPUTS = (
    "application/msword",
    "application/rtf",
    "application/vnd.ms-*",
    "application/vnd.openxmlformats-officedocument.*",
    "application/vnd.oasis.opendocument.*",
    "text/csv",
)

# LibreOffice export filters for formats where the default guess is wrong.
_LO_FILTERS = {"docx": 'docx:"MS Word 2007 XML"', "txt": "txt:Text"}


def route_for(mime: str) -> str | None:
    if mime in PANDOC_INPUTS:
        return "pandoc"
    if mime_matches(mime, OFFICE_INPUTS):
        return "libreoffice"
    return None


class DocumentBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        if mime is None:
            if preset.output_ext == "pdf":
                # LibreOffice alone, or Pandoc with a PDF engine.
                return [("libreoffice", "pandoc"), ("libreoffice", *tools.PDF_ENGINES)]
            return [("libreoffice", "pandoc")]
        route = route_for(mime)
        if route == "libreoffice":
            return [("libreoffice",)]
        if preset.output_ext == "pdf":
            return [("pandoc",), (*tools.PDF_ENGINES, "libreoffice")]
        return [("pandoc",)]

    def run(self, ctx: JobContext) -> None:
        ctx.progress(None)
        route = route_for(ctx.mime)
        ext = ctx.output.suffix.lstrip(".")
        if route == "libreoffice":
            self._libreoffice(ctx, ctx.source, ext)
        elif route == "pandoc":
            self._pandoc(ctx, ext)
        else:
            raise UnsupportedFileError("This kind of document isn't supported yet.")
        ctx.progress(1.0)

    def _libreoffice(self, ctx: JobContext, source: Path, ext: str) -> None:
        exe = tools.require("libreoffice")
        link = ctx.workdir / f"document{source.suffix.lower()}"
        if not link.exists():
            link.symlink_to(source.resolve())
        outdir = ctx.workdir / "lo-out"
        profile = (ctx.workdir / "lo-profile").as_uri()
        cmd = [
            exe,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--convert-to",
            _LO_FILTERS.get(ext, ext),
            "--outdir",
            str(outdir),
            str(link),
        ]
        ctx.run(cmd, failure="LibreOffice couldn't convert this document.")
        produced = outdir / f"document.{ext}"
        if not produced.exists():
            raise ConversionError(
                "LibreOffice couldn't convert this document.",
                hint="It may be damaged or password-protected.",
            )
        produced.replace(ctx.output)

    def _pandoc(self, ctx: JobContext, ext: str) -> None:
        exe = tools.require("pandoc")
        reader = PANDOC_INPUTS[ctx.mime]
        base = [
            exe,
            f"--from={reader}",
            f"--resource-path={ctx.source.parent}",
            str(ctx.source),
        ]
        title = ["--metadata", f"pagetitle={ctx.source.stem}"]
        failure = "Pandoc couldn't convert this document."
        if ext == "html":
            cmd = [*base, "--standalone", "--embed-resources", *title, "-o", str(ctx.output)]
            ctx.run(cmd, failure=failure, cwd=ctx.source.parent)
        elif ext == "pdf":
            engine = tools.pdf_engine()
            if engine:
                cmd = [*base, *title, f"--pdf-engine={engine}", "-o", str(ctx.output)]
                ctx.run(cmd, failure=failure, cwd=ctx.source.parent)
            else:
                # No PDF engine: write ODT, then let LibreOffice print it.
                tools.require(*tools.PDF_ENGINES, "libreoffice")
                odt = ctx.workdir / "document.odt"
                ctx.run([*base, *title, "-o", str(odt)], failure=failure, cwd=ctx.source.parent)
                self._libreoffice(ctx, odt, "pdf")
        else:
            cmd = [*base, *title, "-o", str(ctx.output)]
            ctx.run(cmd, failure=failure, cwd=ctx.source.parent)
