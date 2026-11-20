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
    """The figure is what is known, the unknown calls are counted beside it, and the words say "at least"."""
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


def test_the_allowance_a_watch_and_a_run_each_say_their_figure_in_the_services_words(http, services):
    """`summary` on `GET /api/unattended`, `/api/watches` and `/api/runs/{id}`, and on their MCP twins: `SpendTotal.words`.

    One unattended run of one Watch, with a call whose cost is known and one
    whose cost is unknown: each answer's figure is a floor, and its words say
    "at least" and count the unknown call, where `spent_usd` and
    `actual_cost_usd` carry the known figure alone.
    """
    from arrt.mcp import bindings

    watch = services.watches.create(intent_text="Dalí", surface=InitiatedBy.WEB_UI)
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.UNATTENDED, watch_id=watch.id)
    services.discovery.record_spend(category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal("0.0213"), discovery_run_id=run.id)
    services.discovery.record_spend(
        category=SpendCategory.DISCOVERY_TOKENS, cost_usd=Decimal(0), discovery_run_id=run.id, cost_status=CostStatus.UNKNOWN
    )
    services.discovery.cancel_run(run.id, actual_cost_usd=services.discovery.run_cost(run.id).direct)
    said = "at least $0.0213, and 1 call whose cost is unknown"

    unattended = http.get("/api/unattended").raise_for_status().json()
    (listed,) = http.get("/api/watches").raise_for_status().json()["watches"]
    shown = http.get(f"/api/runs/{run.id}").raise_for_status().json()["run"]

    assert (unattended["spent_usd"], unattended["summary"]) == ("0.02", said)
    assert (listed["spent_usd"], listed["summary"]) == ("0.02", said)
    assert (shown["actual_cost_usd"], shown["summary"]) == ("0.0213", said)
    assert bindings._unattended_standing(services, {})["summary"] == said
    assert [each["summary"] for each in bindings._list_watches(services, {})["watches"]] == [said]
    assert [each["summary"] for each in bindings._list_runs(services, {})["runs"] if each["run_id"] == run.id] == [said]


def test_a_run_with_no_figure_yet_has_no_summary(http, services):
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.WEB_UI)

    shown = http.get(f"/api/runs/{run.id}").raise_for_status().json()["run"]

    assert (shown["actual_cost_usd"], shown["summary"]) == (None, None)
