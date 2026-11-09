"""The Library's scheduler: one thread that wakes on an interval and runs each job's pass.

**It knows jobs, not Watches.** Watches are its first job and upgrades (#178) are
meant to be its second, so a job is anything with a name and a `run_pass` that
says what it did. The Watch job is here too, because it is the only one.

**A positive line on every pass, empty ones included** (`scheduler.pass`, one per
job), because a scheduler that stopped is the new "down looks like up"
(`observability-strategy.md`). The browser sees a stopped scheduler without the
log: a Watch is *overdue* when it has been due for a whole cadence with nothing
started or refused (`WatchStanding.overdue`), reckoned when the Watch is read.

**What a pass may start is decided by `UnattendedAllowance.standing`, then the
Watch's own cap**, both before anything is spent. `initiated_by` stays an
attribution: the scheduler checks permission because it is what starts
unattended work, never because of what a run is labelled.

**A Watch's run is an ordinary discovery run**, started `unattended` with the
Watch's id and the household's unattended model. Its finds stop in To review:
nothing here writes a verdict (`security-model.md` § The unattended trigger fired).
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from arrt.library.services.runner import DiscoveryRunner
from arrt.library.services.settings import UNATTENDED_MODEL, SettingsService
from arrt.library.services.unattended import UnattendedAllowance
from arrt.library.services.watches import WatchRefusal, WatchService
from arrt.persistence.discovery_records import InitiatedBy
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How long the scheduler sleeps between passes. Hourly is the finest cadence,
#: so a Watch starts within a few minutes of being due; a pass that finds nothing
#: due costs a read of a handful of rows.
PASS_SECONDS: Final[float] = 300.0

#: What the scheduler's thread is called, in a stack dump and in the tests.
SCHEDULER_THREAD_NAME: Final[str] = "scheduler"

#: How long a shutdown waits for a pass in flight. A pass only starts runs, whose
#: work happens on threads of their own, so it is short.
_SHUTDOWN_JOIN_SECONDS: Final[float] = 5.0


@dataclass(frozen=True)
class PassResult:
    """What one job's pass did, for its `scheduler.pass` line."""

    due: int = 0
    started: int = 0
    refused: int = 0


class Job(Protocol):
    @property
    def name(self) -> str: ...

    def run_pass(self) -> PassResult: ...


class WatchJob:
    """Starts each Watch that is due, if the allowance and its cap allow, and records why not otherwise."""

    name: Final[str] = "watches"

    def __init__(
        self,
        watches: WatchService,
        unattended: UnattendedAllowance,
        runner: DiscoveryRunner,
        settings: SettingsService,
        *,
        estimate: Callable[[], Decimal],
    ) -> None:
        self._watches = watches
        self._unattended = unattended
        self._runner = runner
        self._settings = settings
        #: What a run is expected to cost before it starts: phase 1's estimate,
        #: phase 2 being free (`DiscoverySettings`).
        self._estimate = estimate

    def run_pass(self) -> PassResult:
        due = self._watches.due()
        started = refused = 0
        # What this pass has already started and not yet been billed for. Each
        # start is priced on top of it, so several due Watches cannot all start
        # on room in the allowance for one.
        committed = Decimal(0)
        for standing in due:
            watch = standing.watch
            refusal = self._refusal(standing.spent_usd, standing.cap_usd, committed)
            if refusal is None:
                refusal = self._start(watch.id, watch.intent_text)
            if refusal is None:
                started += 1
                committed += self._estimate()
            else:
                refused += 1
                self._watches.record_refused(watch.id, refusal)
                log.info(
                    "watch %s was due and did not start: %s",
                    watch.id,
                    refusal,
                    extra={"event": "watch.refused", "watch_id": watch.id, "refusal": str(refusal)},
                )
        return PassResult(due=len(due), started=started, refused=refused)

    def _refusal(self, spent: Decimal, cap: Decimal, committed: Decimal) -> WatchRefusal | None:
        estimate = self._estimate()
        standing = self._unattended.standing(committed + estimate)
        if standing.refusal is not None:
            return WatchRefusal(str(standing.refusal))
        # To the cent, as the allowance is: a cap with nothing left refuses even
        # a run with no estimate.
        if spent >= cap or spent + estimate > cap:
            return WatchRefusal.CAP_SPENT
        return None

    def _start(self, watch_id: str, intent_text: str) -> WatchRefusal | None:
        model = self._settings.value(UNATTENDED_MODEL) or None
        try:
            run = self._runner.start(intent_text=intent_text, initiated_by=InitiatedBy.UNATTENDED, model=model, watch_id=watch_id)
        except ServiceError:
            log.exception(
                "watch %s could not start a run", watch_id, extra={"event": "watch.could_not_start", "watch_id": watch_id}
            )
            return WatchRefusal.COULD_NOT_START
        try:
            self._watches.record_started(watch_id, run.id)
        except ServiceError:
            # The run is started and will spend; only the note of it failed. Said
            # with the run's id, because the next pass, not seeing it, will start
            # this Watch again.
            log.exception(
                "watch %s started run %s and could not record it",
                watch_id,
                run.id,
                extra={"event": "watch.unrecorded_start", "watch_id": watch_id, "run_id": run.id},
            )
        log.info(
            "watch %s started run %s",
            watch_id,
            run.id,
            extra={"event": "watch.started", "watch_id": watch_id, "run_id": run.id, "model": model},
        )
        return None


class Scheduler:
    """Runs every job's pass, logging one line per job per pass whatever it did."""

    def __init__(self, jobs: Sequence[Job]) -> None:
        self._jobs = tuple(jobs)

    def run_pass(self) -> dict[str, PassResult]:
        results: dict[str, PassResult] = {}
        for job in self._jobs:
            try:
                result = job.run_pass()
            except Exception:  # prawduct:allow prawduct/broad-except -- worker boundary: one job's fault must not stop the next
                log.exception("a scheduled job's pass failed", extra={"event": "scheduler.pass_failed", "job": job.name})
                continue
            results[job.name] = result
            log.info(
                "scheduler pass: %s, %d due, %d started, %d refused",
                job.name,
                result.due,
                result.started,
                result.refused,
                extra={
                    "event": "scheduler.pass",
                    "job": job.name,
                    "due": result.due,
                    "started": result.started,
                    "refused": result.refused,
                },
            )
        return results


def start_scheduler(scheduler: Scheduler, *, interval_seconds: float = PASS_SECONDS) -> Callable[[], None]:
    """Run passes on a daemon thread, the first at once, returning the call that stops it."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            scheduler.run_pass()
            stop.wait(interval_seconds)

    thread = threading.Thread(target=loop, name=SCHEDULER_THREAD_NAME, daemon=True)
    thread.start()
    log.info("the scheduler runs a pass every %ds", interval_seconds, extra={"event": "scheduler.started"})

    def halt() -> None:
        stop.set()
        thread.join(timeout=_SHUTDOWN_JOIN_SECONDS)
        if thread.is_alive():
            log.warning(
                "the scheduler did not stop when asked and is still running",
                extra={"event": "scheduler.wedged", "waited_seconds": _SHUTDOWN_JOIN_SECONDS},
            )

    return halt
