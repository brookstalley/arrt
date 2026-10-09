"""Major 2's programme: what the feed says to show, and when the wall may be changed to it.

`contract/vectors/schedule.json` holds the rule itself (`what_to_show`), and
every Player's suite runs it; the rest drives the programme against a display
double that records what it is asked, in order, because the order is the
guard: the display's own wait first, then whether the wall is ours, and only
then a picture.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from conftest import WALL_ID

from arrt_player.manifest import Feed, parse
from arrt_player.programmes.rotation import InMemory
from arrt_player.programmes.schedule import RETRY_SECONDS, Schedule, what_to_show
from arrt_player.wall import DisplayRecord, Picture, Shown

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
VECTORS = json.loads((CONTRACT / "vectors" / "schedule.json").read_text(encoding="utf-8"))


def _feed(document: dict) -> Feed:
    feed = parse(json.dumps(document), rotation_interval_fallback=180, shuffle_fallback=False)
    assert isinstance(feed, Feed)
    return feed


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda vector: vector["name"])
def test_each_schedule_vector_is_what_this_player_shows(vector):
    feed = _feed(VECTORS["feeds"][vector["feed"]])

    showing = what_to_show(feed, datetime.fromisoformat(vector["now"]))

    assert {"work_id": showing.work_id, "scene_id": showing.scene_id} == vector["expect"]


# -- the programme ----------------------------------------------------------------


def _sha(work_id: str) -> str:
    return (work_id.encode().hex() * 64)[:64]


def feed_document(*, slots: list[tuple[str, str, str]], scene: dict | None = None, staging: Sequence[str] = ()) -> dict:
    """A one-day feed on the test clock's day; each slot is (work, from, until) as HH:MM UTC."""
    named = {work for work, _, _ in slots} | set(staging) | ({scene["work_id"]} if scene else set())
    return {
        "schema": {"major": 2, "minor": 0},
        "generated_at": "2026-06-21T00:00:00+00:00",
        "playlist": {"id": "pl-1", "name": "A playlist"},
        "works": {
            work: {
                "media": {"url": f"/media/sha256-{_sha(work)}", "sha256": _sha(work)},
                "mat_color": "#222222",
                "label": {"title": f"Work {work}"},
            }
            for work in sorted(named)
        },
        "schedule": {
            "horizon": {"from": "2026-06-21T00:00:00+00:00", "until": "2026-06-22T00:00:00+00:00"},
            "slots": [
                {"work_id": work, "from": f"2026-06-21T{start}:00+00:00", "until": f"2026-06-21T{until}:00+00:00"}
                for work, start, until in slots
            ],
        },
        "scene": scene,
        "staging": list(staging),
    }


class GateDisplay:
    """Records every question and request, in order; refuses when told to."""

    def __init__(self, clock) -> None:
        self.record = DisplayRecord(clock, wall_id=WALL_ID)
        self.asked: list[str] = []
        self.waiting = False
        self.ours = True
        self.outcome = Shown.YES

    def may_attempt(self) -> bool:
        self.asked.append("may_attempt")
        return not self.waiting

    async def is_ours(self) -> bool:
        self.asked.append("is_ours")
        return self.ours

    async def show(self, picture: Picture) -> Shown:
        self.asked.append(f"show:{picture.work_id}")
        return self.outcome

    def shown(self) -> list[str]:
        return [entry.removeprefix("show:") for entry in self.asked if entry.startswith("show:")]


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    (tmp_path / "media").mkdir()
    return tmp_path


def cache(media_root: Path, *works: str) -> None:
    for work in works:
        (media_root / "media" / f"sha256-{_sha(work)}").write_bytes(b"a master")


@pytest.fixture
def memory() -> InMemory:
    return InMemory()


@pytest.fixture
def schedule(media_root, memory, clock) -> Schedule:
    return Schedule(wall_id=WALL_ID, render_root=media_root, memory=memory, clock=clock.as_clock())


@pytest.fixture
def display(clock) -> GateDisplay:
    return GateDisplay(clock.as_clock())


async def test_it_shows_the_slots_work_once_and_the_next_slots_when_it_begins(schedule, display, media_root, clock, memory):
    cache(media_root, "w1", "w2")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00"), ("w2", "13:00", "18:00")])))

    await schedule.step(display)
    await schedule.step(display)
    assert display.shown() == ["w1"], "the work already on the wall was shown again"

    clock.advance(3599.7)
    await schedule.step(display)
    assert display.shown() == ["w1"], "the next slot began before its time"

    clock.advance(0.6)
    await schedule.step(display)
    assert display.shown() == ["w1", "w2"]
    assert memory.last_selected_work_id == "w2"


async def test_the_wall_is_asked_in_order_and_a_wall_not_ours_is_left_alone(schedule, display, media_root):
    """The display's own wait first, which costs nothing; then whether the wall is ours; only then a picture."""
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    display.waiting = True
    await schedule.step(display)
    assert display.asked == ["may_attempt"], "the set was asked while the wall's wait was running"

    display.waiting, display.ours = False, False
    await schedule.step(display)
    assert display.asked == ["may_attempt", "may_attempt", "is_ours"], "a wall that is not ours was changed"

    display.ours = True
    await schedule.step(display)
    assert display.asked[-3:] == ["may_attempt", "is_ours", "show:w1"]


async def test_a_gap_keeps_the_last_work_on_the_wall(schedule, display, media_root, clock, memory):
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await schedule.step(display)

    clock.advance(2 * 3600.3)
    await schedule.step(display)

    assert display.shown() == ["w1"]
    assert memory.last_selected_work_id == "w1"
    assert display.asked == ["may_attempt", "is_ours", "show:w1"], "the gap asked the set anything"


async def test_a_scene_wins_while_it_lasts_and_the_wall_returns_to_its_slot(schedule, display, media_root, clock):
    cache(media_root, "w1", "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], scene=scene)))

    await schedule.step(display)
    assert display.shown() == ["w9"]
    assert schedule.scene_id == "sc-1"

    clock.advance(20 * 60.3)
    await schedule.step(display)
    assert display.shown() == ["w9", "w1"]
    assert schedule.scene_id is None


async def test_a_work_whose_media_is_not_cached_waits_for_it_and_is_said_once(schedule, display, media_root, caplog):
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    for _ in range(3):
        await schedule.step(display)
    assert display.asked == [], "the wall was asked to change for media it does not have"
    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.media_missing") == 1

    cache(media_root, "w1")
    await schedule.step(display)
    assert display.shown() == ["w1"]


async def test_a_work_the_display_refused_is_left_a_while_before_it_is_tried_again(schedule, display, media_root, clock):
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    display.outcome = Shown.SKIP

    await schedule.step(display)
    clock.advance(RETRY_SECONDS - 0.7)
    await schedule.step(display)
    assert display.shown() == ["w1"], "a refused work was asked for again on the next pass"

    clock.advance(1.3)
    await schedule.step(display)
    assert display.shown() == ["w1", "w1"]


async def test_a_new_feed_lets_a_refused_work_be_tried_at_once(schedule, display, media_root, clock):
    cache(media_root, "w1")
    document = feed_document(slots=[("w1", "08:00", "13:00")])
    schedule.adopt(_feed(document))
    display.outcome = Shown.SKIP
    await schedule.step(display)

    clock.advance(1.3)
    schedule.adopt(_feed(document))
    await schedule.step(display)

    assert display.shown() == ["w1", "w1"]


def test_the_pictures_are_every_work_the_feed_names_staging_included(schedule, media_root):
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00"), ("w2", "13:00", "14:00")], staging=["w7"])))

    assert [(picture.work_id, picture.path) for picture in schedule.pictures] == [
        (work, media_root / "media" / f"sha256-{_sha(work)}") for work in ("w1", "w2", "w7")
    ]


async def test_a_scene_that_ends_into_a_gap_is_over_though_its_work_stays_up(schedule, display, media_root, clock):
    """The work stays (the gap cannot act yet); the scene does not, because nothing is overriding the schedule now."""
    cache(media_root, "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "09:00")], scene=scene)))
    await schedule.step(display)
    assert schedule.scene_id == "sc-1"

    clock.advance(20 * 60.3)
    await schedule.step(display)

    assert display.shown() == ["w9"]
    assert schedule.scene_id is None


async def test_a_scene_that_ends_into_a_slot_not_yet_showable_is_over(schedule, display, media_root, clock):
    cache(media_root, "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], scene=scene)))
    await schedule.step(display)

    clock.advance(20 * 60.3)
    await schedule.step(display)

    assert display.shown() == ["w9"], "w1's media is not cached, so w9 stays up"
    assert schedule.scene_id is None
