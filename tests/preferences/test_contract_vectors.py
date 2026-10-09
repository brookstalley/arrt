"""The contract's conformance vectors, run against a reference statement of each rule.

`contract/vectors/` holds inputs and the outcome every Player must reach from
them, wherever it runs: the mat's geometry for a screen, and what a feed says to
show at an instant. Arrt Player's suite runs the same files against its own
code once wave 4 builds the code they describe (its reader in 4c, its
compositor in 4d); until then nothing in it reads them. This file holds the **reference statement** of both rules, as
`semantic_errors` in `test_player_contract.py` is for the rules a schema cannot
state, so a vector that disagrees with `player-contract.md` § Layout or § Time
fails here before any Player is asked to match it.

The reference is deliberately plain arithmetic with no imaging library, because
the point is to say what the numbers are, not how to draw them. The server's
compositor is held to the `proportional` vectors in its own suite, which is the
independent check that the reference says what has been drawn on the wall since
wave 2.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import pytest
from test_player_contract import _instant, _schema, _validator, semantic_errors

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
MAT = json.loads((CONTRACT / "vectors" / "mat-geometry.json").read_text(encoding="utf-8"))
SCHEDULE = json.loads((CONTRACT / "vectors" / "schedule.json").read_text(encoding="utf-8"))


def _round_half_up(value: float) -> int:
    """The spec's rounding. Python's `round` goes to even on a half, which no other language does by default."""
    return math.floor(value + 0.5)


def mat_geometry(case: dict) -> dict:
    """`player-contract.md` § Layout, the mat: where the work and its mat go on one screen."""
    screen_w, screen_h = case["screen"]["width_px"], case["screen"]["height_px"]
    work_w, work_h = case["work"]["width_px"], case["work"]["height_px"]
    mode = case["mat_mode"]
    if mode == "none":
        side = bottom = 0
    else:
        density = case["pixels_per_inch"]
        if density is None:
            side = _round_half_up(MAT["relative_width"] * min(screen_w, screen_h))
        else:
            side = _round_half_up(case["mat_width_inches"] * density)
        bottom = _round_half_up(side * case["bottom_weight"])
    box_w = max(1, screen_w - 2 * side)
    box_h = max(1, screen_h - side - bottom)
    scale = min(box_w / work_w, box_h / work_h, 1.0)
    rendered_w = max(1, _round_half_up(work_w * scale))
    rendered_h = max(1, _round_half_up(work_h * scale))
    left = side + (box_w - rendered_w) // 2
    top = side + (box_h - rendered_h) // 2
    work = {"left": left, "top": top, "width": rendered_w, "height": rendered_h}
    if mode == "none":
        mat = None
    elif mode == "full":
        mat = {"left": 0, "top": 0, "width": screen_w, "height": screen_h}
    else:
        mat = {"left": left - side, "top": top - side, "width": rendered_w + 2 * side, "height": rendered_h + side + bottom}
    return {"work": work, "mat": mat}


def what_to_show(feed: dict, now: datetime) -> dict:
    """`player-contract.md` § Time and § Scenes: the work a feed says to show at `now`, or dark.

    An active scene wins, at its own absolute times. Otherwise `now` is moved by
    whole horizons into the horizon (forward past its end, back before its start)
    and the slot covering it is shown; a time no slot covers is dark. Every span
    is half-open: a slot or scene that ends at `now` is over.
    """
    scene = feed.get("scene")
    if scene and _instant(scene["from"]) <= now and (scene["until"] is None or now < _instant(scene["until"])):
        return {"work_id": scene["work_id"], "scene_id": scene["id"]}
    start = _instant(feed["schedule"]["horizon"]["from"])
    span = _instant(feed["schedule"]["horizon"]["until"]) - start
    moved = start + (now - start) % span
    for slot in feed["schedule"]["slots"]:
        if _instant(slot["from"]) <= moved < _instant(slot["until"]):
            return {"work_id": slot["work_id"], "scene_id": None}
    return {"work_id": None, "scene_id": None}


@pytest.mark.parametrize("vector", MAT["vectors"], ids=lambda vector: vector["name"])
def test_each_mat_vector_is_the_reference_geometry(vector):
    assert mat_geometry(vector["input"]) == vector["expect"]


@pytest.mark.parametrize("vector", MAT["vectors"], ids=lambda vector: vector["name"])
def test_each_mat_vector_keeps_the_work_inside_its_mat_and_the_screen(vector):
    """Properties that hold whatever the arithmetic, so a vector edited by hand cannot drift into nonsense."""
    screen = vector["input"]["screen"]
    work, mat = vector["expect"]["work"], vector["expect"]["mat"]
    outer = mat or {"left": 0, "top": 0, "width": screen["width_px"], "height": screen["height_px"]}

    assert outer["left"] <= work["left"] and outer["top"] <= work["top"]
    assert work["left"] + work["width"] <= outer["left"] + outer["width"]
    assert work["top"] + work["height"] <= outer["top"] + outer["height"]
    assert outer["left"] >= 0 and outer["top"] >= 0
    assert outer["left"] + outer["width"] <= screen["width_px"] and outer["top"] + outer["height"] <= screen["height_px"]
    # No upscaling, ever.
    assert work["width"] <= vector["input"]["work"]["width_px"] and work["height"] <= vector["input"]["work"]["height_px"]


def test_the_mat_vectors_cover_every_mode_the_schema_names_with_and_without_a_density():
    """Read from the schema, so a mode added there with no vector fails here."""
    settings = _schema("schemas/manifest.v2.schema.json")["properties"]["settings"]["properties"]
    modes = settings["mat"]["properties"]["mode"]["enum"]
    seen = {(vector["input"]["mat_mode"], vector["input"]["pixels_per_inch"] is None) for vector in MAT["vectors"]}

    for mode in modes:
        assert (mode, True) in seen and (mode, False) in seen, mode


@pytest.mark.parametrize("name", sorted(SCHEDULE["feeds"]))
def test_each_schedule_feed_is_a_valid_major_2_document(name):
    feed = SCHEDULE["feeds"][name]

    assert [error.message for error in _validator("schemas/manifest.v2.schema.json").iter_errors(feed)] == []
    assert semantic_errors(feed) == []


@pytest.mark.parametrize("vector", SCHEDULE["vectors"], ids=lambda vector: vector["name"])
def test_each_schedule_vector_is_what_the_reference_shows(vector):
    assert what_to_show(SCHEDULE["feeds"][vector["feed"]], _instant(vector["now"])) == vector["expect"]
