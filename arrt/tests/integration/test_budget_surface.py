"""The month's budget and the estimate's tier, over real HTTP (#290).

The provider's key is a stated answer in place of OpenRouter's `/key`, wired
where the entry point wires the real client's.
"""

from decimal import Decimal

import httpx
import pytest

from arrt.library.discovery.openrouter import KeyStatus
from arrt.library.services.spending import cost_tier


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
