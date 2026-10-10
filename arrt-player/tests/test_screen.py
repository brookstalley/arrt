"""A wall on a screen this client draws itself: the schedule, and what it reports.

Driven one `tick()` at a time against a clock that only moves when a test moves
it, as the Frame's loop is, over a recording output in place of an HDMI
connector. The steps are not multiples of the slot under test, so a slot
ended early cannot pass for one correctly held.
"""

import json
import logging
from pathlib import Path

import pytest
from fakes import RecordingOutput
from jsonschema import Draft202012Validator

from arrt_player.displays.screen import screen_wall
from arrt_player.heartbeat import INTERVAL_SECONDS, path_in
from arrt_player.manifest import Watcher
from arrt_player.wall import Wall


@pytest.fixture
def wall(client_settings, wall_dir):
    return client_settings.wall("living-room")


@pytest.fixture
def output() -> RecordingOutput:
    return RecordingOutput()


@pytest.fixture
def screen(wall, output, clock, publish) -> Wall:
    # The fixture's pictures are composed for this screen, as the wall composes them.
    publish.geometry = wall.geometry_for(output.screen)
    watcher = Watcher(wall.manifest_path)
    return screen_wall(wall=wall, output=output, watcher=watcher, clock=clock.as_clock())


@pytest.fixture
def shown(output, publish):
    """The works the screen was asked to draw, in order."""
    return lambda: [publish.work_of(path) for path in output.shown]


async def test_it_shows_the_first_work_at_once_and_steps_on_when_its_slot_ends(screen, shown, publish, clock):
    publish(["w1", "w2", "w3"], interval_seconds=60)

    await screen.tick()
    assert shown() == ["w1"]

    clock.advance(59.5)
    await screen.tick()
    assert shown() == ["w1"], "the wall stepped on before its slot was over"

    clock.advance(0.7)
    await screen.tick()
    clock.advance(61.3)
    await screen.tick()
    clock.advance(60.1)
    await screen.tick()
    assert shown() == ["w1", "w2", "w3", "w1"]


async def test_a_missing_master_is_passed_over_and_said_once(screen, shown, publish, clock, caplog):
    """The screen keeps the work it has through the missing one's slot, rather than going black."""
    publish(["w1", "w2", "w3"], interval_seconds=60)
    publish.withdraw("w2")

    with caplog.at_level(logging.WARNING):
        for _ in range(4):
            await screen.tick()
            clock.advance(60.3)

    assert shown() == ["w1", "w3", "w1"]
    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.media_missing") == 1


async def test_a_missing_master_is_said_again_for_a_new_feed(screen, shown, publish, clock, caplog):
    """Once per feed, not once per process: a republished feed is news, and so is its gap."""
    publish(["w1", "w2"], interval_seconds=60)
    publish.withdraw("w2")

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await screen.tick()
            clock.advance(60.3)
        publish(["w1", "w2"], interval_seconds=61, media=False)
        for _ in range(3):
            await screen.tick()
            clock.advance(61.3)

    assert shown() == ["w1"], "w2 came back, so the gap was never said again"
    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.media_missing") == 2


async def test_an_empty_screen_shows_media_that_arrives_at_once(screen, output, shown, publish, clock):
    """A screen showing nothing does not sit out the slot when the master arrives."""
    publish(["w1"], interval_seconds=180, media=False)
    await screen.tick()
    assert output.shown == []

    clock.advance(1.3)
    publish(["w1"], interval_seconds=180)
    await screen.tick()

    assert shown() == ["w1"]


async def test_a_feed_with_no_media_at_all_shows_nothing_and_does_not_spin(screen, output, publish):
    publish(["w1", "w2"])
    for name in ("w1", "w2"):
        publish.withdraw(name)

    for _ in range(3):
        await screen.tick()

    assert output.shown == []


async def test_a_republished_schedule_reaches_the_screen_at_once_and_its_slots_carry_on(screen, shown, publish, clock):
    """How a `show_now` arrives: a new feed whose slot now names the work."""
    publish(["w1", "w2", "w3", "w4"])
    await screen.tick()

    publish(["w3", "w4", "w1", "w2"])
    clock.advance(1.3)
    await screen.tick()
    clock.advance(180.7)
    await screen.tick()

    assert shown() == ["w1", "w3", "w4"]


async def test_an_output_that_fails_costs_the_picture_and_not_the_wall(screen, output, shown, publish, clock, caplog):
    publish(["w1", "w2", "w3"])
    output.fails = OSError("the connector went away")
    with caplog.at_level(logging.INFO):
        await screen.tick()
        clock.advance(180.4)
        await screen.tick()

        output.fails = None
        clock.advance(180.4)
        await screen.tick()

    assert shown() == ["w3"]
    events = [record.__dict__.get("event") for record in caplog.records]
    assert events.count("screen.draw_failed") == 1, "a refusing screen was reported per work, not per episode"
    assert events.count("screen.draw_recovered") == 1


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


async def test_every_poll_asks_the_output_to_draw_again_for_a_screen_that_came_back(screen, output, shown, publish, clock):
    publish(["w1", "w2"], interval_seconds=60)

    for _ in range(3):
        await screen.tick()
        clock.advance(7.3)

    assert output.refreshed == 3
    assert shown() == ["w1"], "a refresh is not a change of picture"


async def test_a_screen_that_cannot_be_drawn_again_is_said_once_and_the_schedule_goes_on(
    screen, output, shown, publish, clock, wall_dir, caplog
):
    publish(["w1", "w2"], interval_seconds=60)
    output.refresh_fails = OSError(13, "Permission denied")

    with caplog.at_level(logging.INFO):
        for _ in range(3):
            await screen.tick()
            clock.advance(60.3)
        output.refresh_fails = None
        await screen.tick()

    events = [record.__dict__.get("event") for record in caplog.records]
    assert events.count("screen.refresh_failed") == 1
    assert events.count("screen.refresh_recovered") == 1
    assert shown() == ["w1", "w2", "w1", "w2"]
    assert "Permission denied" in json.loads(path_in(wall_dir, "living-room").read_text())["last_error"]


# -- display state: what the screen is doing (labels-and-surfaces.md § Display state) -------

_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contract" / "schemas" / "heartbeat.v1.schema.json").read_text(encoding="utf-8")
)


def _display(wall_dir) -> tuple[str, str | None]:
    document = json.loads(path_in(wall_dir, "living-room").read_text())
    errors = [
        e.message for e in Draft202012Validator(_SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(document)
    ]
    assert errors == [], errors
    assert document["schema"] == {"major": 1, "minor": 3}
    return document["display_state"]["state"], document["display_state"]["work_id"]


async def test_a_drawn_work_is_showing_art(screen, publish, wall_dir):
    publish(["w1", "w2"])

    await screen.tick()

    assert _display(wall_dir) == ("showing_art", "w1")


async def test_a_connector_reporting_no_screen_is_dark_and_a_returning_screen_is_art_again(
    screen, output, publish, wall_dir, clock
):
    publish(["w1", "w2"], interval_seconds=900)
    await screen.tick()

    output.connected = False
    clock.advance(1.3)
    await screen.tick()
    assert _display(wall_dir) == ("dark", None)

    output.connected = True
    clock.advance(1.3)
    await screen.tick()
    assert _display(wall_dir) == ("showing_art", "w1")


async def test_an_output_the_client_no_longer_lists_is_no_screen(screen, output, publish, wall_dir, clock):
    publish(["w1"])
    await screen.tick()

    output.listed = False
    output.connected = False
    clock.advance(1.3)
    await screen.tick()

    assert _display(wall_dir) == ("no_screen", None)


async def test_before_anything_is_drawn_the_screen_is_dark(screen, wall_dir):
    """No manifest yet: the screen shows the console's black, not art."""
    await screen.tick()

    assert _display(wall_dir) == ("dark", None)


async def test_a_change_is_written_at_once_and_an_unchanged_state_keeps_the_interval(screen, output, publish, wall_dir, clock):
    publish(["w1", "w2"], interval_seconds=900)
    await screen.tick()
    first = path_in(wall_dir, "living-room").read_text()

    clock.advance(INTERVAL_SECONDS / 7)
    await screen.tick()
    assert path_in(wall_dir, "living-room").read_text() == first, "an unchanged state was written before the interval"

    output.connected = False
    clock.advance(INTERVAL_SECONDS / 7)
    await screen.tick()
    assert path_in(wall_dir, "living-room").read_text() != first, "a change waited for the interval"
