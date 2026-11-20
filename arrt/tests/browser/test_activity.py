"""Activity › Queue, in a real browser.

`information-architecture.md` § The *arr layout: Queue is the searches that have
not ended, split on the server's `is_terminal` flag. Every listing below holds
runs of both kinds, so a page that showed everything, or split on the wrong
field, fails rather than passing on a fixture that could not tell.

History reads the event log rather than the finished runs, and has its own file,
`test_the_history.py`.
"""

import pytest
from payloads import a_run

from arrt.http.models import RunListOut

expect = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
).expect


def a_listing(*runs) -> dict:
    return RunListOut(
        runs=list(runs), count=len(runs), total=len(runs), truncated=False, awaiting_works=0, awaiting={}
    ).model_dump(mode="json")


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
    ui.page.wait_for_selector("h2:has-text('In flight')")

    expect(ui.view).to_contain_text("Working on it", use_inner_text=True)
    expect(ui.view, "a run at the approval gate is waiting on the curator, so it is in flight").to_contain_text(
        "Waiting at the gate", use_inner_text=True
    )
    expect(ui.view).not_to_contain_text("All done", use_inner_text=True)
    expect(ui.view).not_to_contain_text("Ran out of money", use_inner_text=True)
    expect(ui.view).to_contain_text("In flight (2)", use_inner_text=True)


def test_the_split_follows_the_server_flag_not_the_status_name(ui):
    """A status this client has never heard of still lands on the right page.

    The split reads `is_terminal` because a list of status names here is what
    goes stale when the enum grows.
    """
    novel = a_run(run_id="r-novel", intent="A state from the future", status="some_new_state", is_terminal=True)
    ui.serve("**/api/runs", a_listing(WORKING, novel))

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('In flight')")
    expect(ui.view).to_contain_text("Working on it", use_inner_text=True)
    expect(ui.view).not_to_contain_text("A state from the future", use_inner_text=True)


def test_an_empty_queue_says_so_and_offers_add_new(ui):
    ui.serve("**/api/runs", a_listing(DONE))
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    expect(ui.view).to_contain_text("No Get is in flight", use_inner_text=True)
    ui.page.click("#view a:has-text('Go to Ask')")
    ui.page.wait_for_selector("#view h1:text-is('Ask')")


def test_add_new_no_longer_lists_the_searches(ui):
    """They moved to Activity; a second copy on Ask would be two lists of one thing."""
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#discover")
    ui.page.wait_for_selector("#view h1:text-is('Ask')")

    # The runs are asked for once the page is up: settled is where their absence means something.
    ui.page.wait_for_load_state("networkidle")
    expect(ui.view).not_to_contain_text("Working on it", use_inner_text=True)
    expect(ui.view).not_to_contain_text("All done", use_inner_text=True)


def test_a_search_opened_from_the_queue_carries_no_opener(ui):
    """The Queue is a run's default return, so the address leaves it out."""
    ui.serve("**/api/runs", EVERY_KIND)
    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('In flight')")

    ui.page.click("#view a[aria-label='Open the Get from Ask: Working on it']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/')")

    assert ui.page.evaluate("() => window.location.hash") == "#get/r-working"


def test_an_empty_queue_over_a_truncated_listing_does_not_claim_nothing_is_in_flight(ui):
    """The cap can leave out an older search still at the approval gate.

    So the empty Queue says what it checked. The paired case above, over a
    complete listing, keeps the plain sentence.
    """
    ui.serve(
        "**/api/runs",
        RunListOut(runs=[DONE], count=1, total=60, truncated=True, awaiting_works=0, awaiting={}).model_dump(mode="json"),
    )
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    expect(ui.view).to_contain_text("No Get is in flight among the 1 most recent Gets.", use_inner_text=True)


def test_a_complete_empty_queue_says_nothing_is_in_flight_plainly(ui):
    ui.serve("**/api/runs", a_listing(DONE))
    ui.open("#queue")
    ui.page.wait_for_selector("#view .empty")

    expect(ui.page.locator("#view .empty-lead")).to_have_text("No Get is in flight.", use_inner_text=True)
    expect(ui.view).not_to_contain_text("most recent", use_inner_text=True)


@pytest.mark.parametrize("where", ["queue", "history"])
def test_a_listing_that_fails_is_announced_not_shown_as_empty(ui, where):
    """A refused request is not an empty history, and must not read as one."""
    ui.serve("**/api/runs", [(503, {"error": "the catalogue is unavailable"})])
    ui.serve("**/api/history*", [(503, {"error": "the catalogue is unavailable"})])
    ui.open(f"#{where}")
    ui.page.wait_for_selector("#error:not([hidden])")

    expect(ui.page.locator("#error")).to_contain_text("unavailable", use_inner_text=True)
    expect(ui.page.locator("body")).not_to_contain_text("No Get is in flight", use_inner_text=True)
    expect(ui.page.locator("body")).not_to_contain_text("Nothing has happened yet", use_inner_text=True)
    # Keyed on the empty state's element as well as its words, so a rewording
    # cannot leave this asserting the absence of a sentence nothing can produce.
    expect(ui.page.locator("#view .empty")).to_have_count(0)


# -- Queue at scale (audit-6 finding 11) ---------------------------------------


def _owing(failing: int, causes: list[dict]) -> dict:
    """The two listings Queue reads, as the server answers them for `causes`."""
    return {
        "listing": {
            "pause": None,
            "works": [],
            "total": 0,
            "limit": 25,
            "offset": 0,
            "failing": failing,
            "causes": len(causes),
        },
        "causes": {"causes": causes, "total": len(causes), "limit": 25, "offset": 0},
    }


def _cause(text: str, works: int) -> dict:
    return {"cause": text, "works": works, "failed": 0, "gave_up": works}


def _serve_failures(ui, causes: list[dict]) -> None:
    answers = _owing(sum(each["works"] for each in causes), causes)
    ui.serve("**/api/runs", a_listing(DONE))
    ui.serve("**/api/acquisitions", answers["listing"])
    ui.serve("**/api/acquisitions/causes", answers["causes"])
    ui.serve("**/api/acquisitions/causes/retry", {"cause": causes[0]["cause"], "retried": causes[0]["works"], "refused": []})


def test_a_retry_over_a_handful_of_works_asks_first_naming_the_count(ui):
    """`Retry 2,000` is two thousand museum requests: it names them and sends nothing until agreed."""
    _serve_failures(ui, [_cause("the museum answered 404.", 2000)])
    ui.open("#queue")
    retry = ui.page.locator(".failure-cause button:text-is('Retry 2,000')")
    expect(retry).to_be_visible()

    retry.click()

    dialog = ui.page.locator("dialog.confirm[open]")
    expect(dialog.locator("h2")).to_have_text("Retry 2,000 works?")
    assert ui.requests_matching("/causes/retry") == [], "the retry was sent before it was agreed to"
    dialog.locator("button:text-is('Cancel')").click()
    expect(dialog).to_have_count(0)
    assert ui.requests_matching("/causes/retry") == [], "declining sent the retry"

    retry.click()
    ui.page.locator("dialog.confirm[open] button:text-is('Retry 2,000')").click()
    expect(ui.page.locator(".retry-all-said")).to_have_text("2,000 works put back in line.")
    assert len(ui.requests_matching("/causes/retry")) == 1


@pytest.mark.parametrize("works", [1, 5])
def test_a_retry_over_a_handful_or_fewer_is_sent_without_asking(ui, works):
    _serve_failures(ui, [_cause("the museum answered 404.", works)])
    ui.open("#queue")

    ui.page.locator(".failure-cause button").click()

    expect(ui.page.locator(".retry-all-said")).to_be_visible()
    assert len(ui.requests_matching("/causes/retry")) == 1
    expect(ui.page.locator("dialog.confirm")).to_have_count(0)


def test_the_page_holds_one_filled_act_and_it_is_the_one_cause_s_retry(ui):
    _serve_failures(ui, [_cause("the museum answered 404.", 2000)])
    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    filled = ui.page.locator("#view .action:not(.quiet)")
    expect(filled).to_have_count(1)
    expect(filled).to_have_text("Retry 2,000")
    # The way on is quiet beside it: two filled acts and neither is.
    expect(ui.page.locator("#view a.action:has-text('Go to Ask')")).to_have_class("action quiet")


def test_with_several_causes_no_retry_is_filled_over_the_others(ui):
    _serve_failures(ui, [_cause("the museum answered 404.", 12), _cause("the museum answered 503.", 9)])
    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    expect(ui.page.locator("#view .action:not(.quiet)")).to_have_count(0)
    expect(ui.page.locator(".failure-cause button.action.quiet")).to_have_count(2)


def test_the_failures_have_no_heading_that_says_the_count_a_third_time(ui):
    _serve_failures(ui, [_cause("the museum answered 404.", 2000)])
    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    expect(ui.page.get_by_role("heading", name="Fetching images (2,000)")).to_have_count(1)
    expect(ui.page.locator(".acquisition-summary")).to_have_text("2,000 works failed")
    expect(ui.page.locator("#view h3")).to_have_count(0)
