"""Too small for a wall: the box agrees with the contract's layout, and the line falls at half of it."""

import json
from pathlib import Path

import pytest

from arrt.programming.adequacy import RELATIVE_MAT_WIDTH, box, too_small

VECTORS = json.loads((Path(__file__).resolve().parents[3] / "contract" / "vectors" / "mat-geometry.json").read_text())


def _no_density_vectors():
    return [
        vector
        for vector in VECTORS["vectors"]
        if vector["input"]["pixels_per_inch"] is None and vector["input"]["mat_mode"] != "none"
    ]


def test_the_mat_width_is_the_contracts():
    assert VECTORS["relative_width"] == RELATIVE_MAT_WIDTH


@pytest.mark.parametrize("vector", _no_density_vectors(), ids=lambda vector: vector["name"])
def test_the_box_is_the_one_a_player_with_no_density_fits_a_work_into(vector):
    """A work larger than the box is fitted to it, so its drawn size touches the box on one side."""
    screen = (vector["input"]["screen"]["width_px"], vector["input"]["screen"]["height_px"])
    drawn = vector["expect"]["work"]
    width, height = box(screen)

    assert drawn["width"] <= width + 1
    assert drawn["height"] <= height + 1
    # One pixel either way, as the contract allows a fitted size to round.
    assert abs(drawn["width"] - width) <= 1 or abs(drawn["height"] - height) <= 1


@pytest.mark.parametrize(
    ("screen", "work", "small"),
    [
        # 4K: the box is 3580 x 1880, so half of it is 940 px tall or 1790 wide.
        ((3840, 2160), (1600, 939), True),
        ((3840, 2160), (1600, 940), False),
        ((3840, 2160), (1789, 900), True),
        ((3840, 2160), (1790, 900), False),
        # The same work is fine on a smaller screen: the judgement is per wall.
        ((1920, 1200), (1000, 700), False),
        ((3840, 2160), (1000, 700), True),
        # A portrait screen turns the box (950 x 1780), and the work's reach with it.
        ((1080, 1920), (300, 890), False),
        ((1080, 1920), (300, 889), True),
        # Larger than the box is never too small.
        ((3840, 2160), (7680, 5000), False),
    ],
)
def test_too_small_is_less_than_half_the_box_along_the_works_longer_reach(screen, work, small):
    assert too_small(screen, work) is small
