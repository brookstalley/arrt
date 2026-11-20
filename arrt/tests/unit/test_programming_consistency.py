"""Programming's consistency: a row read where it is written, a feed written only with what decided it, one act one rebuild.

The 2026-11-19 audit (audit-2 S2, S3, S4). Each is a fault of interleaving or of
rollback, so each test forces the interleaving or the failure rather than hoping
for it:

- **A row is read inside the transaction that writes it back.** Requests run on
  a threadpool, so a Player's heartbeat can land between a curator's read of a
  wall and the write of the whole row. `_between_read_and_write` lands the other
  act on a second thread at the first moment the store's lock lets it in after the
  curator's read, with no sleep and no timeout. Read outside the transaction, that
  is at once, and the curator's write puts the old row back; read inside, it is
  once the curator lets go of the lock, after the write.
- **A feed is written only once the act that decided it can no longer roll back**
  (`FeedPublisher.publishing`, `programming/feeds.py`), and the walls one act changes change together.
- **A bulk act is one announcement and one reconciliation**, so each wall's feed is
  written once for it.
"""

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from arrt.persistence.catalogue import StorageError
from arrt.persistence.records import ThemeAssignment
from arrt.programming import feeds as feeds_module
from arrt.services.errors import ServiceError

_OLD_REPORT_AT = "2026-10-02T14:00:05+00:00"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _frame_report(identity: str, *, at: str) -> dict:
    return {
        "reported_at": at,
        "outputs": [{"name": "frame", "kind": "frame", "connected": True, "screen": None, "identity": identity}],
    }


class _CuratorsLock:
    """The store's lock, unchanged, except that it can say when the curator's thread lets go of it altogether.

    Delegates every acquire and release to the real lock and counts the
    curator's depth; `on_free` runs on the curator's thread at the moment its
    outermost hold ends, before it goes on, which is the first moment a thread
    waiting on the lock could have got in.
    """

    def __init__(self, real, curator: int) -> None:
        self._real = real
        self._curator = curator
        self.depth = 0
        self.on_free: Callable[[], None] | None = None

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        got = self._real.acquire(blocking, timeout)
        if got and threading.get_ident() == self._curator:
            self.depth += 1
        return got

    def release(self) -> None:
        self._real.release()
        if threading.get_ident() == self._curator:
            self.depth -= 1
            if self.depth == 0 and self.on_free is not None:
                then, self.on_free = self.on_free, None
                then()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _between_read_and_write(monkeypatch, store, method: str, act: Callable[[], object]) -> Callable[[], None]:
    """Land `act` on another thread at the first moment the store's lock lets it in after the curator's first `store.<method>`.

    Read outside any transaction, the lock is free at the read, so `act` runs
    there and then, before the curator goes on: the interleaving a threadpool
    allows. Read inside one, the curator holds the lock, so `act` runs the moment
    the curator lets go of it altogether, which is where a thread waiting on the
    lock lands: after the write, when the read and the write share one
    transaction, and between them when they do not. Nothing sleeps and nothing
    is timed: the curator waits for `act` each time, and `act` never waits on the
    lock. (Until 2026-11-20 this started `act` at the read and waited up to a
    second for it to land, a timing bound.)

    Returns a function, called once the curator's act has returned, that says
    whether `act` ran and raises what it raised.
    """
    curator = threading.get_ident()
    lock = _CuratorsLock(store._store._lock, curator)
    # The one lock `transaction()` and `reading()` both hold (`persistence/durable.py`), swapped while nothing holds it.
    monkeypatch.setattr(store._store, "_lock", lock)
    read = getattr(store, method)
    fired: list[bool] = []
    landed: list[bool] = []
    failures: list[BaseException] = []

    def other() -> None:
        try:
            act()
        except BaseException as error:  # noqa: BLE001 -- carried back to the test's thread and raised there
            failures.append(error)

    def land() -> None:
        landed.append(True)
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()

    def reading(*arguments, **keywords):
        found = read(*arguments, **keywords)
        if threading.get_ident() == curator and not fired:
            fired.append(True)
            if lock.depth == 0:
                land()
            else:
                lock.on_free = land
        return found

    monkeypatch.setattr(store, method, reading)

    def finished() -> None:
        assert fired, f"the curator's act never called {method}, so nothing was interleaved"
        assert landed, "the curator's act never let go of the store's lock, so the other act never ran"
        if failures:
            raise failures[0]

    return finished


# -- S2: a row is read where it is written -------------------------------------------------


@pytest.fixture
def moved_frame(services, store, wall_id):
    """A wall on a new Pi's frame output, recorded by place, and a heartbeat that merges it into the Frame's record.

    The Frame was last reported by an old Pi, long ago, so the new Pi's report of
    its identity moves the Frame to it and folds the place record into it
    (`ClientService._merge_place`): the wall's `display_id` changes with no
    curator involved.
    """
    clients = services.clients
    old = clients.add_client(name="The old Pi")
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(old.id)
    clients.record_heartbeat(old.id, _frame_report("FRAME-SERIAL", at=_OLD_REPORT_AT))
    frame = next(display for display in store.list_displays() if display.identity == "FRAME-SERIAL")
    new = clients.add_client(name="The new Pi")
    services.access.issue(new.id)
    placed = clients.assign_wall(wall_id, client_id=new.id, output="frame")
    assert placed.display.id != frame.id

    def heartbeat() -> None:
        clients.record_heartbeat(new.id, _frame_report("FRAME-SERIAL", at=_now()))

    return heartbeat, frame.id


@pytest.mark.parametrize(
    "curator",
    [
        pytest.param(lambda display, wall_id: display.set_playback(wall_id, rotation_interval_seconds=90), id="set_playback"),
        pytest.param(lambda display, wall_id: display.set_mat_mode(wall_id, "full"), id="set_mat_mode"),
        pytest.param(lambda display, wall_id: display.rename_wall(wall_id, name="The hall"), id="rename_wall"),
    ],
)
def test_a_heartbeat_between_a_curators_read_and_write_keeps_its_display(
    services, store, display, wall_id, moved_frame, monkeypatch, curator
):
    """Acceptance 1. Read outside the transaction, the curator's write put back the display the merge removed."""
    heartbeat, frame_id = moved_frame
    finished = _between_read_and_write(monkeypatch, store, "get_wall", heartbeat)

    curator(display, wall_id)
    finished()

    assert store.get_wall(wall_id).display_id == frame_id


def test_a_merge_names_both_players_at_warning(services, wall_id, moved_frame, caplog):
    """Audit-8 F10, as the plan's DECISION rules it: the move stays automatic, and is said at WARNING naming both."""
    heartbeat, _ = moved_frame
    with caplog.at_level(logging.WARNING, logger="arrt.programming.clients"):
        heartbeat()

    said = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert any("moved from client 'The old Pi' to client 'The new Pi'" in message for message in said), said
    # And by its event, so a journal query finds the move as well as a text search.
    (moved,) = [record for record in caplog.records if getattr(record, "event", None) == "client.display_moved"]
    assert (moved.from_client, moved.to_client) == ("The old Pi", "The new Pi")


def test_a_token_issued_between_a_renames_read_and_write_still_opens(services, store, monkeypatch):
    """The client row carries the token's verifier, so a rename read before an issue put the old verifier back."""
    clients, access = services.clients, services.access
    pi = clients.add_client(name="The Pi in the hall")
    issued = []
    finished = _between_read_and_write(monkeypatch, store, "get_client", lambda: issued.append(access.issue(pi.id)))

    clients.rename_client(pi.id, name="The hall's Pi")
    finished()

    assert access.identify(issued[0].token).name == "The hall's Pi"


def test_a_rename_between_a_token_issues_read_and_write_keeps_its_name(services, store, monkeypatch):
    """The other way round: an issue read before a rename put the old name back with the new verifier."""
    clients, access = services.clients, services.access
    pi = clients.add_client(name="The Pi in the hall")
    finished = _between_read_and_write(
        monkeypatch, store, "get_client", lambda: clients.rename_client(pi.id, name="The hall's Pi")
    )

    issued = access.issue(pi.id)
    finished()

    assert store.get_client(pi.id).name == "The hall's Pi"
    assert access.identify(issued.token).name == "The hall's Pi"


# -- S3: a feed is written only with what decided it ---------------------------------------


def test_a_hang_that_fails_after_its_feed_was_built_leaves_the_feed_as_it_was(
    display, store, ready_work, wall_id, wall_settings, monkeypatch
):
    """Acceptance 2: the selection the hang replaces cannot be retired, so the hang rolls back, and so must the feed."""
    display.hang_selection([ready_work(title="Nighthawks").id], wall_id=wall_id)
    selection = display.hanging_on(wall_id)
    before = wall_settings.manifest_v2_path(wall_id).read_bytes()
    theme = display.add_theme(name="Daylight")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work(title="Automat").id)

    def refuse(theme_id):
        raise StorageError("Could not remove the theme: the store refused the write.", reason="the store refused the write.")

    monkeypatch.setattr(store, "remove_theme", refuse)
    with pytest.raises(ServiceError, match="the store refused the write"):
        display.activate_theme(theme.id, wall_id=wall_id)

    assert display.hanging_on(wall_id).id == selection.id
    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == before


def test_a_hang_whose_second_wall_cannot_be_written_changes_neither_wall(
    display, ready_work, wall_id, wall_settings, monkeypatch
):
    """The walls one act rebuilds change together: the hall written and the study refused left the hall disowned."""
    shared = ready_work(title="Nighthawks")
    study = display.add_wall(name="Study").id
    first = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=first.id, artwork_id=shared.id)
    display.activate_theme(first.id, wall_id=study)
    second = display.add_theme(name="Daylight")
    for work in (shared, ready_work(title="Automat")):
        display.add_to_theme(theme_id=second.id, artwork_id=work.id)
    paths = {wall: wall_settings.manifest_v2_path(wall) for wall in (wall_id, study)}
    before = {wall: path.read_bytes() if path.exists() else None for wall, path in paths.items()}
    write, writes = feeds_module.write_atomically, []

    def second_write_fails(path, document):
        writes.append(path)
        if len(writes) == 2:
            raise OSError("No space left on device")
        write(path, document)

    monkeypatch.setattr(feeds_module, "write_atomically", second_write_fails)
    with pytest.raises(OSError, match="No space left on device"):
        display.activate_theme(second.id, wall_id=wall_id)

    assert len(writes) == 2, "the hang did not write two walls, so nothing was tested"
    assert display.hanging_on(wall_id) is None
    assert {wall: path.read_bytes() if path.exists() else None for wall, path in paths.items()} == before
    assert sorted(path.name for path in wall_settings.art_root.iterdir() if ".staged" in path.name) == []


def test_a_start_republishes_a_feed_of_another_theme_than_the_one_hung(display, store, ready_work, wall_id, wall_settings):
    """Acceptance 3: what a hang whose commit failed after its files were renamed leaves, mended at the next start."""
    study = display.add_wall(name="Study").id
    hung, other, its_own = (display.add_theme(name=name) for name in ("Late night", "Daylight", "The study's"))
    display.add_to_theme(theme_id=hung.id, artwork_id=ready_work(title="Nighthawks").id)
    display.add_to_theme(theme_id=other.id, artwork_id=ready_work(title="Automat").id)
    display.add_to_theme(theme_id=its_own.id, artwork_id=ready_work(title="Chop Suey").id)
    display.activate_theme(hung.id, wall_id=wall_id)
    display.activate_theme(its_own.id, wall_id=study)
    display.activate_theme(other.id, wall_id=wall_id)
    # Written around the service: the catalogue names the theme hung before, the
    # feed the one whose commit failed.
    store.set_assignment(ThemeAssignment(wall_id=wall_id, theme_id=hung.id, assigned_at=datetime.now(UTC)))
    study_before = wall_settings.manifest_v2_path(study).read_bytes()

    result = display.reconcile()

    assert json.loads(wall_settings.manifest_v2_path(wall_id).read_text())["playlist"]["id"] == hung.id
    assert wall_id in result.republished
    # The control: a feed of the theme hung is left exactly as it was.
    assert wall_settings.manifest_v2_path(study).read_bytes() == study_before
    assert study not in result.republished


def test_a_feed_is_never_published_inside_a_transaction_it_does_not_own(display, store, ready_work, wall_id, wall_settings):
    """Inside another transaction a feed would be written before that transaction decided anything, so it is refused."""
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)

    with pytest.raises(RuntimeError, match="never inside another"), store.transaction():
        display.activate_theme(theme.id, wall_id=wall_id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_the_refusal_asks_the_store_and_does_not_lean_on_when_callbacks_run(
    display, store, ready_work, wall_id, wall_settings, monkeypatch
):
    """A store of Programming's own may run `after_commit` callbacks at once; the refusal still holds.

    The store says whether a transaction is open on this thread
    (`in_transaction`), so nothing here infers it from a side effect a later
    store need not have.
    """
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    monkeypatch.setattr(store, "after_commit", lambda callback: callback())

    with pytest.raises(RuntimeError, match="never inside another"), store.transaction():
        display.activate_theme(theme.id, wall_id=wall_id)

    assert not wall_settings.manifest_v2_path(wall_id).exists()


def test_a_feed_one_act_has_decided_is_not_read_by_a_request_on_another_thread(
    display, store, ready_work, wall_id, wall_settings
):
    """Mid-act, another thread reads the feed as published, as a Player would: none yet, since the act has not written it."""
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    seen: list[object] = []
    real = display._feeds._write_staged

    def look_from_elsewhere(staged):
        assert staged, "the act decided no feed, so there is nothing for another thread to see"
        other = threading.Thread(target=lambda: seen.append(display._feeds.published(wall_id)))
        other.start()
        other.join()
        seen.append(display._feeds.published(wall_id))
        real(staged)

    display._feeds._write_staged = look_from_elsewhere
    display.activate_theme(theme.id, wall_id=wall_id)

    elsewhere, inside = seen
    assert elsewhere is None
    assert inside is not None
    assert inside.playlist_id == theme.id
    assert wall_settings.manifest_v2_path(wall_id).exists()


def test_a_feed_is_never_written_outside_an_act(display, ready_work, wall_id):
    """`_publish_feed` stages; a caller outside `publishing` would stage a feed nothing writes, so it is refused by name."""
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    display.activate_theme(theme.id, wall_id=wall_id)
    feed = display._feeds.published(wall_id)

    with pytest.raises(RuntimeError, match="outside `publishing`"):
        display._feeds.patch_v2_works(wall_id, feed, {})


# -- S4: one bulk act, one reconciliation ---------------------------------------------------


def test_archiving_fifty_works_on_three_walls_reconciles_once_and_writes_each_feed_once(
    services, display, ready_work, wall_id, wall_settings, monkeypatch
):
    """Acceptance 4. One announcement per work made fifty reconciliations, each rebuilding every wall, on the request."""
    works = [ready_work(title=f"Study {number}") for number in range(52)]
    walls = [wall_id, display.add_wall(name="Study").id, display.add_wall(name="Hall").id]
    theme = display.add_theme(name="Everything")
    display.add_works_to_theme(theme_id=theme.id, artwork_ids=[work.id for work in works])
    for wall in walls:
        display.activate_theme(theme.id, wall_id=wall)
    reconcile, asked = display.reconcile, []

    def counted(work_ids=None, **keywords):
        asked.append(None if work_ids is None else list(work_ids))
        return reconcile(work_ids, **keywords)

    write, written = feeds_module.write_atomically, []

    def counting(path, document):
        written.append(path.name)
        write(path, document)

    monkeypatch.setattr(display, "reconcile", counted)
    monkeypatch.setattr(feeds_module, "write_atomically", counting)
    archived = services.catalogue.archive_artworks([work.id for work in works[:50]])

    assert len(archived) == 50
    assert asked == [[work.id for work in works[:50]]]
    for wall in walls:
        name = wall_settings.manifest_v2_path(wall).name
        assert sum(name in path for path in written) == 1, f"wall {wall}'s feed was written {written}"
        carried = json.loads(wall_settings.manifest_v2_path(wall).read_text())["works"]
        assert set(carried) <= {works[50].id, works[51].id}, "an archived work is still on the wall"
