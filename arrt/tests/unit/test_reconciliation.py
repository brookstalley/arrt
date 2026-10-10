"""Programming keeps every published feed true to what the Library will still show.

When the Library announces a change, Programming asks the facade about that work.
A work the Library now refuses comes off every wall whose published feed carries
it, including a work shown now from outside the theme. A work of a wall's hung
theme that the Library will now show, and the feed lacks, joins it without a
re-hang (the owner, 2026-10-10, superseding the 2026-09-30 ruling that additions
wait for sync). Startup reconciliation applies the same rules to every wall, and
publishes a hung theme's feed for a wall that has none, so an announcement lost
to a crash delays a correction and never leaves it undone.

Also here, because they rewrite the same document: `next` and `show_now` reach
the published feed, and a hang whose feed cannot be written is not recorded.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

import pytest

from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.records import FetchStatus, RenditionKind, ThemeMembership
from arrt.programming import display as display_module
from arrt.services.errors import ServiceError


def _published(settings, wall_id) -> dict:
    return json.loads(settings.manifest_v2_path(wall_id).read_text())


def _entry_ids(settings, wall_id) -> list[str]:
    """The works the wall's feed carries, in id order: the feed keys them, and order is the schedule's."""
    return sorted(_published(settings, wall_id)["works"])


def _master_of(service, work):
    return next(
        view.rendition for view in service.list_renditions(work.id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )


def _first(settings, wall_id) -> str:
    """The work the wall's schedule starts with."""
    return _published(settings, wall_id)["schedule"]["slots"][0]["work_id"]


@pytest.fixture
def hung(display):
    """Hang a theme holding these works on a wall, which publishes its feed."""

    def _hang(wall_id, *works, name="Late night"):
        theme = display.add_theme(name=name)
        for work in works:
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
        display.activate_theme(theme.id, wall_id=wall_id)
        return theme

    return _hang


@pytest.fixture
def study(display) -> str:
    return display.add_wall(name="Study").id


def _re_acquire(service, work) -> None:
    """A new master, which leaves the existing render stale."""
    service.record_original(
        artwork_id=work.id,
        source_id=service.list_sources(work.id)[0].id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="a-later-acquisition",
        fetch_status=FetchStatus.OK,
    )


# -- the handler: the feed follows what the Library will show -----------------------


def test_archiving_a_work_takes_it_off_exactly_the_walls_that_carry_it(
    service, display, ready_work, hung, wall_id, study, wall_settings
):
    shared = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    elsewhere = ready_work(title="Chop Suey")
    hung(wall_id, shared, kept)
    hung(study, elsewhere, name="Daylight")
    untouched = wall_settings.manifest_v2_path(study).read_bytes()

    service.archive_artwork(shared.id)

    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    assert wall_settings.manifest_v2_path(study).read_bytes() == untouched, "a wall not carrying the work was rewritten"


def test_a_work_on_two_walls_comes_off_both(service, ready_work, hung, wall_id, study, wall_settings):
    shared = ready_work()
    hung(wall_id, shared, ready_work(title="Automat"))
    hung(study, shared, ready_work(title="Chop Suey"), name="Daylight")

    service.archive_artwork(shared.id)

    assert shared.id not in _entry_ids(wall_settings, wall_id)
    assert shared.id not in _entry_ids(wall_settings, study)


def test_the_patch_changes_nothing_but_the_refused_entries(service, ready_work, hung, wall_id, wall_settings):
    """The playlist, the settings and the kept works' entries ride through untouched."""
    gone = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    hung(wall_id, gone, kept)
    before = _published(wall_settings, wall_id)

    service.archive_artwork(gone.id)

    after = _published(wall_settings, wall_id)
    for key in ("schema", "playlist"):
        assert after[key] == before[key], key
    assert after.get("settings") == before.get("settings")
    assert after["works"] == {kept.id: before["works"][kept.id]}


def test_a_render_left_stale_by_a_new_original_comes_off_the_wall(service, ready_work, hung, wall_id, wall_settings):
    work = ready_work()
    kept = ready_work(title="Automat")
    hung(wall_id, work, kept)

    _re_acquire(service, work)

    assert _entry_ids(wall_settings, wall_id) == [kept.id]


def test_accepting_a_work_no_hung_theme_holds_republishes_nothing(service, ready_work, hung, wall_id, wall_settings):
    hung(wall_id, ready_work())
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    service.add_artwork(title="Chop Suey")

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


def test_a_work_added_to_a_hung_theme_reaches_the_wall_at_once(service, display, ready_work, hung, wall_id, study, wall_settings):
    """No re-hang: the theme on the wall is the curator's choice, and its works follow it."""
    kept = ready_work(title="Chop Suey")
    theme = hung(wall_id, kept)
    hung(study, ready_work(title="Nighthawks"), name="Daylight")
    on_the_wall = _first(wall_settings, wall_id)
    untouched = wall_settings.manifest_v2_path(study).read_bytes()
    joining = ready_work(title="Automat")

    display.add_to_theme(theme_id=theme.id, artwork_id=joining.id)

    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, joining.id])
    assert _first(wall_settings, wall_id) == on_the_wall, "the work on the wall now finishes its slot"
    assert wall_settings.manifest_v2_path(study).read_bytes() == untouched, "a wall hanging another theme was rewritten"


def test_many_works_added_to_a_hung_theme_reach_the_wall(display, ready_work, hung, wall_id, wall_settings):
    kept = ready_work(title="Chop Suey")
    theme = hung(wall_id, kept)
    joining = [ready_work(title="Automat"), ready_work(title="Nighthawks")]

    display.add_works_to_theme(theme_id=theme.id, artwork_ids=[work.id for work in joining])

    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, *(work.id for work in joining)])


def test_a_work_added_that_cannot_be_shown_rewrites_nothing(display, ready_work, hung, wall_id, wall_settings):
    """A theme member the Library refuses joins no feed, so the wall's feed is left byte for byte."""
    theme = hung(wall_id, ready_work(title="Chop Suey"))
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work(title="Automat", master=False).id)

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


def test_a_work_taken_out_of_a_hung_theme_leaves_the_wall_at_once(display, ready_work, hung, wall_id, wall_settings):
    leaving, kept, also = ready_work(title="Automat"), ready_work(title="Chop Suey"), ready_work(title="Nighthawks")
    theme = hung(wall_id, leaving, kept, also)

    display.remove_from_theme(theme_id=theme.id, artwork_id=leaving.id)
    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, also.id])

    display.remove_works_from_theme(theme_id=theme.id, artwork_ids=[also.id])
    assert _entry_ids(wall_settings, wall_id) == [kept.id]


def test_an_archive_takes_its_work_off_and_leaves_the_rest_of_the_theme_on(
    service, display, ready_work, hung, wall_id, wall_settings
):
    gone = ready_work(title="Nighthawks")
    kept = ready_work(title="Chop Suey")
    theme = hung(wall_id, gone, kept)
    joined = ready_work(title="Automat")
    display.add_to_theme(theme_id=theme.id, artwork_id=joined.id)

    service.archive_artwork(gone.id)

    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, joined.id])


def test_a_work_allowed_back_reaches_the_walls_whose_theme_holds_it_and_no_other(
    display, ready_work, hung, wall_id, study, wall_settings
):
    work, kept = ready_work(title="Automat"), ready_work(title="Chop Suey")
    hung(wall_id, work, kept)
    hung(study, ready_work(title="Nighthawks"), name="Daylight")
    display.exclude_work(work.id)
    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    untouched = wall_settings.manifest_v2_path(study).read_bytes()

    display.allow_work(work.id)

    assert _entry_ids(wall_settings, wall_id) == sorted([work.id, kept.id])
    assert wall_settings.manifest_v2_path(study).read_bytes() == untouched, "a wall whose theme lacks it was rewritten"


def test_a_restored_work_goes_back_on_the_wall(service, ready_work, hung, wall_id, wall_settings):
    """Archive takes it off and Restore puts it back, each as it lands, as the Work page says."""
    work, kept = ready_work(title="Automat"), ready_work(title="Chop Suey")
    hung(wall_id, work, kept)
    service.archive_artwork(work.id)
    assert _entry_ids(wall_settings, wall_id) == [kept.id]

    service.restore_artwork(work.id)

    assert _entry_ids(wall_settings, wall_id) == sorted([work.id, kept.id])


def test_a_work_that_gains_its_master_joins_the_hung_themes_feed(
    service, ready_work, hung, wall_id, wall_settings, decodable_jpeg
):
    """Readiness gained reaches the wall, as any addition to the hung theme does."""
    unmastered = ready_work(title="Automat", master=False)
    kept = ready_work()
    hung(wall_id, kept, unmastered)
    assert _entry_ids(wall_settings, wall_id) == [kept.id]

    decodable_jpeg(wall_settings.art_root / "masters/a.jpg", width=400, height=300)
    service.record_rendition(
        artwork_id=unmastered.id,
        kind=RenditionKind.PRESENTATION_MASTER,
        target_width=7680,
        target_height=7680,
        path="masters/a.jpg",
    )

    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, unmastered.id])


def test_a_new_work_accepted_into_the_hung_default_theme_reaches_the_wall(display, ready_work, hung, wall_id, wall_settings):
    """The whole chain through the Library's announcements: acceptance offers the default, the master makes it showable."""
    kept = ready_work(title="Chop Suey")
    theme = hung(wall_id, kept, name="All works")
    display.make_default(theme.id)

    arrived = ready_work(title="Automat")

    assert _entry_ids(wall_settings, wall_id) == sorted([kept.id, arrived.id])


# -- a work shown now --------------------------------------------------------------


def test_archiving_takes_a_work_shown_now_off_every_wall_showing_it(
    service, display, ready_work, hung, wall_id, study, wall_settings
):
    """A work shown from outside the theme is in the feed as a guest, and leaves it like any other."""
    guest = ready_work(title="Nighthawks")
    hung(wall_id, ready_work(title="Automat"))
    hung(study, ready_work(title="Chop Suey"), name="Daylight")
    display.show_work_now(wall_id, guest.id)
    display.show_work_now(study, guest.id)

    service.archive_artwork(guest.id)

    assert guest.id not in _entry_ids(wall_settings, wall_id)
    assert guest.id not in _entry_ids(wall_settings, study)
    assert guest.id not in {_first(wall_settings, wall_id), _first(wall_settings, study)}


def test_a_work_shown_now_whose_render_went_stale_leaves_the_wall(service, display, ready_work, hung, wall_id, wall_settings):
    """The same rule as reconciliation's, so a restart cannot disagree with the running server."""
    hung(wall_id, ready_work(title="Automat"))
    work = ready_work()
    display.show_work_now(wall_id, work.id)

    _re_acquire(service, work)

    assert work.id not in _entry_ids(wall_settings, wall_id)


def test_the_library_alone_leaves_programmings_feeds_alone(store, display, ready_work, hung, wall_id, wall_settings):
    """With nobody listening, archiving rewrites no feed: the Library writes nothing of Programming's."""
    work = ready_work()
    hung(wall_id, work, ready_work(title="Automat"))
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    CatalogueService(store).archive_artwork(work.id)

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


# -- reconciliation at startup --------------------------------------------------


def test_startup_repairs_a_feed_that_a_lost_announcement_left_stale(store, services, ready_work, hung, wall_id, wall_settings):
    """The Library's change is committed with no subscriber, as if the process died before the handler."""
    gone = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    hung(wall_id, gone, kept)
    services.display.show_work_now(wall_id, gone.id)
    CatalogueService(store).archive_artwork(gone.id)
    assert _entry_ids(wall_settings, wall_id) == sorted([gone.id, kept.id]), "the announcement was not lost after all"

    services.reconcile()

    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    assert _first(wall_settings, wall_id) == kept.id


def test_a_second_start_finds_nothing_to_do_and_says_so(store, services, ready_work, hung, wall_id, caplog):
    gone = ready_work()
    hung(wall_id, gone, ready_work(title="Automat"))
    CatalogueService(store).archive_artwork(gone.id)

    first = services.display.reconcile()
    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        second = services.display.reconcile()

    assert first.changed
    assert not second.changed
    assert second.republished == ()
    assert any("nothing to change" in record.getMessage() for record in caplog.records)


def test_startup_publishes_the_hung_themes_feed_for_a_wall_that_has_none(services, ready_work, hung, wall_id, wall_settings):
    """A wall with a theme hung and no feed, as the wave 4g upgrade left one: it shows nothing new until it has one."""
    works = [ready_work(title="Nighthawks"), ready_work(title="Automat")]
    hung(wall_id, *works)
    wall_settings.manifest_v2_path(wall_id).unlink()

    result = services.display.reconcile()

    assert result.republished == (wall_id,)
    assert _entry_ids(wall_settings, wall_id) == sorted(work.id for work in works)


def test_an_announcement_about_a_member_that_still_cannot_join_rewrites_nothing(
    store, services, ready_work, hung, wall_id, study, wall_settings
):
    """Republishing reshuffles the future, so it happens only when a work joins.

    Each wall's theme holds a member its feed lacks for a reason that stays
    true: one with no master, and one kept off every wall. Both are asked
    about by name, neither may cause a rewrite, and nor may a start.
    """
    unmastered = ready_work(title="Automat", master=False)
    hung(wall_id, ready_work(title="Chop Suey"), unmastered)
    kept_off = ready_work(title="Nighthawks")
    hung(study, ready_work(title="Night Windows"), kept_off, name="Daylight")
    services.display.exclude_work(kept_off.id)
    before = {wall: wall_settings.manifest_v2_path(wall).read_bytes() for wall in (wall_id, study)}

    named = services.display.reconcile([unmastered.id, kept_off.id], cause="re-rendered")
    at_start = services.display.reconcile()

    assert named.asked == 2
    assert not named.changed
    assert not at_start.changed
    assert {wall: wall_settings.manifest_v2_path(wall).read_bytes() for wall in (wall_id, study)} == before


def test_a_wall_with_nothing_hung_gains_no_feed_at_startup(display, wall_id, wall_settings):
    display.reconcile()

    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_a_start_with_nothing_published_asks_about_nothing(display):
    assert display.reconcile().asked == 0


def test_an_unreadable_feed_is_left_for_the_next_sync(display, ready_work, hung, wall_id, wall_settings, caplog):
    hung(wall_id, ready_work())
    wall_settings.manifest_v2_path(wall_id).write_text("{not json")

    with caplog.at_level(logging.WARNING, logger="arrt.programming.manifest.v2"):
        result = display.reconcile()

    assert not result.changed
    assert wall_settings.manifest_v2_path(wall_id).read_text() == "{not json"
    assert any("cannot be read" in record.getMessage() for record in caplog.records)


# -- next and show_now reach the wall ------------------------------------------------


def test_next_reaches_the_published_feed_without_a_sync(display, ready_work, hung, wall_id, wall_settings):
    """The Player reads only its feed, so a step has to be a republish of it."""
    first, second = ready_work(title="Nighthawks"), ready_work(title="Automat")
    theme = hung(wall_id, first, second)
    display.update_theme(theme.id, shuffle=False)
    display.sync(wall_id)
    on_the_wall = _first(wall_settings, wall_id)
    before = _published(wall_settings, wall_id)

    stepped_to = display.step_display(wall_id)

    after = _published(wall_settings, wall_id)
    assert stepped_to == _first(wall_settings, wall_id) != on_the_wall
    assert after["works"] == before["works"]


def test_show_now_reaches_the_published_feed_without_a_sync(display, ready_work, hung, wall_id, wall_settings):
    work = ready_work()
    hung(wall_id, ready_work(title="Automat"), work)

    display.show_work_now(wall_id, work.id)

    assert _first(wall_settings, wall_id) == work.id


def test_a_step_publishes_no_work_the_feed_does_not_carry(store, display, ready_work, hung, wall_id, wall_settings):
    """A step moves the wall on through the works published; adding is the hung theme's business, not a step's."""
    theme = hung(wall_id, ready_work(title="Nighthawks"))
    before = _entry_ids(wall_settings, wall_id)
    # Written around the service, as a membership whose follow-up a crash lost.
    store.add_membership(
        ThemeMembership(theme_id=theme.id, artwork_id=ready_work(title="Automat").id, added_at=datetime.now(UTC))
    )

    display.step_display(wall_id)

    assert _entry_ids(wall_settings, wall_id) == before


def test_a_step_on_a_wall_with_nothing_published_is_refused_and_writes_no_feed(display, wall_id, wall_settings):
    """Answering "skipped" while nothing moves is the silence this product avoids, so it says why."""
    with pytest.raises(ServiceError, match="Nothing has been hung on 'The wall' yet"):
        display.step_display(wall_id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_a_step_that_cannot_reach_the_wall_leaves_the_feed_as_it_was(
    display, ready_work, hung, wall_id, wall_settings, monkeypatch
):
    hung(wall_id, ready_work(), ready_work(title="Automat"))
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    def full_disk(path, document):
        raise OSError("No space left on device")

    monkeypatch.setattr(display_module, "write_atomically", full_disk)
    with pytest.raises(OSError, match="No space left on device"):
        display.step_display(wall_id)

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


# -- a hang whose manifest cannot be written ------------------------------------------


def test_a_hang_whose_manifest_cannot_be_written_is_not_recorded(display, ready_work, hung, wall_id, monkeypatch):
    """The catalogue must not name a theme the wall is not showing (backlog #35)."""
    first = hung(wall_id, ready_work(title="Nighthawks"))
    second = display.add_theme(name="Daylight")
    display.add_to_theme(theme_id=second.id, artwork_id=ready_work(title="Automat").id)

    def full_disk(path, document):
        raise OSError("No space left on device")

    monkeypatch.setattr(display_module, "write_atomically", full_disk)
    with pytest.raises(OSError, match="No space left on device"):
        display.activate_theme(second.id, wall_id=wall_id)

    assert display.hanging_on(wall_id).id == first.id


def test_a_hang_that_is_refused_before_writing_changes_nothing(display, wall_id):
    with pytest.raises(ServiceError):
        display.activate_theme("no-such-theme", wall_id=wall_id)

    assert display.hanging_on(wall_id) is None


def test_a_feed_whose_slots_are_malformed_is_left_for_the_next_sync(display, ready_work, hung, wall_id, wall_settings):
    """Reconciliation runs before the plane serves, so a bad slot must not stop it starting."""
    hung(wall_id, ready_work())
    document = _published(wall_settings, wall_id)
    document["schedule"]["slots"].append("not a slot")
    wall_settings.manifest_v2_path(wall_id).write_text(json.dumps(document))

    assert not display.reconcile().changed


def test_a_start_that_cannot_rewrite_a_manifest_still_serves(
    store, services, ready_work, hung, wall_id, wall_settings, monkeypatch, caplog
):
    """The wall keeps its last feed; the interface is where a curator finds out why."""
    gone = ready_work()
    hung(wall_id, gone, ready_work(title="Automat"))
    CatalogueService(store).archive_artwork(gone.id)

    def full_disk(path, document):
        raise OSError("No space left on device")

    monkeypatch.setattr(display_module, "write_atomically", full_disk)
    with caplog.at_level(logging.ERROR, logger="arrt.services.container"):
        services.reconcile()

    assert any("serving anyway" in record.getMessage() for record in caplog.records)
    assert gone.id in _entry_ids(wall_settings, wall_id), "the failed write changed the feed after all"
    monkeypatch.undo()
    services.reconcile()
    assert gone.id not in _entry_ids(wall_settings, wall_id)


def test_each_wall_names_only_the_works_it_lost(store, display, ready_work, hung, wall_id, study, caplog):
    """A start that finds two works refused on two walls names each on its own wall's line."""
    first = ready_work(title="Nighthawks")
    second = ready_work(title="Automat")
    hung(wall_id, first, ready_work(title="Kept"))
    hung(study, second, name="Daylight")
    unheard = CatalogueService(store)
    unheard.archive_artwork(first.id)
    unheard.archive_artwork(second.id)

    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        display.reconcile()

    lines = [record.getMessage() for record in caplog.records if "took works" in record.getMessage()]
    assert len(lines) == 2, lines
    assert [line for line in lines if first.id in line] == [line for line in lines if second.id not in line]
    assert [line for line in lines if second.id in line] == [line for line in lines if first.id not in line]


def test_a_new_master_points_the_published_feed_at_the_new_bytes(
    store, service, display, ready_work, hung, wall_id, wall_settings, decodable_jpeg
):
    """The old hash is one `/media` no longer serves, so the entry follows the master without a sync.

    A patch, not a rebuild: a member the feed lacks, written around the service
    so nothing announced it, is not published by an announcement about another
    work, and no slot moves.
    """
    work = ready_work()
    master = next(
        view.rendition for view in service.list_renditions(work.id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )
    target = wall_settings.art_root / master.relative_path
    theme = hung(wall_id, work)
    before = _published(wall_settings, wall_id)
    waiting = ready_work(title="Automat")
    store.add_membership(ThemeMembership(theme_id=theme.id, artwork_id=waiting.id, added_at=datetime.now(UTC)))

    decodable_jpeg(target, width=400, height=300, color=(200, 40, 40))
    service.record_rendition(
        artwork_id=work.id,
        kind=master.kind,
        target_width=master.target_width,
        target_height=master.target_height,
        path=master.relative_path,
    )

    after = _published(wall_settings, wall_id)
    assert list(after["works"]) == [work.id], "a sync's worth of works was published"
    assert after["works"][work.id]["media"]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert before["works"][work.id]["media"]["sha256"] != after["works"][work.id]["media"]["sha256"]
    assert after["schedule"] == before["schedule"], "a new master moved a slot"


def test_a_master_that_cannot_be_read_takes_the_work_off_the_feed_and_says_so(
    service, ready_work, hung, wall_id, wall_settings, caplog
):
    """There is no file channel to fall back on, so a work whose master cannot be sent leaves the feed."""
    work = ready_work()
    kept = ready_work(title="Automat")
    master = next(
        view.rendition for view in service.list_renditions(work.id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )
    target = wall_settings.art_root / master.relative_path
    hung(wall_id, work, kept)
    assert work.id in _entry_ids(wall_settings, wall_id), "the work was never published"

    target.unlink()
    target.mkdir()
    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        service.record_rendition(
            artwork_id=work.id,
            kind=master.kind,
            target_width=master.target_width,
            target_height=master.target_height,
            path=master.relative_path,
        )

    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    assert any("took works the Library no longer offers off the feed" in record.getMessage() for record in caplog.records)


def test_an_announcement_about_one_work_asks_the_library_about_that_work_alone(display, ready_work, hung, wall_id):
    """The facade is written as if remote, so a change to one work costs one question, not one per work on every wall."""
    changed = ready_work(title="Nighthawks")
    hung(wall_id, changed, ready_work(title="Automat"), ready_work(title="Chop Suey"))

    assert display.reconcile([changed.id], cause="re-rendered").asked == 1
    assert display.reconcile().asked == 3


def test_a_step_on_a_wall_whose_feed_holds_nothing_is_refused_and_writes_nothing(
    service, display, ready_work, hung, wall_id, wall_settings
):
    """A hung theme none of whose works can be sent has an empty feed; "skipped" would claim a move that cannot happen."""
    only = ready_work()
    hung(wall_id, only)
    service.archive_artwork(only.id)
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()
    assert json.loads(before)["works"] == {}, "the feed still holds a work, so this checks nothing"

    with pytest.raises(ServiceError, match="nothing to move on to"):
        display.step_display(wall_id)

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before
