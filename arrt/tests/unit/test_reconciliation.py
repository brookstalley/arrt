"""Programming keeps every published manifest true to what the Library will still show.

When the Library announces a change, Programming asks the facade about that work.
A work the Library now refuses comes off every wall whose published manifest
carries it, and any pin naming it is withdrawn. Nothing else in the document
changes, so a work added to a theme since its last sync is not published as a
side effect: additions wait for sync (the operator's ruling, 2026-09-30).
Startup reconciliation applies the same rule to every wall, so an announcement
lost to a crash delays a correction and never leaves it undone.

Also here, because they are the same patch applied to the same document: `next`
and `show_now` reach the published manifest, and a hang whose manifest cannot be
written is not recorded.
"""

import hashlib
import json
import logging

import pytest

from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.records import FetchStatus, RenditionKind
from arrt.programming import display as display_module
from arrt.services.errors import ServiceError


def _published(settings, wall_id) -> dict:
    return json.loads(settings.manifest_path(wall_id).read_text())


def _entry_ids(settings, wall_id) -> list[str]:
    return [entry["work_id"] for entry in _published(settings, wall_id)["entries"]]


@pytest.fixture
def hung(display):
    """Hang a theme holding these works on a wall, which publishes its manifest."""

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


# -- the handler: removals republish, additions wait --------------------------------


def test_archiving_a_work_takes_it_off_exactly_the_walls_that_carry_it(
    service, display, ready_work, hung, wall_id, study, wall_settings
):
    shared = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    elsewhere = ready_work(title="Chop Suey")
    hung(wall_id, shared, kept)
    hung(study, elsewhere, name="Daylight")
    untouched = wall_settings.manifest_path(study).read_bytes()

    service.archive_artwork(shared.id)

    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    assert wall_settings.manifest_path(study).read_bytes() == untouched, "a wall not carrying the work was rewritten"


def test_a_work_on_two_walls_comes_off_both(service, ready_work, hung, wall_id, study, wall_settings):
    shared = ready_work()
    hung(wall_id, shared)
    hung(study, shared, name="Daylight")

    service.archive_artwork(shared.id)

    assert _entry_ids(wall_settings, wall_id) == []
    assert _entry_ids(wall_settings, study) == []


def test_the_patch_changes_nothing_but_the_refused_entries(service, ready_work, hung, wall_id, wall_settings):
    """Theme, rotation, directive and the kept entries' labels ride through untouched."""
    gone = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    hung(wall_id, gone, kept)
    before = _published(wall_settings, wall_id)

    service.archive_artwork(gone.id)

    after = _published(wall_settings, wall_id)
    for key in ("schema", "theme", "rotation", "directive"):
        assert after[key] == before[key], key
    assert after["entries"] == [entry for entry in before["entries"] if entry["work_id"] == kept.id]


def test_a_render_left_stale_by_a_new_master_comes_off_the_wall(service, ready_work, hung, wall_id, wall_settings):
    work = ready_work()
    hung(wall_id, work)

    _re_acquire(service, work)

    assert _entry_ids(wall_settings, wall_id) == []


def test_accepting_a_work_republishes_nothing(service, ready_work, hung, wall_id, wall_settings):
    hung(wall_id, ready_work())
    before = wall_settings.manifest_path(wall_id).read_bytes()

    service.add_artwork(title="Chop Suey")

    assert wall_settings.manifest_path(wall_id).read_bytes() == before


def test_a_work_added_since_the_last_sync_is_not_published_by_an_archive(
    service, display, ready_work, hung, wall_id, wall_settings
):
    """Additions wait for sync, even when a removal rewrites the same document."""
    gone = ready_work(title="Nighthawks")
    theme = hung(wall_id, gone)
    waiting = ready_work(title="Automat")
    display.add_to_theme(theme_id=theme.id, artwork_id=waiting.id)

    service.archive_artwork(gone.id)

    assert _entry_ids(wall_settings, wall_id) == []
    display.sync(wall_id)
    assert _entry_ids(wall_settings, wall_id) == [waiting.id]


def test_a_new_render_does_not_republish(service, ready_work, hung, wall_id, wall_settings):
    """Readiness gained waits for sync, like any addition."""
    unrendered = ready_work(title="Automat", rendition=False)
    hung(wall_id, ready_work(), unrendered)
    before = wall_settings.manifest_path(wall_id).read_bytes()

    service.record_rendition(
        artwork_id=unrendered.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path="ready/a.jpg"
    )

    assert wall_settings.manifest_path(wall_id).read_bytes() == before


# -- pins -----------------------------------------------------------------------


def test_archiving_withdraws_the_pin_on_every_wall_that_holds_it(service, display, ready_work, wall_id, study):
    work = ready_work()
    display.show_work_now(wall_id, work.id)
    display.show_work_now(study, work.id)

    service.archive_artwork(work.id)

    assert display.read_directive(wall_id).pinned_work_id is None
    assert display.read_directive(study).pinned_work_id is None


def test_a_withdrawn_pin_leaves_the_published_directive_unpinned_and_unadvanced(
    service, display, ready_work, hung, wall_id, wall_settings
):
    work = ready_work()
    hung(wall_id, work)
    display.show_work_now(wall_id, work.id)
    sequence = _published(wall_settings, wall_id)["directive"]["sequence"]

    service.archive_artwork(work.id)

    assert _published(wall_settings, wall_id)["directive"] == {"sequence": sequence, "pinned_work_id": None}
    assert display.read_directive(wall_id).sequence == sequence


def test_a_pin_on_a_work_whose_render_went_stale_is_withdrawn(service, display, ready_work, wall_id):
    """The same rule as reconciliation's, so a restart cannot disagree with the running server."""
    work = ready_work()
    display.show_work_now(wall_id, work.id)

    _re_acquire(service, work)

    assert display.read_directive(wall_id).pinned_work_id is None


def test_the_library_alone_leaves_programmings_pins_alone(store, display, ready_work, wall_id):
    """With nobody listening, archiving writes no directive: the Library writes no Programming table."""
    work = ready_work()
    display.show_work_now(wall_id, work.id)

    CatalogueService(store).archive_artwork(work.id)

    assert display.read_directive(wall_id).pinned_work_id == work.id


# -- reconciliation at startup --------------------------------------------------


def test_startup_repairs_a_manifest_and_a_pin_that_a_lost_announcement_left_stale(
    store, services, ready_work, hung, wall_id, wall_settings
):
    """The Library's change is committed with no subscriber, as if the process died before the handler."""
    gone = ready_work(title="Nighthawks")
    kept = ready_work(title="Automat")
    hung(wall_id, gone, kept)
    services.display.show_work_now(wall_id, gone.id)
    CatalogueService(store).archive_artwork(gone.id)
    assert _entry_ids(wall_settings, wall_id) == [gone.id, kept.id], "the announcement was not lost after all"

    services.reconcile()

    assert _entry_ids(wall_settings, wall_id) == [kept.id]
    assert services.display.read_directive(wall_id).pinned_work_id is None


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
    assert second.pins_withdrawn == ()
    assert any("nothing to change" in record.getMessage() for record in caplog.records)


def test_a_start_with_nothing_published_asks_about_nothing(display):
    assert display.reconcile().asked == 0


def test_an_unreadable_manifest_is_left_for_the_next_sync(display, ready_work, hung, wall_id, wall_settings, caplog):
    hung(wall_id, ready_work())
    wall_settings.manifest_path(wall_id).write_text("{not json")

    with caplog.at_level(logging.WARNING, logger="arrt.programming.manifest.builder"):
        result = display.reconcile()

    assert not result.changed
    assert wall_settings.manifest_path(wall_id).read_text() == "{not json"
    assert any("not valid JSON" in record.getMessage() for record in caplog.records)


# -- next and show_now reach the wall ------------------------------------------------


def test_next_reaches_the_published_manifest_without_a_sync(display, ready_work, hung, wall_id, wall_settings):
    """The Player reads its directive only from the manifest, so one left in the catalogue never arrives."""
    hung(wall_id, ready_work())
    before = _published(wall_settings, wall_id)

    directive = display.step_display(wall_id)

    after = _published(wall_settings, wall_id)
    assert after["directive"] == {"sequence": directive.sequence, "pinned_work_id": None}
    assert after["directive"]["sequence"] == before["directive"]["sequence"] + 1
    assert after["entries"] == before["entries"]


def test_show_now_reaches_the_published_manifest_without_a_sync(display, ready_work, hung, wall_id, wall_settings):
    work = ready_work()
    hung(wall_id, work)

    display.show_work_now(wall_id, work.id)

    assert _published(wall_settings, wall_id)["directive"]["pinned_work_id"] == work.id


def test_a_step_publishes_no_work_added_since_the_last_sync(display, ready_work, hung, wall_id, wall_settings):
    theme = hung(wall_id, ready_work(title="Nighthawks"))
    before = _entry_ids(wall_settings, wall_id)
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work(title="Automat").id)

    display.step_display(wall_id)

    assert _entry_ids(wall_settings, wall_id) == before


def test_a_step_on_a_wall_with_nothing_published_writes_no_manifest(display, wall_id, wall_settings):
    display.step_display(wall_id)

    assert not wall_settings.manifest_path(wall_id).exists()


def test_a_step_that_cannot_reach_the_wall_is_not_recorded(display, ready_work, hung, wall_id, monkeypatch):
    hung(wall_id, ready_work())
    sequence = display.read_directive(wall_id).sequence

    def full_disk(path, document):
        raise OSError("No space left on device")

    monkeypatch.setattr(display_module, "write_atomically", full_disk)
    with pytest.raises(OSError, match="No space left on device"):
        display.step_display(wall_id)

    assert display.read_directive(wall_id).sequence == sequence


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


def test_a_manifest_whose_entries_are_malformed_is_left_for_the_next_sync(display, ready_work, hung, wall_id, wall_settings):
    """Reconciliation runs before the plane serves, so a bad entry must not stop it starting."""
    hung(wall_id, ready_work())
    document = _published(wall_settings, wall_id)
    document["entries"].append("not an entry")
    wall_settings.manifest_path(wall_id).write_text(json.dumps(document))

    assert not display.reconcile().changed


def test_a_start_that_cannot_rewrite_a_manifest_still_serves(
    store, services, ready_work, hung, wall_id, wall_settings, monkeypatch, caplog
):
    """The wall keeps its last manifest; the interface is where a curator finds out why."""
    gone = ready_work()
    hung(wall_id, gone, ready_work(title="Automat"))
    services.display.show_work_now(wall_id, gone.id)
    CatalogueService(store).archive_artwork(gone.id)

    def full_disk(path, document):
        raise OSError("No space left on device")

    monkeypatch.setattr(display_module, "write_atomically", full_disk)
    with caplog.at_level(logging.ERROR, logger="arrt.services.container"):
        services.reconcile()

    assert any("serving anyway" in record.getMessage() for record in caplog.records)
    # Nothing half-applied: the pin withdrawal rolled back with the failed write.
    assert services.display.read_directive(wall_id).pinned_work_id == gone.id
    monkeypatch.undo()
    services.reconcile()
    assert services.display.read_directive(wall_id).pinned_work_id is None


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


def test_a_re_render_points_the_published_manifest_at_the_new_bytes(service, display, ready_work, hung, wall_id, wall_settings):
    """The old hash is one `/media` no longer serves, so the entry follows the render without a sync."""
    work = ready_work()
    render = next(view.rendition for view in service.list_renditions(work.id))
    target = wall_settings.art_root / render.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"the first render")
    theme = hung(wall_id, work)
    before = _published(wall_settings, wall_id)
    waiting = ready_work(title="Automat")
    display.add_to_theme(theme_id=theme.id, artwork_id=waiting.id)

    target.write_bytes(b"the render, redone")
    service.record_rendition(
        artwork_id=work.id,
        kind=render.kind,
        target_width=render.target_width,
        target_height=render.target_height,
        path=render.relative_path,
    )

    after = _published(wall_settings, wall_id)
    assert [entry["work_id"] for entry in after["entries"]] == [work.id], "a sync's worth of works was published"
    assert after["entries"][0]["media"]["sha256"] == hashlib.sha256(b"the render, redone").hexdigest()
    assert before["entries"][0]["media"]["sha256"] != after["entries"][0]["media"]["sha256"]
    assert {k: v for k, v in after["entries"][0].items() if k != "media"} == {
        k: v for k, v in before["entries"][0].items() if k != "media"
    }


def test_a_re_render_that_cannot_be_read_takes_the_media_off_the_entry_and_says_so(
    service, ready_work, hung, wall_id, wall_settings, caplog
):
    """The entry stays for the file channel, and names no hash `/media` would refuse."""
    work = ready_work()
    render = next(view.rendition for view in service.list_renditions(work.id))
    target = wall_settings.art_root / render.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"the first render")
    hung(wall_id, work)
    assert "media" in _published(wall_settings, wall_id)["entries"][0], "no media was ever published"

    target.unlink()
    target.mkdir()
    with caplog.at_level(logging.INFO, logger="arrt.programming.display"):
        service.record_rendition(
            artwork_id=work.id,
            kind=render.kind,
            target_width=render.target_width,
            target_height=render.target_height,
            path=render.relative_path,
        )

    entry = _published(wall_settings, wall_id)["entries"][0]
    assert entry["work_id"] == work.id
    assert "media" not in entry
    assert any("pointed the published manifest at the current render" in record.getMessage() for record in caplog.records)
