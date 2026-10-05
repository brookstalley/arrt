"""Fetching and preparing every accepted work that holds no image, in the background.

Acceptance makes a work and its sources, and until now nothing fetched the work's
master image or prepared it for a wall, so a work accepted through Get or Ask
stayed off every wall until somebody called `retry_acquisition` and `regenerate`
by hand. This is the worker that does both: one thread, one work at a time, woken
by acceptance and catching up at every start, shaped like the topic sweep.

**One at a time, fetch then prepare.** The Pi's memory is the limit
(`nonfunctional-requirements.md`): a tiled fetch can take half an hour and a
gigapixel, and a preparation decodes what it brought. A pass takes the works due
in order, oldest acceptance first and a Retry ahead of all of them, and for each
one fetches (`AcquisitionService.acquire`) when it holds no image, then prepares
(`PreparationService.prepare`). A first preparation asks the vision model for the
mat colour, so the queue spends; `PreparationService` records it.

**What counts, and what it costs the work.** A fetch that comes back with gaps is
an image, and the work goes on the wall with it (`partial_tiles` is a recorded
outcome, not a failure). A fetch that records a failure, a refusal about this
work (no source, or several and none primary), or a preparation that refuses is
one failure, and the work is tried again after an hour, a day and three days;
after the fourth failure in a row the queue gives up until someone asks again
(`retry`). A preparation that failed after a good fetch is retried by preparing
alone: the image is held, and fetching it again would cost a museum a gigapixel
to repeat what already worked.

**A deployment fault pauses the queue and costs no work anything.** The
conditions acquisition raises for rather than records (`DEPLOYMENT_FAULTS`: a
disk below `MIN_FREE_BYTES`, no dezoomify-rs, a provider with no resolver) are
none of them one work's fault, and retrying the work cannot fix any of them. So
the pass stops, the queue remembers why, and it tries again every 15 minutes and
on every wake. `acquire` journals the fault itself (`acquisition.deployment_fault`);
the queue adds the pause.

**What is stored answers five questions and no more** (`data-model.md` Q31 to
Q35, the `acquisition_queue` table): which works are due, how many times each has
failed in a row and when it may next be tried, why the last attempt failed,
whether the queue gave up, and which source a Retry named. What is in flight and
why the queue is paused live in memory; a restart re-derives both by trying.
"""

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final, Protocol

from arrt.library.acquisition.mat import MAT_LIGHTNESS_FLOOR, below_the_floor
from arrt.library.acquisition.preparation import PreparationResult
from arrt.library.acquisition.service import DEPLOYMENT_FAULTS, AcquisitionOutcome, AcquisitionResult, remedy_for
from arrt.library.services.catalogue import CatalogueService
from arrt.persistence.catalogue import CatalogueStore, WorkToAcquire
from arrt.persistence.records import ArtworkStatus, QueuedAcquisition
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How long after each failure in a row the work is tried again: the owner's
#: schedule of 2026-10-02. One entry per retry, so the number of attempts before
#: the queue gives up is one more than its length.
RETRY_AFTER: Final[tuple[timedelta, ...]] = (timedelta(hours=1), timedelta(days=1), timedelta(days=3))

#: Failures in a row after which the queue stops trying a work until Retry: the
#: first attempt and each retry above.
GIVE_UP_AFTER: Final[int] = len(RETRY_AFTER) + 1

#: How often a paused queue tries again when nothing wakes it. Freeing disk or
#: installing the binary is somebody at the machine, and a quarter of an hour is
#: soon enough after they have done it without polling a full disk every minute.
PAUSED_RETRY_SECONDS: Final[float] = 900.0

#: How long the queue sleeps with nothing due and nothing waking it. A pass then
#: runs anyway and logs, so a queue that died can be told from one with nothing
#: to do, and a work catalogued by another process is found within a day.
IDLE_SECONDS: Final[float] = 86_400.0

#: The shortest wait between passes, so a retry falling due a moment from now is
#: never a busy loop.
_MIN_WAIT_SECONDS: Final[float] = 1.0

#: What the queue's thread is called, in `journalctl` and in a stack dump, and
#: what a test looks for to say it was or was not started.
ACQUISITION_QUEUE_THREAD_NAME: Final[str] = "acquisition-queue"

#: How long a shutdown waits for the work in hand. A tiled fetch can run for
#: half an hour, so this does not wait for one: the thread is a daemon, and the
#: line it logs says a fetch was abandoned rather than finished.
_SHUTDOWN_JOIN_SECONDS: Final[float] = 5.0


class Acquirer(Protocol):
    """What the queue needs of acquisition: `AcquisitionService.acquire`."""

    def acquire(self, artwork_id: str, *, source_id: str | None = None) -> AcquisitionResult: ...


class Preparer(Protocol):
    """What the queue needs of preparation: `PreparationService.prepare`."""

    def prepare(self, artwork_id: str, *, force: bool = False) -> PreparationResult: ...


class AcquisitionPhase(StrEnum):
    """Where one work stands in the queue."""

    #: Due now, waiting its turn.
    QUEUED = "queued"
    #: Being fetched, or prepared straight after its fetch, right now.
    FETCHING = "fetching"
    #: Failed, and waiting for its next try.
    FAILED = "failed"
    #: Failed `GIVE_UP_AFTER` times in a row; waits for Retry.
    GAVE_UP = "gave_up"
    #: Due now, and held back because the queue is paused.
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class AcquisitionState:
    """One work's place in the queue, as a surface says it."""

    artwork_id: str
    phase: AcquisitionPhase
    #: Failures in a row so far. Non-zero on a work queued again after one.
    failures: int = 0
    #: Why the last attempt failed (`failed`, `gave_up`, and a queued work that
    #: failed before), or why the queue is paused (`paused`).
    detail: str | None = None
    #: When a failed work will next be tried.
    next_try_at: datetime | None = None
    #: When the fetch in hand began (`fetching`).
    since: datetime | None = None
    #: The deployment fault the queue is paused on, by its exception's name (`paused`).
    condition: str | None = None

    @property
    def remedy(self) -> str | None:
        """What an operator changes to end the pause this work waits on; None when there is none to name."""
        return None if self.condition is None else remedy_for(self.condition)


@dataclass(frozen=True, slots=True)
class QueuePause:
    """Why the queue is paused: a condition that is the deployment's, not any work's."""

    #: The exception's own type name, as `acquisition.deployment_fault` carries it.
    condition: str
    detail: str
    since: datetime

    @property
    def remedy(self) -> str | None:
        """What an operator changes to end it. None for an error nothing anticipated: the journal has that one."""
        return remedy_for(self.condition)


@dataclass(frozen=True, slots=True)
class QueuePassResult:
    """What one pass did."""

    #: Works due when the pass began.
    due: int = 0
    #: Fetched (or held already) and prepared.
    acquired: int = 0
    #: Failed and will be tried again.
    failed: int = 0
    #: Failed for the last time; the queue gave up on them.
    gave_up: int = 0
    #: Owed something and not due yet, or given up on.
    waiting: int = 0
    #: The pause the pass ended in, if it ended in one.
    paused: QueuePause | None = None


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One work the queue owes something, named for a person reading the queue."""

    title: str
    state: AcquisitionState


@dataclass(frozen=True, slots=True)
class QueueListing:
    """What Activity › Queue shows of acquisition: the pause, if any, then every work owed."""

    pause: QueuePause | None
    entries: Sequence[QueueEntry]


class _Paused(Exception):
    """Internal: an attempt met a deployment fault, and the pass stops."""

    def __init__(self, pause: QueuePause) -> None:
        super().__init__(pause.detail)
        self.pause = pause


class AcquisitionQueue:
    """Fetch, then prepare, every accepted work that holds no image, one at a time."""

    def __init__(
        self,
        store: CatalogueStore,
        catalogue: CatalogueService,
        acquisition: Acquirer,
        preparation: Preparer,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._catalogue = catalogue
        self._acquisition = acquisition
        self._preparation = preparation
        self._clock = clock
        #: Set by `nudge`, so a waiting loop runs a pass now rather than later.
        self._wake = threading.Event()
        #: One pass at a time: a nudge arriving mid-pass runs the next one.
        self._pass_lock = threading.Lock()
        #: Guards the in-memory state below, which request threads read.
        self._state_lock = threading.Lock()
        self._fetching: tuple[str, datetime] | None = None
        self._pause: QueuePause | None = None
        #: Works a Retry asked for, in the order asked, taken before the rest.
        #: In memory only: after a restart a retried work simply waits its turn
        #: in acceptance order, which is the low-impact half of the ordering.
        self._front: list[str] = []

    # -- what a surface calls --------------------------------------------------

    def nudge(self) -> None:
        """Ask for a pass soon: a work was accepted or restored. Never blocks, never fetches."""
        self._wake.set()

    def retry(self, artwork_id: str, *, source_id: str | None = None) -> AcquisitionState:
        """Forget a work's failures and put it at the front of the queue; fetch nothing here.

        Naming a source makes the next attempt fetch from it, even for a work
        that already holds an image: that is how a curator asks for a different
        or a complete scan. Without one, the next attempt finishes what is owed
        — a fetch for a work with no image, a preparation for one with.
        """
        artwork = self._catalogue.get_artwork(artwork_id).artwork
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is archived; restore it and it will be fetched.")
        sources = {source.id for source in self._catalogue.list_sources(artwork_id)}
        if not sources:
            # Refused here rather than queued to fail an hour later: nothing a
            # retry schedule does can give a work a source, and the caller asking
            # is the one who can.
            raise ServiceError(f"Artwork {artwork_id!r} has no source to acquire from.")
        if source_id is not None and source_id not in sources:
            raise ServiceError(f"Source {source_id!r} does not belong to artwork {artwork_id!r}.")
        with self._state_lock:
            if self._fetching is not None and self._fetching[0] == artwork_id:
                raise ServiceError(f"Artwork {artwork_id!r} is being fetched now; there is nothing to retry yet.")
            self._store.set_queued_acquisition(QueuedAcquisition(artwork_id=artwork_id, source_id=source_id))
            if artwork_id in self._front:
                self._front.remove(artwork_id)
            self._front.append(artwork_id)
        log.info(
            "acquisition of %s asked for again", artwork_id, extra={"event": "acquisition.queue_retry", "artwork_id": artwork_id}
        )
        self.nudge()
        return self.state_of([artwork_id])[artwork_id]

    def owe_recomposition(self, layout: str) -> int:
        """Queue a preparation for every work whose canvas was drawn at another layout. Returns how many.

        Run at startup, so a changed mat or panel reaches the canvases already
        drawn. The queue's prepare-only path does the work, one at a time, and
        `prepare` recomposes because the canvas is no longer current. The old
        canvas stays on the wall until the new one is recorded, since nothing
        that decides what plays reads the layout. A work the queue already holds
        a row for is left as it is, so this never resets a failure count.
        """
        queued = 0
        with self._state_lock:
            for artwork_id in self._store.works_with_canvas_outside_layout(layout):
                if self._store.get_queued_acquisition(artwork_id) is None:
                    self._store.set_queued_acquisition(QueuedAcquisition(artwork_id=artwork_id))
                    queued += 1
        log.info(
            "%d canvases queued to be recomposed at %s",
            queued,
            layout,
            extra={"event": "preparation.recompose_queued", "queued": queued, "layout": layout},
        )
        if queued:
            self.nudge()
        return queued

    def owe_mats_over_the_floor(self) -> int:
        """Queue a preparation for every work on a canvas with no mat it may keep. Returns how many.

        Run at startup, so mats that predate the floor (all of them carried from
        2024) are chosen again without anyone asking for each, and so is the mat
        of a work with a canvas and no mat at all, which is what a fresh seed
        leaves for a 2024 colour below the floor. `prepare` does the choosing and
        redraws the canvas in the new colour. The old canvas stays on the wall
        until then. Each one is a paid model call, and the count is in the
        journal. A work the queue already holds a row for is left as it is.

        `CatalogueService.record_mat_color` refuses a colour below the floor, so
        once these are chosen this finds nothing on later starts.
        """
        queued = 0
        with self._state_lock:
            for artwork_id, hex_rgb in self._store.current_mats_of_works_with_canvas():
                owed = hex_rgb is None or below_the_floor(hex_rgb)
                if owed and self._store.get_queued_acquisition(artwork_id) is None:
                    self._store.set_queued_acquisition(QueuedAcquisition(artwork_id=artwork_id))
                    queued += 1
        log.info(
            "%d works queued to have a mat chosen: none, or one below the floor of L* %g",
            queued,
            MAT_LIGHTNESS_FLOOR,
            extra={"event": "preparation.mat_rechoice_queued", "queued": queued, "floor": MAT_LIGHTNESS_FLOOR},
        )
        if queued:
            self.nudge()
        return queued

    @property
    def pause(self) -> QueuePause | None:
        """Why the queue is paused, or None while it is not."""
        with self._state_lock:
            return self._pause

    def state_of(self, artwork_ids: Sequence[str]) -> Mapping[str, AcquisitionState]:
        """Where each of these works stands, for those the queue owes something.

        A work that holds its image and owes nothing, an archived work, and an
        id the catalogue does not hold are absent from the answer rather than
        given a state of their own: the queue has nothing to say about them.
        """
        with self._state_lock:
            fetching, pause = self._fetching, self._pause
        now = self._clock()
        states: dict[str, AcquisitionState] = {}
        with self._store.reading():
            for artwork_id in artwork_ids:
                artwork = self._store.get_artwork(artwork_id)
                if artwork is None or artwork.status is not ArtworkStatus.ACCEPTED:
                    continue
                queued = self._store.get_queued_acquisition(artwork_id)
                if queued is None and self._store.get_original(artwork_id) is not None:
                    continue
                states[artwork_id] = _state(artwork_id, queued, now=now, fetching=fetching, pause=pause)
        return states

    def listing(self) -> QueueListing:
        """Everything the queue owes, in the order it will be tried, and why it is paused if it is.

        The work being fetched leads, then a Retry's works, then oldest
        acceptance; works given up on and works waiting for a retry follow in
        the same order, since each still holds its place.
        """
        works = self._in_turn(list(self._store.works_to_acquire()))
        with self._state_lock:
            fetching = None if self._fetching is None else self._fetching[0]
        ids = [work.artwork_id for work in works]
        if fetching in ids:
            ids.remove(fetching)
            ids.insert(0, fetching)
        states = self.state_of(ids)
        entries = []
        for artwork_id in ids:
            state = states.get(artwork_id)
            artwork = self._store.get_artwork(artwork_id)
            if state is None or artwork is None:
                continue
            entries.append(QueueEntry(title=artwork.title, state=state))
        return QueueListing(pause=self.pause, entries=tuple(entries))

    # -- the worker ------------------------------------------------------------

    def wait_for_work(self) -> None:
        """Wait until nudged, or until the next thing falls due, whichever is sooner.

        A paused queue waits at most `PAUSED_RETRY_SECONDS`; otherwise the wait
        ends when the earliest failed work's next try falls due, and at most
        after `IDLE_SECONDS`. The nudge is cleared on the way out, as the topic
        sweep's is: one landing after that wakes the pass after.
        """
        self._wake.wait(self._seconds_until_due())
        self._wake.clear()

    def note_error(self, exc: Exception) -> None:
        """Pause on an error a pass did not expect, so the loop that caught it does not spin.

        The work in hand is due again at once, so a loop that went straight back
        to it would raise the same error as fast as it could log it. As a pause it
        is tried every 15 minutes, and Activity says why, as it does for a full disk.
        """
        self._enter_pause(QueuePause(condition=type(exc).__name__, detail=str(exc) or repr(exc), since=self._clock()))

    def run(self, *, stop: threading.Event | None = None) -> QueuePassResult:
        """Work through every due work, one at a time. Safe to call at any time, any number of times.

        `stop` is checked between works, so a shutdown ends the pass after the
        work in hand rather than after the whole backlog.
        """
        with self._pass_lock:
            candidates = self._store.works_to_acquire()
            now = self._clock()
            due = self._in_turn([work for work in candidates if _is_due(work.queued, now)])
            acquired = failed = gave_up = 0
            paused: QueuePause | None = None
            for work in due:
                if stop is not None and stop.is_set():
                    break
                try:
                    outcome = self._attempt(work)
                except _Paused as halted:
                    paused = halted.pause
                    break
                if outcome is _Outcome.DONE:
                    acquired += 1
                elif outcome is _Outcome.FAILED:
                    failed += 1
                else:
                    gave_up += 1
            if paused is None:
                # Every attempt got past the deployment's checks, or nothing was
                # due for a pause to hold back: either way it is over.
                self._leave_pause()
            result = QueuePassResult(
                due=len(due),
                acquired=acquired,
                failed=failed,
                gave_up=gave_up,
                waiting=len(candidates) - len(due),
                paused=paused,
            )
        # At INFO on every pass, including one with nothing due, for the sweeps'
        # reason: a periodic job that logs only when it acts cannot be told from
        # one that died.
        log.info(
            "acquisition queue pass",
            extra={
                "event": "acquisition.queue_pass",
                "due": result.due,
                "acquired": result.acquired,
                "failed": result.failed,
                "gave_up": result.gave_up,
                "waiting": result.waiting,
                "paused": None if result.paused is None else result.paused.condition,
            },
        )
        return result

    # -- one work --------------------------------------------------------------

    def _attempt(self, work: WorkToAcquire) -> _Outcome:
        artwork_id = work.artwork_id
        # Read again rather than taken from the pass's list: a Retry made while
        # an earlier work was being fetched has reset this row since. Read under
        # the lock `retry` writes under, and marked as fetching in the same
        # breath, so a Retry lands either before the read (and is used) or after
        # the mark (and is refused) — never between, where this attempt would
        # overwrite the reset or delete a named source on success.
        with self._state_lock:
            queued = self._store.get_queued_acquisition(artwork_id)
            entry = queued or QueuedAcquisition(artwork_id=artwork_id)
            if queued is None:
                # Written before anything is fetched, so a process that dies between
                # the fetch and the preparation leaves a row saying the preparation is
                # owed, and the next start finishes it instead of leaving the work
                # off the wall.
                self._store.set_queued_acquisition(entry)
            self._fetching = (artwork_id, self._clock())
            if artwork_id in self._front:
                self._front.remove(artwork_id)
        try:
            try:
                if not work.holds_original or entry.source_id is not None:
                    failure = self._fetch(entry)
                    if failure is not None:
                        return self._record_failure(entry, failure)
                    if entry.source_id is not None:
                        # Fetched from the source that was named, so the next attempt,
                        # if preparation fails, must not fetch again.
                        entry = replace(entry, source_id=None)
                        self._store.set_queued_acquisition(entry)
                try:
                    self._preparation.prepare(artwork_id)
                except ServiceError as exc:
                    return self._record_failure(entry, f"the image was fetched but could not be prepared: {exc}")
            except _Paused:
                raise
            except (
                Exception
            ) as exc:  # prawduct:allow prawduct/broad-except -- one work's surprise must not hold every work behind it
                # Counted against this work rather than pausing the queue: a
                # pause leaves the work first in line, so an error peculiar to it
                # would be met again on every pass and nothing behind it would
                # ever be fetched. A fault that is truly the host's fails each work
                # in turn instead, on the retry schedule, and says so on each.
                log.exception(
                    "acquiring %s raised an error nothing expected; it counts as a failure of that work",
                    artwork_id,
                    extra={"event": "acquisition.queue_unexpected", "artwork_id": artwork_id},
                )
                return self._record_failure(entry, f"an unexpected error: {type(exc).__name__}: {exc}")
            self._store.remove_queued_acquisition(artwork_id)
            return _Outcome.DONE
        finally:
            with self._state_lock:
                self._fetching = None

    def _fetch(self, entry: QueuedAcquisition) -> str | None:
        """Fetch the work's image; return why it failed, or None once it holds one."""
        try:
            result = self._acquisition.acquire(entry.artwork_id, source_id=entry.source_id)
        except DEPLOYMENT_FAULTS as exc:
            pause = QueuePause(condition=type(exc).__name__, detail=str(exc), since=self._clock())
            self._enter_pause(pause)
            raise _Paused(pause) from exc
        except ServiceError as exc:
            # A refusal about this work — no source, several and none primary, a
            # named source that went away — which a curator can act on.
            return str(exc)
        if result.outcome is AcquisitionOutcome.FAILED:
            return result.detail
        # Acquired, partial, or kept-held: every one leaves the work holding an
        # image, and a partial is one the owner chose to show rather than retry.
        return None

    def _record_failure(self, entry: QueuedAcquisition, detail: str) -> _Outcome:
        failures = entry.failures + 1
        gave_up = failures >= GIVE_UP_AFTER
        next_try_at = None if gave_up else self._clock() + RETRY_AFTER[failures - 1]
        self._store.set_queued_acquisition(replace(entry, failures=failures, next_try_at=next_try_at, detail=detail))
        if gave_up:
            log.warning(
                "gave up acquiring %s after %d failures; it waits for Retry: %s",
                entry.artwork_id,
                failures,
                detail,
                extra={"event": "acquisition.queue_gave_up", "artwork_id": entry.artwork_id, "failures": failures},
            )
            return _Outcome.GAVE_UP
        log.info(
            "acquiring %s failed (%d of %d); next try at %s: %s",
            entry.artwork_id,
            failures,
            GIVE_UP_AFTER,
            next_try_at.isoformat() if next_try_at else None,
            detail,
            extra={"event": "acquisition.queue_failed", "artwork_id": entry.artwork_id, "failures": failures},
        )
        return _Outcome.FAILED

    # -- the pause and the order -----------------------------------------------

    def _enter_pause(self, pause: QueuePause) -> None:
        with self._state_lock:
            previous, self._pause = self._pause, pause
        if previous is None or previous.condition != pause.condition:
            # Once per condition rather than once per pass: the pass line carries
            # `paused` every time, and this is the line that says why.
            log.warning(
                "the acquisition queue is paused: %s",
                pause.detail,
                extra={"event": "acquisition.queue_paused", "condition": pause.condition},
            )

    def _leave_pause(self) -> None:
        with self._state_lock:
            self._pause = None

    def _in_turn(self, due: list[WorkToAcquire]) -> list[WorkToAcquire]:
        """The due works in the order they are tried: a Retry first, then oldest acceptance."""
        with self._state_lock:
            front = list(self._front)
        rank = {artwork_id: position for position, artwork_id in enumerate(front)}
        return sorted(due, key=lambda work: rank.get(work.artwork_id, len(rank)))

    def _seconds_until_due(self) -> float:
        if self.pause is not None:
            return PAUSED_RETRY_SECONDS
        now = self._clock()
        upcoming = [
            work.queued.next_try_at
            for work in self._store.works_to_acquire()
            if work.queued is not None and work.queued.next_try_at is not None and work.queued.failures < GIVE_UP_AFTER
        ]
        if not upcoming:
            return IDLE_SECONDS
        return min(IDLE_SECONDS, max(_MIN_WAIT_SECONDS, (min(upcoming) - now).total_seconds()))


class _Outcome(StrEnum):
    DONE = "done"
    FAILED = "failed"
    GAVE_UP = "gave_up"


def _is_due(queued: QueuedAcquisition | None, now: datetime) -> bool:
    if queued is None:
        return True
    if queued.failures >= GIVE_UP_AFTER:
        return False
    return queued.next_try_at is None or queued.next_try_at <= now


def _state(
    artwork_id: str,
    queued: QueuedAcquisition | None,
    *,
    now: datetime,
    fetching: tuple[str, datetime] | None,
    pause: QueuePause | None,
) -> AcquisitionState:
    failures = 0 if queued is None else queued.failures
    detail = None if queued is None else queued.detail
    if fetching is not None and fetching[0] == artwork_id:
        return AcquisitionState(artwork_id, AcquisitionPhase.FETCHING, failures=failures, since=fetching[1])
    if queued is not None and queued.failures >= GIVE_UP_AFTER:
        return AcquisitionState(artwork_id, AcquisitionPhase.GAVE_UP, failures=failures, detail=detail)
    if not _is_due(queued, now):
        assert queued is not None  # noqa: S101 -- a work with no row is always due
        return AcquisitionState(
            artwork_id, AcquisitionPhase.FAILED, failures=failures, detail=detail, next_try_at=queued.next_try_at
        )
    if pause is not None:
        return AcquisitionState(
            artwork_id, AcquisitionPhase.PAUSED, failures=failures, detail=pause.detail, condition=pause.condition
        )
    return AcquisitionState(artwork_id, AcquisitionPhase.QUEUED, failures=failures, detail=detail)


def run_acquisition_queue(
    queue: AcquisitionQueue, *, stop: threading.Event, after_pass: Callable[[], None] = lambda: None
) -> None:
    """Run a pass at once, then whenever nudged or something falls due, until `stop` is set.

    `after_pass` is called once per completed pass: the seam a test counts passes by.
    """
    while not stop.is_set():
        try:
            queue.run(stop=stop)
        except (
            Exception
        ) as exc:  # prawduct:allow prawduct/broad-except -- a background loop that dies stops every fetch, silently
            log.exception(
                "an acquisition queue pass failed; it pauses and tries again", extra={"event": "acquisition.queue_error"}
            )
            queue.note_error(exc)
        after_pass()
        # Its own catch, because waiting reads the store too (when is the next
        # retry due?), and a read that fails here would otherwise end the thread
        # with no line in the journal while every accepted work read "queued".
        # A pause is the answer, as for a failed pass: a paused queue's wait
        # reads nothing, so a broken store cannot spin the loop.
        try:
            queue.wait_for_work()
        except (
            Exception
        ) as exc:  # prawduct:allow prawduct/broad-except -- a background loop that dies stops every fetch, silently
            log.exception(
                "the acquisition queue could not wait for its next work; it pauses and tries again",
                extra={"event": "acquisition.queue_error"},
            )
            queue.note_error(exc)


def start_acquisition_queue(queue: AcquisitionQueue) -> Callable[[], None]:
    """Run the queue on a daemon thread, returning the call that stops it."""
    stop = threading.Event()
    thread = threading.Thread(
        target=run_acquisition_queue, args=(queue,), kwargs={"stop": stop}, name=ACQUISITION_QUEUE_THREAD_NAME, daemon=True
    )
    thread.start()

    def halt() -> None:
        stop.set()
        queue.nudge()
        thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
        if thread.is_alive():
            log.warning(
                "the acquisition queue did not stop when asked; a fetch is still running and is abandoned",
                extra={"event": "acquisition.queue_wedged", "waited_seconds": _SHUTDOWN_JOIN_SECONDS},
            )

    return halt


__all__ = [
    "ACQUISITION_QUEUE_THREAD_NAME",
    "GIVE_UP_AFTER",
    "IDLE_SECONDS",
    "PAUSED_RETRY_SECONDS",
    "RETRY_AFTER",
    "AcquisitionPhase",
    "AcquisitionQueue",
    "AcquisitionState",
    "QueueEntry",
    "QueueListing",
    "QueuePassResult",
    "QueuePause",
    "start_acquisition_queue",
]
