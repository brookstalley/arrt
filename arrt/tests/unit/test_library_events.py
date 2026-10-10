"""The Library announces what changed, only once it is committed, and never fails for a subscriber.

`architecture.md` § Direction, the Library/Programming seam, rule 4. These tests
hold the Library's half: which operation announces what, when the announcement is
made, and that a subscriber's failure cannot reach back into the Library's
operation. What Programming does on hearing one is `test_reconciliation.py`.
"""

import logging
from collections.abc import Callable

import pytest

from arrt.library.events import LibraryEvents, WorkChange, WorkChanged
from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.records import FetchStatus, MatMethod, RenditionKind


@pytest.fixture
def heard(library) -> list[WorkChanged]:
    """Every announcement the facade passes on, in order."""
    received: list[WorkChanged] = []
    library.subscribe(received.append)
    return received


def _accept(service, ready_work) -> str:
    return service.add_artwork(title="Nighthawks").id


def _archive(service, ready_work) -> str:
    work = ready_work()
    service.archive_artwork(work.id)
    return work.id


def _restore(service, ready_work) -> str:
    work = ready_work()
    service.archive_artwork(work.id)
    service.restore_artwork(work.id)
    return work.id


def _new_master(service, ready_work) -> str:
    work = ready_work()
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
    return work.id


def _new_render(service, ready_work) -> str:
    work = ready_work(master=False)
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path="masters/x.jpg"
    )
    return work.id


def _new_mat(service, ready_work) -> str:
    work = ready_work()
    service.record_mat_color(artwork_id=work.id, hex_rgb="#2a3a5e", method=MatMethod.MANUAL)
    return work.id


#: Each operation that changes a work, and what it must announce last. Keyed so
#: that every `WorkChange` has at least one producer below.
_PRODUCERS: list[tuple[str, Callable[..., str], WorkChange]] = [
    ("add_artwork", _accept, WorkChange.ACCEPTED),
    ("restore_artwork", _restore, WorkChange.ACCEPTED),
    ("archive_artwork", _archive, WorkChange.ARCHIVED),
    ("record_original", _new_master, WorkChange.IMAGE_CHANGED),
    ("record_rendition", _new_render, WorkChange.IMAGE_CHANGED),
    ("record_mat_color", _new_mat, WorkChange.MAT_CHANGED),
]


def test_every_kind_of_change_has_an_operation_that_announces_it():
    assert {change for _, _, change in _PRODUCERS} == set(WorkChange)


@pytest.mark.parametrize(("operation", "make", "change"), _PRODUCERS, ids=[name for name, _, _ in _PRODUCERS])
def test_each_operation_announces_its_change(service, ready_work, heard, operation, make, change):
    work_id = make(service, ready_work)

    assert heard[-1] == WorkChanged(change=change, work_id=work_id)


def test_an_announcement_waits_for_the_outermost_commit(service, store, heard):
    """Acceptance adds a work inside discovery's transaction; nothing is said until it commits."""
    with store.transaction():
        work = service.add_artwork(title="Nighthawks")
        assert heard == [], "announced inside a transaction that could still roll back"

    assert heard == [WorkChanged(change=WorkChange.ACCEPTED, work_id=work.id)]


def test_a_change_that_rolls_back_is_never_announced(service, store, heard):
    def add_then_fail() -> None:
        with store.transaction():
            service.add_artwork(title="Nighthawks")
            raise RuntimeError("the rest of the operation failed")

    with pytest.raises(RuntimeError, match="the rest of the operation failed"):
        add_then_fail()

    assert heard == []
    assert service.list_artworks().entries == []


def test_a_failing_subscriber_fails_neither_the_change_nor_the_subscribers_after_it(service, library, caplog):
    def refuses(event: WorkChanged) -> None:
        raise OSError("disk full")

    after: list[WorkChanged] = []
    library.subscribe(refuses)
    library.subscribe(after.append)

    with caplog.at_level(logging.ERROR, logger="arrt.library.events"):
        work = service.add_artwork(title="Nighthawks")

    assert service.get_artwork(work.id).artwork.title == "Nighthawks"
    assert after == [WorkChanged(change=WorkChange.ACCEPTED, work_id=work.id)]
    assert [record.levelno for record in caplog.records] == [logging.ERROR]
    assert work.id in caplog.records[0].getMessage()


def test_a_catalogue_built_without_a_publisher_still_works(store):
    """It announces to nobody, which is a catalogue with no Programming beside it."""
    assert CatalogueService(store).add_artwork(title="Nighthawks").title == "Nighthawks"


def test_publishing_calls_subscribers_in_the_order_they_subscribed():
    events = LibraryEvents()
    order: list[str] = []
    events.subscribe(lambda _: order.append("first"))
    events.subscribe(lambda _: order.append("second"))

    events.publish(WorkChanged(change=WorkChange.ARCHIVED, work_id="w"))

    assert order == ["first", "second"]


def test_the_librarys_store_contract_names_no_programming_table():
    """The Library writes no Programming table, and its contract has no way to.

    Read off the protocol itself, so a method added back for a shortcut fails
    here by name.
    """
    programming_nouns = ("theme", "wall", "directive", "membership", "assignment")
    offered = [name for name in dir(CatalogueStore) if not name.startswith("_")]

    assert offered, "the protocol has no methods, so this check reads nothing"
    assert [name for name in offered if any(noun in name for noun in programming_nouns)] == []


class TestAfterCommit:
    """The durable store's hook the announcements ride on."""

    def test_outside_a_transaction_it_runs_at_once(self, store):
        ran: list[str] = []

        store.after_commit(lambda: ran.append("ran"))

        assert ran == ["ran"]

    def test_inside_nested_transactions_it_waits_for_the_outermost(self, store):
        ran: list[str] = []
        with store.transaction():
            with store.transaction():
                store.after_commit(lambda: ran.append("ran"))
            assert ran == [], "ran when the inner block closed, before anything was committed"

        assert ran == ["ran"]

    def test_a_rollback_discards_it_and_the_next_commit_does_not_run_it(self, store):
        ran: list[str] = []

        def queue_then_abandon() -> None:
            with store.transaction():
                store.after_commit(lambda: ran.append("stale"))
                raise RuntimeError("abandoned")

        with pytest.raises(RuntimeError, match="abandoned"):
            queue_then_abandon()

        with store.transaction():
            store.after_commit(lambda: ran.append("fresh"))

        assert ran == ["fresh"]
