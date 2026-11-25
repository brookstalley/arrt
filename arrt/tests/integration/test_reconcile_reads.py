"""What the reconcile and the facade under it cost the catalogue file, counted in statements.

The periodic reconcile (`FeedPublisher.reconcile`) asks the Library about every
work of every hung theme while it holds the store's lock, and an act arriving
meanwhile waits for it (ruling 5 of 2026-11-20). So what a pass costs is held
here as a count of the statements it sends the file, which must not grow with
the works the Library holds; and the Library's answer is read as one instant,
which is held by asking, between two of its reads, whether a writer could get
in.

Counted with SQLite's own trace hook on the one connection both adapters
share, so every statement any layer sends is seen, whichever method sent it.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from arrt.library.facade import PlayableWork
from arrt.persistence.records import RenditionKind


@contextmanager
def _statements(catalogue_file) -> Iterator[list[str]]:
    """Every statement the catalogue file runs inside the block, in order."""
    seen: list[str] = []
    catalogue_file._connection.set_trace_callback(seen.append)
    try:
        yield seen
    finally:
        catalogue_file._connection.set_trace_callback(None)


def _starting(statements: list[str], verb: str) -> list[str]:
    return [statement for statement in statements if statement.lstrip().upper().startswith(verb)]


@pytest.fixture
def study(display) -> str:
    return display.add_wall(name="Study").id


@pytest.fixture
def ready_works(service, ready_work):
    """`count` works ready for a wall, every third unattributed and the rest shared among two artists."""

    def _make(count: int) -> list[str]:
        artists = [service.add_artist(name=name) for name in ("Edward Hopper", "Georgia O'Keeffe")]
        return [
            ready_work(title=f"Work {index}", artist_id=None if index % 3 == 0 else artists[index % 3 - 1].id).id
            for index in range(count)
        ]

    return _make


def _reads_of_playable(library, catalogue_file, work_ids) -> int:
    library.playable(work_ids)  # each master hashed and measured once, as on a server that has run a while
    with _statements(catalogue_file) as seen:
        answers = library.playable(work_ids)
    assert all(isinstance(answer, PlayableWork) for answer in answers.values()), "a work was refused, so not every read ran"
    return len(_starting(seen, "SELECT"))


def test_the_facade_reads_a_set_of_works_in_the_same_number_of_statements_however_many(
    library, ready_works, quiet_catalogue_file
):
    few = ready_works(4)
    many = ready_works(40)

    assert _reads_of_playable(library, quiet_catalogue_file, few) == _reads_of_playable(library, quiet_catalogue_file, few + many)


def test_a_reconcile_with_nothing_to_fix_sends_the_same_statements_however_large_the_theme(
    display, ready_works, quiet_catalogue_file, wall_id, study
):
    """Through the caller the wait belongs to: a whole pass over two hung walls, at two sizes of theme."""
    counts = []
    for size in (4, 40):
        works = ready_works(size)
        for wall in (wall_id, study):
            theme = display.add_theme(name=f"{size} works, {wall}")
            display.add_works_to_theme(theme_id=theme.id, artwork_ids=works)
            display.activate_theme(theme.id, wall_id=wall)
        display.reconcile()  # whatever a hang left to mend is mended here, so the pass counted fixes nothing
        with _statements(quiet_catalogue_file) as seen:
            result = display.reconcile()
        assert result.asked >= size, "the pass asked about fewer works than the theme holds, so the count measures nothing"
        assert result.republished == (), "the pass fixed something, so it counted more than the lookups"
        counts.append(len(seen))

    assert counts[0] == counts[1]


def test_the_set_is_read_as_one_instant_and_a_writer_is_let_in_once_it_is_read(
    library, ready_works, store, quiet_catalogue_file, monkeypatch
):
    """Between two of the facade's reads no writer can get in; once the set is read, one can at once.

    The probe takes the store's own lock without waiting, from another thread,
    so it says whether a writer would be held there and never waits itself.
    """
    work_ids = ready_works(3)

    def could_a_writer_get_in() -> bool:
        taken: list[bool] = []

        def probe() -> None:
            acquired = quiet_catalogue_file._lock.acquire(blocking=False)
            if acquired:
                quiet_catalogue_file._lock.release()
            taken.append(acquired)

        writer = threading.Thread(target=probe)
        writer.start()
        writer.join()
        return taken[0]

    probes: list[bool] = []
    read_originals = store.get_originals

    def between_two_reads(artwork_ids):
        probes.append(could_a_writer_get_in())
        return read_originals(artwork_ids)

    monkeypatch.setattr(store, "get_originals", between_two_reads)

    library.playable(work_ids)

    assert probes == [False], "a writer could have changed the catalogue between the works' rows and their originals"
    assert could_a_writer_get_in(), "the read scope was left open, so every writer would now wait"


def test_a_master_with_no_hash_is_hashed_once_and_then_never_again(
    library, service, ready_work, wall_settings, decodable_jpeg, quiet_catalogue_file
):
    """`with_content` writes a master's hash the first time it is needed, and only then."""
    work = ready_work(master=False)
    path = f"presentation/{work.id}.jpg"
    service.record_rendition(
        artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )
    decodable_jpeg(wall_settings.art_root / path, width=400, height=300)

    def hashes_written() -> int:
        with _statements(quiet_catalogue_file) as seen:
            assert isinstance(library.playable([work.id, "no-such-work"])[work.id], PlayableWork)
        return sum(1 for statement in _starting(seen, "INSERT") + _starting(seen, "UPDATE") if "renditions" in statement)

    assert [hashes_written(), hashes_written()] == [1, 0]
