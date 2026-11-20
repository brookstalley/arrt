"""What `DisplayService` guaranteed about the feeds before `FeedPublisher` was cut out of it, held after.

The feed publisher moved from `display.py` to `feeds.py` on 2026-11-19 (audit
wave 2, Chunk 20). A move keeps what the old arrangement guaranteed only if each
guarantee is checked where it now lives:

- **One subscriber reconciles each announcement.** The container subscribes the
  facade's `on_work_changed`, which reconciles through the publisher. A second
  subscription, or the publisher subscribing itself as well, would reconcile
  every announcement twice; none would reconcile nothing.
- **The feed's journal lines keep their logger.** A logger's name is what a
  reader of the journal filters on, so the lines `feeds.py` says are said under
  `arrt.programming.display`, as they were.

And the publisher's promises of audit wave 2b, Chunk 39:

- **A feed is never over the bound a Player reads** (`FEED_MAX_BYTES`, quoted
  from `contract/transport.json` through `arrt_contract`): the act asked for is
  refused whole and the wall keeps its feed; a heartbeat's roll, a reconcile of
  its own and a neighbour's rebuild pass the wall over; each says it once.
- **One instant per act**: a step, its schedule and every wall's scene layer
  are decided for one reading of the clock.
- **A neighbour that cannot be rebuilt is one the wall republished steps aside
  from**, whether it was refused before the wall was built, after, or at staging.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from arrt_contract import transport

from arrt.programming import feeds as feeds_module
from arrt.programming.feeds import FEED_MAX_BYTES, served_size
from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError

HOUR = 3600


@pytest.fixture
def reconciled(display, monkeypatch):
    """Each reconciliation the publisher runs, as the works it was asked about: the one place one runs."""
    asked: list[list[str] | None] = []
    reconcile = display._feeds.reconcile

    def counted(work_ids=None, **keywords):
        asked.append(None if work_ids is None else sorted(work_ids))
        return reconcile(work_ids, **keywords)

    monkeypatch.setattr(display._feeds, "reconcile", counted)
    return asked


def test_one_announcement_reconciles_once_through_the_publisher(services, ready_work, reconciled):
    first, second = ready_work(title="Nighthawks"), ready_work(title="Automat")
    reconciled.clear()

    services.catalogue.archive_artworks([first.id, second.id])

    assert reconciled == [sorted([first.id, second.id])]


def test_an_acceptance_is_reconciled_and_offered_its_theme_once(services, display, monkeypatch, reconciled):
    """The other half of the subscriber: an accepted work is offered once, after the one reconciliation."""
    offered: list[list[str]] = []
    monkeypatch.setattr(display, "offer_destinations", lambda work_ids: offered.append(list(work_ids)) or [])

    work = services.catalogue.add_artwork(title="Nighthawks")

    assert offered == [[work.id]]
    assert reconciled == [[work.id]]


def test_the_feed_s_lines_and_the_facade_s_are_said_under_one_logger(display, ready_work, wall_id, caplog):
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)

    with caplog.at_level(logging.INFO):
        display.activate_theme(theme.id, wall_id=wall_id)
        display.rename_wall(wall_id, name="The hall")

    published = [record for record in caplog.records if record.getMessage().startswith("Published the feed for wall")]
    renamed = [record for record in caplog.records if "is now called" in record.getMessage()]
    assert published, "the hang said nothing about its feed, so the logger was not read"
    assert renamed, "the rename said nothing, so the facade's logger was not read"
    assert {record.name for record in published + renamed} == {"arrt.programming.display"}


# -- helpers for the walls below ------------------------------------------------------


@pytest.fixture
def feed(wall_settings):
    def _feed(wall_id):
        return read_published(wall_settings.manifest_v2_path(wall_id))

    return _feed


@pytest.fixture
def themed(display, ready_work):
    """A theme of new works, in order, played in order at `interval` on the wall it is hung on."""

    def _themed(wall_id, *titles, name, interval=HOUR, works=None):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works if works is not None else [ready_work(title) for title in titles]):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        display.set_playback(wall_id, rotation_interval_seconds=interval, shuffle=False)
        display.activate_theme(theme.id, wall_id=wall_id)
        return theme

    return _themed


def _age(wall_settings, wall_id, *, by):
    """Move the published feed back in time, as if it had been published `by` ago."""
    path = wall_settings.manifest_v2_path(wall_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    for span in [document["schedule"]["horizon"], *document["schedule"]["slots"]]:
        for key in ("from", "until"):
            span[key] = (datetime.fromisoformat(span[key]) - by).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")


def _overlaps_after(one, other, now):
    """Slots of one feed after the one on the wall now that show a work the other shows at the same moment."""
    return [
        slot
        for slot in one.slots
        if not slot.covers(now) and any(s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) for s in other.slots)
    ]


def _over_bound_lines(caplog):
    return [record for record in caplog.records if getattr(record, "event", None) == "feed.over_bound"]


def _bound(monkeypatch, size):
    """The publisher's bound lowered to `size`, so a feed of a test's size can be over it."""
    monkeypatch.setattr(feeds_module, "FEED_MAX_BYTES", size, raising=False)


# -- the bound: a feed no Player would read is never published --------------------------


def test_the_bound_is_the_contracts():
    assert transport()["routes"]["manifest_major"]["max_bytes"] == FEED_MAX_BYTES


def test_a_feeds_size_is_measured_as_the_file_a_player_is_sent(display, ready_work, wall_id, wall_settings):
    """The measure and the writer spell the document alike: two-space indents, a closing newline, and UTF-8 unescaped."""
    theme = display.add_theme(name="Café Terrace — Arles")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work("Nuit étoilée").id)
    display.activate_theme(theme.id, wall_id=wall_id)
    sent = wall_settings.manifest_v2_path(wall_id).read_bytes()

    assert served_size(json.loads(sent)) == len(sent)


def test_an_act_whose_feed_would_be_over_the_bound_is_refused_whole_and_said_once(
    display, themed, wall_id, wall_settings, monkeypatch, caplog
):
    """Quickening the wall doubles its slots: refused, the feed and the wall's pace stay as they were, and it is said once."""
    themed(wall_id, "Nighthawks", "Automat", name="Late night")
    path = wall_settings.manifest_v2_path(wall_id)
    before = path.read_bytes()
    _bound(monkeypatch, len(before) + 64)

    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        for _ in range(2):
            with pytest.raises(ServiceError, match=r"bytes, past the .* a Player reads"):
                display.set_playback(wall_id, rotation_interval_seconds=HOUR // 2)

    assert path.read_bytes() == before
    assert display.get_wall(wall_id).rotation_interval_seconds == HOUR
    [line] = _over_bound_lines(caplog)
    assert (line.wall_id, line.max_bytes) == (wall_id, len(before) + 64)
    assert line.bytes > len(before) + 64


def test_a_wall_said_over_the_bound_is_said_again_after_a_feed_of_it_was_published(
    display, themed, wall_id, wall_settings, monkeypatch, caplog
):
    """Once per spell over the bound: a feed published in between ends the spell."""
    theme = themed(wall_id, "Nighthawks", "Automat", name="Late night")
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()
    _bound(monkeypatch, len(before) + 64)

    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        with pytest.raises(ServiceError):
            display.set_playback(wall_id, rotation_interval_seconds=HOUR // 2)
        display.activate_theme(theme.id, wall_id=wall_id)
        with pytest.raises(ServiceError):
            display.set_playback(wall_id, rotation_interval_seconds=HOUR // 2)

    assert len(_over_bound_lines(caplog)) == 2


def test_a_roll_over_the_bound_leaves_the_heartbeat_answered_and_the_feed_as_it_was(
    display, themed, wall_id, wall_settings, monkeypatch, caplog, a_player_shows_the_wall
):
    themed(wall_id, "Nighthawks", "Automat", name="Late night")
    _age(wall_settings, wall_id, by=timedelta(days=1, hours=1))
    path = wall_settings.manifest_v2_path(wall_id)
    aged = path.read_bytes()
    _bound(monkeypatch, 1024)

    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        for _ in range(2):
            display.record_heartbeat(
                wall_id,
                {"schema": {"major": 1, "minor": 1}, "reported_at": datetime.now(UTC).isoformat(), "current_work_id": None},
            )

    assert path.read_bytes() == aged
    assert len(_over_bound_lines(caplog)) == 1


def test_a_reconcile_of_its_own_passes_a_wall_over_the_bound_over_and_mends_the_rest(
    services, display, themed, wall_id, wall_settings, monkeypatch, caplog
):
    """A start and a scheduled pass: the hall, over the bound, keeps no feed; the study is mended; neither stops."""
    study = display.add_wall(name="Study").id
    themed(wall_id, "Nighthawks", "Automat", "Chop Suey", name="Late night")
    themed(study, "Gas", name="Roads")
    hall_path, study_path = (wall_settings.manifest_v2_path(wall) for wall in (wall_id, study))
    small = len(study_path.read_bytes())
    hall_path.unlink()
    study_path.unlink()
    _bound(monkeypatch, small + 64)

    with caplog.at_level(logging.INFO):
        started = display.reconcile()
        first = services.scheduler.run_pass()
        second = services.scheduler.run_pass()

    assert started.republished == (study,)
    assert (first["feeds"].started, second["feeds"].started) == (0, 0)
    assert not hall_path.exists()
    assert study_path.exists()
    assert [line.wall_id for line in _over_bound_lines(caplog)] == [wall_id]
    assert not [record for record in caplog.records if getattr(record, "event", None) == "scheduler.pass_failed"]


def test_a_neighbour_over_the_bound_keeps_its_feed_and_the_wall_acted_on_steps_aside_from_it(
    display, themed, ready_work, wall_id, wall_settings, feed, monkeypatch, caplog
):
    """The study, quicker, is rebuilt after the hall and refused at staging; the pass runs again and the hall steps aside from it.

    Built the first time, the hall counted the study by its slot now alone, as
    a wall that would step aside from it. Refused, the study goes on with its
    published slots, which show both of the works the two share in every hour;
    a hall built against only its slot now would show one of them beside it,
    slot after slot. Built against them whole, it shows its third work.
    """
    x, y, z = ready_work("X"), ready_work("Y"), ready_work("Z")
    study = display.add_wall(name="Study").id
    themed(study, works=[x, y], name="Study's", interval=HOUR // 2)
    _age(wall_settings, study, by=timedelta(seconds=97))
    hall = themed(wall_id, works=[x, y, z], name="Hall's", interval=HOUR)
    _age(wall_settings, study, by=timedelta(seconds=97))
    hall_size = len(wall_settings.manifest_v2_path(wall_id).read_bytes())
    study_before = wall_settings.manifest_v2_path(study).read_bytes()
    assert len(study_before) > hall_size + 2048, "the study's feed is not larger than the hall's, so no bound falls between"
    _bound(monkeypatch, hall_size + 1024)

    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        display.activate_theme(hall.id, wall_id=wall_id)

    assert wall_settings.manifest_v2_path(study).read_bytes() == study_before
    assert [line.wall_id for line in _over_bound_lines(caplog)] == [study]
    assert any("Study" in r.getMessage() and "could not be rebuilt" in r.getMessage() for r in caplog.records)
    assert _overlaps_after(feed(wall_id), feed(study), datetime.now(UTC)) == []


def test_a_neighbour_at_the_walls_pace_that_cannot_be_rebuilt_is_stepped_aside_from(
    display, themed, ready_work, wall_id, wall_settings, feed, monkeypatch, caplog
):
    """The study is at the hall's pace, so it is built after the hall; refused, it keeps its slots, and the hall steps aside.

    The case Chunk 43 left: its fix lines the hall up with a slower wall
    refused before it, and a wall built after the hall was counted by its slot
    now alone, as one that would step aside. Refused, it does not, so the pass
    runs again without it and the hall is built against its whole schedule.
    """
    x, y = ready_work("X"), ready_work("Y")
    study = display.add_wall(name="Study").id
    themed(study, works=[x, y], name="Study's", interval=HOUR)
    _age(wall_settings, study, by=timedelta(seconds=97))
    before = feed(study).slots
    hall = display.add_theme(name="Hall's")
    for position, work in enumerate([x, y]):
        display.add_to_theme(theme_id=hall.id, artwork_id=work.id, position=position)
    display.set_playback(wall_id, rotation_interval_seconds=HOUR, shuffle=False)
    built = display._feeds.build_manifest

    def refusing(wall, theme_id=None):
        if wall == study:
            raise ServiceError("the study's theme cannot be read")
        return built(wall, theme_id)

    monkeypatch.setattr(display._feeds, "build_manifest", refusing)
    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        display.activate_theme(hall.id, wall_id=wall_id)

    assert feed(wall_id).playlist_id == hall.id
    assert feed(study).slots == before
    said = [r for r in caplog.records if "Study" in r.getMessage() and "could not be rebuilt" in r.getMessage()]
    assert len(said) == 1, "the study's refusal was said once per run of the pass, not once"
    assert _overlaps_after(feed(wall_id), feed(study), datetime.now(UTC)) == []


# -- one instant per act ---------------------------------------------------------------


def test_a_step_moves_on_from_the_work_on_the_wall_at_the_instant_its_feed_starts(display, themed, wall_id, feed, monkeypatch):
    """Next chooses the work after the one up now, and schedules from the same now.

    The clock here reads now once and, at every later reading, just past the
    end of the slot on the wall: a slow act's second reading. Read twice, the
    step chose the work after the first slot and started the new feed inside
    the second, where that work was already up, so the wall did not move on.
    """
    themed(wall_id, "A", "B", "C", name="Alphabet")
    old = feed(wall_id)
    up = old.on_the_wall(datetime.now(UTC))
    jump = up.until - datetime.now(UTC) + timedelta(seconds=1)
    readings: list[None] = []

    class Jumping(datetime):
        @classmethod
        def now(cls, tz=None):
            readings.append(None)
            real = datetime.now(tz)
            return real if len(readings) == 1 else real + jump

    monkeypatch.setattr(feeds_module, "datetime", Jumping)

    shown = display.step_display(wall_id)

    new = feed(wall_id)
    assert new.slots[0].work_id == shown
    assert old.on_the_wall(new.slots[0].start).work_id != shown, "the step put up the work already on the wall"


def test_every_wall_of_an_act_has_its_scene_layer_decided_for_the_acts_one_instant(
    display, themed, ready_work, wall_id, monkeypatch
):
    """Each wall's scene layer and each schedule of one act read one now, however slowly the act runs."""
    x, y = ready_work("X"), ready_work("Y")
    study = display.add_wall(name="Study").id
    themed(study, works=[x, y], name="Study's", interval=HOUR)
    themed(wall_id, works=[x, y], name="Hall's", interval=HOUR // 2)
    readings: list[None] = []

    class Slow(datetime):
        @classmethod
        def now(cls, tz=None):
            readings.append(None)
            return datetime.now(tz) + timedelta(seconds=len(readings))

    seen: list[tuple[str, str, datetime]] = []
    pins, build = display._feeds._control_pins, feeds_module.build_schedule

    def recording_pins(wall, now):
        seen.append(("scene layer", wall, now))
        return pins(wall, now)

    def recording_build(**arguments):
        seen.append(("schedule", arguments["wall_id"], arguments["now"]))
        return build(**arguments)

    monkeypatch.setattr(feeds_module, "datetime", Slow)
    monkeypatch.setattr(display._feeds, "_control_pins", recording_pins)
    monkeypatch.setattr(feeds_module, "build_schedule", recording_build)

    display.show_work_now(wall_id, x.id)

    assert {(kind, wall) for kind, wall, _ in seen} >= {
        ("scene layer", wall_id),
        ("scene layer", study),
        ("schedule", wall_id),
        ("schedule", study),
    }
    assert len({now for _, _, now in seen}) == 1, seen
