from __future__ import annotations

import math

import pytest

from roue.engine.presets import load_presets
from roue.radial import (
    MAX_PRESETS,
    Geometry,
    choose_presets,
    clamp_center,
    slice_anchor,
    slice_at,
    slice_span,
)

G = Geometry()


def test_slice_zero_is_centred_at_twelve_o_clock() -> None:
    start, end = slice_span(0, 8)
    assert math.isclose((start + end) / 2, -math.pi / 2)
    assert math.isclose(end - start, math.pi / 4)


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [
        (0, -120, 0),  # straight up
        (120, 0, 2),  # right (8 slices, clockwise)
        (0, 120, 4),  # down
        (-120, 0, 6),  # left
        (85, -85, 1),  # up-right
    ],
)
def test_slice_at_follows_direction(dx: float, dy: float, expected: int) -> None:
    assert slice_at(dx, dy, 8) == expected


def test_hub_and_far_away_select_nothing() -> None:
    assert slice_at(10, 10, 8) is None
    assert slice_at(0, -(G.outer + G.reach + 5), 8) is None
    assert slice_at(0, -(G.outer + G.reach - 5), 8) == 0  # a little past the rim still counts
    assert slice_at(0, -100, 0) is None


@pytest.mark.parametrize("count", [3, 5, 8])
def test_anchor_points_back_to_their_own_slice(count: int) -> None:
    for i in range(count):
        dx, dy = slice_anchor(i, count, (G.inner + G.outer) / 2)
        assert slice_at(dx, dy, count) == i


def test_clamp_keeps_the_wheel_on_screen() -> None:
    half = G.size / 2
    assert clamp_center(5, 5, 1920, 1080) == (half, half)
    assert clamp_center(1915, 1075, 1920, 1080) == (1920 - half, 1080 - half)
    assert clamp_center(900, 500, 1920, 1080) == (900, 500)
    assert clamp_center(10, 10, 300, 300) == (150, 150)  # screen smaller than the wheel


def test_choose_presets_for_a_photo() -> None:
    registry = load_presets(include_user=False)
    presets, more = choose_presets(registry, ["image/heic"])
    assert presets[0].id == "jpg"
    assert len(presets) == MAX_PRESETS and more
    assert all(p.group == "image" for p in presets)


def test_choose_presets_for_a_pdf_has_no_more() -> None:
    registry = load_presets(include_user=False)
    presets, more = choose_presets(registry, ["application/pdf"])
    assert [p.id for p in presets] == ["compress-pdf", "pdf-to-png", "pdf-to-text"]
    assert not more


def test_no_presets_without_files() -> None:
    # The wheel never offers a format before it knows what it'll convert.
    registry = load_presets(include_user=False)
    assert choose_presets(registry) == ([], False)
