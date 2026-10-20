"""Custom presets that run any command.

``params.command`` is a list (or a shell-like string) with placeholders:

- ``{in}``: the input file
- ``{out}``: the file to write (Roue moves it next to the original after)
- ``{outdir}``: a folder to write into, for presets with ``output: folder``
- ``{stem}``: the input name without extension

The command runs without a shell, so placeholders never need quoting.
"""

from __future__ import annotations

import shlex

from ..errors import PresetError
from ..presets import Preset
from .base import JobContext, Requirements


def command_words(preset: Preset) -> list[str]:
    raw = preset.params.get("command")
    words = shlex.split(raw) if isinstance(raw, str) else [str(w) for w in raw or []]
    if not words:
        raise PresetError(f"Preset {preset.id} has an empty command.")
    return words


class CommandBackend:
    def requirements(self, preset: Preset, mime: str | None = None) -> Requirements:
        return [(command_words(preset)[0],)]

    def run(self, ctx: JobContext) -> None:
        values = {
            "in": str(ctx.source),
            "out": str(ctx.output),
            "outdir": str(ctx.output_folder) if ctx.preset.output == "folder" else "",
            "stem": ctx.source.stem,
        }
        cmd = []
        for word in command_words(ctx.preset):
            try:
                cmd.append(word.format_map(values))
            except (KeyError, ValueError, IndexError) as exc:
                raise PresetError(
                    f"Preset {ctx.preset.id}: unknown placeholder in '{word}'.",
                    hint="Use {in}, {out}, {outdir} or {stem}.",
                ) from exc
        ctx.progress(None)
        ctx.run(cmd, failure=f"The command for '{ctx.preset.name}' failed.")
        ctx.progress(1.0)
