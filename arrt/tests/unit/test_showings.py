"""What each wall has shown: the rules that turn reports into showings, the store, and the heartbeat that feeds it.

`programming/showings.py` states the rules. The first half here drives
`advance` with one report at a time; the second drives `record_heartbeat`, the
one caller, against a real catalogue file and a published feed, because a rule
the caller never reaches is a rule nothing keeps.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from arrt.persistence.errors import StorageError
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import Showing
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.programming.display_state import ReportedState, ScreenState
from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS
from arrt.programming.manifest.v2 import read_published
from arrt.programming.showings import advance
from arrt.services.errors import ServiceError

WALL = "wall-hall"
T0 = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)
#: Not a multiple of anything under test, so a step can't land on a boundary by luck.
MINUTE = timedelta(seconds=61)
STALE = timedelta(seconds=STALE_AFTER_SECONDS)


def _showing(work_id="dali", *, started=T0, seen=None, ended=None):
    return Showing(wall_id=WALL, work_id=work_id, started_at=started, last_seen_at=seen or started, ended_at=ended)


def _art(work_id, since=None):
    return ReportedState(state=ScreenState.SHOWING_ART, work_id=work_id, since=since)


def _advance(latest, reported, at, playable=("dali", "magritte")):
    return list(advance(latest, reported, wall_id=WALL, at=at, playable=frozenset(playable)))


# -- minor 3: a showing is its `since` -------------------------------------------------


def test_a_first_report_begins_a_showing_at_its_since():
    assert _advance(None, _art("dali", since=T0), T0 + MINUTE) == [_showing(started=T0, seen=T0 + MINUTE)]


def test_a_report_resent_with_the_same_since_extends_its_showing_rather_than_adding_one():
    open_ = _showing(started=T0, seen=T0 + MINUTE)

    assert _advance(open_, _art("dali", since=T0), T0 + 2 * MINUTE) == [_showing(started=T0, seen=T0 + 2 * MINUTE)]


def test_a_new_work_ends_the_open_showing_at_its_since_and_begins_another():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    changed = T0 + MINUTE + timedelta(seconds=7)

    assert _advance(open_, _art("magritte", since=changed), T0 + 2 * MINUTE) == [
        _showing(started=T0, seen=T0 + MINUTE, ended=changed),
        _showing("magritte", started=changed, seen=T0 + 2 * MINUTE),
    ]


def test_the_same_work_shown_again_with_a_new_since_is_a_second_showing():
    """Taken down and put back is two showings: a new `since` says the screen left it between.

    Inside the gap a Player before minor 3 would join, so only the `since` can tell them apart.
    """
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    again = T0 + MINUTE + timedelta(seconds=30)

    saved = _advance(open_, _art("dali", since=again), T0 + 2 * MINUTE)

    assert [(showing.started_at, showing.ended_at) for showing in saved] == [(T0, again), (again, None)]


@pytest.mark.parametrize("state", [ScreenState.DARK, ScreenState.IN_USE, ScreenState.NO_SCREEN])
def test_a_screen_doing_anything_else_ends_the_showing_at_its_since(state):
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    went = T0 + MINUTE + timedelta(seconds=13)

    assert _advance(open_, ReportedState(state=state, work_id=None, since=went), T0 + 2 * MINUTE) == [
        _showing(started=T0, seen=T0 + MINUTE, ended=went)
    ]


def test_a_picture_this_wall_did_not_put_there_ends_the_showing_and_begins_none():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    went = T0 + MINUTE + timedelta(seconds=5)

    assert _advance(open_, _art(None, since=went), T0 + 2 * MINUTE) == [_showing(started=T0, seen=T0 + MINUTE, ended=went)]


def test_a_work_the_feed_does_not_carry_is_not_believed_and_ends_the_showing_before_it():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    went = T0 + MINUTE + timedelta(seconds=5)

    saved = _advance(open_, _art("not-sent", since=went), T0 + 2 * MINUTE)

    assert saved == [_showing(started=T0, seen=T0 + MINUTE, ended=went)]
    assert _advance(None, _art("not-sent", since=went), T0 + 2 * MINUTE) == []


def test_unreachable_ends_the_showing_where_it_was_last_seen_since_nothing_after_is_known():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    lost = T0 + 2 * MINUTE

    assert _advance(open_, ReportedState(state=ScreenState.UNREACHABLE, work_id=None, since=lost), T0 + 3 * MINUTE) == [
        _showing(started=T0, seen=T0 + MINUTE, ended=T0 + MINUTE)
    ]


def test_an_end_the_controller_dates_before_the_last_sight_is_held_at_the_last_sight():
    open_ = _showing(started=T0, seen=T0 + 2 * MINUTE)

    [ended] = _advance(open_, ReportedState(state=ScreenState.DARK, work_id=None, since=T0 + MINUTE), T0 + 3 * MINUTE)

    assert ended.ended_at == T0 + 2 * MINUTE


def test_nothing_on_screen_with_nothing_open_saves_nothing():
    closed = _showing(started=T0, seen=T0 + MINUTE, ended=T0 + MINUTE)

    assert _advance(closed, ReportedState(state=ScreenState.DARK, work_id=None, since=T0 + MINUTE), T0 + 2 * MINUTE) == []
    assert _advance(None, ReportedState(state=ScreenState.DARK, work_id=None, since=T0), T0 + MINUTE) == []


def test_a_showing_after_a_dark_spell_begins_a_new_one_and_leaves_the_ended_one_alone():
    ended = _showing(started=T0, seen=T0 + MINUTE, ended=T0 + 2 * MINUTE)
    back = T0 + 5 * MINUTE

    assert _advance(ended, _art("dali", since=back), T0 + 6 * MINUTE) == [_showing(started=back, seen=T0 + 6 * MINUTE)]


def test_a_new_showing_never_starts_before_the_one_it_follows_ended():
    """A wall shows one thing at a time, so a `since` dated inside the last showing is moved to its end."""
    ended = _showing(started=T0, seen=T0 + MINUTE, ended=T0 + 2 * MINUTE)

    [begun] = _advance(ended, _art("magritte", since=T0 + MINUTE + timedelta(seconds=30)), T0 + 3 * MINUTE)

    assert begun.started_at == T0 + 2 * MINUTE


def test_the_next_report_of_a_showing_whose_start_was_moved_still_extends_it():
    moved = _showing("magritte", started=T0 + 2 * MINUTE, seen=T0 + 3 * MINUTE)

    assert _advance(moved, _art("magritte", since=T0 + MINUTE + timedelta(seconds=30)), T0 + 4 * MINUTE) == [
        _showing("magritte", started=T0 + 2 * MINUTE, seen=T0 + 4 * MINUTE)
    ]


def test_a_report_older_than_the_last_sight_changes_nothing():
    """A report that arrives after a newer one says nothing about now."""
    open_ = _showing("magritte", started=T0 + MINUTE, seen=T0 + 3 * MINUTE)

    assert _advance(open_, _art("dali", since=T0), T0 + 2 * MINUTE) == []


def test_a_late_report_of_another_state_does_not_end_a_showing_seen_after_it():
    """Dark at a minute, arriving after a report at three minutes that the work was still up."""
    open_ = _showing(started=T0, seen=T0 + 3 * MINUTE)

    assert _advance(open_, ReportedState(state=ScreenState.DARK, work_id=None, since=T0 + MINUTE), T0 + 2 * MINUTE) == []


def test_an_echo_of_a_showing_already_ended_does_not_reopen_it():
    ended = _showing(started=T0, seen=T0 + MINUTE, ended=T0 + 2 * MINUTE)

    assert _advance(ended, _art("dali", since=T0), T0 + 2 * MINUTE) == []


# -- before minor 3: a showing is a run of reports ---------------------------------------


def test_a_player_before_minor_3_begins_a_showing_at_its_first_report():
    assert _advance(None, _art("dali"), T0) == [_showing(started=T0, seen=T0)]


def test_reports_within_the_stale_gap_join_one_showing():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    later = T0 + MINUTE + STALE

    assert _advance(open_, _art("dali"), later) == [_showing(started=T0, seen=later)]


def test_a_report_after_a_longer_gap_is_a_second_showing_and_the_first_ends_where_it_was_last_seen():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    later = T0 + MINUTE + STALE + timedelta(seconds=1)

    assert _advance(open_, _art("dali"), later) == [
        _showing(started=T0, seen=T0 + MINUTE, ended=T0 + MINUTE),
        _showing(started=later, seen=later),
    ]


def test_a_different_work_ends_the_showing_at_the_report_that_named_it():
    open_ = _showing(started=T0, seen=T0 + MINUTE)
    later = T0 + 2 * MINUTE

    assert _advance(open_, _art("magritte"), later) == [
        _showing(started=T0, seen=T0 + MINUTE, ended=later),
        _showing("magritte", started=later, seen=later),
    ]


# -- the store ------------------------------------------------------------------------


def test_showings_survive_reopening_the_catalogue_file(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    catalogue.save_showing(_showing(started=T0, seen=T0 + MINUTE, ended=T0 + 2 * MINUTE))
    catalogue.save_showing(_showing("magritte", started=T0 + 2 * MINUTE, seen=T0 + 3 * MINUTE))
    catalogue.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert reopened.latest_showing(WALL) == _showing("magritte", started=T0 + 2 * MINUTE, seen=T0 + 3 * MINUTE)
        assert reopened.last_shown_by_work() == {"dali": T0 + MINUTE, "magritte": T0 + 3 * MINUTE}
    finally:
        reopened.close()


def test_the_latest_showing_is_by_start_and_per_wall(store):
    """Saved out of order, and beside another wall's later one, so neither insertion order nor a global maximum passes."""
    store.save_showing(_showing("magritte", started=T0 + 2 * MINUTE))
    store.save_showing(_showing("dali", started=T0, seen=T0 + 5 * MINUTE, ended=T0 + 2 * MINUTE))
    store.save_showing(Showing(wall_id="wall-study", work_id="ernst", started_at=T0 + 9 * MINUTE, last_seen_at=T0 + 9 * MINUTE))

    assert store.latest_showing(WALL).work_id == "magritte"
    assert store.latest_showing("wall-nowhere") is None


def test_a_work_last_shown_is_its_latest_sight_on_any_wall(store):
    store.save_showing(_showing("dali", started=T0, seen=T0 + 4 * MINUTE, ended=T0 + 4 * MINUTE))
    store.save_showing(_showing("dali", started=T0 + 4 * MINUTE, seen=T0 + MINUTE * 9))
    store.save_showing(Showing(wall_id="wall-study", work_id="dali", started_at=T0, last_seen_at=T0 + 6 * MINUTE))

    assert store.last_shown_by_work() == {"dali": T0 + MINUTE * 9}


# -- through the heartbeat ------------------------------------------------------------


@pytest.fixture
def hung(services, ready_work, wall_id):
    """Two works on the wall's published feed."""
    first, second = ready_work("Dalí"), ready_work("Magritte")
    theme = services.display.add_theme(name="Surrealism")
    for work in (first, second):
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    return first, second


def _heartbeat(at, state="showing_art", work_id=None, since=None):
    return {
        "schema": {"major": 1, "minor": 3},
        "reported_at": at.isoformat(),
        "display_state": {"state": state, "work_id": work_id, "since": (since or at).isoformat()},
    }


def _minor_1(at, work_id):
    return {"schema": {"major": 1, "minor": 1}, "reported_at": at.isoformat(), "current_work_id": work_id}


def test_a_rotation_reported_by_heartbeat_is_kept_as_showings(display, hung, wall_id):
    first, second = hung
    now = datetime.now(UTC)

    display.record_heartbeat(wall_id, _heartbeat(now - 3 * MINUTE, work_id=first.id, since=now - 4 * MINUTE))
    display.record_heartbeat(wall_id, _heartbeat(now - 2 * MINUTE, work_id=first.id, since=now - 4 * MINUTE))
    display.record_heartbeat(wall_id, _heartbeat(now - MINUTE, work_id=second.id, since=now - MINUTE))
    display.record_heartbeat(wall_id, _heartbeat(now, state="dark", since=now))

    assert display.last_showing(wall_id) == Showing(
        wall_id=wall_id, work_id=second.id, started_at=now - MINUTE, last_seen_at=now - MINUTE, ended_at=now
    )
    assert display.work_ids_shown() == {first.id, second.id}
    assert display.work_ids_shown(since=now - MINUTE - timedelta(seconds=1)) == {second.id}


def test_a_player_before_minor_3_is_kept_from_its_current_work(display, hung, wall_id):
    first, _ = hung
    now = datetime.now(UTC)

    display.record_heartbeat(wall_id, _minor_1(now - MINUTE, first.id))
    display.record_heartbeat(wall_id, _minor_1(now, first.id))

    assert display.last_showing(wall_id) == Showing(wall_id=wall_id, work_id=first.id, started_at=now - MINUTE, last_seen_at=now)


def test_a_work_the_walls_feed_does_not_carry_is_not_recorded_and_is_logged(display, hung, ready_work, wall_id, caplog):
    stranger = ready_work("Ernst")
    now = datetime.now(UTC)

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat(now, work_id=stranger.id))

    assert display.last_showing(wall_id) is None
    assert display.work_ids_shown() == frozenset()
    (line,) = [record for record in caplog.records if getattr(record, "event", None) == "showings.not_in_feed"]
    assert (line.wall_id, line.work_id) == (wall_id, stranger.id)


def _not_in_feed(caplog):
    return [record for record in caplog.records if getattr(record, "event", None) == "showings.not_in_feed"]


def test_a_wall_with_nothing_published_records_nothing_and_blames_no_feed(display, ready_work, wall_id, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat(datetime.now(UTC), work_id=ready_work().id))

    assert display.last_showing(wall_id) is None
    assert _not_in_feed(caplog) == []


def test_a_work_the_feed_carries_is_not_logged_as_a_stranger(display, hung, wall_id, caplog):
    first, _ = hung

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat(datetime.now(UTC), work_id=first.id))

    assert _not_in_feed(caplog) == []


def test_a_superseded_report_of_a_stranger_is_not_logged(display, hung, ready_work, wall_id, caplog):
    first, _ = hung
    stranger = ready_work("Ernst")
    now = datetime.now(UTC)
    display.record_heartbeat(wall_id, _heartbeat(now, work_id=first.id))

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat(now - MINUTE, work_id=stranger.id))

    assert _not_in_feed(caplog) == []


def test_a_showing_on_a_wall_since_removed_still_counts_as_shown(display, store, hung):
    first, _ = hung
    store.save_showing(Showing(wall_id="a-wall-taken-down", work_id=first.id, started_at=T0, last_seen_at=T0 + MINUTE))

    assert display.work_ids_shown() == {first.id}


def test_a_record_that_cannot_be_written_is_logged_and_the_heartbeat_still_kept(
    display, hung, store, wall_id, wall_settings, monkeypatch, caplog
):
    first, _ = hung

    def refuse(showing):
        raise StorageError("the disk is full.")

    monkeypatch.setattr(store, "save_showing", refuse)
    with caplog.at_level(logging.ERROR, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat(datetime.now(UTC), work_id=first.id))

    assert wall_settings.heartbeat_path(wall_id).exists()
    (line,) = [record for record in caplog.records if getattr(record, "event", None) == "showings.not_recorded"]
    assert line.wall_id == wall_id


def test_last_showing_refuses_a_wall_that_does_not_exist(display):
    with pytest.raises(ServiceError):
        display.last_showing("no-such-wall")


def test_a_record_that_cannot_be_written_still_lets_the_horizon_roll(display, hung, store, wall_id, wall_settings, monkeypatch):
    """The roll runs after the record on the same heartbeat, and a wall whose horizon stopped rolling runs out of schedule."""
    first, _ = hung
    path = wall_settings.manifest_v2_path(wall_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    for span in [document["schedule"]["horizon"], *document["schedule"]["slots"]]:
        for key in ("from", "until"):
            span[key] = (datetime.fromisoformat(span[key]) - timedelta(days=1, hours=1)).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")

    def broken(showing):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(store, "save_showing", broken)
    display.record_heartbeat(wall_id, _heartbeat(datetime.now(UTC), work_id=first.id))

    assert read_published(path).horizon_until - datetime.now(UTC) > timedelta(days=2)
