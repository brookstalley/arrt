"""The month's budget and the estimate's tier, over real HTTP (#290).

The provider's key is a stated answer in place of OpenRouter's `/key`, wired
where the entry point wires the real client's.
"""

from decimal import Decimal

import httpx
import pytest

from arrt.library.discovery.openrouter import KeyStatus
from arrt.library.services.spending import cost_tier
from arrt.persistence.discovery_records import CostStatus, InitiatedBy, SpendCategory


@pytest.fixture
def key_status():
    return lambda: KeyStatus(
        limit_usd=Decimal(20),
        usage_usd=Decimal("0.588850173"),
        remaining_usd=Decimal("19.94596061"),
        resets="monthly",
        usage_monthly_usd=Decimal("0.05403939"),
    )


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def test_the_budget_is_what_the_provider_says_is_left_this_month(http):
    budget = http.get("/api/budget").raise_for_status().json()

    assert budget == {
        "state": "known",
        "remaining_usd": "19.94596061",
        "budget_usd": "20",
        "spent_usd": "0.05403939",
        "note": None,
        "tiers": {"cents_below_usd": "0.05", "dimes_below_usd": "0.50"},
    }


class TestWithNoKey:
    @pytest.fixture
    def key_status(self):
        return None

    def test_the_budget_says_nothing_spends(self, http):
        budget = http.get("/api/budget").raise_for_status().json()

        assert (budget["state"], budget["remaining_usd"]) == ("not_configured", None)


def test_asking_carries_the_tier_of_its_bound(http, settings):
    estimate = http.get("/api/estimate").raise_for_status().json()

    bound = settings.discovery_settings.phase1_estimate_usd
    assert (estimate["estimated_cost_usd"], estimate["tier"]) == (str(bound), str(cost_tier(bound)))
    assert estimate["tier"] != "free", "asking always spends something"


def test_a_run_s_spend_counts_its_calls_whose_cost_is_unknown_apart(http, services):
    """Chunk 35: the figure is what is known, the unknown calls are counted beside it, and the words say "at least"."""
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.WEB_UI)
    services.discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.0213"), discovery_run_id=run.id)
    services.discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal(0), discovery_run_id=run.id, cost_status=CostStatus.UNKNOWN
    )

    spend = http.get(f"/api/runs/{run.id}/spend").raise_for_status().json()

    assert (spend["cost_usd"], spend["unknown_cost_calls"]) == ("0.0213", 1)
    assert spend["summary"] == "at least $0.0213, and 1 call whose cost is unknown"


def test_a_run_with_every_cost_known_counts_none_unknown(http, services):
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.WEB_UI)
    services.discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.05"), discovery_run_id=run.id)

    spend = http.get(f"/api/runs/{run.id}/spend").raise_for_status().json()

    assert (spend["unknown_cost_calls"], spend["summary"]) == (0, "$0.05")
