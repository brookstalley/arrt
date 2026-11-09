"""Settings › Watches, and what a Watch's work says elsewhere, in a real browser against a real server.

A Watch is written here, says where it stands in the server's sentence, and is
changed control by control; a pass is driven by the test (`services.scheduler`),
as the app's lifespan does on its thread. What a Watch finds is said to be a
Watch's on its Get, and an overdue Watch reaches the status indicator and Status.
"""

from decimal import Decimal

import httpx
import pytest

from arrt.library.discovery.openrouter import KeyStatus
from arrt.persistence.discovery_records import InitiatedBy

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

WORDS = "new abstract expressionist paintings in museum collections"


def panel_of(ui, watch_id: str):
    return ui.page.locator(f"[data-watch='{watch_id}']")


def test_a_watch_written_here_is_listed_with_its_sentence_and_its_controls(ui, services):
    ui.open("#watches")
    ui.page.wait_for_selector(".new-watch")
    assert ui.page.locator(".page-facts").inner_text() == "No Watches yet."

    ui.page.locator("#new-watch-words").fill(WORDS)
    ui.page.locator("#new-watch-cadence").select_option("weekly")
    ui.page.locator(".new-watch button[type=submit]").click()
    ui.page.wait_for_selector("section.watch")

    [watch] = services.watches.list()
    assert (watch.intent_text, watch.cadence, watch.created_by) == (WORDS, "weekly", InitiatedBy.WEB_UI)
    panel = panel_of(ui, watch.id)
    assert panel.locator("h2").inner_text() == WORDS
    assert panel.locator(".watch-standing").inner_text() == "Not run yet: it runs at the next pass."
    assert panel.locator(f"#watch-{watch.id}-cadence").input_value() == "weekly"
    assert ui.page.locator(".page-facts").inner_text() == "1 Watch, 1 on."


def test_a_watch_refused_while_unattended_work_is_off_says_so_and_points_to_general(ui, services):
    watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    services.scheduler.run_pass()

    ui.open("#watches")
    ui.page.wait_for_selector("section.watch")

    assert panel_of(ui, watch.id).locator(".watch-standing").inner_text() == (
        "Not run: unattended work is off in Settings › General."
    )
    assert ui.page.locator(".unattended-standing").inner_text() == "Unattended work is off, so nothing runs with nobody watching."
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
    assert cap.input_value() == ""
    assert services.watches.get(watch.id).monthly_cap_usd is None


def test_removing_a_watch_asks_first_and_a_no_keeps_it(ui, services):
    watch = services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI)
    ui.open("#watches")
    ui.page.wait_for_selector("section.watch")

    panel_of(ui, watch.id).locator("button", has_text="Remove…").click()
    dialog = ui.page.locator("dialog.confirm")
    assert f"Remove the Watch “{WORDS}”?" in dialog.inner_text()
    dialog.locator("button", has_text="Cancel").click()
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
        assert ui.page.locator("h1").inner_text() == WORDS
        assert ui.page.locator(".found-by-watch").inner_text().startswith("Found by one of your Watches, with nobody watching.")

        ui.open(f"#review/{run_id}")
        ui.page.wait_for_selector(".found-by-watch")

        ui.open("#queue")
        ui.page.wait_for_selector("h1")
        assert "Get from a Watch" in ui.page.locator("#view").inner_text()

        ui.open(f"#get/{asked.id}")
        ui.page.wait_for_selector("h1")
        assert ui.page.locator("h1").inner_text() == "something a person asked"
        assert ui.page.locator(".found-by-watch").count() == 0


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
    assert ui.page.locator(".watches-reading .fault").inner_text().startswith(f"“{WORDS}” is overdue")


def test_with_nothing_overdue_the_indicator_says_nothing_of_watches(ui, services):
    services.watches.create(intent_text=WORDS, enabled=False, surface=InitiatedBy.WEB_UI)
    ui.open("#watches")
    ui.page.wait_for_function("document.querySelector('#status').dataset.state !== undefined")

    assert "Watch" not in ui.page.locator("#status").evaluate("(n) => n.textContent")
