"""Geometry and choices for the wheel (radial menu). No GTK here, so it's testable.

Slices are numbered clockwise from the top. Like any pie menu, direction is
what counts: past the hub, every point belongs to the slice it points at, up
to a little beyond the rim.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .engine.backends import is_available
from .engine.presets import Preset, PresetRegistry

#: Presets per wheel; one more slice holds "More…". Pie menus stay fast up to ~8.
MAX_PRESETS = 7


@dataclass(frozen=True)
class Geometry:
    inner: float = 62.0  # hub radius: releasing here cancels
    outer: float = 172.0  # rim
    reach: float = 70.0  # beyond the rim, still counts as that slice
    gap: float = math.radians(1.6)  # visual gap between slices

    @property
    def size(self) -> int:
        """Side of the square that fits the wheel, its hover pop and shadow."""
        return int(2 * (self.outer + 34))


DEFAULT = Geometry()


def slice_span(index: int, count: int) -> tuple[float, float]:
    """Start and end angle (radians, screen coordinates) of a slice.

    Slice 0 is centred on 12 o'clock and the rest follow clockwise.
    """
    width = 2 * math.pi / count
    start = -math.pi / 2 - width / 2 + index * width
    return start, start + width


def slice_at(dx: float, dy: float, count: int, geometry: Geometry = DEFAULT) -> int | None:
    """Slice under a point given relative to the centre, or None (hub or outside)."""
    if count <= 0:
        return None
    distance = math.hypot(dx, dy)
    if distance < geometry.inner or distance > geometry.outer + geometry.reach:
        return None
    width = 2 * math.pi / count
    # Angle measured clockwise from the start of slice 0.
    angle = (math.atan2(dy, dx) + math.pi / 2 + width / 2) % (2 * math.pi)
    return int(angle // width) % count


def slice_anchor(index: int, count: int, radius: float) -> tuple[float, float]:
    """Point in the middle of a slice at ``radius``, relative to the centre."""
    start, end = slice_span(index, count)
    middle = (start + end) / 2
    return radius * math.cos(middle), radius * math.sin(middle)


def clamp_center(
    x: float, y: float, width: float, height: float, geometry: Geometry = DEFAULT
) -> tuple[float, float]:
    """Keep the whole wheel on screen when the pointer is near an edge."""
    half = geometry.size / 2

    def clamp(value: float, extent: float) -> float:
        return min(max(value, half), extent - half) if extent >= 2 * half else extent / 2

    return clamp(x, width), clamp(y, height)


def choose_presets(
    registry: PresetRegistry,
    mimes: Iterable[str] = (),
    limit: int = MAX_PRESETS,
) -> tuple[list[Preset], bool]:
    """Presets for the wheel, best first, and whether more exist beyond them.

    These are the presets that take all the files (most relevant kind first).
    Without files there are none: the wheel never offers a format it can't
    make from what you drop.
    """
    mimes = list(mimes)
    if not mimes:
        return [], False
    candidates = [p for p in registry.matching(mimes) if is_available(p)]
    return candidates[:limit], len(candidates) > limit
