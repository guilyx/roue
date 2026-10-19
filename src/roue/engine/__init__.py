"""The conversion engine. No GTK here: everything is usable from scripts and tests.

The panel, the file-manager menu and the CLI are all thin front doors to
:class:`~roue.engine.runner.Runner`.
"""

from .detect import kind_of, mime_type
from .errors import RoueError
from .presets import Preset, PresetRegistry, load_presets
from .runner import Batch, Job, JobState, Runner, human_size

__all__ = [
    "Batch",
    "Job",
    "JobState",
    "Preset",
    "PresetRegistry",
    "RoueError",
    "Runner",
    "human_size",
    "kind_of",
    "load_presets",
    "mime_type",
]
