"""Major 2's programme: what the feed says to show, and when the wall may be changed to it.

`contract/vectors/schedule.json` holds the rule itself (`what_to_show`), and
every Player's suite runs it; the rest drives the programme against a display
double that records what it is asked, in order, because the order is the
guard: the display's own wait first, then whether the wall is ours, and only
then a picture.
"""

import asyncio
import json
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from conftest import WALL_ID, a_master

from arrt_player.compose import Geometry, Uncomposable, compose, composition_key
from arrt_player.manifest import Feed, parse
from arrt_player.programmes.schedule import COMPOSE_RETRY_SECONDS, RETRY_SECONDS, InMemory, Schedule, what_to_show
from arrt_player.wall import DisplayRecord, Picture, Shown

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
VECTORS = json.loads((CONTRACT / "vectors" / "schedule.json").read_text(encoding="utf-8"))


def _feed(document: dict) -> Feed:
    feed = parse(json.dumps(document))
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


#: A small screen with no density, so composing is quick.
GEOMETRY = Geometry(screen=(160, 90), pixels_per_inch=None, mat_width_inches=1.5, bottom_weight=1.15)


def cache(media_root: Path, *works: str) -> None:
    for work in works:
        a_master(media_root / "media" / f"sha256-{_sha(work)}")


def composed(media_root: Path, work: str, *, mode: str = "proportional", geometry: Geometry = GEOMETRY) -> Path:
    key = composition_key(master_sha256=_sha(work), mat_color="#222222", mode=mode, geometry=geometry)
    return media_root / "composed" / f"{key}.jpg"


async def step(schedule: Schedule, display) -> None:
    """One pass, with every composition owed finished first, so a test reads what the wall shows once composing is done."""
    await schedule.settle()
    await schedule.step(display)


@pytest.fixture
def memory() -> InMemory:
    return InMemory()


@pytest.fixture
def schedule(media_root, memory, clock) -> Schedule:
    return Schedule(
        wall_id=WALL_ID,
        render_root=media_root,
        composed_root=media_root / "composed",
        geometry=lambda: GEOMETRY,
        memory=memory,
        clock=clock.as_clock(),
    )


@pytest.fixture
def display(clock) -> GateDisplay:
    return GateDisplay(clock.as_clock())


async def test_it_shows_the_slots_work_once_and_the_next_slots_when_it_begins(schedule, display, media_root, clock, memory):
    cache(media_root, "w1", "w2")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00"), ("w2", "13:00", "18:00")])))

    await step(schedule, display)
    await step(schedule, display)
    assert display.shown() == ["w1"], "the work already on the wall was shown again"

    clock.advance(3599.7)
    await step(schedule, display)
    assert display.shown() == ["w1"], "the next slot began before its time"

    clock.advance(0.6)
    await step(schedule, display)
    assert display.shown() == ["w1", "w2"]
    assert memory.last_selected_work_id == "w2"


async def test_the_wall_is_asked_in_order_and_a_wall_not_ours_is_left_alone(schedule, display, media_root):
    """The display's own wait first, which costs nothing; then whether the wall is ours; only then a picture."""
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    display.waiting = True
    await step(schedule, display)
    assert display.asked == ["may_attempt"], "the set was asked while the wall's wait was running"

    display.waiting, display.ours = False, False
    await step(schedule, display)
    assert display.asked == ["may_attempt", "may_attempt", "is_ours"], "a wall that is not ours was changed"

    display.ours = True
    await step(schedule, display)
    assert display.asked[-3:] == ["may_attempt", "is_ours", "show:w1"]


async def test_a_gap_keeps_the_last_work_on_the_wall(schedule, display, media_root, clock, memory):
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)

    clock.advance(2 * 3600.3)
    await step(schedule, display)

    assert display.shown() == ["w1"]
    assert memory.last_selected_work_id == "w1"
    assert display.asked == ["may_attempt", "is_ours", "show:w1"], "the gap asked the set anything"


async def test_an_empty_feed_keeps_the_last_work_on_the_wall(schedule, display, media_root, clock, memory):
    """What a theme with nothing it can send publishes: no works, no slots. The wall
    keeps its picture, as through any gap, rather than going dark or asking the set."""
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)

    schedule.adopt(_feed(feed_document(slots=[])))
    clock.advance(60.3)
    await step(schedule, display)

    assert display.shown() == ["w1"]
    assert memory.last_selected_work_id == "w1"
    assert display.asked == ["may_attempt", "is_ours", "show:w1"], "the empty feed asked the set anything"


async def test_a_scene_wins_while_it_lasts_and_the_wall_returns_to_its_slot(schedule, display, media_root, clock):
    cache(media_root, "w1", "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], scene=scene)))

    await step(schedule, display)
    assert display.shown() == ["w9"]
    assert schedule.scene_id == "sc-1"

    clock.advance(20 * 60.3)
    await step(schedule, display)
    assert display.shown() == ["w9", "w1"]
    assert schedule.scene_id is None


async def test_a_work_whose_media_is_not_cached_waits_for_it_and_is_said_once(schedule, display, media_root, caplog):
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    for _ in range(3):
        await step(schedule, display)
    assert display.asked == [], "the wall was asked to change for media it does not have"
    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.media_missing") == 1

    cache(media_root, "w1")
    await step(schedule, display)
    assert display.shown() == ["w1"]


async def test_a_work_the_display_refused_is_left_a_while_before_it_is_tried_again(schedule, display, media_root, clock):
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    display.outcome = Shown.SKIP

    await step(schedule, display)
    clock.advance(RETRY_SECONDS - 0.7)
    await step(schedule, display)
    assert display.shown() == ["w1"], "a refused work was asked for again on the next pass"

    clock.advance(1.3)
    await step(schedule, display)
    assert display.shown() == ["w1", "w1"]


async def test_a_new_feed_lets_a_refused_work_be_tried_at_once(schedule, display, media_root, clock):
    cache(media_root, "w1")
    document = feed_document(slots=[("w1", "08:00", "13:00")])
    schedule.adopt(_feed(document))
    display.outcome = Shown.SKIP
    await step(schedule, display)

    clock.advance(1.3)
    schedule.adopt(_feed(document))
    await step(schedule, display)

    assert display.shown() == ["w1", "w1"]


def test_the_pictures_are_every_work_the_feed_names_staging_included(schedule, media_root):
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00"), ("w2", "13:00", "14:00")], staging=["w7"])))

    assert [(picture.work_id, picture.path) for picture in schedule.pictures] == [
        (work, composed(media_root, work)) for work in ("w1", "w2", "w7")
    ], "each as the file it composes to, so a display can prepare it before it exists"


async def test_a_scene_that_ends_into_a_gap_is_over_though_its_work_stays_up(schedule, display, media_root, clock):
    """The work stays (the gap cannot act yet); the scene does not, because nothing is overriding the schedule now."""
    cache(media_root, "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "09:00")], scene=scene)))
    await step(schedule, display)
    assert schedule.scene_id == "sc-1"

    clock.advance(20 * 60.3)
    await step(schedule, display)

    assert display.shown() == ["w9"]
    assert schedule.scene_id is None


async def test_a_scene_that_ends_into_a_slot_not_yet_showable_is_over(schedule, display, media_root, clock):
    cache(media_root, "w9")
    scene = {"id": "sc-1", "work_id": "w9", "from": "2026-06-21T11:30:00+00:00", "until": "2026-06-21T12:20:00+00:00"}
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], scene=scene)))
    await step(schedule, display)

    clock.advance(20 * 60.3)
    await step(schedule, display)

    assert display.shown() == ["w9"], "w1's media is not cached, so w9 stays up"
    assert schedule.scene_id is None


# -- composing ------------------------------------------------------------------


def a_schedule(media_root, memory, clock, *, composer=None, geometry=lambda: GEOMETRY) -> Schedule:
    extra = {} if composer is None else {"composer": composer}
    return Schedule(
        wall_id=WALL_ID,
        render_root=media_root,
        composed_root=media_root / "composed",
        geometry=geometry,
        memory=memory,
        clock=clock.as_clock(),
        **extra,
    )


async def test_a_slow_composition_never_holds_up_the_pass(media_root, memory, clock, display):
    """A compose is seconds on a Pi; the pass that starts one returns at once and the next one shows it."""
    release = threading.Event()

    def slow(*args, **kwargs):
        assert release.wait(5), "the test never released the composition"
        return compose(*args, **kwargs)

    schedule = a_schedule(media_root, memory, clock, composer=slow)
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    await asyncio.wait_for(schedule.step(display), timeout=1)
    await asyncio.wait_for(schedule.step(display), timeout=1)
    assert display.asked == [], "the wall was asked to change before its picture existed"

    release.set()
    await schedule.settle()
    await schedule.step(display)
    assert display.shown() == ["w1"]


async def test_the_slots_work_is_composed_before_the_rest(media_root, memory, clock):
    order: list[str] = []

    def recording(master, **kwargs):
        order.append(master.name)
        return compose(master, **kwargs)

    schedule = a_schedule(media_root, memory, clock, composer=recording)
    cache(media_root, "w1", "w2", "w3")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "10:00"), ("w2", "10:00", "13:00"), ("w3", "13:00", "14:00")])))

    await schedule.step(GateDisplay(clock.as_clock()))
    await schedule.settle()

    assert order[0] == f"sha256-{_sha('w2')}", "the work the wall needs now waited behind the others"
    assert sorted(order) == sorted(f"sha256-{_sha(work)}" for work in ("w1", "w2", "w3"))


async def test_a_staged_work_is_composed_ahead_and_never_shown(schedule, display, media_root):
    cache(media_root, "w1", "w7")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], staging=["w7"])))

    await step(schedule, display)

    assert composed(media_root, "w7").is_file()
    assert display.shown() == ["w1"]


@pytest.mark.parametrize(
    ("settings", "drawn"),
    [
        ({"mat": {"mode": "full"}}, "full"),
        ({"mat": {"mode": "none"}}, "none"),
        ({}, "proportional"),
        ({"mat": {"mode": "floating"}}, "proportional"),
        ({"mat": "full"}, "proportional"),
    ],
)
async def test_the_feeds_mat_mode_is_drawn_and_one_this_player_does_not_know_is_the_default(
    schedule, display, media_root, settings, drawn
):
    cache(media_root, "w1")
    document = feed_document(slots=[("w1", "08:00", "13:00")])
    document["settings"] = settings
    schedule.adopt(_feed(document))

    await step(schedule, display)

    assert [picture.path for picture in schedule.pictures] == [composed(media_root, "w1", mode=drawn)]
    assert composed(media_root, "w1", mode=drawn).is_file()


async def test_a_master_that_will_not_decode_costs_its_work_and_is_said_once(schedule, display, media_root, clock, caplog):
    (media_root / "media" / f"sha256-{_sha('w1')}").write_bytes(b"not a picture")
    cache(media_root, "w2")
    document = feed_document(slots=[("w1", "08:00", "13:00")], staging=["w2"])
    schedule.adopt(_feed(document))

    for _ in range(3):
        clock.advance(400.3)
        await step(schedule, display)

    assert display.asked == []
    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.uncomposable") == 1
    assert composed(media_root, "w2").is_file(), "one bad master held up the rest"


async def test_a_picture_that_could_not_be_written_is_tried_again_later(media_root, memory, clock, display, caplog):
    attempts: list[int] = []

    def full_twice(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= 2:
            raise OSError(28, "No space left on device")
        return compose(*args, **kwargs)

    schedule = a_schedule(media_root, memory, clock, composer=full_twice)
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    await step(schedule, display)
    clock.advance(COMPOSE_RETRY_SECONDS - 0.7)
    await step(schedule, display)
    assert (len(attempts), display.shown()) == (1, []), "a failed write was retried on the next pass"

    clock.advance(1.3)
    await step(schedule, display)
    assert (len(attempts), display.shown()) == (2, []), "the failed write was not tried again after its wait"
    assert [record.__dict__.get("event") for record in caplog.records].count(
        "schedule.compose_write_failed"
    ) == 1, "a write failing again was said again"

    clock.advance(COMPOSE_RETRY_SECONDS + 0.3)
    await step(schedule, display)
    assert display.shown() == ["w1"]


async def test_a_new_feed_lets_an_undecodable_master_be_tried_again(media_root, memory, clock, display):
    """Its bytes may be new: a feed is news."""
    attempts: list[int] = []

    def refusing(*args, **kwargs):
        attempts.append(1)
        raise Uncomposable("no")

    schedule = a_schedule(media_root, memory, clock, composer=refusing)
    cache(media_root, "w1")
    document = feed_document(slots=[("w1", "08:00", "13:00")])
    schedule.adopt(_feed(document))
    await step(schedule, display)
    clock.advance(COMPOSE_RETRY_SECONDS + 0.3)
    await step(schedule, display)
    assert len(attempts) == 1, "the same bytes were decoded again, which cannot go differently"

    schedule.adopt(_feed(document))
    await step(schedule, display)
    assert len(attempts) == 2


async def test_pictures_no_work_composes_to_are_removed_and_so_is_a_half_written_one(schedule, display, media_root):
    cache(media_root, "w1", "w2")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], staging=["w2"])))
    await step(schedule, display)
    leftover = media_root / "composed" / "deadbeef.jpg.composing"
    leftover.write_bytes(b"half a picture")

    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)

    assert sorted(path.name for path in (media_root / "composed").iterdir()) == [composed(media_root, "w1").name]


async def test_with_no_screen_nothing_is_composed_or_shown(media_root, memory, clock, display):
    schedule = a_schedule(media_root, memory, clock, geometry=lambda: None)
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    await step(schedule, display)

    assert schedule.pictures == ()
    assert display.asked == []
    assert not (media_root / "composed").exists()


async def test_a_programme_switched_to_puts_its_own_picture_up_though_the_wall_names_the_work(
    schedule, display, media_root, memory
):
    """The other major put its own picture of this work up meanwhile."""
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)
    await step(schedule, display)
    assert display.shown() == ["w1"]

    memory.set_last_selected_work_id("w1")
    schedule.entered()
    await step(schedule, display)

    assert display.shown() == ["w1", "w1"]


async def test_a_work_already_composed_is_not_handed_to_the_compositor_again(media_root, memory, clock, display):
    calls: list[str] = []

    def counting(master, **kwargs):
        calls.append(master.name)
        return compose(master, **kwargs)

    schedule = a_schedule(media_root, memory, clock, composer=counting)
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)

    for _ in range(3):
        clock.advance(1.3)
        await step(schedule, display)

    assert calls == [f"sha256-{_sha('w1')}"]


async def test_the_picture_a_new_one_replaced_is_removed_once_it_is_down(media_root, memory, clock, display):
    geometry = {"now": GEOMETRY}
    schedule = a_schedule(media_root, memory, clock, geometry=lambda: geometry["now"])
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)
    first = composed(media_root, "w1")

    geometry["now"] = Geometry(screen=(200, 100), pixels_per_inch=None, mat_width_inches=1.5, bottom_weight=1.15)
    await schedule.settle()
    assert first.is_file(), "taken by the tidy before its replacement was up"
    await schedule.step(display)

    assert display.shown() == ["w1", "w1"]
    assert not first.exists(), "the picture no work composes to any more was left behind"


async def test_a_composed_directory_that_cannot_be_read_costs_the_tidy_and_never_the_wall(schedule, display, media_root, caplog):
    cache(media_root, "w1")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
    await step(schedule, display)
    (media_root / "composed" / "a-directory").mkdir()
    (media_root / "composed").chmod(0o300)
    try:
        for _ in range(2):
            schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))
            await step(schedule, display)
    finally:
        (media_root / "composed").chmod(0o700)

    assert [record.__dict__.get("event") for record in caplog.records].count("schedule.tidy_failed") == 1
    assert (media_root / "composed" / "a-directory").is_dir(), "the tidy removes files, never a directory"


async def test_a_directory_inside_the_composed_one_is_left_alone(schedule, display, media_root, caplog):
    """Passed over as not a picture, not tried and reported as a failure to remove."""
    cache(media_root, "w1")
    (media_root / "composed" / "a-directory").mkdir(parents=True)
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")])))

    await step(schedule, display)

    assert (media_root / "composed" / "a-directory").is_dir()
    assert display.shown() == ["w1"]
    assert "schedule.tidy_failed" not in [record.__dict__.get("event") for record in caplog.records]


async def test_every_line_a_composition_logs_names_its_work(schedule, display, media_root, caplog):
    """`observability-strategy.md` § Correlation: a work's journal is one filter on its id, the thread's lines included."""
    from arrt_player.logs import WorkCorrelationFilter

    caplog.handler.addFilter(WorkCorrelationFilter())
    caplog.set_level("INFO")
    cache(media_root, "w1")
    (media_root / "media" / f"sha256-{_sha('w2')}").write_bytes(b"not a picture")
    schedule.adopt(_feed(feed_document(slots=[("w1", "08:00", "13:00")], staging=["w2"])))

    await step(schedule, display)

    by_event = {record.__dict__.get("event"): getattr(record, "work_id", None) for record in caplog.records}
    assert by_event["compose.done"] == "w1"
    assert by_event["schedule.uncomposable"] == "w2"
