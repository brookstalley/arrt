"""Settings › Watches, and what a Watch's work says elsewhere, in a real browser against a real server.

A Watch is written here, says where it stands in the server's sentence, and is
changed control by control; a pass is driven by the test (`services.scheduler`),
as the app's lifespan does on its thread. What a Watch finds is said to be a
Watch's on its Get, and an overdue Watch reaches the status indicator and Status.
"""

import re
from decimal import Decimal

import httpx
import pytest

from arrt.library.discovery.openrouter import KeyStatus
from arrt.persistence.discovery_records import InitiatedBy

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

WORDS = "new abstract expressionist paintings in museum collections"


def panel_of(ui, watch_id: str):
    return ui.page.locator(f"[data-watch='{watch_id}']")


def test_a_watch_written_here_is_listed_with_its_sentence_and_its_controls(ui, services):
    ui.open("#watches")
    ui.page.wait_for_selector(".new-watch")
    expect(ui.page.locator(".page-facts")).to_have_text("No Watches yet.", use_inner_text=True)

    ui.page.locator("#new-watch-words").fill(WORDS)
    ui.page.locator("#new-watch-cadence").select_option("weekly")
    ui.page.locator(".new-watch button[type=submit]").click()
    ui.page.wait_for_selector("section.watch")

    [watch] = services.watches.list()
    assert (watch.intent_text, watch.cadence, watch.created_by) == (WORDS, "weekly", InitiatedBy.WEB_UI)
    panel = panel_of(ui, watch.id)
    expect(panel.locator("h2")).to_have_text(WORDS, use_inner_text=True)
    expect(panel.locator(".watch-standing")).to_have_text("Not run yet: it runs at the next pass.", use_inner_text=True)
    expect(panel.locator(f"#watch-{watch.id}-cadence")).to_have_value("weekly")
    expect(ui.page.locator(".page-facts")).to_have_text("1 Watch, 1 on.", use_inner_text=True)


def test_a_watch_s_words_are_described_as_asked_of_ask_and_never_of_discover(ui):
    """The page Ask was called Discover until 2026-10-02; its help said so for a month after (audit-6 finding 21)."""
    ui.open("#watches")
    ui.page.wait_for_selector(".new-watch")

    expect(ui.view).to_contain_text("as you would put it to Ask", use_inner_text=True)
    expect(ui.view).not_to_contain_text("Discover", use_inner_text=True)


def test_a_watch_refused_while_unattended_work_is_off_says_so_and_points_to_general(ui, services):
    watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    services.scheduler.run_pass()

    ui.open("#watches")
    ui.page.wait_for_selector("section.watch")

    expect(panel_of(ui, watch.id).locator(".watch-standing")).to_have_text(
        "Not run: unattended work is off in Settings › General.", use_inner_text=True
    )
    expect(ui.page.locator(".unattended-standing")).to_have_text(
        "Unattended work is off, so nothing runs with nobody watching.", use_inner_text=True
    )
    ui.page.locator(".watches-standing a").click()
    ui.page.wait_for_selector("#setting-unattended_work")


def test_switching_a_watch_off_applies_at_once_and_a_refused_cap_returns_to_what_it_was(ui, services):
    watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    ui.open("#watches")
    ui.page.wait_for_selector("section.watch")

    ui.page.locator(f"#watch-{watch.id}-enabled").select_option("off")
    ui.page.wait_for_function(
        f"document.querySelector(\"[data-watch='{watch.id}'] .watch-standing\").textContent.startsWith('Off')"
    )
    assert services.watches.get(watch.id).enabled is False

    cap = ui.page.locator(f"#watch-{watch.id}-cap")
    cap.fill("3")
    cap.press("Enter")
    said = ui.said_beside(cap)
    assert "cannot be more than it; got $3.00" in said, "the allowance is $0.00, so any cap is refused, in the server's words"
    expect(cap).to_have_value("")
    assert services.watches.get(watch.id).monthly_cap_usd is None


def test_removing_a_watch_asks_first_and_a_no_keeps_it(ui, services):
    watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    ui.open("#watches")
    ui.page.wait_for_selector("section.watch")

    panel_of(ui, watch.id).locator("button", has_text="Remove…").click()
    dialog = ui.page.locator("dialog.confirm")
    expect(dialog).to_contain_text(f"Remove the Watch “{WORDS}”?", use_inner_text=True)
    dialog.locator("button", has_text="Cancel").click()
    # The No was received, so the Watch's still being there is a Watch kept and not a removal yet to come.
    expect(dialog).to_be_hidden()
    assert [kept.id for kept in services.watches.list()] == [watch.id]

    panel_of(ui, watch.id).locator("button", has_text="Remove…").click()
    ui.page.locator("dialog.confirm button", has_text="Remove").click()
    ui.page.wait_for_selector(".empty")
    assert services.watches.list() == []


class TestWithAModelKey:
    @pytest.fixture
    def key_status(self):
        return lambda: KeyStatus(limit_usd=Decimal(20), usage_usd=Decimal(1), remaining_usd=Decimal(19))

    def test_a_watchs_get_says_it_was_found_by_a_watch_and_one_asked_for_does_not(self, ui, services):
        services.settings.set("unattended_work", "on", surface=InitiatedBy.WEB_UI)
        services.settings.set("unattended_allowance_usd", "5", surface=InitiatedBy.WEB_UI)
        watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
        services.scheduler.run_pass()
        run_id = services.watches.get(watch.id).last_run_id
        assert run_id, "the pass started no run, so nothing below is tested"
        asked = services.runner.start(intent_text="something a person asked", initiated_by=InitiatedBy.WEB_UI)

        ui.open("#watches")
        ui.page.wait_for_selector("section.watch")
        panel_of(ui, watch.id).locator(".watch-last-run a").click()
        ui.page.wait_for_selector(".found-by-watch")
        expect(ui.page.locator("h1")).to_have_text(WORDS, use_inner_text=True)
        expect(ui.page.locator(".found-by-watch")).to_have_text(
            re.compile("^" + re.escape("Found by one of your Watches, with nobody watching.")), use_inner_text=True
        )

        ui.open(f"#review/{run_id}")
        ui.page.wait_for_selector(".found-by-watch")

        ui.open("#queue")
        ui.page.wait_for_selector("h1")
        expect(ui.view).to_contain_text("Get from a Watch", use_inner_text=True)

        ui.open(f"#get/{asked.id}")
        ui.page.wait_for_selector("h1")
        expect(ui.page.locator("h1")).to_have_text("something a person asked", use_inner_text=True)
        expect(ui.page.locator(".found-by-watch")).to_have_count(0)


def an_overdue_reading(health: dict) -> dict:
    return health | {"watches": {"overdue": [WORDS], "allowance_spent": False}}


def test_an_overdue_watch_is_named_on_the_status_indicator_and_on_status(ui, server_url):
    ui.serve("**/api/health", [an_overdue_reading(httpx.get(f"{server_url}/api/health", timeout=30).json())])
    ui.open("#watches")

    indicator = ui.page.locator("#status")
    ui.page.wait_for_function("document.querySelector('#status').dataset.state !== undefined")
    assert f"Watch “{WORDS}” is overdue" in indicator.evaluate("(n) => n.textContent")

    ui.open("#health")
    ui.page.wait_for_selector(".watches-reading")
    expect(ui.page.locator(".watches-reading .fault")).to_have_text(
        re.compile("^" + re.escape(f"“{WORDS}” is overdue")), use_inner_text=True
    )


def test_with_nothing_overdue_the_indicator_says_nothing_of_watches(ui, services):
    services.watches.create(intent_text=WORDS, enabled=False, surface=InitiatedBy.WEB_UI)
    ui.open("#watches")
    ui.page.wait_for_function("document.querySelector('#status').dataset.state !== undefined")

    assert "Watch" not in ui.page.locator("#status").evaluate("(n) => n.textContent")
