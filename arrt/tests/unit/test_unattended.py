"""Whether agent work may start with nobody watching: the switch, the key, and the month's allowance."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from arrt.library.services.settings import Limits, SettingsService
from arrt.library.services.unattended import Refusal, UnattendedAllowance
from arrt.persistence.discovery_records import (
    DiscoveryRun,
    InitiatedBy,
    RunKind,
    RunStatus,
    SpendCategory,
    SpendRecord,
)
from arrt.persistence.sqlite_discovery import SqliteDiscovery

#: Mid-November, UTC: the month the allowance counts.
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def discovery(store) -> SqliteDiscovery:
    return SqliteDiscovery(store._store)


def a_run(discovery, run_id: str, started_by: InitiatedBy) -> str:
    discovery.add_run(
        DiscoveryRun(
            id=run_id,
            kind=RunKind.DISCOVERY,
            initiated_by=started_by,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=NOW,
        )
    )
    return run_id


def spent(discovery, amount: str, *, run_id: str | None, at: datetime = NOW, record_id: str | None = None) -> None:
    discovery.add_spend_record(
        SpendRecord(
            id=record_id or f"spend-{run_id}-{amount}-{at.isoformat()}",
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=Decimal(amount),
            occurred_at=at,
            discovery_run_id=run_id,
        )
    )


def allowance(discovery, *, on: bool = True, usd: str = "5.00", has_key: bool = True) -> UnattendedAllowance:
    settings = SettingsService(discovery, environment={"unattended_work": "on" if on else "off", "unattended_allowance_usd": usd})
    return UnattendedAllowance(settings, discovery, has_key=has_key, now=lambda: NOW)


def test_off_by_default_so_a_fresh_install_spends_nothing_unattended(discovery):
    standing = UnattendedAllowance(SettingsService(discovery), discovery, has_key=True, now=lambda: NOW).standing()

    assert (standing.switched_on, standing.allowance_usd, standing.refusal) == (False, Decimal("0.00"), Refusal.OFF)
    assert standing.may_start is False


def test_switched_on_with_no_key_is_refused_for_the_key(discovery):
    standing = allowance(discovery, has_key=False).standing()

    assert standing.refusal is Refusal.NO_KEY
    assert "no model key" in standing.sentence


def test_switched_on_with_no_allowance_is_refused_and_says_the_allowance_is_nothing(discovery):
    standing = allowance(discovery, usd="0").standing()

    assert standing.refusal is Refusal.ALLOWANCE_SPENT
    assert "$0.00" in standing.sentence


def test_only_the_spend_of_runs_started_unattended_counts(discovery):
    spent(discovery, "1.25", run_id=a_run(discovery, "watched", InitiatedBy.UNATTENDED))
    spent(discovery, "3.00", run_id=a_run(discovery, "asked", InitiatedBy.WEB_UI))
    spent(discovery, "2.00", run_id=a_run(discovery, "agent", InitiatedBy.MCP_CLIENT))
    spent(discovery, "0.40", run_id=None)  # a mat colour: the curator's act, with no run

    standing = allowance(discovery).standing()

    assert standing.spent_usd == Decimal("1.25")
    assert standing.remaining_usd == Decimal("3.75")
    assert standing.may_start is True


def test_the_month_is_utcs_from_its_first_instant_to_the_next_months(discovery):
    run = a_run(discovery, "watched", InitiatedBy.UNATTENDED)
    spent(discovery, "1.00", run_id=run, at=datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC))
    spent(discovery, "0.10", run_id=run, at=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    spent(discovery, "0.20", run_id=run, at=datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC))
    spent(discovery, "2.00", run_id=run, at=datetime(2026, 12, 1, 0, 0, tzinfo=UTC))

    assert allowance(discovery).spent_this_month() == Decimal("0.30")


def test_a_piece_that_would_pass_the_allowance_is_refused_and_one_that_fits_may_start(discovery):
    spent(discovery, "4.98", run_id=a_run(discovery, "watched", InitiatedBy.UNATTENDED))
    unattended = allowance(discovery, usd="5.00")

    assert unattended.standing(estimate_usd=Decimal("0.02")).may_start is True, "exactly to the allowance fits"
    passed = unattended.standing(estimate_usd=Decimal("0.03"))
    assert passed.refusal is Refusal.ALLOWANCE_SPENT
    assert "$4.98 of $5.00" in passed.sentence


def test_the_remaining_figure_is_never_below_nothing(discovery):
    """A run under way may finish past the allowance (it is budgeting, not the ceiling)."""
    spent(discovery, "6.00", run_id=a_run(discovery, "watched", InitiatedBy.UNATTENDED))

    standing = allowance(discovery, usd="5.00").standing()

    assert (standing.remaining_usd, standing.refusal) == (Decimal(0), Refusal.ALLOWANCE_SPENT)


def test_a_stored_allowance_above_a_budget_since_lowered_reads_as_nothing(discovery):
    """Failing closed: an allowance the deployment no longer allows is not spent from."""
    SettingsService(discovery).set("unattended_allowance_usd", "15", surface=InitiatedBy.WEB_UI)
    settings = SettingsService(discovery, environment={"unattended_work": "on"}, limits=Limits(monthly_budget_usd=Decimal(10)))

    standing = UnattendedAllowance(settings, discovery, has_key=True, now=lambda: NOW).standing()

    assert standing.allowance_usd == Decimal("0.00")
    assert standing.may_start is False


def test_an_allowance_spent_to_the_cent_refuses_even_a_piece_with_no_estimate(discovery):
    """The setting says work stops starting once it is spent; a piece that cannot say its cost is no exception."""
    spent(discovery, "5.00", run_id=a_run(discovery, "watched", InitiatedBy.UNATTENDED))

    standing = allowance(discovery, usd="5.00").standing()

    assert standing.refusal is Refusal.ALLOWANCE_SPENT
    assert standing.may_start is False
