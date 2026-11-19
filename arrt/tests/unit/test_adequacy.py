"""Too small for a wall: the box agrees with the contract's layout, and the line falls at half of it.

The mat's two numbers are the contract's (`contract/vectors/mat-geometry.json`):
`relative_width` and `defaults.bottom_weight`. `adequacy.py` quotes both, so each
quote is held to its owner here, and the box is shown to be drawn with them.
"""

import json

import pytest
from arrt_contract import root

from arrt.programming import adequacy
from arrt.programming.adequacy import BOTTOM_WEIGHT, RELATIVE_MAT_WIDTH, box, too_small

VECTORS = json.loads((root() / "vectors" / "mat-geometry.json").read_text())


def _no_density_vectors():
    return [
        vector
        for vector in VECTORS["vectors"]
        if vector["input"]["pixels_per_inch"] is None and vector["input"]["mat_mode"] != "none"
    ]


def test_the_mat_width_is_the_contracts():
    assert VECTORS["relative_width"] == RELATIVE_MAT_WIDTH


def test_the_bottom_weight_is_the_contracts_default():
    assert VECTORS["defaults"]["bottom_weight"] == BOTTOM_WEIGHT


def test_the_box_is_drawn_with_the_bottom_weight(monkeypatch):
    """Through `box`, with a weight that is not the default, so a box that ignored the constant would fail here.

    1080p: the side margin is 65 px; at 1.15 the bottom is 75 and the box 1790 x 940,
    at 2.0 the bottom is 130 and the box 1790 x 885.
    """
    assert box((1920, 1080)) == (1790, 940)

    monkeypatch.setattr(adequacy, "BOTTOM_WEIGHT", 2.0)

    assert box((1920, 1080)) == (1790, 885)


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
