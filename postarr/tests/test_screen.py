"""A wall on a screen this client draws itself: the rotation, the directive, and what it reports.

Driven one `tick()` at a time against a clock that only moves when a test moves
it, as the Frame's loop is, over a recording output in place of an HDMI
connector. The steps are not multiples of the interval under test, so a timer
consumed early cannot pass for one correctly withheld.
"""

import json
import logging
import random

import pytest
from fakes import RecordingOutput

from postarr.heartbeat import path_in
from postarr.manifest import Watcher
from postarr.screen import PendingOutput, ScreenWall


@pytest.fixture
def wall(client_settings, wall_dir):
    return client_settings.wall("living-room")


@pytest.fixture
def output() -> RecordingOutput:
    return RecordingOutput()


@pytest.fixture
def screen(wall, output, clock) -> ScreenWall:
    watcher = Watcher(wall.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    return ScreenWall(wall=wall, output=output, watcher=watcher, clock=clock.as_clock(), rng=random.Random(7))


def shown(output: RecordingOutput) -> list[str]:
    return [path.stem for path in output.shown]


async def test_it_shows_the_first_work_at_once_and_steps_on_when_the_interval_is_up(screen, output, publish, clock):
    publish(["w1", "w2", "w3"], interval_seconds=60)

    await screen.tick()
    assert shown(output) == ["w1"]

    clock.advance(59.5)
    await screen.tick()
    assert shown(output) == ["w1"], "the wall stepped on before its interval was up"

    clock.advance(0.7)
    await screen.tick()
    clock.advance(61.3)
    await screen.tick()
    clock.advance(60.1)
    await screen.tick()
    assert shown(output) == ["w1", "w2", "w3", "w1"]


async def test_a_missing_render_is_skipped_and_said_once(screen, output, publish, clock, wall_dir, caplog):
    publish(["w1", "w2", "w3"], interval_seconds=60)
    (wall_dir / "ready" / "w2.jpg").unlink()

    with caplog.at_level(logging.WARNING):
        for _ in range(4):
            await screen.tick()
            clock.advance(60.3)

    assert shown(output) == ["w1", "w3", "w1", "w3"]
    assert [record.__dict__.get("event") for record in caplog.records].count("rotation.render_missing") == 1


async def test_a_theme_with_no_render_at_all_shows_nothing_and_does_not_spin(screen, output, publish, wall_dir):
    publish(["w1", "w2"])
    for name in ("w1", "w2"):
        (wall_dir / "ready" / f"{name}.jpg").unlink()

    for _ in range(3):
        await screen.tick()

    assert output.shown == []


async def test_the_first_directive_is_a_baseline_and_the_next_one_is_acted_on(screen, output, publish, clock):
    """A worker starting on a manifest that pins a work does not jump to it: the
    pin was somebody's `show_now` from before this worker existed."""
    publish(["w1", "w2", "w3"], sequence=5, pinned_work_id="w3")
    await screen.tick()
    assert shown(output) == ["w1"], "the baseline was acted on"

    publish(["w1", "w2", "w3"], sequence=6)
    clock.advance(1.3)
    await screen.tick()

    assert shown(output) == ["w1", "w2"]


async def test_show_now_jumps_to_the_pinned_work_and_rotation_carries_on_from_it(screen, output, publish, clock):
    publish(["w1", "w2", "w3", "w4"], sequence=1)
    await screen.tick()

    publish(["w1", "w2", "w3", "w4"], sequence=2, pinned_work_id="w3")
    clock.advance(1.3)
    await screen.tick()
    clock.advance(180.7)
    await screen.tick()

    assert shown(output) == ["w1", "w3", "w4"]


async def test_a_sequence_that_goes_backwards_rebaselines_without_acting(screen, output, publish, clock, caplog):
    publish(["w1", "w2", "w3"], sequence=9)
    await screen.tick()

    with caplog.at_level(logging.WARNING):
        publish(["w1", "w2", "w3"], sequence=3, pinned_work_id="w3")
        clock.advance(1.3)
        await screen.tick()

    assert shown(output) == ["w1"]
    assert "directive.regressed" in [record.__dict__.get("event") for record in caplog.records]


async def test_a_sync_mid_interval_keeps_the_place(screen, output, publish, clock):
    """A rewritten manifest resumes after the work on the screen, not at the first one."""
    publish(["w1", "w2", "w3"])
    await screen.tick()
    clock.advance(180.4)
    await screen.tick()
    assert shown(output) == ["w1", "w2"]

    publish(["w0", "w1", "w2", "w3"])
    clock.advance(180.4)
    await screen.tick()

    assert shown(output) == ["w1", "w2", "w3"]


async def test_shuffle_shows_every_work_once_per_pass(screen, output, publish, clock):
    works = [f"w{n}" for n in range(6)]
    publish(works, shuffle=True, interval_seconds=10)

    for _ in range(6):
        await screen.tick()
        clock.advance(10.3)

    assert sorted(shown(output)) == works
    assert shown(output) != works, "a shuffled theme came out in order, so this shows nothing about shuffling"


async def test_an_output_that_fails_costs_the_picture_and_not_the_wall(screen, output, publish, clock):
    publish(["w1", "w2"])
    output.fails = OSError("the connector went away")
    await screen.tick()

    output.fails = None
    clock.advance(180.4)
    await screen.tick()

    assert shown(output) == ["w1"]


async def test_its_heartbeat_names_the_work_on_the_screen_and_no_television(screen, publish, wall_dir):
    publish(["w1"], theme_id="th-winter")

    await screen.tick()

    document = json.loads(path_in(wall_dir, "living-room").read_text())
    assert document["current_work_id"] == "w1"
    assert document["theme_id"] == "th-winter"
    assert document["television_reachable"] is None
    assert document["has_label_surface"] is False


async def test_with_no_manifest_yet_it_shows_nothing_and_still_beats(screen, output, wall_dir):
    await screen.tick()

    assert output.shown == []
    assert json.loads(path_in(wall_dir, "living-room").read_text())["manifest_schema"] is None


def test_the_pending_output_says_once_that_it_draws_nothing(tmp_path, caplog):
    pending = PendingOutput(wall_id="hall", output="hdmi-a-1")

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            pending.show(tmp_path / "a-render")

    lines = [record.getMessage() for record in caplog.records]
    assert len(lines) == 1
    assert "HDMI drawing arrives in Chunk 04" in lines[0]
    assert (pending.connected, pending.screen) == (False, None)
