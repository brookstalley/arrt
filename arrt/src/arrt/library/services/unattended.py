"""Whether agent work may start with nobody watching, and what such work has spent.

**The allowance is budgeting under the ceiling, not a second ceiling**
(`build-plan-unattended-settings.md`, the owner's ruling of 2026-11-09). The
ceiling stays the provider's key limit (`nonfunctional-requirements.md`); the
allowance bounds unattended work's share of the month, as the per-run search cap
bounds one run's ambition. So a run already under way may finish past it, and
the next one is refused.

**What counts is the spend of runs started unattended**, read through each
spend row's run (`InitiatedBy.UNATTENDED`), in the UTC calendar month, the
boundary the provider's limit resets on. A spend row with no run (a mat colour)
is the curator's act and never counts.

`initiated_by` stays an attribution, never an authorisation input: nothing
branches on it but this sum. Whatever starts unattended work asks `may_start`
first; nothing else does.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from arrt.library.services.settings import UNATTENDED_ALLOWANCE, UNATTENDED_WORK, SettingsService, Switch
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import InitiatedBy

_DECEMBER = 12


class Refusal(StrEnum):
    """Why unattended work may not start now."""

    OFF = "off"
    NO_KEY = "no_key"
    ALLOWANCE_SPENT = "allowance_spent"


@dataclass(frozen=True)
class Standing:
    """Where unattended work stands this month, and whether a piece of it may start."""

    switched_on: bool
    allowance_usd: Decimal
    spent_usd: Decimal
    #: Why it may not start, or None when it may.
    refusal: Refusal | None
    #: One sentence for the screen and the log.
    sentence: str

    @property
    def remaining_usd(self) -> Decimal:
        return max(self.allowance_usd - self.spent_usd, Decimal(0))

    @property
    def may_start(self) -> bool:
        return self.refusal is None


class UnattendedAllowance:
    """Answers whether unattended work may start, from the settings and the month's spend."""

    def __init__(
        self,
        settings: SettingsService,
        store: DiscoveryStore,
        *,
        has_key: bool,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._store = store
        self._has_key = has_key
        self._now = now

    def spent_this_month(self) -> Decimal:
        """What runs started unattended were billed in this UTC calendar month."""
        now = self._now().astimezone(UTC)
        since = datetime(now.year, now.month, 1, tzinfo=UTC)
        until = datetime(now.year + (now.month == _DECEMBER), now.month % _DECEMBER + 1, 1, tzinfo=UTC)
        started_by: dict[str, InitiatedBy | None] = {}
        total = Decimal(0)
        for record in self._store.list_spend_records(since=since, until=until):
            run_id = record.discovery_run_id
            if run_id is None:
                continue
            if run_id not in started_by:
                run = self._store.get_run(run_id)
                started_by[run_id] = None if run is None else run.initiated_by
            if started_by[run_id] is InitiatedBy.UNATTENDED:
                total += record.cost_usd
        return total

    def standing(self, estimate_usd: Decimal = Decimal(0)) -> Standing:
        """Where unattended work stands, and whether a piece expected to cost `estimate_usd` may start.

        Refused when the setting is off, when there is no model key to spend
        with, or when what is spent this month plus the estimate would pass the
        allowance. An allowance of nothing refuses everything that costs anything.
        """
        switched_on = self._settings.value(UNATTENDED_WORK) is Switch.ON
        allowance = self._settings.value(UNATTENDED_ALLOWANCE)
        spent = self.spent_this_month()
        if not switched_on:
            refusal, sentence = Refusal.OFF, "Unattended work is off, so nothing runs with nobody watching."
        elif not self._has_key:
            refusal, sentence = Refusal.NO_KEY, "There is no model key, so unattended work has nothing to spend with."
        elif allowance == 0:
            refusal = Refusal.ALLOWANCE_SPENT
            sentence = "The monthly allowance for unattended work is $0.00, so nothing runs with nobody watching."
        elif spent + estimate_usd > allowance:
            refusal = Refusal.ALLOWANCE_SPENT
            sentence = f"This month's unattended allowance is spent: ${spent:.2f} of ${allowance:.2f}."
        else:
            refusal = None
            sentence = f"Unattended work may run: ${spent:.2f} of this month's ${allowance:.2f} is spent."
        return Standing(switched_on=switched_on, allowance_usd=allowance, spent_usd=spent, refusal=refusal, sentence=sentence)
