"""A wall reads both majors, and a new document of the other major switches it without a restart.

Driven through both real drivers (the Frame over its television double, a
screen over a recording output), because the switch lives in the shared loop
and each display remembers what is on the wall in its own way.
"""

import random

import pytest
from conftest import write_manifest
from fakes import FakeTv, RecordingOutput

from arrt_player.displays.frame import frame_wall
from arrt_player.displays.screen import screen_wall
from arrt_player.manifest import Watcher


def _sha(work_id: str) -> str:
    return (work_id.encode().hex() * 64)[:64]


def publish_feed(wall_dir, slots: list[tuple[str, str, str]]) -> dict:
    """Cache a one-day major 2 feed on the test clock's day, with every master in the media cache."""
    (wall_dir / "media").mkdir(exist_ok=True)
    works = {}
    for work, _, _ in slots:
        (wall_dir / "media" / f"sha256-{_sha(work)}").write_bytes(f"the master of {work}".encode())
        works[work] = {
            "media": {"url": f"/media/sha256-{_sha(work)}", "sha256": _sha(work)},
            "mat_color": "#222",
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


async def test_a_screen_switches_from_major_1_to_a_feed_and_back(screen, publish, wall_dir, clock):
    wall, output = screen
    publish(["w1", "w2"], interval_seconds=60)
    await wall.tick()
    assert [path.stem for path in output.shown] == ["w1"]

    clock.advance(1.3)
    publish_feed(wall_dir, [("f1", "08:00", "18:00")])
    await wall.tick()
    assert output.shown[-1].name == f"sha256-{_sha('f1')}", "the feed's slot was not shown"

    clock.advance(1.3)
    publish(["w1", "w2"], interval_seconds=60)
    await wall.tick()
    clock.advance(60.4)
    await wall.tick()
    # The feed's work is on the wall and the theme does not carry it, so the
    # rotation starts from the top when its interval is up, as for any new theme.
    assert [path.stem for path in output.shown[2:]] == ["w1"], "major 1's rotation did not take the wall back"


async def test_the_frame_shows_a_feeds_slot_and_then_the_next(settings, tv: FakeTv, state, wall_dir, clock):
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    wall = frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())
    publish_feed(wall_dir, [("f1", "08:00", "13:00"), ("f2", "13:00", "18:00")])

    await wall.tick()
    assert tv.on_the_wall.name == f"sha256-{_sha('f1')}"
    assert state.last_selected_work_id == "f1"

    clock.advance(3600.4)
    await wall.tick()
    assert tv.on_the_wall.name == f"sha256-{_sha('f2')}"


async def test_the_frame_leaves_a_feeds_slot_alone_while_somebody_watches_television(
    settings, tv: FakeTv, state, wall_dir, clock
):
    """The schedule asks the set the same question the rotation does before it touches the wall."""
    watcher = Watcher(settings.manifest_path, rotation_interval_fallback=180, shuffle_fallback=False)
    wall = frame_wall(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())
    tv.art_mode = "off"
    publish_feed(wall_dir, [("f1", "08:00", "13:00")])

    await wall.tick()

    assert tv.selected == []
