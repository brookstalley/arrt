"""What is left of the month's budget, and how much an action will cost, in tiers.

The owner's ruling of 2026-10-07 (`ia-proposal.md` § Rulings, ruling 3): spend
is shown as a monthly budget and a tier on every action, and taking the action
is the approval. Asking for approval a cent at a time is a nuisance; being
conscious of total spend is the point.

**The budget is read from the provider, never tallied here**
(`nonfunctional-requirements.md` § Direction, the corollary: read from the
authority, not a local tally). On a key with a monthly limit, `limit_remaining`
is what is left this month (`openrouter-api-findings.md`, re-measured
2026-10-07). On a key with no limit the provider's own `usage_monthly` is read
against `MONTHLY_BUDGET_USD`, which the deployment sets and nothing enforces:
the provider's per-key limit stays the only thing that stops the bill.

**Display only.** `/key` lags the provider's enforcement by minutes and was
seen reporting credit while calls were refused, so nothing gates on this. The
refusal at the cap is what stops spending, and it says the month's budget is
spent (`openrouter._read_body`).
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from arrt.library.discovery.openrouter import KeyStatus, OpenRouterError

log = logging.getLogger(__name__)


class CostTier(StrEnum):
    """How much an action will cost, as the curator reads it before taking it."""

    FREE = "free"
    #: Cents.
    CENTS = "$"
    #: Dimes.
    DIMES = "$$"
    #: A dollar or so, or more.
    DOLLARS = "$$$"


#: The tier boundaries, and the one place they are set: an estimate under the
#: first is `$`, under the second `$$`, and anything else `$$$`. Nothing is free
#: but nothing.
CENTS_BELOW: Final[Decimal] = Decimal("0.05")
DIMES_BELOW: Final[Decimal] = Decimal("0.50")


def cost_tier(estimate_usd: Decimal) -> CostTier:
    """The tier of an estimate: free at zero, then `$`, `$$` or `$$$` by `CENTS_BELOW` and `DIMES_BELOW`."""
    if estimate_usd < 0:
        raise ValueError(f"An estimate cannot be negative, got {estimate_usd}.")
    if estimate_usd == 0:
        return CostTier.FREE
    if estimate_usd < CENTS_BELOW:
        return CostTier.CENTS
    if estimate_usd < DIMES_BELOW:
        return CostTier.DIMES
    return CostTier.DOLLARS


class BudgetState(StrEnum):
    """Why the budget reads what it reads."""

    #: The key has a monthly limit, and the provider said what is left of it.
    KNOWN = "known"
    #: The key has no limit, and `MONTHLY_BUDGET_USD` is what is left measured
    #: against: a figure the deployment chose and nothing enforces.
    CONFIGURED = "configured"
    #: The key has no limit and no budget is configured: spend this month is all
    #: there is to say.
    UNCAPPED = "uncapped"
    #: No OpenRouter key is configured, so nothing here spends.
    NOT_CONFIGURED = "not_configured"
    #: The provider could not be asked just now.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class BudgetView:
    """What is left of this month's budget, and how that is known."""

    state: BudgetState
    #: What is left this month; `None` unless `KNOWN` or `CONFIGURED`. Never
    #: below zero: a key past its budget has nothing left.
    remaining_usd: Decimal | None = None
    #: The month's budget: the key's limit, or `MONTHLY_BUDGET_USD`.
    budget_usd: Decimal | None = None
    #: What the provider counts as spent this month, where it said.
    spent_usd: Decimal | None = None
    #: A sentence for the curator when the figure needs one.
    note: str | None = None


#: How long one reading of the provider's figures is kept. The sidebar asks on
#: every page, and the figure lags by minutes anyway; a failure is not kept.
KEPT_FOR_SECONDS: Final[float] = 60.0


class BudgetService:
    """Read what is left of the month's budget from the provider."""

    def __init__(
        self,
        key_status: Callable[[], KeyStatus] | None,
        *,
        monthly_budget_usd: Decimal | None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._key_status = key_status
        self._monthly_budget_usd = monthly_budget_usd
        self._clock = clock
        self._lock = threading.Lock()
        self._kept: tuple[float, KeyStatus] | None = None

    def view(self) -> BudgetView:
        """What is left this month, or why that cannot be said."""
        if self._key_status is None:
            return BudgetView(
                state=BudgetState.NOT_CONFIGURED,
                note="No OpenRouter key is configured, so nothing here spends money.",
            )
        try:
            status = self._read(self._key_status)
        except OpenRouterError as exc:
            log.warning("Could not read the OpenRouter key's budget: %s", exc, extra={"event": "budget.unavailable"})
            return BudgetView(
                state=BudgetState.UNAVAILABLE, note="What is left of this month's budget could not be read just now."
            )
        if status.remaining_usd is not None:
            return BudgetView(
                state=BudgetState.KNOWN,
                remaining_usd=max(status.remaining_usd, Decimal(0)),
                budget_usd=status.limit_usd,
                spent_usd=status.usage_monthly_usd,
            )
        if self._monthly_budget_usd is not None:
            if status.usage_monthly_usd is None:
                return BudgetView(
                    state=BudgetState.UNAVAILABLE,
                    budget_usd=self._monthly_budget_usd,
                    note="OpenRouter did not say what was spent this month, so what is left cannot be said.",
                )
            return BudgetView(
                state=BudgetState.CONFIGURED,
                remaining_usd=max(self._monthly_budget_usd - status.usage_monthly_usd, Decimal(0)),
                budget_usd=self._monthly_budget_usd,
                spent_usd=status.usage_monthly_usd,
                note="The OpenRouter key has no limit, so nothing stops spending at this budget.",
            )
        return BudgetView(
            state=BudgetState.UNCAPPED,
            spent_usd=status.usage_monthly_usd,
            note="The OpenRouter key has no limit and no monthly budget is set (MONTHLY_BUDGET_USD).",
        )

    def _read(self, key_status: Callable[[], KeyStatus]) -> KeyStatus:
        now = self._clock()
        with self._lock:
            if self._kept is not None and now - self._kept[0] < KEPT_FOR_SECONDS:
                return self._kept[1]
        # Asked outside the lock: a slow provider must not hold every other page.
        status = key_status()
        with self._lock:
            self._kept = (now, status)
        return status
