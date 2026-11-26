"""The Spend page's read, over real HTTP: the months, and the sentence the server says each in."""

from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from arrt.library.services.discovery import SpendTotal
from arrt.persistence.discovery_records import CostStatus, InitiatedBy, SpendCategory


def _services_clock() -> datetime:
    raise AssertionError("the services' clock is read only inside a test (`_now_is_the_services`)")


@pytest.fixture(autouse=True)
def _now_is_the_services(shared_clock, monkeypatch):
    """`_now` reads the services' clock (`shared_clock`), so what a test writes beside them is on their time."""
    monkeypatch.setitem(globals(), "_services_clock", shared_clock)


def _now() -> datetime:
    return _services_clock()


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def test_the_months_answer_in_the_servers_own_sentences(http, services):
    now = _now()
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.WEB_UI)
    services.discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.0213"), discovery_run_id=run.id, model_id="the-model", at=now
    )
    unknown = services.discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS,
        cost_usd=Decimal(0),
        discovery_run_id=run.id,
        model_id="the-model",
        at=now,
        cost_status=CostStatus.UNKNOWN,
    )

    history = http.get("/api/spend").raise_for_status().json()

    month = history["months"][0]
    assert (month["year"], month["month"]) == (now.year, now.month)
    assert month["summary"] == "at least $0.0213, and 1 call whose cost is unknown"
    assert month["summary"] == SpendTotal(cost_usd=Decimal("0.0213"), unknown_calls=1).words
    assert (month["cost_usd"], month["unknown_cost_calls"]) == ("0.0213", 1)
    assert [(each["category"], each["calls"], each["summary"]) for each in month["categories"]] == [
        ("discovery_tokens", 2, "at least $0.0213, and 1 call whose cost is unknown")
    ]
    assert [(each["run_id"], each["kind"], each["intent"], each["calls"]) for each in month["gets"]] == [
        (run.id, "discovery", "Dalí", 2)
    ]
    assert [(each["spend_id"], each["category"], each["model_id"], each["run_id"]) for each in month["unknown_calls"]] == [
        (unknown.id, "discovery_tokens", "the-model", run.id)
    ]
    assert history["older_months"] == 0


def test_a_month_with_nothing_spent_says_so_in_the_same_form(http):
    month = http.get("/api/spend").raise_for_status().json()["months"][0]

    assert (month["summary"], month["unknown_cost_calls"], month["categories"], month["gets"], month["unknown_calls"]) == (
        "$0.00",
        0,
        [],
        [],
        [],
    )


def test_a_spend_below_the_finest_figure_is_not_said_as_nothing(http, services):
    """$0.000012 is not "$0.00", the words of a month with no spend; it is under the finest figure, never rounded up."""
    services.discovery.record_spend(category=SpendCategory.MAT_COLOR_VISION, cost_usd=Decimal("0.000012"), model_id="m")

    month = http.get("/api/spend").raise_for_status().json()["months"][0]

    assert month["summary"] == "under $0.0001"
    assert [each["summary"] for each in month["categories"]] == ["under $0.0001"]
    # With a call whose cost is unknown beside it, the floor is still more than nothing.
    assert SpendTotal(cost_usd=Decimal("0.000012"), unknown_calls=1).words == (
        "more than $0.00, and 1 call whose cost is unknown"
    )


def test_a_spend_of_a_thousand_dollars_or_more_is_grouped_as_a_count_is(http, services):
    """ "$1,234.56", grouped as the client writes a count ("2,000"); still rounded down, to the cent."""
    services.discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("1234.567"), model_id="m")

    month = http.get("/api/spend").raise_for_status().json()["months"][0]

    assert month["summary"] == "$1,234.56"
    assert SpendTotal(cost_usd=Decimal("1234.567"), unknown_calls=2).words == (
        "at least $1,234.56, and 2 calls whose cost is unknown"
    )
