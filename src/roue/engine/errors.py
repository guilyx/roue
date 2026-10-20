"""Errors that are safe to show to people.

Every error raised by the engine carries a short, plain-English ``message``.
Raw tool output goes into ``details`` and is only shown on request
(``roue convert --verbose``) or in bug reports.
"""

from __future__ import annotations


class RoueError(Exception):
    """Base class for errors with a human-readable message."""

    def __init__(self, message: str, *, hint: str | None = None, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details

    def __str__(self) -> str:
        return self.message if not self.hint else f"{self.message} {self.hint}"


class PresetError(RoueError):
    """A preset file is invalid or a preset id is unknown."""


class MissingToolError(RoueError):
    """A command-line tool needed for a conversion is not installed."""

    def __init__(self, tools: tuple[str, ...], *, hint: str | None = None):
        names = " or ".join(tools)
        super().__init__(f"This needs {names}, which isn't installed.", hint=hint)
        self.tools = tools


class UnsupportedFileError(RoueError):
    """The preset cannot handle this kind of file."""


class ConversionError(RoueError):
    """The conversion tool ran and failed."""


class NothingToDo(RoueError):
    """The conversion would not help (already small enough, no gain...).

    Jobs ending with this are reported as skipped, not failed.
    """


class Cancelled(RoueError):
    """The job was cancelled before it finished."""

    def __init__(self) -> None:
        super().__init__("Cancelled.")
