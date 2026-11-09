"""A household's Watches: standing requests in words, which Arrt re-runs with nobody watching.

A Watch is the *arr apps' monitored list (Radarr's Lists), and the product's first
unattended agent work (`agents-and-memory.md` ruling 5). This module is the record
and its rules. The scheduler that runs a Watch is `scheduler.py`, and each run is
an ordinary discovery run, so it spends, dedups and is reviewed as an Ask is.

**One policy: what a Watch finds goes to To review.** Auto-accept is not offered
(the owner, 2026-11-09; `security-model.md` § The unattended trigger fired), so
there is no field for it, and nothing here writes a verdict.

**A Watch's cap is a share of the unattended allowance**, as the allowance is a
share of the month's budget. A cap above the allowance is refused when written,
and one the allowance has since fallen below reads as the allowance
(`effective_cap`), the same fail-closed rule the allowance follows under a lowered
budget. Neither replaces the provider's key limit, which is what stops the bill.

**Every write names its surface** (`created_by`, `updated_by`, and the log line),
because an agent on MCP can write a Watch, and a surprise in the month's spend has
to be traceable to whoever made it.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final

from arrt.library.services.settings import (
    UNATTENDED_ALLOWANCE,
    UNATTENDED_CADENCE,
    Cadence,
    SettingRefused,
    SettingsService,
    dollars,
)
from arrt.library.services.unattended import Refusal, UnattendedAllowance
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import DiscoveryRun, InitiatedBy, RunStatus, Watch
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)

#: How long each cadence waits between a Watch's starts.
INTERVAL: Final[dict[Cadence, timedelta]] = {
    Cadence.HOURLY: timedelta(hours=1),
    Cadence.DAILY: timedelta(days=1),
    Cadence.WEEKLY: timedelta(weeks=1),
}

#: How soon a Watch whose last attempt was refused, or whose last run did not
#: finish, is tried again: at the next pass after this, not at its full interval
#: (tacularr's "due again soon", `upgrades.md`), and never sooner, so a Watch
#: that keeps failing costs at most one attempt an hour.
RETRY_AFTER: Final[timedelta] = timedelta(hours=1)

#: How long past due a Watch may go untried before it reads as overdue. A live
#: scheduler tries a due Watch within one pass (`scheduler.PASS_SECONDS`, five
#: minutes), so an hour untried is a scheduler that has stopped, whatever the
#: Watch's cadence: a weekly Watch must not take a week to say so.
OVERDUE_AFTER: Final[timedelta] = timedelta(hours=1)

#: How a run ending this way leaves its Watch: due again soon, because nothing
#: it was asked for was done. A cancelled run was someone's choice and waits the
#: full interval, as a completed one does.
_DID_NOT_FINISH: Final[frozenset[RunStatus]] = frozenset({RunStatus.FAILED, RunStatus.INTERRUPTED, RunStatus.HALTED_BY_BUDGET})


class WatchRefusal(StrEnum):
    """Why a Watch that was due did not start: the allowance's reasons, its own cap, or a start that failed."""

    OFF = str(Refusal.OFF)
    NO_KEY = str(Refusal.NO_KEY)
    ALLOWANCE_SPENT = str(Refusal.ALLOWANCE_SPENT)
    CAP_SPENT = "cap_spent"
    COULD_NOT_START = "could_not_start"


_REFUSED: Final[dict[str, str]] = {
    WatchRefusal.OFF: "Not run: unattended work is off in Settings › General.",
    WatchRefusal.NO_KEY: "Not run: there is no model key to spend with.",
    WatchRefusal.ALLOWANCE_SPENT: "Not run: this month's unattended allowance is spent.",
    WatchRefusal.CAP_SPENT: "Not run: this Watch's monthly cap is spent.",
    WatchRefusal.COULD_NOT_START: "Not run: discovery could not start. The server log says why.",
}


@dataclass(frozen=True)
class WatchStanding:
    """Where one Watch stands: what it last did, when it is next due, and what it has spent this month."""

    watch: Watch
    cadence: Cadence
    #: The status of its last started run, or None when it has started none
    #: (or that run is gone).
    last_run_status: RunStatus | None
    #: When it is next due, or None while it is off or a run of it is in flight.
    next_due_at: datetime | None
    #: On, unattended work switched on, and due for longer than `OVERDUE_AFTER`
    #: with nothing started or refused: the sign that the scheduler has stopped.
    overdue: bool
    spent_usd: Decimal
    cap_usd: Decimal
    #: Whether this process is working on its last run now.
    in_flight: bool
    #: One sentence for the screen and the tool.
    sentence: str


@dataclass(frozen=True, slots=True)
class WatchesReading:
    """What the household's Watches need a person to know, with nobody else to tell them.

    Here because a Watch runs with nobody watching, so a stopped scheduler or a
    spent allowance does not announce itself at the next session
    (`observability-strategy.md` § Accepted detection latency, revisited
    2026-11-09). Neither is a verdict: overdue is `WatchStanding.overdue`'s rule.
    """

    #: The words of each Watch that is overdue, in the order they were written.
    overdue: Sequence[str] = ()
    #: Whether a Watch that is on is waiting for next month because the
    #: unattended allowance is spent.
    allowance_spent: bool = False


#: The longest a Watch's words may be. An Ask's request is a sentence or two; a
#: bound keeps a pasted page from becoming a standing prompt resent every pass.
MAX_INTENT_CHARS: Final[int] = 1000


class WatchService:
    """Reads and writes the household's Watches."""

    def __init__(
        self,
        store: DiscoveryStore,
        settings: SettingsService,
        unattended: UnattendedAllowance,
        *,
        working_on: Callable[[str], bool],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._settings = settings
        self._unattended = unattended
        #: Whether this process is working on a run (`DiscoveryRunner.is_working_on`).
        #: What "in flight" means for a Watch, because a run's status can name a
        #: phase nothing here advances: phase 2 with no image engine wired.
        self._working_on = working_on
        self._now = now

    # -- reads ----------------------------------------------------------------

    def list(self) -> Sequence[Watch]:
        """Every Watch, in the order the household wrote them."""
        return self._store.list_watches()

    def get(self, watch_id: str) -> Watch:
        found = self._store.get_watch(watch_id)
        if found is None:
            raise ServiceError(f"No Watch with id {watch_id!r}.")
        return found

    def cadence_of(self, watch: Watch) -> Cadence:
        """How often this Watch runs: its own cadence, or the household's default for unattended work."""
        # Read by its value, never constructed from it: a cadence a later release
        # stored must not make this Watch, the pass or the health reading
        # unreadable. Such a Watch follows the household's default meanwhile.
        own = Cadence._value2member_map_.get(watch.cadence) if watch.cadence is not None else None
        if own is None:
            return self._settings.value(UNATTENDED_CADENCE)
        return Cadence(own)

    def effective_cap(self, watch: Watch) -> Decimal:
        """What this Watch may spend this month: its cap, never more than the allowance, or the allowance."""
        allowance = self._settings.value(UNATTENDED_ALLOWANCE)
        if watch.monthly_cap_usd is None:
            return allowance
        return min(watch.monthly_cap_usd, allowance)

    def standing(self, watch: Watch) -> WatchStanding:
        """Where `watch` stands now. The scheduler and the screen both read it, so they agree on "due"."""
        now = self._now()
        cadence = self.cadence_of(watch)
        run = None if watch.last_run_id is None else self._store.get_run(watch.last_run_id)
        last_status = None if run is None else run.status
        in_flight = run is not None and not run.status.is_terminal and self._working_on(run.id)
        due_at = None if not watch.enabled or in_flight else _next_due(watch, cadence, run)
        # Reckoned from when it was due or last changed, whichever is later: a
        # Watch switched on again, or given a shorter cadence, is due at once but
        # has not yet had a pass to be tried in.
        overdue = (
            due_at is not None
            and now - max(due_at, watch.updated_at) > OVERDUE_AFTER
            and self._unattended.standing().switched_on
        )
        return WatchStanding(
            watch=watch,
            cadence=cadence,
            last_run_status=last_status,
            next_due_at=due_at,
            overdue=overdue,
            spent_usd=self._unattended.spent_by_watch_this_month(watch.id),
            cap_usd=self.effective_cap(watch),
            in_flight=in_flight,
            sentence=_sentence(watch, last_status, in_flight=in_flight, overdue=overdue),
        )

    def reading(self) -> WatchesReading:
        """What the Watches need a person to know: which are overdue, and whether a spent allowance holds one."""
        standings = [self.standing(watch) for watch in self.list()]
        holding = any(standing.watch.enabled for standing in standings) and (
            self._unattended.standing().refusal is Refusal.ALLOWANCE_SPENT
        )
        return WatchesReading(
            overdue=tuple(standing.watch.intent_text for standing in standings if standing.overdue),
            allowance_spent=holding,
        )

    def due(self) -> Sequence[WatchStanding]:
        """The Watches due to be tried now, in the order they were written."""
        now = self._now()
        standings = (self.standing(watch) for watch in self.list())
        return [standing for standing in standings if standing.next_due_at is not None and standing.next_due_at <= now]

    # -- the scheduler's bookkeeping ---------------------------------------------

    def record_started(self, watch_id: str, run_id: str) -> None:
        """A pass started a run of this Watch. Not a household edit, so `updated_*` stay."""
        self._record(watch_id, last_run_id=run_id, last_refusal=None)

    def record_refused(self, watch_id: str, refusal: WatchRefusal) -> None:
        """A pass found this Watch due and did not start it, for `refusal`."""
        self._record(watch_id, last_refusal=str(refusal))

    def _record(self, watch_id: str, **fields: str | None) -> None:
        # Read and written in one transaction, so a household's edit landing in
        # the same moment is neither lost nor overwritten by stale fields.
        with self._store.transaction():
            current = self._store.get_watch(watch_id)
            if current is None:
                # Deleted between the pass reading it and writing this: there is
                # nothing to record against, and a run already started keeps its
                # `watch_id` as history.
                return
            store_write(self._store.update_watch, replace(current, last_attempt_at=self._now(), **fields))

    # -- writes ---------------------------------------------------------------

    def create(
        self,
        *,
        intent_text: str,
        surface: InitiatedBy,
        cadence: str = "",
        monthly_cap_usd: str = "",
        enabled: bool = True,
    ) -> Watch:
        """Write a new Watch. An empty cadence follows the household's default; an empty cap leaves only the allowance."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        now = self._now()
        watch = Watch(
            id=str(uuid.uuid4()),
            intent_text=_intent(intent_text),
            enabled=bool(enabled),
            created_at=now,
            created_by=by,
            updated_at=now,
            updated_by=by,
            cadence=_cadence(cadence),
            monthly_cap_usd=self._cap(monthly_cap_usd),
        )
        store_write(self._store.add_watch, watch)
        log.info(
            "watch %s written by %s",
            watch.id,
            by,
            extra={"event": "watch.created", "watch_id": watch.id, "surface": str(by), "enabled": watch.enabled},
        )
        return watch

    def update(
        self,
        watch_id: str,
        *,
        surface: InitiatedBy,
        intent_text: str | None = None,
        cadence: str | None = None,
        monthly_cap_usd: str | None = None,
        enabled: bool | None = None,
    ) -> Watch:
        """Change what is given and leave the rest. An empty cadence or cap clears it, as on `create`."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        # Checked before the read, so the transaction below holds no store lock
        # while a refusal is composed.
        words = None if intent_text is None else _intent(intent_text)
        every = None if cadence is None else _cadence(cadence)
        cap = None if monthly_cap_usd is None else self._cap(monthly_cap_usd)
        # Read and written in one transaction, as the scheduler's bookkeeping is,
        # so a start recorded in between is never overwritten with the run before
        # it, which would leave the Watch's live run unseen and start it again.
        with self._store.transaction():
            before = self.get(watch_id)
            after = replace(
                before,
                intent_text=before.intent_text if words is None else words,
                cadence=before.cadence if cadence is None else every,
                monthly_cap_usd=before.monthly_cap_usd if monthly_cap_usd is None else cap,
                enabled=before.enabled if enabled is None else bool(enabled),
                updated_at=self._now(),
                updated_by=by,
            )
            store_write(self._store.update_watch, after)
        changed = sorted(
            name
            for name in ("intent_text", "cadence", "monthly_cap_usd", "enabled")
            if getattr(before, name) != getattr(after, name)
        )
        log.info(
            "watch %s changed (%s) by %s",
            watch_id,
            ", ".join(changed) or "nothing",
            by,
            extra={"event": "watch.updated", "watch_id": watch_id, "surface": str(by), "changed": changed},
        )
        return after

    def delete(self, watch_id: str, *, surface: InitiatedBy) -> Watch:
        """Remove a Watch and return what was removed. Its runs and their finds stay."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        going = self.get(watch_id)
        store_write(self._store.delete_watch, watch_id)
        log.info(
            "watch %s deleted by %s",
            watch_id,
            by,
            extra={"event": "watch.deleted", "watch_id": watch_id, "surface": str(by)},
        )
        return going

    def _cap(self, raw: str) -> Decimal | None:
        if not raw.strip():
            return None
        try:
            cap = dollars(raw)
        except SettingRefused as exc:
            raise ServiceError(f"A Watch's monthly cap {exc}") from exc
        allowance = self._settings.value(UNATTENDED_ALLOWANCE)
        if cap > allowance:
            raise ServiceError(
                f"A Watch's monthly cap is a share of the unattended allowance, ${allowance:.2f}, and cannot be more "
                f"than it; got ${cap:.2f}. Raise the allowance in Settings › General first, or leave the cap empty."
            )
        return cap


def _intent(raw: str) -> str:
    text = require_text(raw, field="intent_text")
    if len(text) > MAX_INTENT_CHARS:
        raise ServiceError(f"A Watch's words are at most {MAX_INTENT_CHARS} characters, got {len(text)}.")
    return text


def _cadence(raw: str) -> str | None:
    text = raw.strip().lower()
    if not text:
        return None
    try:
        return str(Cadence(text))
    except ValueError as exc:
        allowed = ", ".join(str(member) for member in Cadence)
        raise ServiceError(f"A Watch's cadence is one of {allowed}, or empty for the household's default; got {raw!r}.") from exc


def _next_due(watch: Watch, cadence: Cadence, last_run: DiscoveryRun | None) -> datetime:
    """When `watch` is next due: at once if never tried, soon after a refusal or an unfinished run, else a cadence on."""
    if watch.last_attempt_at is None:
        return watch.created_at
    again_soon = watch.last_refusal is not None or (last_run is not None and last_run.status in _DID_NOT_FINISH)
    wait = min(INTERVAL[cadence], RETRY_AFTER) if again_soon else INTERVAL[cadence]
    return watch.last_attempt_at + wait


def _sentence(watch: Watch, last_status: RunStatus | None, *, in_flight: bool, overdue: bool) -> str:
    """One sentence for where a Watch stands, the first that applies, in this order."""
    if not watch.enabled:
        return "Off: this Watch does not run until it is switched on."
    if overdue:
        return "Overdue: this Watch has been due for over an hour and has not been tried. The scheduler may have stopped."
    if in_flight:
        return "Running now."
    if watch.last_refusal is not None:
        # Read by its value, never constructed from it: a refusal a later
        # release stored must not make this Watch, or the pass, unreadable.
        return _REFUSED.get(watch.last_refusal, f"Not run: {watch.last_refusal}.")
    if watch.last_attempt_at is None:
        return "Not run yet: it runs at the next pass."
    return _LAST_RUN.get(last_status) or f"Its last run is {last_status}."


#: What a Watch's last run says of it, by how that run stands; None is a run no
#: longer recorded.
_LAST_RUN: Final[dict[RunStatus | None, str]] = {
    None: "Its last run is no longer recorded.",
    RunStatus.COMPLETED: "Last run finished; what it found is in To review.",
    RunStatus.FAILED: "Last run failed, and it will be tried again within the hour.",
    RunStatus.INTERRUPTED: "Last run was interrupted by a restart, and it will be tried again within the hour.",
    RunStatus.HALTED_BY_BUDGET: "Last run stopped at the month's budget, and it will be tried again within the hour.",
    RunStatus.CANCELLED: "Last run was cancelled.",
    RunStatus.DECLINED: "Last run was declined.",
    RunStatus.AWAITING_APPROVAL: "Last run is waiting for approval in Activity.",
    RunStatus.RESOLVING_WORKS: "Last run is still listed as asking, though nothing is working on it now.",
    RunStatus.RESOLVING_IMAGES: "Last run proposed its works; finding their images is not set up here.",
}
