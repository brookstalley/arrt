"""Each path that publishes a wall's major 1 manifest publishes its major 2 feed as well.

The paths are the table in `build-plan-wave-4e-schedule.md` (derived from
`programming/display.py` and its callers), and each test below names the path it
drives and what that path must do to the slot on the wall now. Every feed any test
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

from arrt.library.services import catalogue as catalogue_module
from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import MatMethod, RenditionKind
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.programming.display import Unjudged
from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError

#: Long enough that no test here can cross a slot boundary while it runs, so a
#: kept slot is the same slot before and after.
HOUR = 3600


@pytest.fixture
def mastered(services, ready_work, wall_settings, decodable_jpeg):
    """A work ready for the wall, with a presentation master on disk at a size of its own."""

    def _work(title="Nighthawks", *, width=4000, height=3000):
        work = ready_work(title)
        path = f"masters/{work.id}.jpg"
        decodable_jpeg(wall_settings.art_root / path, width=width, height=height)
        services.catalogue.record_rendition(
            artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
        )
        return work

    return _work


@pytest.fixture
def theme_of(display):
    def _theme(*works, name="Surrealism", interval=HOUR):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        display.update_theme(theme.id, rotation_interval_seconds=interval, shuffle=False)
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


def test_hanging_a_theme_publishes_its_feed_beside_its_manifest(display, mastered, theme_of, wall_id, wall_settings):
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
    assert wall_settings.manifest_path(wall_id).exists()


def test_a_work_without_a_master_stays_on_major_1_and_is_named(display, mastered, ready_work, theme_of, wall_id, feed, caplog):
    with_master, without = mastered("Nighthawks"), ready_work("Gas")
    theme = theme_of(with_master, without)

    with caplog.at_level(logging.WARNING, logger="arrt.programming.display"):
        build = display.activate_theme(theme.id, wall_id=wall_id)

    assert {entry.work_id for entry in build.entries} == {with_master.id, without.id}
    assert set(feed(wall_id).works) == {with_master.id}
    assert any(without.id in record.getMessage() and "presentation master" in record.getMessage() for record in caplog.records)


def test_a_theme_whose_works_have_no_master_publishes_no_feed_and_removes_an_old_one(
    display, mastered, ready_work, theme_of, wall_id, wall_settings
):
    display.activate_theme(theme_of(mastered("Nighthawks"), name="Before").id, wall_id=wall_id)
    assert wall_settings.manifest_v2_path(wall_id).exists()

    display.activate_theme(theme_of(ready_work("Gas"), name="After").id, wall_id=wall_id)

    # Its Player asks for v2, is told 404, and stays on the manifest that has the work.
    assert not wall_settings.manifest_v2_path(wall_id).exists()


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


def test_showing_a_work_with_no_master_leaves_the_feed_alone(display, mastered, ready_work, theme_of, wall_id, feed):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    before = feed(wall_id)
    plain = ready_work("Plain")

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

    assert wall_id in result.republished_v2
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


def test_a_heartbeat_with_more_than_two_days_left_rewrites_nothing(display, mastered, theme_of, wall_id, wall_settings):
    display.activate_theme(theme_of(mastered("A"), mastered("B")).id, wall_id=wall_id)
    _age(wall_settings, wall_id, by=timedelta(hours=23))
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    display.record_heartbeat(wall_id, _heartbeat())

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


# -- the household rule across walls -----------------------------------------------------


def test_two_walls_hanging_one_theme_never_show_a_work_at_the_same_moment(display, mastered, theme_of, wall_id, feed):
    theme = theme_of(mastered("A"), mastered("B"), mastered("C"))
    study = display.add_wall(name="Study").id

    display.activate_theme(theme.id, wall_id=wall_id)
    display.activate_theme(theme.id, wall_id=study)

    hall, other = feed(wall_id), feed(study)
    for slot in other.slots:
        assert not any(s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) for s in hall.slots)


def test_a_clash_the_rule_cannot_avoid_is_said(display, mastered, theme_of, wall_id, caplog):
    theme = theme_of(mastered("Solo"))
    study = display.add_wall(name="Study").id
    display.activate_theme(theme.id, wall_id=wall_id)

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.activate_theme(theme.id, wall_id=study)

    assert any("Study" in r.getMessage() and "another wall shows at the same time" in r.getMessage() for r in caplog.records)


def test_reconciliation_reads_the_feed_even_when_the_manifest_beside_it_is_unreadable(
    store, display, mastered, theme_of, wall_id, wall_settings, feed
):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    wall_settings.manifest_path(wall_id).write_text("not json", encoding="utf-8")
    CatalogueService(store).archive_artwork(b.id)

    display.reconcile()

    assert b.id not in feed(wall_id).works


def test_a_work_whose_master_file_is_gone_leaves_the_feed_and_stays_on_major_1(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    (wall_settings.art_root / f"masters/{b.id}.jpg").unlink()

    display.reconcile([b.id])

    assert b.id not in feed(wall_id).works
    assert b.id in [entry["work_id"] for entry in json.loads(wall_settings.manifest_path(wall_id).read_text())["entries"]]


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
    # The television render is redone for the new image; the master is not yet.
    services.catalogue.record_rendition(
        artwork_id=b.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path=f"ready/{b.id}.jpg"
    )

    build = display.activate_theme(theme_of(a, b).id, wall_id=wall_id)

    assert b.id in {entry.work_id for entry in build.entries}
    assert set(feed(wall_id).works) == {a.id}


def test_withdrawing_the_only_mastered_work_removes_the_feed_while_major_1_has_works(
    display, mastered, ready_work, theme_of, wall_id, wall_settings
):
    only, plain = mastered("A"), ready_work("B")
    display.activate_theme(theme_of(only, plain).id, wall_id=wall_id)

    display.exclude_work(only.id, wall_id=wall_id)

    # An empty feed would leave the excluded work up (a Player keeps the last
    # work through a gap); with none, the Player falls back to major 1.
    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_reconciling_away_the_only_mastered_work_removes_the_feed_while_major_1_has_works(
    services, display, mastered, ready_work, theme_of, wall_id, wall_settings
):
    only, plain = mastered("A"), ready_work("B")
    display.activate_theme(theme_of(only, plain).id, wall_id=wall_id)

    services.catalogue.archive_artwork(only.id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


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


def test_withdrawing_a_themes_only_work_leaves_both_majors_empty_and_agreeing(
    display, mastered, theme_of, wall_id, wall_settings, feed
):
    only = mastered("A")
    display.activate_theme(theme_of(only).id, wall_id=wall_id)

    display.exclude_work(only.id, wall_id=wall_id)

    manifest = json.loads(wall_settings.manifest_path(wall_id).read_text(encoding="utf-8"))
    assert manifest["entries"] == []
    assert feed(wall_id).works == {}
    assert feed(wall_id).slots == ()


def test_a_patched_entry_keeps_the_walls_settings(services, display, mastered, theme_of, wall_id, feed):
    a, b = mastered("A"), mastered("B")
    display.activate_theme(theme_of(a, b).id, wall_id=wall_id)
    display.set_mat_mode(wall_id, "full")

    services.catalogue.record_mat_color(artwork_id=b.id, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)

    assert feed(wall_id).settings == {"mat": {"mode": "full"}}
    assert feed(wall_id).works[b.id]["mat_color"] == "#3b2f2a"


def test_a_feed_left_holding_only_a_guest_is_removed_while_major_1_has_works(
    display, mastered, ready_work, theme_of, wall_id, wall_settings
):
    only, plain = mastered("A"), ready_work("B")
    display.activate_theme(theme_of(only, plain).id, wall_id=wall_id)
    display.show_work_now(wall_id, mastered("Guest").id)

    display.exclude_work(only.id, wall_id=wall_id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_a_re_hang_whose_members_all_lost_their_masters_removes_a_feed_holding_a_guest(
    display, mastered, theme_of, wall_id, wall_settings
):
    a = mastered("A")
    theme = theme_of(a)
    display.activate_theme(theme.id, wall_id=wall_id)
    display.show_work_now(wall_id, mastered("Guest").id)
    (wall_settings.art_root / f"masters/{a.id}.jpg").unlink()

    display.activate_theme(theme.id, wall_id=wall_id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


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
        {"backend": "framebuffer"},
        {"screen": {"width_px": 0, "height_px": 2160}},
        {"screen": {"width_px": 3840, "height_px": "2160"}},
        {"screen": {"width_px": True, "height_px": 2160}},
    ],
)
def test_a_heartbeat_with_a_screen_this_server_cannot_read_is_refused(display, wall_id, shown_by_a_client, capabilities):
    with pytest.raises(ServiceError, match="capabilities"):
        display.record_heartbeat(wall_id, {**_heartbeat(), "capabilities": capabilities})

    assert display.largest_screen(wall_id) is None


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


# -- a work that gains its master after a sync joins the feed ------------------------------


def test_a_work_that_gains_its_master_after_the_sync_joins_the_feed(
    services, display, mastered, ready_work, theme_of, wall_id, wall_settings, decodable_jpeg, feed
):
    early, late = mastered("Early"), ready_work("Late")
    display.activate_theme(theme_of(early, late).id, wall_id=wall_id)
    assert set(feed(wall_id).works) == {early.id}
    on_the_wall = feed(wall_id).on_the_wall(_now())

    path = f"masters/{late.id}.jpg"
    decodable_jpeg(wall_settings.art_root / path, width=3000, height=2000)
    services.catalogue.record_rendition(
        artwork_id=late.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )

    assert set(feed(wall_id).works) == {early.id, late.id}
    assert feed(wall_id).slots[0] == on_the_wall
    assert late.id in {slot.work_id for slot in feed(wall_id).slots}


def test_a_work_off_the_manifest_does_not_join_the_feed_when_it_gains_a_master(
    services, display, mastered, ready_work, theme_of, wall_id, wall_settings, decodable_jpeg, feed
):
    theme = theme_of(mastered("Early"))
    display.activate_theme(theme.id, wall_id=wall_id)
    outsider = ready_work("Added since the sync")
    display.add_to_theme(theme_id=theme.id, artwork_id=outsider.id)

    path = f"masters/{outsider.id}.jpg"
    decodable_jpeg(wall_settings.art_root / path, width=3000, height=2000)
    services.catalogue.record_rendition(
        artwork_id=outsider.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )

    # Deciding when new work reaches the wall is what sync is for.
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


def test_a_member_added_since_the_sync_and_pinned_does_not_join_the_feed_when_it_gains_a_master(
    services, display, mastered, theme_of, ready_work, wall_id, wall_settings, decodable_jpeg, feed
):
    theme = theme_of(mastered("A"), mastered("B"))
    display.activate_theme(theme.id, wall_id=wall_id)
    added = ready_work("Added since the sync")
    display.add_to_theme(theme_id=theme.id, artwork_id=added.id)
    display.show_work_now(wall_id, added.id)  # pinned on major 1; left off major 2 for want of a master

    path = f"masters/{added.id}.jpg"
    decodable_jpeg(wall_settings.art_root / path, width=3000, height=2000)
    services.catalogue.record_rendition(
        artwork_id=added.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )

    # The Library was asked about it (its pin names it), and it is a member of
    # the theme, but no manifest this wall carries has it: only a sync, or a
    # show now made once it has a master, puts it on the feed.
    assert added.id not in feed(wall_id).works
