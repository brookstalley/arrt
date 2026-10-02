"""Activity › Queue and History, in a real browser.

`information-architecture.md` § The *arr layout: Queue is the searches that have
not ended and History the ones that have, split on the server's `is_terminal`
flag. Every listing below holds runs of both kinds, so a page that showed
everything, or split on the wrong field, fails rather than passing on a fixture
that could not tell.
"""

import pytest
from payloads import a_run

from arrt.http.models import RunListOut

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


def a_listing(*runs) -> dict:
    return RunListOut(runs=list(runs), count=len(runs), total=len(runs), truncated=False).model_dump(mode="json")


#: One run in each state the split has to tell apart. Waiting at the gate is in
#: flight: the run has not ended, and it is waiting on the curator.
WORKING = a_run(run_id="r-working", intent="Working on it", status="resolving_works", is_terminal=False)
AT_THE_GATE = a_run(run_id="r-gate", intent="Waiting at the gate", status="awaiting_approval", is_terminal=False)
DONE = a_run(run_id="r-done", intent="All done", status="completed", is_terminal=True)
BROKE = a_run(run_id="r-broke", intent="Ran out of money", status="halted_by_budget", is_terminal=True)
EVERY_KIND = a_listing(WORKING, AT_THE_GATE, DONE, BROKE)


def test_queue_shows_the_searches_that_have_not_ended(ui):
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#queue")
    ui.page.wait_for_selector("h3:has-text('In flight')")

    text = ui.text()
    assert "Working on it" in text
    assert "Waiting at the gate" in text, "a run at the approval gate is waiting on the curator, so it is in flight"
    assert "All done" not in text
    assert "Ran out of money" not in text
    assert "In flight (2)" in text


def test_history_shows_the_searches_that_ended_and_how(ui):
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#history")
    ui.page.wait_for_selector("h3:has-text('Finished')")

    text = ui.text()
    assert "All done" in text
    assert "Ran out of money" in text
    # How it ended, carried as itself: out of money and completed call for
    # different responses from the person reading the row.
    assert "halted_by_budget" in text
    assert "Working on it" not in text
    assert "Waiting at the gate" not in text


def test_the_split_follows_the_server_flag_not_the_status_name(ui):
    """A status this client has never heard of still lands on the right page.

    The split reads `is_terminal` because a list of status names here is what
    goes stale when the enum grows.
    """
    novel = a_run(run_id="r-novel", intent="A state from the future", status="some_new_state", is_terminal=True)
    ui.serve("**/api/runs", a_listing(WORKING, novel))

    ui.open("#history")
    ui.page.wait_for_selector("h3:has-text('Finished')")
    assert "A state from the future" in ui.text()

    ui.open("#queue")
    ui.page.wait_for_selector("h3:has-text('In flight')")
    assert "A state from the future" not in ui.text()


def test_an_empty_queue_says_so_and_offers_add_new(ui):
    ui.serve("**/api/runs", a_listing(DONE))
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing is in flight" in ui.text()
    ui.page.click("#view button:has-text('Go to Ask')")
    ui.page.wait_for_selector("#view h2:text-is('Ask')")


def test_an_empty_history_says_so(ui):
    ui.serve("**/api/runs", a_listing(WORKING))
    ui.open("#history")
    ui.page.wait_for_selector("#view .empty")

    assert "No search has finished yet" in ui.text()


def test_add_new_no_longer_lists_the_searches(ui):
    """They moved to Activity; a second copy on Ask would be two lists of one thing."""
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#discover")
    ui.page.wait_for_selector("#view h2:text-is('Ask')")

    assert "Working on it" not in ui.text()
    assert "All done" not in ui.text()


def test_a_search_opened_from_history_returns_to_history(ui):
    """History is not a run's default return, so the opener travels in the address."""
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#history")
    ui.page.wait_for_selector("h3:has-text('Finished')")

    ui.page.click("#view button[aria-label='Open the search for All done']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/')")

    assert ui.page.evaluate("() => window.location.hash") == "#run/r-done?from=history"


def test_a_search_opened_from_the_queue_carries_no_opener(ui):
    """The Queue is a run's default return, so the address leaves it out."""
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#queue")
    ui.page.wait_for_selector("h3:has-text('In flight')")

    ui.page.click("#view button[aria-label='Open the search for Working on it']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/')")

    assert ui.page.evaluate("() => window.location.hash") == "#run/r-working"


def test_an_empty_queue_over_a_truncated_listing_does_not_claim_nothing_is_in_flight(ui):
    """The cap can leave out an older search still at the approval gate.

    So the empty Queue says what it checked. The paired case above, over a
    complete listing, keeps the plain sentence.
    """
    ui.serve(
        "**/api/runs",
        RunListOut(runs=[DONE], count=1, total=60, truncated=True).model_dump(mode="json"),
    )
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing is in flight among the 1 most recent searches." in ui.text()


def test_a_complete_empty_queue_says_nothing_is_in_flight_plainly(ui):
    ui.serve("**/api/runs", a_listing(DONE))
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing is in flight. " in ui.text()
    assert "most recent" not in ui.text()


@pytest.mark.parametrize("where", ["queue", "history"])
def test_a_listing_that_fails_is_announced_not_shown_as_empty(ui, where):
    """A refused request is not an empty history, and must not read as one."""
    ui.serve("**/api/runs", [(503, {"error": "the catalogue is unavailable"})])
    ui.open(f"#{where}")
    ui.page.wait_for_selector("#error:not([hidden])")

    assert "unavailable" in ui.page.inner_text("#error")
    assert "Nothing is in flight" not in ui.page.inner_text("body")
    assert "No search has finished yet" not in ui.page.inner_text("body")
