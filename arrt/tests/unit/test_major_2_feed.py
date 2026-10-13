"""Each path that changes what a wall shows publishes its feed, manifest major 2.

The paths are the comment over `programming/display.py`'s feed methods (derived
from that module and its callers), and each test below names the path it drives
and what that path must do to the slot on the wall now. Every feed any test
here publishes is also checked against the contract as it is built
(`feed_guard.py`, wrapped round every test by `conftest.py`).
"""

import json
import logging
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from feed_guard import problems

from arrt.library.facade import UnplayableReason
from arrt.library.services import catalogue as catalogue_module
from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import MatMethod, RenditionKind, ThemeMembership
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.programming.display import Unjudged
from arrt.programming.manifest.builder import KeptOff
from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError

#: Long enough that no test here can cross a slot boundary while it runs, so a
#: kept slot is the same slot before and after.
HOUR = 3600


@pytest.fixture
def mastered(services, ready_work, wall_settings, decodable_jpeg):
    """A work ready for the wall, with a presentation master on disk at a size of its own."""

    def _work(title="Nighthawks", *, width=4000, height=3000):
        work = ready_work(title, master=False)
        path = f"masters/{work.id}.jpg"
        decodable_jpeg(wall_settings.art_root / path, width=width, height=height)
        services.catalogue.record_rendition(
            artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
        )
        return work

    return _work


@pytest.fixture
def theme_of(display, wall_id):
    """A theme of these works, in this order; the wall it is hung on plays it in order at `interval`."""

    def _theme(*works, name="Surrealism", interval=HOUR):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        display.set_playback(wall_id, rotation_interval_seconds=interval, shuffle=False)
        return theme

    return _theme


@pytest.fixture
def feed(wall_settings):
    def _feed(wall_id):
        return read_published(wall_settings.manifest_v2_path(wall_id))

    return _feed


def _now():
    return datetime.now(UTC)


# -- sync: hanging a theme, re-hanging it, hanging a selection --------------------------


def test_hanging_a_theme_publishes_its_feed(display, mastered, theme_of, wall_id, wall_settings):
    first, second = mastered("Nighthawks", width=4000, height=3000), mastered("Gas", width=2000, height=3000)
    theme = theme_of(first, second)

    display.activate_theme(theme.id, wall_id=wall_id)

    document = json.loads(wall_settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))
    assert document["playlist"] == {"id": theme.id, "name": "Surrealism"}
    assert [slot["work_id"] for slot in document["schedule"]["slots"][:3]] == [first.id, second.id, first.id]
    media = document["works"][second.id]["media"]
    assert (media["width"], media["height"]) == (2000, 3000)
    assert media["url"] == f"/media/sha256-{media['sha256']}"
    assert document["works"][first.id]["mat_color"] == "#27285b"
    assert document["works"][first.id]["label"]["title"] == "Nighthawks"
    assert sorted(path.name for path in wall_settings.art_root.glob("theme-manifest-*")) == [f"theme-manifest-{wall_id}.v2.json"]


def test_a_work_without_a_master_is_left_off_the_feed_and_named(display, mastered, ready_work, theme_of, wall_id, feed):
    with_master, without = mastered("Nighthawks"), ready_work("Gas", master=False)
    theme = theme_of(with_master, without)

    build = display.activate_theme(theme.id, wall_id=wall_id)

    assert set(feed(wall_id).works) == {with_master.id}
    assert [(exclusion.work_id, exclusion.reason) for exclusion in build.exclusions] == [
        (without.id, UnplayableReason.NO_RENDITION)
    ]


def test_a_theme_none_of_whose_works_has_a_master_publishes_an_empty_feed(display, mastered, ready_work, theme_of, wall_id, feed):
    """The feed is the only one a wall has, so it says the theme has nothing to show rather than vanishing."""
    display.activate_theme(theme_of(mastered("Nighthawks"), name="Before").id, wall_id=wall_id)

    display.activate_theme(theme_of(ready_work("Gas", master=False), name="After").id, wall_id=wall_id)

    assert feed(wall_id).playlist_name == "After"
    assert feed(wall_id).works == {}
    assert feed(wall_id).slots == ()


def test_an_empty_theme_publishes_a_feed_with_nothing_scheduled(display, theme_of, wall_id, feed):
    theme = theme_of(name="Empty")

    display.activate_theme(theme.id, wall_id=wall_id)

    published = feed(wall_id)
    assert published.slots == ()
    assert published.horizon_until - published.horizon_from == timedelta(days=3)


def test_re_hanging_the_same_theme_keeps_the_slot_on_the_wall(display, mastered, theme_of, wall_id, feed):
    theme = theme_of(mastered("A"), mastered("B"), mastered("C"))
    display.activate_theme(theme.id, wall_id=wall_id)
    before = feed(wall_id)
    added = mastered("D")
    display.add_to_theme(theme_id=theme.id, artwork_id=added.id)

    display.activate_theme(theme.id, wall_id=wall_id)

    after = feed(wall_id)
    assert after.slots[0] == before.slots[0]
    assert after.horizon_from == before.horizon_from
    assert added.id in after.works


def test_hanging_another_theme_starts_fresh_now(display, mastered, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A"), mastered("B"), name="First").id, wall_id=wall_id)
    second = theme_of(mastered("C"), mastered("D"), name="Second")
    started = _now().replace(microsecond=0)

    display.activate_theme(second.id, wall_id=wall_id)

    after = feed(wall_id)
    assert after.playlist_id == second.id
    assert after.horizon_from >= started
    assert set(after.works) <= set(display.theme_work_ids(second.id))


def test_hanging_a_selection_publishes_its_feed(display, mastered, wall_id, feed):
    works = [mastered("A"), mastered("B")]

    build = display.hang_selection([work.id for work in works], wall_id=wall_id)

    assert feed(wall_id).playlist_id == build.theme.id
    assert set(feed(wall_id).works) == {work.id for work in works}


# -- show now and next ------------------------------------------------------------------


def test_showing_a_work_now_starts_the_feed_with_it(display, mastered, theme_of, wall_id, feed):
    a, b, c = mastered("A"), mastered("B"), mastered("C")
    display.activate_theme(theme_of(a, b, c).id, wall_id=wall_id)

    display.show_work_now(wall_id, c.id)

    on_the_wall = feed(wall_id).on_the_wall(_now())
    assert on_the_wall.work_id == c.id
    assert feed(wall_id).slots[1].work_id == a.id


def test_showing_a_work_from_outside_the_theme_carries_it_in_the_feed(display, mastered, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    guest = mastered("Guest")

    display.show_work_now(wall_id, guest.id)

    published = feed(wall_id)
    assert published.on_the_wall(_now()).work_id == guest.id
    assert guest.id in published.works
    # A guest finishes its slot and does not join the cycle.
    assert [slot.work_id for slot in published.slots[1:]].count(guest.id) == 0


def test_a_guest_survives_a_re_hang_of_the_same_theme(display, mastered, theme_of, wall_id, feed):
    theme = theme_of(mastered("A"), mastered("B"))
    display.activate_theme(theme.id, wall_id=wall_id)
    guest = mastered("Guest")
    display.show_work_now(wall_id, guest.id)

    display.activate_theme(theme.id, wall_id=wall_id)

    assert feed(wall_id).on_the_wall(_now()).work_id == guest.id


def test_showing_a_work_with_no_master_is_refused_and_leaves_the_feed_alone(
    display, mastered, ready_work, theme_of, wall_id, feed
):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    before = feed(wall_id)
    plain = ready_work("Plain", master=False)

    with pytest.raises(ServiceError, match="no presentation master has been made"):
        display.show_work_now(wall_id, plain.id)

    assert feed(wall_id).slots == before.slots


def test_next_starts_the_feed_with_the_work_that_was_coming_up(display, mastered, theme_of, wall_id, feed):
    a, b, c = mastered("A"), mastered("B"), mastered("C")
    display.activate_theme(theme_of(a, b, c).id, wall_id=wall_id)
    coming = feed(wall_id).after(_now())

    display.step_display(wall_id)

    assert feed(wall_id).on_the_wall(_now()).work_id == coming == b.id


# -- withdrawals and the Library's changes ---------------------------------------------


def test_a_work_leaving_the_theme_leaves_the_feed_and_the_slot_on_the_wall_stays(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    a, b, c = mastered("A"), mastered("B"), mastered("C")
    display.activate_theme(theme_of(a, b, c).id, wall_id=wall_id)
    # Published ten minutes ago, so a slot kept and one started afresh at now
    # cannot be told apart by the second they share.
    _age(wall_settings, wall_id, by=timedelta(minutes=10))
    on_the_wall = feed(wall_id).on_the_wall(_now())
    assert on_the_wall.work_id == a.id

    display.leave_theme(b.id, wall_id=wall_id)

    after = feed(wall_id)
    assert after.slots[0] == on_the_wall
    assert b.id not in after.works
    assert all(slot.work_id != b.id for slot in after.slots)


def test_the_work_on_the_wall_leaving_starts_the_feed_fresh_without_it(display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)

    display.exclude_work(a.id, wall_id=wall_id)

    after = feed(wall_id)
    assert a.id not in after.works
    assert after.on_the_wall(_now()).work_id == b.id


def test_archiving_a_work_takes_it_off_every_feed(services, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)

    services.catalogue.archive_artwork(b.id)

    assert b.id not in feed(wall_id).works


def test_a_new_mat_colour_replaces_the_works_entry_and_moves_no_slot(services, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    before = feed(wall_id)

    services.catalogue.record_mat_color(artwork_id=b.id, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)

    after = feed(wall_id)
    assert after.works[b.id]["mat_color"] == "#3b2f2a"
    assert after.slots == before.slots


def test_startup_reconciliation_takes_a_refused_work_off_the_feed(store, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    # A catalogue service nobody subscribed to: the Library's change commits as
    # if the process died before the handler ran.
    CatalogueService(store).archive_artwork(b.id)
    assert b.id in feed(wall_id).works, "the announcement was not lost after all"

    result = display.reconcile()

    assert wall_id in result.republished
    assert b.id not in feed(wall_id).works


# -- the horizon rolls forward on the heartbeat ------------------------------------------


def _heartbeat():
    return {"schema": {"major": 1, "minor": 1}, "reported_at": _now().isoformat(), "current_work_id": None}


def _age(wall_settings, wall_id, *, by):
    """Move the published feed back in time, as if it had been published `by` ago."""
    path = wall_settings.manifest_v2_path(wall_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    for span in [document["schedule"]["horizon"], *document["schedule"]["slots"]]:
        for key in ("from", "until"):
            span[key] = (datetime.fromisoformat(span[key]) - by).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")


def test_a_heartbeat_with_under_two_days_left_rolls_the_horizon_forward(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    _age(wall_settings, wall_id, by=timedelta(days=1, hours=1))
    aged = feed(wall_id)
    on_the_wall = aged.on_the_wall(_now())

    display.record_heartbeat(wall_id, _heartbeat())

    rolled = feed(wall_id)
    assert rolled.horizon_until - _now() > timedelta(days=2, hours=23)
    assert rolled.slots[0] == on_the_wall
    # At the theme's own pace, not the deployment's default.
    assert {slot.until - slot.start for slot in rolled.slots[1:-1]} == {timedelta(seconds=HOUR)}


def test_a_rolled_horizon_goes_on_through_the_theme_past_the_works_the_last_one_named(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    """A feed names only what its horizon schedules, so a roll that cycled those alone narrowed the theme for good."""
    works = [mastered(title) for title in "ABCDEF"]
    display.activate_theme(theme_of(*works, interval=24 * HOUR).id, wall_id=wall_id)
    first = set(feed(wall_id).works)
    assert first < {work.id for work in works}, "the horizon names every work, so nothing here can narrow"
    _age(wall_settings, wall_id, by=timedelta(days=1, hours=1))

    display.record_heartbeat(wall_id, _heartbeat())

    assert set(feed(wall_id).works) - first


def test_a_roll_carries_a_work_that_joined_the_hung_theme_unannounced(
    store, caplog, display, mastered, theme_of, wall_id, wall_settings, feed
):
    """An announcement lost to a crash: the next roll builds the hung theme, so the work arrives within a day."""
    theme = theme_of(mastered("A"))
    display.activate_theme(theme.id, wall_id=wall_id)
    lost = mastered("B")
    store.add_membership(ThemeMembership(theme_id=theme.id, artwork_id=lost.id, added_at=_now(), position=1))
    _age(wall_settings, wall_id, by=timedelta(days=1, hours=1))

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.record_heartbeat(wall_id, _heartbeat())

    assert lost.id in feed(wall_id).works
    assert any("rolled its horizon forward from theme" in record.getMessage() for record in caplog.records)


def test_a_roll_on_a_wall_with_nothing_hung_goes_on_with_what_it_carries(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    """A wall whose theme was taken down keeps showing what it was showing; a roll does not empty it."""
    works = {mastered("A").id, mastered("B").id}
    theme = display.add_theme(name="Taken down")
    for work_id in sorted(works):
        display.add_to_theme(theme_id=theme.id, artwork_id=work_id)
    display.activate_theme(theme.id, wall_id=wall_id)
    display.clear_wall(wall_id)
    _age(wall_settings, wall_id, by=timedelta(days=1, hours=1))

    display.record_heartbeat(wall_id, _heartbeat())

    assert set(feed(wall_id).works) == works
    assert feed(wall_id).horizon_until - _now() > timedelta(days=2, hours=23)


def test_a_heartbeat_with_more_than_two_days_left_rewrites_nothing(display, mastered, theme_of, wall_id, wall_settings):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    _age(wall_settings, wall_id, by=timedelta(hours=23))
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    display.record_heartbeat(wall_id, _heartbeat())

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


# -- the wall's rotation: how long a work stays up, and whether it is shuffled ------------


def test_a_new_pace_republishes_at_once_and_keeps_the_slot_on_the_wall(display, mastered, theme_of, wall_id, feed):
    """The slot on the wall now finishes as published; later ones take the new length, bar the last, which the horizon may cut."""
    theme = theme_of(mastered("A"), mastered("B"), mastered("C"))
    display.activate_theme(theme.id, wall_id=wall_id)
    before = feed(wall_id)

    display.set_playback(wall_id, rotation_interval_seconds=2 * HOUR)

    after = feed(wall_id)
    assert after.slots[0] == before.slots[0]
    assert {slot.until - slot.start for slot in after.slots[1:-1]} == {timedelta(hours=2)}
    # The setting left alone is left alone.
    assert display.get_wall(wall_id).shuffle is False


def test_the_walls_pace_stays_when_another_theme_is_hung(display, mastered, theme_of, wall_id, feed):
    """The ruling's point: the pace is the wall's, so it is not the theme's to take with it."""
    display.activate_theme(theme_of(mastered("A"), mastered("B"), name="Before").id, wall_id=wall_id)
    display.set_playback(wall_id, rotation_interval_seconds=2 * HOUR)
    other = display.add_theme(name="After")
    for work in (mastered("C"), mastered("D")):
        display.add_to_theme(theme_id=other.id, artwork_id=work.id)

    display.activate_theme(other.id, wall_id=wall_id)

    assert feed(wall_id).playlist_name == "After"
    assert {slot.until - slot.start for slot in feed(wall_id).slots[:-1]} == {timedelta(hours=2)}


def test_a_wall_with_nothing_hung_takes_a_new_pace_for_what_it_carries(display, mastered, theme_of, wall_id, feed):
    works = {mastered("A").id, mastered("B").id}
    theme = display.add_theme(name="Taken down")
    for work_id in sorted(works):
        display.add_to_theme(theme_id=theme.id, artwork_id=work_id)
    display.activate_theme(theme.id, wall_id=wall_id)
    display.clear_wall(wall_id)

    display.set_playback(wall_id, rotation_interval_seconds=2 * HOUR)

    assert set(feed(wall_id).works) == works
    assert {slot.until - slot.start for slot in feed(wall_id).slots[1:-1]} == {timedelta(hours=2)}


def test_a_wall_with_no_feed_keeps_the_setting_and_publishes_nothing(display, wall_id, wall_settings):
    display.set_playback(wall_id, rotation_interval_seconds=931, shuffle=True)

    assert (display.get_wall(wall_id).rotation_interval_seconds, display.get_wall(wall_id).shuffle) == (931, True)
    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_null_returns_each_setting_to_the_deployment_default(display, mastered, theme_of, wall_id, wall_settings, feed):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)

    display.set_playback(wall_id, rotation_interval_seconds=None, shuffle=None)

    wall = display.get_wall(wall_id)
    assert (wall.rotation_interval_seconds, wall.shuffle) == (None, None)
    default = timedelta(seconds=wall_settings.rotation_interval_seconds)
    assert {slot.until - slot.start for slot in feed(wall_id).slots[1:-1]} == {default}


def test_a_pace_of_zero_is_refused_and_nothing_changes(display, wall_id):
    display.set_playback(wall_id, rotation_interval_seconds=931)

    with pytest.raises(ServiceError, match="greater than zero"):
        display.set_playback(wall_id, rotation_interval_seconds=0)

    assert display.get_wall(wall_id).rotation_interval_seconds == 931


# -- the wall's shapes ------------------------------------------------------------------


@pytest.fixture
def three_shapes(mastered):
    """A landscape, a portrait, and a square scanned a few pixels off square."""
    return (
        mastered("Wide", width=4000, height=3000),
        mastered("Tall", width=2000, height=3000),
        mastered("Square", width=3003, height=3000),
    )


def test_a_work_wider_than_the_wall_shows_is_left_off_by_name(display, three_shapes, theme_of, wall_id, feed):
    wide, tall, square = three_shapes
    display.set_playback(wall_id, widest="1:1")

    build = display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)

    assert set(feed(wall_id).works) == {tall.id, square.id}
    [exclusion] = build.exclusions
    assert (exclusion.work_id, exclusion.reason) == (wide.id, KeptOff.WALL_SHAPE)
    assert exclusion.detail.startswith("This wall shows nothing wider than 1:1, and this work is 4:3.")
    assert build.summarise() == "2 of 3 works in this theme are on the wall; 1 is outside this wall's shapes."


def test_a_tallest_bound_alone_leaves_off_only_the_taller_work(display, three_shapes, theme_of, wall_id, feed):
    wide, tall, square = three_shapes
    display.set_playback(wall_id, tallest="1:1")

    display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)

    assert set(feed(wall_id).works) == {wide.id, square.id}


def test_new_shapes_republish_at_once_and_any_puts_the_work_back(display, three_shapes, theme_of, wall_id, feed):
    wide, tall, square = three_shapes
    display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)
    before = feed(wall_id)

    display.set_playback(wall_id, widest="1:1")
    narrowed = feed(wall_id)
    display.set_playback(wall_id, widest="any")

    assert set(narrowed.works) == {tall.id, square.id}
    assert wide.id not in {slot.work_id for slot in narrowed.slots[1:]}
    assert set(feed(wall_id).works) == {wide.id, tall.id, square.id}
    assert display.get_wall(wall_id).max_aspect_ratio is None
    # The pace and order were not named, so they stayed.
    assert (display.get_wall(wall_id).rotation_interval_seconds, display.get_wall(wall_id).shuffle) == (HOUR, False)
    assert before.slots[0].start == feed(wall_id).slots[0].start


def test_shapes_that_leave_nothing_make_the_wall_dark_and_say_so(display, three_shapes, theme_of, wall_id, feed):
    """The owner's ruling: honoured exactly, never a quiet fallback to the whole theme."""
    wide, tall, square = three_shapes
    display.set_playback(wall_id, tallest="21:9")

    build = display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)

    assert feed(wall_id).works == {}
    assert feed(wall_id).slots == ()
    assert build.summarise() == (
        "0 of 3 works in this theme are on the wall; 3 are outside this wall's shapes, so the wall is dark."
    )


def test_the_walls_shapes_stay_when_another_theme_is_hung(display, three_shapes, theme_of, wall_id, feed):
    wide, tall, square = three_shapes
    display.activate_theme(theme_of(tall, name="Before").id, wall_id=wall_id)
    display.set_playback(wall_id, widest="1:1")

    display.activate_theme(theme_of(wide, square, name="After").id, wall_id=wall_id)

    assert set(feed(wall_id).works) == {square.id}


def test_a_work_kept_off_every_wall_is_reported_as_that_whatever_its_shape(display, three_shapes, theme_of, wall_id):
    """The curator's word on the work outranks the wall's range: allowing it again is what would change anything first."""
    wide, tall, square = three_shapes
    display.exclude_work(wide.id)
    display.set_playback(wall_id, widest="1:1")

    build = display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)

    assert {(exclusion.work_id, exclusion.reason) for exclusion in build.exclusions} == {(wide.id, KeptOff.EVERY_WALL)}


def test_a_wall_its_shapes_darken_warns_and_a_narrowed_wall_that_still_shows_works_does_not(
    display, three_shapes, theme_of, wall_id, caplog
):
    """The curator's choice is not a fault, unless it leaves the wall dark: then it is the loudest one."""
    wide, tall, square = three_shapes
    display.activate_theme(theme_of(wide, tall, square).id, wall_id=wall_id)

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.set_playback(wall_id, widest="1:1")
        narrowed = [r for r in caplog.records if "Published the feed" in r.getMessage()]
        caplog.clear()
        display.set_playback(wall_id, tallest="21:9", widest="any")
        darkened = [r for r in caplog.records if "Published the feed" in r.getMessage()]

    assert [r.levelno for r in narrowed] == [logging.INFO]
    assert "1 is outside this wall's shapes" in narrowed[0].getMessage()
    assert [r.levelno for r in darkened] == [logging.WARNING]
    assert darkened[0].getMessage().endswith("so the wall is dark.")


def test_a_tallest_wider_than_the_widest_is_refused_and_nothing_changes(display, wall_id):
    display.set_playback(wall_id, widest="16:9")

    with pytest.raises(ServiceError, match="wider than the widest"):
        display.set_playback(wall_id, tallest="21:9")
    with pytest.raises(ServiceError, match="width:height"):
        display.set_playback(wall_id, widest="wide")

    wall = display.get_wall(wall_id)
    assert (wall.min_aspect_ratio, wall.max_aspect_ratio) == (None, pytest.approx(16 / 9))


def test_on_a_wall_with_nothing_hung_the_shapes_wait_for_the_next_hanging(display, three_shapes, theme_of, wall_id, feed):
    """The carried feed cannot be trimmed: with no theme to rebuild from, a widened range could not bring a work back."""
    wide, tall, square = three_shapes
    theme = theme_of(wide, tall, square)
    display.activate_theme(theme.id, wall_id=wall_id)
    display.clear_wall(wall_id)

    display.set_playback(wall_id, widest="1:1")
    carried = feed(wall_id)
    display.activate_theme(theme.id, wall_id=wall_id)

    assert set(carried.works) == {wide.id, tall.id, square.id}
    assert set(feed(wall_id).works) == {tall.id, square.id}


# -- the household rule across walls -----------------------------------------------------


def test_two_walls_hanging_one_theme_never_show_a_work_at_the_same_moment(display, mastered, theme_of, wall_id, feed):
    theme = theme_of(mastered("A"), mastered("B"), mastered("C"))
    study = display.add_wall(name="Study").id
    display.set_playback(study, rotation_interval_seconds=HOUR, shuffle=False)

    display.activate_theme(theme.id, wall_id=wall_id)
    display.activate_theme(theme.id, wall_id=study)

    hall, other = feed(wall_id), feed(study)
    for slot in other.slots:
        assert not any(s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) for s in hall.slots)


def test_a_clash_the_rule_cannot_avoid_is_said(display, mastered, theme_of, wall_id, caplog):
    theme = theme_of(mastered("Solo"))
    study = display.add_wall(name="Study").id
    display.set_playback(study, rotation_interval_seconds=HOUR, shuffle=False)
    display.activate_theme(theme.id, wall_id=wall_id)

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.activate_theme(theme.id, wall_id=study)

    assert any("Study" in r.getMessage() and "another wall shows at the same time" in r.getMessage() for r in caplog.records)


def test_a_work_whose_master_file_is_gone_leaves_the_feed(display, mastered, theme_of, wall_id, wall_settings, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    (wall_settings.art_root / f"masters/{b.id}.jpg").unlink()

    display.reconcile([b.id])

    assert set(feed(wall_id).works) == {a.id}


def test_a_master_drawn_from_an_earlier_original_is_not_offered(services, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    original = services.catalogue.get_original(b.id)
    services.catalogue.record_original(
        artwork_id=b.id,
        source_id=original.source_id,
        path=original.relative_path,
        width=original.width,
        height=original.height,
        byte_size=original.byte_size,
        content_hash="a-new-acquisition",
        fetch_status=None,
    )

    build = display.activate_theme(theme_of(a, b).id, wall_id=wall_id)

    assert [(exclusion.work_id, exclusion.reason) for exclusion in build.exclusions] == [(b.id, UnplayableReason.STALE_RENDITION)]
    assert set(feed(wall_id).works) == {a.id}


def test_a_member_that_lost_its_master_is_not_carried_through_a_re_hang(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    a, b = mastered("A"), mastered("B")
    theme = theme_of(a, b)
    display.activate_theme(theme.id, wall_id=wall_id)
    assert feed(wall_id).on_the_wall(_now()).work_id == a.id
    (wall_settings.art_root / f"masters/{a.id}.jpg").unlink()

    display.activate_theme(theme.id, wall_id=wall_id)

    assert a.id not in feed(wall_id).works


def test_a_patched_entry_is_still_a_feed_the_contract_accepts(services, display, mastered, theme_of, wall_id, wall_settings):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)

    services.catalogue.record_mat_color(artwork_id=b.id, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)

    assert problems(json.loads(wall_settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))) == []


def test_withdrawing_a_themes_only_work_leaves_the_feed_empty(display, mastered, theme_of, wall_id, feed):
    only = mastered("A")
    display.activate_theme(theme_of(only).id, wall_id=wall_id)

    display.exclude_work(only.id, wall_id=wall_id)

    assert feed(wall_id).works == {}
    assert feed(wall_id).slots == ()


def test_a_patched_entry_keeps_the_walls_settings(services, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    display.set_mat_mode(wall_id, "full")

    services.catalogue.record_mat_color(artwork_id=b.id, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)

    assert feed(wall_id).settings == {"mat": {"mode": "full"}}
    assert feed(wall_id).works[b.id]["mat_color"] == "#3b2f2a"


# -- a wall's mat mode -------------------------------------------------------------------


def test_choosing_a_mat_mode_republishes_the_feed_with_it_and_moves_no_slot(display, mastered, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    before = feed(wall_id)

    wall = display.set_mat_mode(wall_id, "none")

    assert wall.mat_mode == "none"
    assert feed(wall_id).settings == {"mat": {"mode": "none"}}
    assert feed(wall_id).slots == before.slots
    assert feed(wall_id).works == before.works


def test_leaving_the_mat_to_the_player_takes_the_key_out(display, mastered, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A")).id, wall_id=wall_id)
    display.set_mat_mode(wall_id, "full")

    display.set_mat_mode(wall_id, None)

    assert display.get_wall(wall_id).mat_mode is None
    assert feed(wall_id).settings == {}


def test_a_chosen_mat_mode_rides_every_later_feed(display, mastered, theme_of, wall_id, feed):
    display.set_mat_mode(wall_id, "proportional")

    display.activate_theme(theme_of(mastered("A"), name="Later").id, wall_id=wall_id)

    assert feed(wall_id).settings == {"mat": {"mode": "proportional"}}


def test_a_mat_mode_nobody_defined_is_refused_and_nothing_changes(display, mastered, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A")).id, wall_id=wall_id)

    with pytest.raises(ServiceError, match="mat mode"):
        display.set_mat_mode(wall_id, "thick")

    assert display.get_wall(wall_id).mat_mode is None
    assert feed(wall_id).settings == {}


def test_a_mat_mode_survives_the_store(store, display, wall_id):
    display.set_mat_mode(wall_id, "full")

    assert store.get_wall(wall_id).mat_mode == "full"


def test_a_catalogue_file_from_before_the_mat_mode_gains_it_and_keeps_its_walls(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path, wall_name="Hall").close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("ALTER TABLE walls DROP COLUMN mat_mode")
        connection.commit()
    finally:
        connection.close()

    store = SqliteCatalogue(open_catalogue_file(path))
    try:
        (wall,) = store.list_walls()
        assert (wall.name, wall.mat_mode) == ("Hall", None)
        store.update_wall(replace(wall, mat_mode="full"))
        assert store.get_wall(wall.id).mat_mode == "full"
    finally:
        store.close()


# -- too small for this wall ---------------------------------------------------------------


@pytest.fixture
def shown_by_a_client(services, wall_id):
    """The wall on a client's HDMI output, so it has a display to remember screens against."""
    client = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    return services.display.get_wall(wall_id)


def _beat_with_screen(width, height):
    return {
        **_heartbeat(),
        "schema": {"major": 1, "minor": 2},
        "capabilities": {
            "screen": {"width_px": width, "height_px": height},
            "backend": "framebuffer",
            "label_modes": ["none"],
            "manifest_majors": [2, 1],
        },
    }


def test_a_wall_whose_player_reported_no_screen_judges_nothing(display, mastered, theme_of, wall_id, shown_by_a_client):
    display.activate_theme(theme_of(mastered("Tiny", width=400, height=300)).id, wall_id=wall_id)
    display.record_heartbeat(wall_id, _heartbeat())

    assert display.largest_screen(wall_id) is None
    assert display.too_small_on(wall_id) == frozenset()


def test_a_reported_screen_makes_a_small_work_too_small_and_a_large_one_not(
    display, mastered, theme_of, wall_id, shown_by_a_client
):
    tiny, large = mastered("Tiny", width=1000, height=700), mastered("Large", width=6000, height=4000)
    theme = theme_of(tiny, large)
    display.activate_theme(theme.id, wall_id=wall_id)

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    assert display.largest_screen(wall_id) == (3840, 2160)
    assert display.too_small_on(wall_id) == {tiny.id}
    assert display.too_small_for_walls(theme.id) == {tiny.id: [shown_by_a_client.name]}


def test_a_later_smaller_report_does_not_clear_the_judgement_within_the_window(
    display, mastered, theme_of, wall_id, shown_by_a_client
):
    tiny = mastered("Tiny", width=1000, height=700)
    display.activate_theme(theme_of(tiny, mastered("Large", width=6000, height=4000)).id, wall_id=wall_id)
    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    display.record_heartbeat(wall_id, _beat_with_screen(1280, 720))

    assert display.largest_screen(wall_id) == (3840, 2160)
    assert tiny.id in display.too_small_on(wall_id)


def test_a_screen_last_reported_beyond_the_window_no_longer_counts_and_is_forgotten(
    store, display, mastered, theme_of, wall_id, shown_by_a_client
):
    store.record_screen(shown_by_a_client.display_id, 3840, 2160, datetime.now(UTC) - timedelta(days=8))

    display.record_heartbeat(wall_id, _beat_with_screen(1920, 1080))

    assert display.largest_screen(wall_id) == (1920, 1080)
    assert [(w, h) for w, h, _ in store.reported_screens(shown_by_a_client.display_id)] == [(1920, 1080)]


def test_judging_a_work_too_small_takes_nothing_off_the_schedule(display, mastered, theme_of, wall_id, shown_by_a_client, feed):
    tiny = mastered("Tiny", width=1000, height=700)
    display.activate_theme(theme_of(tiny, mastered("Large", width=6000, height=4000)).id, wall_id=wall_id)
    before = feed(wall_id)

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    assert tiny.id in display.too_small_on(wall_id)
    assert feed(wall_id).slots == before.slots
    assert tiny.id in feed(wall_id).works


def test_a_wall_with_no_display_remembers_no_screen(display, mastered, theme_of, wall_id, store):
    display.activate_theme(theme_of(mastered("Tiny", width=400, height=300)).id, wall_id=wall_id)

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    assert display.largest_screen(wall_id) is None


def test_the_largest_screen_is_by_area_whatever_order_the_store_returns(display, wall_id, shown_by_a_client):
    # A portrait 4K panel, then a smaller landscape window whose width sorts
    # after it: keyed (display, width, height), the store would hand back the
    # small one last.
    display.record_heartbeat(wall_id, _beat_with_screen(2160, 3840))
    display.record_heartbeat(wall_id, _beat_with_screen(2560, 1440))

    assert display.largest_screen(wall_id) == (2160, 3840)


def test_a_stale_size_does_not_count_even_before_a_heartbeat_forgets_it(store, display, wall_id, shown_by_a_client):
    store.record_screen(shown_by_a_client.display_id, 3840, 2160, datetime.now(UTC) - timedelta(days=8))

    assert display.largest_screen(wall_id) is None


# -- each quiet state of the size judgement says which it is -------------------------------


def test_a_wall_on_no_display_says_so_rather_than_judging_everything_fine(display, mastered, theme_of, wall_id):
    display.activate_theme(theme_of(mastered("A")).id, wall_id=wall_id)

    judgement = display.judge_sizes(wall_id)

    assert (judgement.screen, judgement.unjudged, judgement.too_small) == (None, Unjudged.NO_DISPLAY, frozenset())


def test_a_wall_whose_player_reported_no_screen_says_so(display, mastered, theme_of, wall_id, shown_by_a_client):
    display.activate_theme(theme_of(mastered("A")).id, wall_id=wall_id)

    assert display.judge_sizes(wall_id).unjudged is Unjudged.NO_SCREEN


def test_a_wall_with_no_feed_says_so(display, wall_id, shown_by_a_client):
    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    assert display.judge_sizes(wall_id).unjudged is Unjudged.NO_FEED


def test_a_wall_judged_fine_says_what_it_was_judged_against(display, mastered, theme_of, wall_id, shown_by_a_client):
    display.activate_theme(theme_of(mastered("Large", width=6000, height=4000)).id, wall_id=wall_id)
    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    judgement = display.judge_sizes(wall_id)

    assert (judgement.screen, judgement.unjudged, judgement.too_small) == ((3840, 2160), None, frozenset())


@pytest.mark.parametrize(
    "capabilities",
    [
        "not an object",
        # Minor 4 made the screen optional, and one that is there is still read.
        {"screen": "3840x2160"},
        {"screen": {"width_px": 3840}},
        {"screen": {"width_px": 0, "height_px": 2160}},
        {"screen": {"width_px": 3840, "height_px": "2160"}},
        {"screen": {"width_px": True, "height_px": 2160}},
    ],
)
def test_a_heartbeat_with_a_screen_this_server_cannot_read_is_refused(display, wall_id, shown_by_a_client, capabilities):
    with pytest.raises(ServiceError, match="capabilities"):
        display.record_heartbeat(wall_id, {**_heartbeat(), "capabilities": capabilities})

    assert display.largest_screen(wall_id) is None


def test_a_heartbeat_whose_player_cannot_see_its_screen_is_kept_and_judges_nothing(
    display, mastered, theme_of, wall_id, shown_by_a_client
):
    """Minor 4: capabilities with no screen. Its majors count; no size is recorded from it."""
    display.activate_theme(theme_of(mastered("Tiny", width=400, height=300)).id, wall_id=wall_id)
    beat = {
        **_heartbeat(),
        "schema": {"major": 1, "minor": 4},
        "capabilities": {"backend": "framebuffer", "label_modes": ["none"], "manifest_majors": [2]},
    }

    display.record_heartbeat(wall_id, beat)

    assert display.get_wall_view(wall_id).reads_feed is True
    assert display.largest_screen(wall_id) is None
    assert display.too_small_on(wall_id) == frozenset()


def test_the_same_size_reported_within_the_hour_writes_nothing(store, display, wall_id, shown_by_a_client):
    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))
    [(_, _, first)] = store.reported_screens(shown_by_a_client.display_id)

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    assert store.reported_screens(shown_by_a_client.display_id) == [(3840, 2160, first)]


def test_the_same_size_reported_after_the_hour_refreshes_its_time(store, display, wall_id, shown_by_a_client):
    two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
    store.record_screen(shown_by_a_client.display_id, 3840, 2160, two_hours_ago)

    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    [(_, _, refreshed)] = store.reported_screens(shown_by_a_client.display_id)
    assert refreshed > two_hours_ago + timedelta(hours=1)


# -- a work that gains its master after a hang joins the feed ------------------------------


def test_a_work_that_gains_its_master_after_the_hang_joins_the_feed(
    services, display, mastered, ready_work, theme_of, wall_id, wall_settings, decodable_jpeg, feed
):
    """Gaining a master is readiness gained, and the hung theme's feed follows it (the owner, 2026-10-10)."""
    early, late = mastered("Early"), ready_work("Late", master=False)
    display.activate_theme(theme_of(early, late).id, wall_id=wall_id)
    assert set(feed(wall_id).works) == {early.id}

    path = f"masters/{late.id}.jpg"
    decodable_jpeg(wall_settings.art_root / path, width=3000, height=2000)
    services.catalogue.record_rendition(
        artwork_id=late.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )

    assert set(feed(wall_id).works) == {early.id, late.id}


def test_a_work_in_no_hung_theme_does_not_join_the_feed_when_it_gains_a_master(
    services, display, mastered, ready_work, theme_of, wall_id, wall_settings, decodable_jpeg, feed
):
    display.activate_theme(theme_of(mastered("Early")).id, wall_id=wall_id)
    outsider = ready_work("In another theme", master=False)
    display.add_to_theme(theme_id=display.add_theme(name="Elsewhere").id, artwork_id=outsider.id)

    path = f"masters/{outsider.id}.jpg"
    decodable_jpeg(wall_settings.art_root / path, width=3000, height=2000)
    services.catalogue.record_rendition(
        artwork_id=outsider.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )

    assert outsider.id not in feed(wall_id).works


def test_a_masters_size_is_read_from_its_file_once(services, mastered, monkeypatch):
    work = mastered("A", width=3000, height=2000)
    master = next(
        view.rendition
        for view in services.catalogue.list_renditions(work.id)
        if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )
    master = services.catalogue.with_content(master)
    opened = []
    real_open = catalogue_module.Image.open
    monkeypatch.setattr(catalogue_module.Image, "open", lambda *a, **k: opened.append(a) or real_open(*a, **k))

    sizes = [services.catalogue.pixel_size(master) for _ in range(3)]

    assert sizes == [(3000, 2000)] * 3
    assert len(opened) == 1


def test_a_new_size_within_the_hour_is_still_recorded(store, display, wall_id, shown_by_a_client):
    display.record_heartbeat(wall_id, _beat_with_screen(3840, 2160))

    display.record_heartbeat(wall_id, _beat_with_screen(1920, 1080))

    assert sorted((w, h) for w, h, _ in store.reported_screens(shown_by_a_client.display_id)) == [(1920, 1080), (3840, 2160)]
