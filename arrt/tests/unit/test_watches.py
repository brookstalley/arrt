"""A household's Watches: what is stored, what is refused, and what a Watch reads from the settings."""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from arrt.library.services.settings import Cadence, SettingsService
from arrt.library.services.watches import MAX_INTENT_CHARS, WatchService
from arrt.persistence.discovery_records import DiscoveryRun, InitiatedBy, RunKind, RunStatus
from arrt.persistence.file import open_catalogue_file
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.services.errors import ServiceError

WORDS = "new abstract expressionist paintings in museum collections"


@pytest.fixture
def discovery(store) -> SqliteDiscovery:
    return SqliteDiscovery(store._store)


@pytest.fixture
def settings(discovery) -> SettingsService:
    return SettingsService(discovery)


class Clock:
    """A clock a test moves, so created and updated times can be told apart."""

    def __init__(self) -> None:
        self.at = datetime(2026, 11, 9, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at

    def advance(self) -> None:
        self.at += timedelta(minutes=5)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def watches(discovery, settings, clock) -> WatchService:
    return WatchService(discovery, settings, now=clock)


def allowance(settings: SettingsService, amount: str) -> None:
    settings.set("unattended_allowance_usd", amount, surface=InitiatedBy.WEB_UI)


# -- what is stored ------------------------------------------------------------


def test_a_new_watch_is_on_follows_the_households_cadence_and_has_only_the_allowance(watches, settings):
    allowance(settings, "4")

    watch = watches.create(intent_text=f"  {WORDS}  ", surface=InitiatedBy.MCP_CLIENT)

    assert watches.get(watch.id) == watch
    assert (watch.intent_text, watch.enabled, watch.cadence, watch.monthly_cap_usd) == (WORDS, True, None, None)
    assert (watch.created_by, watch.updated_by) == (InitiatedBy.MCP_CLIENT, InitiatedBy.MCP_CLIENT)
    assert watches.cadence_of(watch) is Cadence.DAILY
    assert watches.effective_cap(watch) == Decimal("4.00")


def test_a_watch_without_a_cadence_follows_the_setting_when_it_changes(watches, settings):
    watch = watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)

    settings.set("unattended_cadence", "weekly", surface=InitiatedBy.WEB_UI)

    assert watches.cadence_of(watch) is Cadence.WEEKLY


def test_a_watch_with_its_own_cadence_keeps_it_whatever_the_setting_says(watches, settings):
    watch = watches.create(intent_text=WORDS, cadence=" Hourly ", surface=InitiatedBy.WEB_UI)
    settings.set("unattended_cadence", "weekly", surface=InitiatedBy.WEB_UI)

    assert watch.cadence == "hourly"
    assert watches.cadence_of(watch) is Cadence.HOURLY


def test_watches_are_listed_in_the_order_they_were_written(watches, clock):
    first = watches.create(intent_text="first", surface=InitiatedBy.WEB_UI)
    clock.advance()
    second = watches.create(intent_text="second", surface=InitiatedBy.WEB_UI)
    clock.advance()
    watches.update(first.id, intent_text="first, reworded", surface=InitiatedBy.WEB_UI)

    assert [watch.id for watch in watches.list()] == [first.id, second.id]


def test_a_cap_is_dollars_to_the_cent_and_a_share_of_the_allowance(watches, settings):
    allowance(settings, "5")

    assert watches.create(intent_text=WORDS, monthly_cap_usd="$2.5", surface=InitiatedBy.WEB_UI).monthly_cap_usd == Decimal(
        "2.50"
    )
    assert watches.create(intent_text=WORDS, monthly_cap_usd="5", surface=InitiatedBy.WEB_UI).monthly_cap_usd == Decimal(5)
    with pytest.raises(ServiceError, match=r"share of the unattended allowance, \$5\.00, .* got \$5\.01"):
        watches.create(intent_text=WORDS, monthly_cap_usd="5.01", surface=InitiatedBy.WEB_UI)


def test_a_cap_is_refused_while_there_is_no_allowance_saying_where_to_raise_it(watches):
    with pytest.raises(ServiceError, match=r"\$0\.00, .* got \$1\.00\. Raise the allowance in Settings › General"):
        watches.create(intent_text=WORDS, monthly_cap_usd="1", surface=InitiatedBy.WEB_UI)


def test_a_cap_above_an_allowance_since_lowered_reads_as_the_allowance(watches, settings):
    allowance(settings, "5")
    capped = watches.create(intent_text=WORDS, monthly_cap_usd="4", surface=InitiatedBy.WEB_UI)
    under = watches.create(intent_text=WORDS, monthly_cap_usd="1", surface=InitiatedBy.WEB_UI)

    allowance(settings, "2")

    assert watches.get(capped.id).monthly_cap_usd == Decimal("4.00"), "the household's choice is kept"
    assert watches.effective_cap(watches.get(capped.id)) == Decimal("2.00")
    assert watches.effective_cap(watches.get(under.id)) == Decimal("1.00")


# -- what is refused, by name ---------------------------------------------------


@pytest.mark.parametrize(
    ("given", "said"),
    [
        ({"intent_text": "   "}, "intent_text cannot be empty"),
        ({"intent_text": "x" * (MAX_INTENT_CHARS + 1)}, f"at most {MAX_INTENT_CHARS} characters"),
        ({"cadence": "fortnightly"}, "cadence is one of hourly, daily, weekly"),
        ({"monthly_cap_usd": "-1"}, "at least 0"),
        ({"monthly_cap_usd": "a few dollars"}, "must be an amount in dollars"),
        ({"monthly_cap_usd": "0.001"}, "whole cents"),
    ],
)
def test_a_watch_that_cannot_be_is_refused_naming_what_is_wrong(watches, settings, given, said):
    allowance(settings, "5")
    fields = {"intent_text": WORDS} | given

    with pytest.raises(ServiceError, match=said):
        watches.create(surface=InitiatedBy.WEB_UI, **fields)
    assert watches.list() == []


def test_an_unknown_watch_is_refused_by_every_action_naming_its_id(watches):
    for attempt in (
        lambda: watches.get("nope"),
        lambda: watches.update("nope", enabled=False, surface=InitiatedBy.WEB_UI),
        lambda: watches.delete("nope", surface=InitiatedBy.WEB_UI),
    ):
        with pytest.raises(ServiceError, match="No Watch with id 'nope'"):
            attempt()


# -- changing and removing ---------------------------------------------------


def test_an_update_changes_what_it_is_given_and_leaves_the_rest(watches, settings, clock):
    allowance(settings, "5")
    before = watches.create(intent_text=WORDS, cadence="weekly", monthly_cap_usd="3", surface=InitiatedBy.WEB_UI)
    clock.advance()

    after = watches.update(before.id, enabled=False, surface=InitiatedBy.MCP_CLIENT)

    assert after.enabled is False
    assert (after.intent_text, after.cadence, after.monthly_cap_usd) == (WORDS, "weekly", Decimal("3.00"))
    assert (after.created_by, after.created_at) == (InitiatedBy.WEB_UI, before.created_at)
    assert (after.updated_by, after.updated_at) == (InitiatedBy.MCP_CLIENT, clock.at)
    assert watches.get(before.id) == after


def test_an_empty_cadence_or_cap_clears_it_and_an_absent_one_leaves_it(watches, settings):
    allowance(settings, "5")
    watch = watches.create(intent_text=WORDS, cadence="hourly", monthly_cap_usd="3", surface=InitiatedBy.WEB_UI)

    kept = watches.update(watch.id, intent_text="reworded", surface=InitiatedBy.WEB_UI)
    assert (kept.cadence, kept.monthly_cap_usd) == ("hourly", Decimal("3.00"))

    cleared = watches.update(watch.id, cadence="", monthly_cap_usd=" ", surface=InitiatedBy.WEB_UI)
    assert (cleared.cadence, cleared.monthly_cap_usd) == (None, None)


def test_a_refused_update_changes_nothing(watches, settings):
    allowance(settings, "5")
    watch = watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)

    with pytest.raises(ServiceError):
        watches.update(watch.id, intent_text="reworded", monthly_cap_usd="9", surface=InitiatedBy.MCP_CLIENT)

    assert watches.get(watch.id) == watch


def test_every_write_is_logged_with_the_surface_that_made_it(watches, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.services.watches"):
        watch = watches.create(intent_text=WORDS, surface=InitiatedBy.MCP_CLIENT)
        watches.update(watch.id, cadence="weekly", enabled=False, surface=InitiatedBy.WEB_UI)
        watches.delete(watch.id, surface=InitiatedBy.MCP_CLIENT)

    lines = {record.event: record for record in caplog.records}
    assert (lines["watch.created"].surface, lines["watch.created"].watch_id) == ("mcp_client", watch.id)
    assert (lines["watch.updated"].surface, lines["watch.updated"].changed) == ("web_ui", ["cadence", "enabled"])
    assert lines["watch.deleted"].surface == "mcp_client"


def test_a_deleted_watch_is_gone_and_its_runs_keep_naming_it(watches, discovery):
    watch = watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    run = DiscoveryRun(
        id="run-1",
        kind=RunKind.DISCOVERY,
        initiated_by=InitiatedBy.UNATTENDED,
        status=RunStatus.COMPLETED,
        approval_required=False,
        started_at=datetime.now(UTC),
        intent_text=WORDS,
        watch_id=watch.id,
    )
    discovery.add_run(run)

    assert watches.delete(watch.id, surface=InitiatedBy.WEB_UI) == watch
    assert watches.list() == []
    assert discovery.get_run("run-1").watch_id == watch.id


# -- the stored format ----------------------------------------------------------


def test_a_catalogue_file_from_before_watches_opens_and_gains_the_table_and_the_column(tmp_path):
    """Additive: a file with no `watches` table and no `discovery_runs.watch_id` is widened, not refused."""
    path = tmp_path / "catalogue.sqlite"
    store = open_catalogue_file(path)
    SqliteDiscovery(store).add_run(
        DiscoveryRun(
            id="before",
            kind=RunKind.DISCOVERY,
            initiated_by=InitiatedBy.WEB_UI,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=datetime.now(UTC),
            intent_text="asked by a person",
        )
    )
    store.close()
    with sqlite3.connect(path) as raw:
        raw.execute("DROP TABLE watches")
        raw.execute("DROP INDEX discovery_runs_by_watch")
        raw.execute("ALTER TABLE discovery_runs DROP COLUMN watch_id")
    assert "watch_id" not in {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(discovery_runs)")}

    reopened = open_catalogue_file(path)
    try:
        discovery = SqliteDiscovery(reopened)
        assert discovery.get_run("before").watch_id is None
        service = WatchService(discovery, SettingsService(discovery))
        written = service.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
        assert service.list() == [written]
    finally:
        reopened.close()
