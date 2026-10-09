"""The server's compositor against the contract's mat vectors.

`contract/vectors/mat-geometry.json` states where a work and its mat go on a
screen, and Arrt Player's compositor is ported against it in wave 4. The
`proportional` vectors with a known pixel density describe what this
compositor has drawn on the Frame since wave 2, so it is held to them here,
through the real `compose` and the real `tv_artwork_box`. That is what makes the
vectors a record of the wall as it is rather than a fresh design, and it is the
check that fails if either side moves before the port.

The other vectors (`none`, `full`, and a screen of no known density) describe
modes this compositor never had. They are held to the reference statement in the
root suite.
"""

import dataclasses
import json
import math
from pathlib import Path

import pytest
from PIL import Image

from arrt.config import Settings
from arrt.library.acquisition.compose import compose

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
VECTORS = json.loads((CONTRACT / "vectors" / "mat-geometry.json").read_text(encoding="utf-8"))["vectors"]
DRAWN_HERE = [
    vector
    for vector in VECTORS
    if vector["input"]["mat_mode"] == "proportional" and vector["input"]["pixels_per_inch"] is not None
]

#: The spec rounds a half up; this compositor rounds through Python's `round`,
#: which takes a half to even, and Pillow fits a thumbnail with its own rounding.
#: The vectors allow a pixel for that.
_TOLERANCE_PX = 1


def test_the_compositor_is_held_to_some_vectors():
    assert len(DRAWN_HERE) >= 3


@pytest.mark.parametrize("vector", DRAWN_HERE, ids=lambda vector: vector["name"])
def test_the_compositor_draws_each_proportional_vector(vector, settings: Settings, tmp_path):
    case = vector["input"]
    width, height = case["screen"]["width_px"], case["screen"]["height_px"]
    configured = dataclasses.replace(
        settings,
        tv_panel_width_px=width,
        tv_panel_height_px=height,
        # The vector gives the density; the server is configured by the diagonal it comes from.
        tv_panel_diagonal_inches=math.hypot(width, height) / case["pixels_per_inch"],
        mat_width_inches=case["mat_width_inches"],
        mat_bottom_weight=case["bottom_weight"],
    )
    source = tmp_path / "master.png"
    Image.new("RGB", (case["work"]["width_px"], case["work"]["height_px"]), (200, 180, 160)).save(source)

    drawn = compose(
        source,
        destination=tmp_path / "canvas.jpg",
        mat_hex="#27285b",
        panel_width=width,
        panel_height=height,
        box=configured.tv_artwork_box,
    )

    work, mat = vector["expect"]["work"], vector["expect"]["mat"]
    actual_work = {
        "left": drawn.artwork_left,
        "top": drawn.artwork_top,
        "width": drawn.rendered_width,
        "height": drawn.rendered_height,
    }
    actual_mat = {"left": drawn.mat_left, "top": drawn.mat_top, "width": drawn.mat_width, "height": drawn.mat_height}
    for expected, actual in ((work, actual_work), (mat, actual_mat)):
        assert all(abs(expected[key] - actual[key]) <= _TOLERANCE_PX for key in expected), (expected, actual)
