"""A wall reads both majors, and a new document of the other major switches it without a restart.

Driven through both real drivers (the Frame over its television double, a
screen over a recording output), because the switch lives in the shared loop
and each display remembers what is on the wall in its own way.
"""

import json
import random
from pathlib import Path

import pytest
from conftest import a_master, tick_until, write_manifest
from fakes import FakeTv, RecordingOutput
from PIL import Image

from arrt_player.compose import Geometry, composition_key
from arrt_player.displays.frame import FrameDisplay, frame_wall
from arrt_player.displays.screen import screen_wall
from arrt_player.heartbeat import path_in
from arrt_player.manifest import Watcher

MAT = "#222222"


def _sha(work_id: str) -> str:
    return (work_id.encode().hex() * 64)[:64]


def composed(wall_dir: Path, sha: str, geometry: Geometry, *, mode: str = "proportional") -> Path:
    """The file a work composes to on this wall, as the schedule names it."""
    return wall_dir / "composed" / f"{composition_key(master_sha256=sha, mat_color=MAT, mode=mode, geometry=geometry)}.jpg"


def publish_feed(wall_dir, slots: list[tuple[str, str, str]]) -> dict:
    """Cache a one-day major 2 feed on the test clock's day, with every master in the media cache."""
    works = {}
    for work, _, _ in slots:
        a_master(wall_dir / "media" / f"sha256-{_sha(work)}")
        works[work] = {
            "media": {"url": f"/media/sha256-{_sha(work)}", "sha256": _sha(work)},
            "mat_color": MAT,
            "label": {"title": work},
        }
    document = {
        "schema": {"major": 2, "minor": 0},
        "generated_at": "2026-06-21T00:00:00+00:00",
        "playlist": {"id": "pl-1", "name": "A playlist"},
        "works": works,
        "schedule": {
            "horizon": {"from": "2026-06-21T00:00:00+00:00", "until": "2026-06-22T00:00:00+00:00"},
            "slots": [
                {"work_id": work, "from": f"2026-06-21T{a}:00+00:00", "until": f"2026-06-21T{b}:00+00:00"} for work, a, b in slots
            ],
        },
    }
    write_manifest(wall_dir, document)
    return document


@pytest.fixture
def screen(client_settings, wall_dir, clock):
    wall = client_settings.wall("living-room")
    output = RecordingOutput()
    watcher = Watcher(wall.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    return screen_wall(wall=wall, output=output, watcher=watcher, clock=clock.as_clock(), rng=random.Random(7)), output


@pytest.fixture
def screen_geometry(client_settings) -> Geometry:
    """What the screen fixture composes for: the recording output's mode, with no density."""
    return client_settings.wall("living-room").geometry_for(RecordingOutput().screen)


async def test_a_screen_switches_from_major_1_to_a_feed_and_back(screen, publish, wall_dir, clock, screen_geometry):
    wall, output = screen
    publish(["w1", "w2"], interval_seconds=60)
    await wall.tick()
    assert output.shown == [wall_dir / "ready" / "w1.jpg"], "major 1's render is handed over as it arrived, never matted again"

    clock.advance(1.3)
    publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    await tick_until(wall.tick, lambda: len(output.shown) == 2)
    assert output.shown[-1] == composed(wall_dir, _sha("f1"), screen_geometry), "the feed's slot was not shown composed"

    clock.advance(1.3)
    publish(["w1", "w2"], interval_seconds=60)
    await wall.tick()
    # Switched back, the rotation takes the wall at once, as a restarted one
    # does: the feed's picture is up and the theme does not carry its work, so
    # it starts from the top.
    assert [path.name for path in output.shown[2:]] == ["w1.jpg"], "major 1's rotation did not take the wall back"


async def test_a_wall_switched_away_and_back_puts_its_own_picture_up_again(screen, publish, wall_dir, clock, screen_geometry):
    """Major 1's render of a work is not major 2's picture of it, though the wall's memory names the same work."""
    wall, output = screen
    publish_feed(wall_dir, [("w1", "08:00", "18:00")])
    await tick_until(wall.tick, lambda: len(output.shown) == 1)

    clock.advance(1.3)
    publish(["w1"], interval_seconds=60)
    await wall.tick()
    assert output.shown[-1].name == "w1.jpg", "major 1 put its own render of the work up"

    clock.advance(1.3)
    publish_feed(wall_dir, [("w1", "08:00", "18:00")])
    await tick_until(wall.tick, lambda: len(output.shown) == 3)

    assert output.shown[-1] == composed(wall_dir, _sha("w1"), screen_geometry), "the composed render stayed up"


async def test_the_frame_shows_a_feeds_slot_and_then_the_next(settings, tv: FakeTv, state, wall_dir, clock):
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    wall = frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())
    publish_feed(wall_dir, [("f1", "08:00", "13:00"), ("f2", "13:00", "18:00")])

    await tick_until(wall.tick, lambda: state.last_selected_work_id == "f1")
    assert tv.on_the_wall == composed(wall_dir, _sha("f1"), settings.geometry), "the Frame was not handed the composition"

    clock.advance(3600.4)
    await tick_until(wall.tick, lambda: state.last_selected_work_id == "f2")
    assert tv.on_the_wall == composed(wall_dir, _sha("f2"), settings.geometry)


async def test_the_frame_composes_for_its_configured_panel(settings, tv: FakeTv, state, wall_dir, clock):
    """A 4K panel at the fixture's 50 inches, not the screen double's 1080p."""
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    wall = frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())
    publish_feed(wall_dir, [("f1", "08:00", "18:00")])

    await tick_until(wall.tick, lambda: tv.on_the_wall is not None)

    with Image.open(tv.on_the_wall) as picture:
        assert picture.size == (3840, 2160)


async def test_the_frame_leaves_a_feeds_slot_alone_while_somebody_watches_television(
    settings, tv: FakeTv, state, wall_dir, clock
):
    """The schedule asks the set the same question the rotation does before it touches the wall."""
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    wall = frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())
    tv.art_mode = "off"
    publish_feed(wall_dir, [("f1", "08:00", "13:00")])

    await tick_until(wall.tick, lambda: composed(wall_dir, _sha("f1"), settings.geometry).is_file())
    await wall.tick()

    assert tv.selected == []


async def test_a_scene_a_wall_shows_is_in_its_heartbeat(screen, wall_dir, client_settings):
    """The UI shows which walls a scene has reached from this key (`player-contract.md` § Scenes)."""
    loop, output = screen
    document = publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    a_master(wall_dir / "media" / f"sha256-{_sha('f9')}")
    document["works"]["f9"] = {"media": {"url": "/m", "sha256": _sha("f9")}, "mat_color": MAT, "label": {"title": "f9"}}
    document["scene"] = {"id": "sc-1", "work_id": "f9", "from": "2026-06-21T11:00:00+00:00", "until": None}
    write_manifest(wall_dir, document)

    await tick_until(loop.tick, lambda: len(output.shown) == 1)
    await loop.tick()

    wall = client_settings.wall("living-room")
    assert json.loads(path_in(wall.heartbeat_root, "living-room").read_text())["scene_id"] == "sc-1"


def test_the_frame_says_it_is_a_frame(settings, tv, state, clock):
    """Not yet written (its screen is not this Player's to know), but read by the heartbeat as soon as it is."""
    display = FrameDisplay(settings=settings, tv=tv, state=state, clock=clock.as_clock())

    found = display.capabilities()

    assert (found.backend, found.screen, found.label_modes) == ("frame", None, ("none",))


async def test_a_wall_moved_to_a_feed_naming_the_work_already_up_shows_its_composition(
    screen, publish, wall_dir, clock, screen_geometry
):
    """The work's id is the same; the picture is not — major 1 put up the server's composed render."""
    loop, output = screen
    publish(["w1"], interval_seconds=60)
    await loop.tick()

    clock.advance(1.3)
    publish_feed(wall_dir, [("w1", "08:00", "18:00")])
    await tick_until(loop.tick, lambda: len(output.shown) == 2)

    assert output.shown == [wall_dir / "ready" / "w1.jpg", composed(wall_dir, _sha("w1"), screen_geometry)]


async def test_a_work_given_new_media_under_the_same_id_is_shown_again(screen, wall_dir, clock, screen_geometry):
    loop, output = screen
    document = publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    await tick_until(loop.tick, lambda: len(output.shown) == 1)

    clock.advance(1.3)
    new = "b" * 64
    a_master(wall_dir / "media" / f"sha256-{new}", colour=(30, 30, 200))
    document["works"]["f1"]["media"] = {"url": f"/media/sha256-{new}", "sha256": new}
    write_manifest(wall_dir, document)
    await tick_until(loop.tick, lambda: len(output.shown) == 2)

    assert output.shown == [composed(wall_dir, _sha("f1"), screen_geometry), composed(wall_dir, new, screen_geometry)]


async def test_a_screen_whose_mode_changes_is_composed_for_again(screen, wall_dir, client_settings):
    """The geometry is in the composition's key, so a new mode is a new picture."""
    loop, output = screen
    publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    await tick_until(loop.tick, lambda: len(output.shown) == 1)

    output.screen = (1280, 1024)
    await tick_until(loop.tick, lambda: len(output.shown) == 2)

    wall = client_settings.wall("living-room")
    assert output.shown[-1] == composed(wall_dir, _sha("f1"), wall.geometry_for((1280, 1024)))
    assert not output.shown[0].exists(), "the picture composed for the old mode was left behind"


async def test_a_feed_republished_with_the_same_work_up_leaves_the_wall_alone(screen, wall_dir, clock):
    """Only a switch of major tells a programme the wall holds another's picture; a new feed of its own major does not."""
    loop, output = screen
    document = publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    await tick_until(loop.tick, lambda: len(output.shown) == 1)

    clock.advance(1.3)
    document["generated_at"] = "2026-06-21T12:00:00+00:00"
    write_manifest(wall_dir, document)
    for _ in range(3):
        await loop.tick()

    assert len(output.shown) == 1


class ReadingOutput(RecordingOutput):
    """A screen that, like the real output, opens the picture it is showing whenever it draws it again."""

    def refresh(self) -> None:
        super().refresh()
        if self.shown:
            with Image.open(self.shown[-1]) as picture:
                picture.load()


async def test_a_mode_change_in_a_gap_keeps_the_picture_the_screen_is_showing(client_settings, wall_dir, clock):
    """In a gap nothing replaces the work on the wall, so its file must outlive the tidy a new mode owes."""
    wall = client_settings.wall("living-room")
    output = ReadingOutput()
    watcher = Watcher(wall.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    loop = screen_wall(wall=wall, output=output, watcher=watcher, clock=clock.as_clock())
    publish_feed(wall_dir, [("f1", "11:00", "12:01")])
    await tick_until(loop.tick, lambda: len(output.shown) == 1)

    clock.advance(90.3)
    output.screen = (1280, 1024)
    for _ in range(5):
        await loop.tick()

    assert output.shown[-1].is_file(), "the picture on the wall was removed while the screen still shows it"
    assert len(output.shown) == 1, "a gap put something new up"
    assert "refresh" not in (json.loads(path_in(wall.heartbeat_root, "living-room").read_text()).get("last_error") or "")
