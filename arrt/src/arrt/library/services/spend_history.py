"""What was spent, month by month: where it went, which Gets it was for, and which calls nobody could price.

The ledger (`SpendRecord`) answers three questions a person asks of the money,
and `DiscoveryService.month_spend` answers only the first, as one figure: how
much did this month cost. This reads the same rows into the other two, for the
page that lists them: **what was it spent on** (a category's calls and cost) and
**which Gets spent it** (a run's own calls in the month), and, apart from both,
**which calls were sent and never said what they cost** (`CostStatus.UNKNOWN`),
each by when, what and which Get, so a person can set them against the
provider's own activity page.

**Every figure is a `SpendTotal`, so every sentence is its `words`.** A month,
a category and a Get each say "at least $X, and N calls whose cost is unknown"
when any call in them is unknown, in the one function that words it; nothing
that shows these formats a number from `cost_usd` itself.

**Nothing here limits spending, and nothing implies it does.** The ceiling is
the provider's, a credit limit on the key (`SpendRecord`'s docstring); this is
attribution and history only, and offers nothing to set.

**The month is the UTC month**, the boundary the provider's own limit resets on
(`arrt.library.months`), as the month's single figure is.

Read from a `DiscoveryService`'s public methods and never from its store: the
route that serves this and an agent's twin of it must not be able to come to
different answers by reading the ledger two ways.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from arrt.library.months import utc_month_of
from arrt.library.services.discovery import DiscoveryService, SpendTotal
from arrt.persistence.discovery_records import CostStatus, DiscoveryRun, SpendCategory, SpendRecord

#: How many months are listed, the current one first: a household's spend table
#: holds a few hundred rows a year, so a year of months is a page, and the rest
#: is counted rather than listed (`SpendHistory.older_months`).
MONTHS_LISTED: Final[int] = 12


@dataclass(frozen=True, slots=True)
class SpendByCategory:
    """What one kind of spending cost in a month."""

    category: SpendCategory
    #: How many calls the ledger holds under it, the unknown ones included.
    calls: int
    total: SpendTotal


@dataclass(frozen=True, slots=True)
class SpendOnGet:
    """What one Get spent itself in a month.

    **Its own calls, not its family's**: a re-search is a Get of its own, listed
    on its own row, and a family can span months, so a figure that rolled the
    family up would count the same call under two months. A Get's whole cost,
    retries included, is `GET /api/runs/{id}/spend`.
    """

    run: DiscoveryRun
    calls: int
    total: SpendTotal


@dataclass(frozen=True, slots=True)
class UnknownCostCall:
    """One call that was sent and never said what it cost: the provider may have billed it."""

    spend_id: str
    category: SpendCategory
    occurred_at: datetime
    model_id: str | None
    #: The Get it belonged to; None for a call that belonged to none (Ask's reply, a mat).
    run_id: str | None


@dataclass(frozen=True, slots=True)
class SpendMonth:
    """One UTC calendar month: its total, where it went, which Gets spent it, and its unknown calls."""

    year: int
    month: int
    total: SpendTotal
    #: Only the kinds the month spent on, in the enum's order.
    categories: Sequence[SpendByCategory]
    #: The Gets that spent in it, newest first.
    gets: Sequence[SpendOnGet]
    #: Every call whose cost is unknown, newest first.
    unknown_calls: Sequence[UnknownCostCall]


@dataclass(frozen=True, slots=True)
class SpendHistory:
    """The months listed, newest first, and how many earlier ones there are that are not."""

    months: Sequence[SpendMonth]
    older_months: int


def read(discovery: DiscoveryService, *, now: datetime | None = None, limit: int = MONTHS_LISTED) -> SpendHistory:
    """The current month and the `limit - 1` most recent others that spent anything, newest first.

    The current month is always listed, spent in or not, so a page opened before
    anything is spent says so ("$0.00") rather than listing nothing.
    """
    moment = now if now is not None else discovery.now()
    this_month = _key(moment)
    ledger = discovery.spend_ledger()
    by_month: dict[tuple[int, int], list[SpendRecord]] = defaultdict(list)
    for record in ledger:
        by_month[_key(record.occurred_at)].append(record)
    spent_in = sorted((key for key in by_month if key != this_month), reverse=True)
    listed = [this_month, *spent_in[: limit - 1]]
    runs: dict[str, DiscoveryRun] = {}
    return SpendHistory(
        months=[_month(year, month, by_month.get((year, month), []), discovery, runs) for year, month in listed],
        older_months=len(spent_in) - len(listed) + 1,
    )


def _key(moment: datetime) -> tuple[int, int]:
    since, _ = utc_month_of(moment)
    return since.year, since.month


def _month(
    year: int, month: int, inside: Sequence[SpendRecord], discovery: DiscoveryService, runs: dict[str, DiscoveryRun]
) -> SpendMonth:
    by_category: dict[SpendCategory, list[SpendRecord]] = defaultdict(list)
    by_run: dict[str, list[SpendRecord]] = defaultdict(list)
    for record in inside:
        by_category[record.category].append(record)
        if record.discovery_run_id is not None:
            by_run[record.discovery_run_id].append(record)
    for run_id in by_run:
        if run_id not in runs:
            runs[run_id] = discovery.get_run(run_id)
    return SpendMonth(
        year=year,
        month=month,
        total=SpendTotal.of(inside),
        categories=[
            SpendByCategory(category=category, calls=len(by_category[category]), total=SpendTotal.of(by_category[category]))
            for category in SpendCategory
            if category in by_category
        ],
        gets=sorted(
            (SpendOnGet(run=runs[run_id], calls=len(rows), total=SpendTotal.of(rows)) for run_id, rows in by_run.items()),
            key=lambda each: each.run.started_at,
            reverse=True,
        ),
        unknown_calls=[
            UnknownCostCall(
                spend_id=record.id,
                category=record.category,
                occurred_at=record.occurred_at,
                model_id=record.model_id,
                run_id=record.discovery_run_id,
            )
            for record in sorted(inside, key=lambda each: each.occurred_at, reverse=True)
            if record.cost_status is CostStatus.UNKNOWN
        ],
    )
