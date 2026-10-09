"""The wall loop's own contract, held against a display that is neither the Frame nor a screen.

The Frame's and a screen's suites drive the loop through their own drivers, so
they would pass as well against two loops as against one. These hold the loop to
what `wall.Display` promises any display, with a third one that has nothing of
either: it names its own unavailable error, and the loop must treat that error,
and only that one, as the display going away.
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any

import pytest
from conftest import WALL_ID

from arrt_player.heartbeat import ScreenState, path_in
from arrt_player.manifest import Watcher
from arrt_player.programmes.rotation import InMemory, Rotation
from arrt_player.wall import DisplayRecord, Picture, Shown, Wall


class Asleep(Exception):
    """This display's own word for "cannot be reached"."""


class Broken(Exception):
    """Something this display does not claim to understand."""


class ThirdDisplay:
    """The smallest display: records what it is asked, and fails when told to."""

    unavailable: tuple[type[Exception], ...] = (Asleep,)
    journal_name = "third"
    description = "the third display"

    def __init__(self, clock, *, wait: float = 42.5) -> None:
        self.record = DisplayRecord(clock, wall_id=WALL_ID)
        self.shown: list[str] = []
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.went_away_with: list[Exception] = []
        self.wait = wait
        self.closed = False

    @property
    def last_error(self) -> str | None:
        return str(self.went_away_with[-1]) if self.went_away_with else None

    def start_lines(self) -> dict[str, object]:
        return {"wall_id": WALL_ID}

    def adopted(self, pictures: Sequence[Picture]) -> None:
        self.calls.append(f"adopted:{len(pictures)}")

    async def prepare(self, pictures: Sequence[Picture]) -> None:
        self.calls.append("prepare")
        if self.fail_with is not None:
            raise self.fail_with

    def may_attempt(self) -> bool:
        return True

    async def is_ours(self) -> bool:
        return True

    async def show(self, picture: Picture) -> Shown:
        self.shown.append(picture.work_id)
        self.record.moved_to(ScreenState.SHOWING_ART, picture.work_id)
        return Shown.YES

    async def after(self, pictures: Sequence[Picture]) -> None:
        self.calls.append("after")

    async def idle(self) -> None:
        self.calls.append("idle")

    def went_away(self, exc: Exception) -> float:
        self.went_away_with.append(exc)
        self.record.moved_to(ScreenState.UNREACHABLE)
        return self.wait

    def answering(self) -> None:
        self.calls.append("answering")

    def heartbeat_fields(self, *, reachable: bool | None) -> dict[str, Any]:
        return {"television_reachable": reachable}

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def wall_settings(client_settings, wall_dir):
    return client_settings.wall(WALL_ID)


@pytest.fixture
def display(clock) -> ThirdDisplay:
    return ThirdDisplay(clock.as_clock())


@pytest.fixture
def wall(wall_settings, display, clock) -> Wall:
    watcher = Watcher(wall_settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    programme = Rotation(wall_id=WALL_ID, render_root=wall_settings.render_root, memory=InMemory(), clock=clock.as_clock())
    return Wall(wall=wall_settings, display=display, programmes={1: programme}, watcher=watcher, clock=clock.as_clock())


def heartbeat(wall_settings) -> dict:
    return json.loads(path_in(wall_settings.heartbeat_root, WALL_ID).read_text())


async def test_a_third_display_rotates_through_the_shared_loop(wall, display, publish, clock, wall_settings):
    publish(["w1", "w2"], interval_seconds=60)

    for _ in range(3):
        await wall.tick()
        clock.advance(60.4)

    assert display.shown == ["w1", "w2", "w1"]
    assert display.calls[0] == "adopted:2", "the display was not told what the manifest names"
    assert heartbeat(wall_settings)["current_work_id"] == "w1"


async def test_with_no_manifest_the_display_idles_and_the_wall_still_beats(wall, display, wall_settings):
    interval = await wall.tick()

    assert display.calls == ["idle"]
    assert interval == wall_settings.poll_interval_seconds
    assert heartbeat(wall_settings)["television_reachable"] is None


async def test_the_displays_own_unavailable_error_is_the_display_going_away(wall, display, publish, wall_settings):
    publish(["w1"])
    display.fail_with = Asleep("asleep")

    interval = await wall.tick()

    assert interval == display.wait, "the wall did not wait as long as its display asked"
    assert [str(exc) for exc in display.went_away_with] == ["asleep"]
    assert display.shown == []
    assert "answering" not in display.calls
    written = heartbeat(wall_settings)
    assert written["television_reachable"] is False
    assert written["display_state"]["state"] == "unreachable"
    assert written["last_error"] == "asleep"


async def test_an_error_the_display_does_not_name_is_not_taken_for_it_going_away(wall, display, publish):
    publish(["w1"])
    display.fail_with = Broken("something nobody predicted")

    with pytest.raises(Broken):
        await wall.tick()

    assert display.went_away_with == []


async def test_a_pass_that_reaches_the_display_says_so(wall, display, publish, wall_settings):
    publish(["w1"])

    interval = await wall.tick()

    assert interval == wall_settings.poll_interval_seconds
    assert display.calls[-1] == "answering"
    assert heartbeat(wall_settings)["television_reachable"] is True


async def test_a_crash_says_which_wall_fell_over(wall, display, publish, caplog):
    """Every wall of a client runs in one process, so a crash line naming no wall names nothing."""
    publish(["w1"])
    display.fail_with = Broken("something nobody predicted")

    with caplog.at_level(logging.ERROR), pytest.raises(Broken):
        await wall.run(asyncio.Event())

    (crashed,) = [record for record in caplog.records if record.__dict__.get("event") == "third.crashed"]
    assert crashed.__dict__.get("wall_id") == WALL_ID
    assert display.closed
