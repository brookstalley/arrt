"""The Spend page's read, over real HTTP (Chunk 36): the months, and the sentence the server says each in."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from arrt.library.services.discovery import SpendTotal
from arrt.persistence.discovery_records import CostStatus, InitiatedBy, SpendCategory


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def test_the_months_answer_in_the_servers_own_sentences(http, services):
    now = datetime.now(UTC)
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
