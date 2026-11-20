"""Months of spending, read through the service the Spend page and any twin of it use (Chunk 36).

Each answer is compared with the service's own figure for the same month
(`month_spend`) and its own words (`SpendTotal.words`), never with arithmetic
written here, so the history cannot say a month cost something the month's own
report does not.
"""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arrt.library.services import spend_history
from arrt.persistence.discovery_records import CostStatus, InitiatedBy, SpendCategory

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _spend(discovery, *, at, cost="0.10", category=SpendCategory.DISCOVERY_TOKENS, run=None, status=CostStatus.KNOWN, model="m"):
    return discovery.record_spend(
        category=category,
        cost_usd=Decimal(0) if status is CostStatus.UNKNOWN else Decimal(cost),
        discovery_run_id=None if run is None else run.id,
        model_id=model,
        at=at,
        cost_status=status,
    )


def test_the_current_month_is_listed_even_when_nothing_was_spent(discovery):
    history = spend_history.read(discovery, now=NOW)

    assert [(each.year, each.month) for each in history.months] == [(2026, 11)]
    assert history.months[0].total.words == "$0.00"
    assert (history.months[0].categories, history.months[0].gets, history.months[0].unknown_calls) == ([], [], [])
    assert history.older_months == 0


def test_each_month_says_what_the_services_own_month_report_says(discovery, run):
    _spend(discovery, at=datetime(2026, 11, 3, tzinfo=UTC), cost="0.25", run=run)
    _spend(discovery, at=datetime(2026, 11, 4, tzinfo=UTC), status=CostStatus.UNKNOWN, run=run)
    _spend(discovery, at=datetime(2026, 10, 31, 23, 59, tzinfo=UTC), cost="1.5", run=run)

    history = spend_history.read(discovery, now=NOW)

    assert [(each.year, each.month) for each in history.months] == [(2026, 11), (2026, 10)]
    for listed in history.months:
        assert listed.total == discovery.month_spend(year=listed.year, month=listed.month)
    assert history.months[0].total.words == "at least $0.25, and 1 call whose cost is unknown"
    assert history.months[1].total.words == "$1.50"


def test_a_month_is_cut_at_utc_midnight(discovery):
    _spend(discovery, at=datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC), cost="1")
    _spend(discovery, at=datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC), cost="2")
    # 02:00 on 1 November in UTC+5 is 21:00 on 31 October in UTC: the UTC month, not the writer's.
    _spend(discovery, at=datetime(2026, 11, 1, 2, 0, tzinfo=timezone(timedelta(hours=5))), cost="4")

    november, october = spend_history.read(discovery, now=NOW).months

    assert (november.total.cost_usd, october.total.cost_usd) == (Decimal(2), Decimal(5))


def test_categories_count_every_call_and_the_unknown_ones_apart(discovery):
    at = datetime(2026, 11, 5, tzinfo=UTC)
    _spend(discovery, at=at, cost="0.30", category=SpendCategory.ASK_TOKENS)
    _spend(discovery, at=at, cost="0.20", category=SpendCategory.ASK_TOKENS)
    _spend(discovery, at=at, category=SpendCategory.ASK_TOKENS, status=CostStatus.UNKNOWN)
    _spend(discovery, at=at, cost="0.05", category=SpendCategory.MAT_COLOR_VISION)

    categories = spend_history.read(discovery, now=NOW).months[0].categories

    # In the enum's order, and only the kinds that were spent on.
    assert [each.category for each in categories] == [SpendCategory.MAT_COLOR_VISION, SpendCategory.ASK_TOKENS]
    ask = categories[1]
    assert (ask.calls, ask.total.cost_usd, ask.total.unknown_calls) == (3, Decimal("0.50"), 1)
    assert ask.total.words == "at least $0.50, and 1 call whose cost is unknown"


def test_gets_are_listed_by_their_own_calls_newest_first_and_spend_without_one_is_not_a_get(discovery, run):
    other = discovery.start_discovery_run(intent_text="Hopper", initiated_by=InitiatedBy.WEB_UI)
    at = datetime(2026, 11, 5, tzinfo=UTC)
    _spend(discovery, at=at, cost="0.10", run=run)
    _spend(discovery, at=at, status=CostStatus.UNKNOWN, run=other)
    _spend(discovery, at=at, cost="0.07", category=SpendCategory.ASK_TOKENS)

    month = spend_history.read(discovery, now=NOW).months[0]

    by_id = {each.run.id: each for each in month.gets}
    assert set(by_id) == {run.id, other.id}, "an Ask reply belongs to no Get and must not be listed as one"
    assert (by_id[run.id].calls, by_id[run.id].total.cost_usd) == (1, Decimal("0.10"))
    assert by_id[other.id].total.words == "at least $0.00, and 1 call whose cost is unknown"
    assert [each.run.started_at for each in month.gets] == sorted((each.run.started_at for each in month.gets), reverse=True)


def test_a_gets_calls_in_two_months_are_counted_in_each_never_twice(discovery, run):
    _spend(discovery, at=datetime(2026, 10, 30, tzinfo=UTC), cost="0.40", run=run)
    _spend(discovery, at=datetime(2026, 11, 2, tzinfo=UTC), cost="0.10", run=run)

    november, october = spend_history.read(discovery, now=NOW).months

    assert [each.total.cost_usd for each in november.gets] == [Decimal("0.10")]
    assert [each.total.cost_usd for each in october.gets] == [Decimal("0.40")]


def test_unknown_calls_are_listed_apart_newest_first_with_what_and_which_get(discovery, run):
    _spend(discovery, at=datetime(2026, 11, 2, tzinfo=UTC), cost="0.10", run=run)
    older = _spend(discovery, at=datetime(2026, 11, 3, tzinfo=UTC), status=CostStatus.UNKNOWN, run=run, model="vision-1")
    newer = _spend(
        discovery, at=datetime(2026, 11, 9, tzinfo=UTC), category=SpendCategory.ASK_TOKENS, status=CostStatus.UNKNOWN, model=None
    )

    calls = spend_history.read(discovery, now=NOW).months[0].unknown_calls

    assert [each.spend_id for each in calls] == [
        newer.id,
        older.id,
    ], "the known call must not be listed, and the newest comes first"
    assert (calls[1].category, calls[1].model_id, calls[1].run_id) == (SpendCategory.DISCOVERY_TOKENS, "vision-1", run.id)
    assert (calls[0].category, calls[0].model_id, calls[0].run_id) == (SpendCategory.ASK_TOKENS, None, None)


@pytest.mark.parametrize(("spent_in", "limit", "listed", "older"), [(3, 12, 4, 0), (3, 2, 2, 2), (13, 12, 12, 2)])
def test_only_the_months_that_spent_are_listed_up_to_the_limit_and_the_rest_are_counted(
    discovery, spent_in, limit, listed, older
):
    for back in range(1, spent_in + 1):
        year, month = divmod(2026 * 12 + 10 - back, 12)
        _spend(discovery, at=datetime(year, month + 1, 10, tzinfo=UTC))

    history = spend_history.read(discovery, now=NOW, limit=limit)

    assert (len(history.months), history.older_months) == (min(listed, limit), older)
    keys = [(each.year, each.month) for each in history.months]
    assert keys == sorted(keys, reverse=True)
    assert keys[0] == (2026, 11), "the current month is first whether or not it spent"
