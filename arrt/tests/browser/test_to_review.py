"""To review, and its count in the sidebar, in a real browser against a real server.

The page lists the runs holding works that wait for a verdict, each opening
Review. The count sits on its own link as a number beside the words *To review*,
and on Activity's link as *N to review*, so neither is a bare number. A verdict
takes a work off the count at once. The listing is answered by the test, which is
what lets a count change between two reads.
"""

import json
import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_verdict, an_instance_listing

from arrt.http.models import RunListOut

GET_ID = "get-1"
SEARCH_ID = "search-1"


def waiting(runs, counts) -> dict:
    return RunListOut(
        runs=runs,
        count=len(runs),
        total=len(runs),
        truncated=False,
        awaiting_works=sum(counts.values()),
        awaiting=counts,
    ).model_dump(mode="json")


TWO_RUNS = waiting(
    [a_run(run_id=GET_ID, kind="get", intent=None), a_run(run_id=SEARCH_ID, intent="Quiet interiors")],
    {GET_ID: 2, SEARCH_ID: 1},
)
NOTHING = waiting([], {})


def test_it_lists_the_runs_waiting_with_how_many_each_holds(ui):
    ui.serve("**/api/runs?awaiting=true", TWO_RUNS)
    ui.open("#to_review")
    ui.page.wait_for_selector("#view h1:text-is('To review')")

    # Each row's cells are read as one line, as the whitespace-joined read did:
    # a pattern is matched against the raw innerText, so a space is `\s+`.
    rows = ui.page.locator("#view tbody tr")
    expect(ui.page.locator("#view h2").first).to_have_text("3 works to review", use_inner_text=True)
    expect(rows.nth(0)).to_have_text(re.compile(r"^Works\s+you\s+chose\s+Get\s+of\s+chosen\s+works\s+2\s"), use_inner_text=True)
    expect(rows.nth(1)).to_have_text(re.compile(r"^Quiet\s+interiors\s+Get\s+from\s+Ask\s+1\s"), use_inner_text=True)


def test_a_get_opens_on_its_own_page_where_it_is_reviewed(ui):
    """A Get's page is its review (the owner's ruling, 2026-10-02).

    This test opened `#review/<get>` until then. The claim it guards — the
    row's Review leads to where that run's works are judged — is unchanged;
    where that is moved, for a Get.
    """
    ui.serve("**/api/runs?awaiting=true", TWO_RUNS)
    ui.open("#to_review")

    ui.page.locator("#view tbody tr").first.locator("a:text-is('Review')").click()

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#get/{GET_ID}')")


def test_a_search_still_opens_review(ui):
    """The paired negative: only a Get moved. A discovery run's works are judged on Review."""
    ui.serve("**/api/runs?awaiting=true", TWO_RUNS)
    ui.open("#to_review")

    ui.page.locator("#view tbody tr").nth(1).locator("a:text-is('Review')").click()

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#review/{SEARCH_ID}')")


def test_with_nothing_waiting_it_says_so(ui):
    ui.serve("**/api/runs?awaiting=true", NOTHING)
    ui.open("#to_review")

    ui.page.wait_for_selector("#view p:has-text('Nothing waits for you.')")
    expect(ui.page.locator("#view table")).to_have_count(0)


def test_the_sidebar_says_how_many_wait_in_words_and_a_number(ui):
    ui.serve("**/api/runs?awaiting=true", TWO_RUNS)
    ui.open("#to_review")
    page_link = ui.page.locator("nav ul.pages a[data-view='to_review']")
    section_link = ui.page.locator("li.section[data-section='activity'] a.section-link")
    page_link.locator(".awaiting-count").wait_for()

    expect(page_link).to_have_text("To review 3", use_inner_text=True)
    expect(section_link.locator(".awaiting-count")).to_have_text("3 to review", use_inner_text=True)
    expect(page_link).to_have_attribute("aria-label", "To review: 3 works to review")
    expect(section_link).to_have_attribute("aria-label", "Activity: 3 works to review")


def test_with_nothing_waiting_the_sidebar_shows_no_count(ui):
    ui.serve("**/api/runs?awaiting=true", NOTHING)
    ui.open("#walls")
    ui.page.wait_for_selector("#view *")
    # The count is written when the listing answers, and an answer of nothing
    # writes nothing a wait could name: so the page is let go quiet first, the
    # listing's request and the write after it both in.
    ui.page.wait_for_load_state("networkidle")

    expect(ui.page.locator(".awaiting-count")).to_have_count(0)
    expect(ui.page.locator("nav ul.pages a[data-view='to_review']")).not_to_have_attribute("aria-label")


def test_activity_opens_to_review(ui):
    ui.serve("**/api/runs?awaiting=true", NOTHING)
    ui.open("#walls")

    ui.page.click("li.section[data-section='activity'] a.section-link")

    ui.page.wait_for_selector("#view h1:text-is('To review')")


def test_a_verdict_takes_the_work_off_the_count(ui):
    one = waiting([a_run(run_id=GET_ID, kind="get", intent=None)], {GET_ID: 1})
    judged = {"done": False}

    def listing(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(NOTHING if judged["done"] else one))

    def verdict(route):
        judged["done"] = True
        body = a_verdict(work=a_candidate(work_id="work-1", verdict="accepted"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    ui.page.route("**/api/runs?awaiting=true", listing)
    ui.page.route("**/api/candidates/work-1/verdict", verdict)
    card = a_card(work=a_candidate(work_id="work-1"))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/candidates/work-1", a_card(work=a_candidate(work_id="work-1", verdict="accepted")).model_dump(mode="json"))
    ui.open(f"#review/{GET_ID}")
    count = ui.page.locator("nav .awaiting-count")
    count.first.wait_for()

    ui.page.click("li.card button:text-is('Accept')")

    count.first.wait_for(state="detached")


def test_turning_a_scan_down_reads_the_count_again(ui):
    """Turning down the only scan leaves nothing to accept, so the work leaves To review."""
    one = waiting([a_run(run_id=GET_ID, kind="get", intent=None)], {GET_ID: 1})
    turned = {"down": False}

    def listing(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(NOTHING if turned["down"] else one))

    def reject(route):
        turned["down"] = True
        route.fulfill(status=200, content_type="application/json", body=json.dumps({}))

    ui.page.route("**/api/runs?awaiting=true", listing)
    ui.page.route("**/api/candidate-images/*/reject", reject)
    card = a_card(work=a_candidate(work_id="work-1"))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.serve("**/api/candidates/work-1/images", an_instance_listing())
    ui.serve("**/api/candidates/work-1", card.model_dump(mode="json"))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.open(f"#review/{GET_ID}")
    count = ui.page.locator("nav .awaiting-count")
    count.first.wait_for()
    ui.page.click("li.card summary")

    ui.page.click("li.card button:has-text('Turn it down')")

    count.first.wait_for(state="detached")
