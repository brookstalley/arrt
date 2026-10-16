"""The month's budget, read from the provider, and the tier an estimate shows (#290).

The budget is display only and read from the key, never tallied from the
ledger; the tiers are one rule with its boundaries in one place.
"""

from decimal import Decimal

import pytest

from arrt.library.discovery.openrouter import KeyStatus, OpenRouterError
from arrt.library.services.spending import (
    CENTS_BELOW,
    DIMES_BELOW,
    KEPT_FOR_SECONDS,
    BudgetService,
    BudgetState,
    CostTier,
    cost_tier,
)

CAPPED = KeyStatus(
    limit_usd=Decimal(20),
    usage_usd=Decimal("0.588850173"),
    remaining_usd=Decimal("19.94596061"),
    resets="monthly",
    usage_monthly_usd=Decimal("0.05403939"),
)
UNCAPPED = KeyStatus(limit_usd=None, usage_usd=Decimal("3.5"), remaining_usd=None, resets=None, usage_monthly_usd=Decimal("1.25"))


# -- tiers ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estimate", "tier"),
    [
        (Decimal(0), CostTier.FREE),
        (Decimal("0.0001"), CostTier.CENTS),
        (CENTS_BELOW - Decimal("0.0001"), CostTier.CENTS),
        (CENTS_BELOW, CostTier.DIMES),
        (DIMES_BELOW - Decimal("0.0001"), CostTier.DIMES),
        (DIMES_BELOW, CostTier.DOLLARS),
        (Decimal(12), CostTier.DOLLARS),
    ],
)
def test_an_estimate_is_free_only_at_nothing_and_changes_tier_at_each_boundary(estimate, tier):
    assert cost_tier(estimate) is tier


def test_the_boundaries_are_the_owners_cents_and_dimes():
    """Under five cents is $, under fifty cents $$ (the owner, 2026-10-07: "$0.01, $0.10, or $1")."""
    assert (Decimal("0.05"), Decimal("0.50")) == (CENTS_BELOW, DIMES_BELOW)


def test_a_negative_estimate_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        cost_tier(Decimal("-0.01"))


def test_asking_shows_the_tier_of_its_bound(runner, settings):
    estimate = runner.estimate()

    assert estimate.cost_usd == settings.discovery_settings.phase1_estimate_usd
    assert estimate.tier is cost_tier(settings.discovery_settings.phase1_estimate_usd)


# -- the budget ---------------------------------------------------------------------


def test_a_capped_key_shows_what_the_provider_says_is_left():
    view = BudgetService(lambda: CAPPED, monthly_budget_usd=Decimal(5)).view()

    assert view.state is BudgetState.KNOWN
    assert view.remaining_usd == Decimal("19.94596061"), "the provider's figure, not the configured budget's"
    assert (view.budget_usd, view.spent_usd) == (Decimal(20), Decimal("0.05403939"))


def test_a_key_past_its_limit_has_nothing_left_never_less():
    """`/key` lags; a figure past the limit is shown as none left."""
    over = KeyStatus(limit_usd=Decimal(20), usage_usd=Decimal(21), remaining_usd=Decimal(-1), resets="monthly")

    assert BudgetService(lambda: over, monthly_budget_usd=None).view().remaining_usd == Decimal(0)


def test_an_uncapped_key_is_measured_against_the_configured_budget_by_the_providers_monthly_spend():
    view = BudgetService(lambda: UNCAPPED, monthly_budget_usd=Decimal(10)).view()

    assert view.state is BudgetState.CONFIGURED
    # The provider's month, not its lifetime `usage` (3.5), and not a ledger tally.
    assert (view.remaining_usd, view.budget_usd, view.spent_usd) == (Decimal("8.75"), Decimal(10), Decimal("1.25"))
    assert "nothing stops spending" in view.note


def test_an_uncapped_key_with_no_budget_says_only_what_was_spent():
    view = BudgetService(lambda: UNCAPPED, monthly_budget_usd=None).view()

    assert (view.state, view.remaining_usd, view.spent_usd) == (BudgetState.UNCAPPED, None, Decimal("1.25"))
    assert "MONTHLY_BUDGET_USD" in view.note


def test_a_budget_with_no_monthly_spend_reported_says_it_cannot_tell():
    silent = KeyStatus(limit_usd=None, usage_usd=Decimal(3), remaining_usd=None, resets=None)

    view = BudgetService(lambda: silent, monthly_budget_usd=Decimal(10)).view()

    assert (view.state, view.remaining_usd) == (BudgetState.UNAVAILABLE, None), "never the whole budget left"


def test_no_key_says_nothing_spends():
    view = BudgetService(None, monthly_budget_usd=Decimal(10)).view()

    assert (view.state, view.remaining_usd) == (BudgetState.NOT_CONFIGURED, None)


def test_a_reading_is_kept_for_a_minute_and_a_failure_is_not():
    now = [0.0]
    answers = [OpenRouterError("down"), CAPPED, UNCAPPED]
    asked = []

    def key_status():
        asked.append(now[0])
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    budget = BudgetService(key_status, monthly_budget_usd=None, clock=lambda: now[0])

    assert budget.view().state is BudgetState.UNAVAILABLE
    assert budget.view().state is BudgetState.KNOWN, "the failure was not kept"
    now[0] = KEPT_FOR_SECONDS - 1
    assert budget.view().state is BudgetState.KNOWN
    now[0] = KEPT_FOR_SECONDS + 1
    assert budget.view().state is BudgetState.UNCAPPED
    assert asked == [0.0, 0.0, KEPT_FOR_SECONDS + 1]
