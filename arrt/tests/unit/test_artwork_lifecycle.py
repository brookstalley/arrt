"""The Artwork state machine, and what it means for a work shown on a wall now.

An artwork has exactly two states and four edges, two of which are refusals. It
never carries a pending or rejected state: everything before acceptance is a
candidate, which is a separate entity with its own verdict, so there is no second
lifecycle here to drift out of step with that one.

Showing a work now is tested with the lifecycle because the two meet: a work
taken out of circulation cannot be put on a wall.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from arrt.library.dimensions import Units
from arrt.library.facade import LibraryFacade
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.discovery import DiscoveryService
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import (
    ArtworkStatus,
    MatMethod,
    Theme,
)
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.programming.display import DisplayService, DisplaySettings
from arrt.services.errors import ServiceError


def _display(store, tmp_path, *, catalogue=None):
    """A display service over an explicitly opened store, wired as the entry point wires one."""
    catalogue = catalogue or CatalogueService(store)
    # The discovery tables share the catalogue's open file, as in the container.
    discovery = DiscoveryService(SqliteDiscovery(store._store), catalogue)
    return DisplayService(
        store,
        LibraryFacade(catalogue, discovery, label_units=Units.IMPERIAL),
        DisplaySettings(art_root=tmp_path, rotation_interval_seconds=180, shuffle=True),
    )


def test_a_work_can_be_taken_out_of_circulation_and_brought_back(service):
    work = service.add_artwork(title="Nighthawks")

    archived = service.archive_artwork(work.id)
    assert archived.status is ArtworkStatus.ARCHIVED
    assert service.get_artwork(work.id).artwork.status is ArtworkStatus.ARCHIVED

    restored = service.restore_artwork(work.id)
    assert restored.status is ArtworkStatus.ACCEPTED
    assert service.get_artwork(work.id).artwork.status is ArtworkStatus.ACCEPTED


def test_archiving_an_archived_work_is_refused_rather_than_ignored(service):
    work = service.add_artwork(title="Nighthawks")
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError, match="already archived"):
        service.archive_artwork(work.id)


def test_restoring_a_work_that_was_never_archived_is_refused(service):
    work = service.add_artwork(title="Nighthawks")

    with pytest.raises(ServiceError, match="not archived"):
        service.restore_artwork(work.id)


def test_archiving_an_unknown_work_names_the_id_it_could_not_find(service):
    with pytest.raises(ServiceError, match="No artwork with id 'nope'"):
        service.archive_artwork("nope")


def test_archiving_keeps_the_record_and_its_mat_history(service):
    """Archiving is removal from circulation, not deletion — that is the whole point.

    The mat colours are the expensive part: each one cost a model call, and the
    hand-tuned ones are this product's quality corpus.
    """
    work = service.add_artwork(title="Nighthawks")
    service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    service.record_mat_color(artwork_id=work.id, hex_rgb="#3a3a3a", method=MatMethod.MANUAL)

    service.archive_artwork(work.id)

    assert len(service.mat_color_history(work.id)) == 2
    assert service.current_mat_color(work.id).hex_rgb == "#3a3a3a"


def test_an_archived_work_moves_between_the_status_listings(service):
    work = service.add_artwork(title="Nighthawks")
    service.archive_artwork(work.id)

    assert service.list_artworks(status="accepted").total == 0
    assert service.list_artworks(status="archived").total == 1
    # "The whole catalogue" still means both.
    assert service.list_artworks().total == 1


# -- a work shown now -------------------------------------------------------------


def test_archiving_some_other_work_leaves_the_work_shown_now_alone(service, ready_work, display, wall_id, wall_settings):
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work(title="Automat").id)
    display.activate_theme(theme.id, wall_id=wall_id)
    shown = ready_work()
    other = service.add_artwork(title="Chop Suey")
    display.show_work_now(wall_id, shown.id)
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()

    service.archive_artwork(other.id)

    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


def test_an_archived_work_cannot_be_shown_now(service, ready_work, display, wall_id):
    work = ready_work()
    service.archive_artwork(work.id)

    with pytest.raises(ServiceError, match="archived"):
        display.show_work_now(wall_id, work.id)


def test_showing_an_unknown_work_now_is_refused(display, wall_id):
    """In the catalogue's words alone, not as a work that "cannot be shown on the wall".

    An id that names nothing is a different mistake from a work that is not ready,
    and a curator told the second goes looking for a missing render.
    """
    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, "nope")

    assert str(refused.value) == "No artwork with id 'nope' is in the catalogue."


def test_adding_an_unknown_work_to_a_theme_is_refused_in_the_catalogues_words(display):
    """Programming asks the Library whether the work exists, and says what the catalogue says.

    Without the question, the add reaches the store and fails on its foreign key,
    as a storage error nobody wrote for a curator.
    """
    theme = display.add_theme(name="Hopper")

    with pytest.raises(ServiceError) as refused:
        display.add_to_theme(theme_id=theme.id, artwork_id="nope")

    assert str(refused.value) == "No artwork with id 'nope' is in the catalogue."
    assert display.theme_work_ids(theme.id) == []


# -- nothing is ever hung by anything but a curator -----------------------------
#
# This section asserted the opposite until 2026-08-12, and the reversal is a
# ruling rather than a relaxation. `reconcile` promoted the oldest theme when
# none was active, and `add_theme` promoted a new one for the same reason: a
# catalogue with themes and none active left the display plane no sync target.
# With more than one wall that rule hangs the same theme in every room unbidden,
# and "a wall with nothing on it" is now a designed state rather than a broken
# one — so the promotion is dropped and these are what is left to hold.


def _catalogue_with_unhung_themes(path):
    """Two themes, neither hanging anywhere. The ordinary state of a fresh catalogue."""
    catalogue = SqliteCatalogue(open_catalogue_file(path))
    moment = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
    catalogue.add_theme(Theme(id="t-late", name="Late night", created_at=moment + timedelta(days=1)))
    catalogue.add_theme(Theme(id="t-early", name="Daylight", created_at=moment))
    return catalogue


def test_a_catalogue_of_unhung_themes_stays_that_way_across_a_restart(tmp_path, caplog):
    """Nothing promotes a theme automatically, and opening the file is not an exception.

    With N walls there is no defensible answer to which theme belongs on a wall
    the curator has not hung anything on — so the honest answer is the empty one,
    and it is silent, because there is nothing wrong to report. Opening the file
    is where the repair used to be reachable from, which is why the restart is
    the interesting moment rather than an incidental one.

    (`Services.reconcile` is the other half of this and is asserted where the
    container is: a display repair that no longer exists cannot be entered here.)
    """
    path = tmp_path / "catalogue.sqlite"
    _catalogue_with_unhung_themes(path).close()
    # The restart is the moment under test, and `caplog` has been capturing since
    # the call phase began — including the line the migration writes when the
    # helper above creates the file, which is a different event with its own
    # tests. Without this, the assertion below is about everything this function
    # has said rather than about opening the file.
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="arrt"):
        catalogue = SqliteCatalogue(open_catalogue_file(path))
    try:
        display = _display(catalogue, tmp_path)
        assert display.hanging_on(catalogue.list_walls()[0].id) is None
        assert [theme.id for theme in display.list_themes()] == ["t-early", "t-late"]
        # Scoped to this plane's own loggers rather than to everything the
        # process said: the claim is that *curation* reported no repair, and a
        # bare emptiness check makes any library's warning fail this test for a
        # reason that has nothing to do with hanging.
        assert [record.message for record in caplog.records if record.name.startswith("arrt.")] == []
    finally:
        catalogue.close()


def test_adding_a_theme_to_a_catalogue_with_nothing_hanging_hangs_nothing(tmp_path):
    """The condition used to be "none is active", which made this a second repair path."""
    catalogue = _catalogue_with_unhung_themes(tmp_path / "catalogue.sqlite")
    try:
        display = _display(catalogue, tmp_path)

        added = display.add_theme(name="Precisionists")

        assert display.walls_hanging(added.id) == []
        assert display.hanging_on(catalogue.list_walls()[0].id) is None
    finally:
        catalogue.close()


def test_what_a_curator_hung_reaches_the_file_and_survives_a_reopen(tmp_path):
    """The other half of the same claim: a deliberate hang is durable.

    Dropping the promotion means the assignment row is the only thing that can
    put a theme on a wall, so it is the only thing that can put one back after a
    restart.
    """
    path = tmp_path / "catalogue.sqlite"
    catalogue = _catalogue_with_unhung_themes(path)
    wall_id = catalogue.list_walls()[0].id
    _display(catalogue, tmp_path).activate_theme("t-early", wall_id=wall_id)
    catalogue.close()

    reopened = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert _display(reopened, tmp_path).hanging_on(wall_id).id == "t-early"
    finally:
        reopened.close()
