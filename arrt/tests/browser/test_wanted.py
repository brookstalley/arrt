"""Wanting a work, and Activity › Wanted, in a real browser.

The owner's ruling on #168 (2026-10-02): a work its search found no scan for
offers **Want** and **Forget** in place of Accept and Reject; wanted works, with
or without a scan, wait in **Activity › Wanted**, each with *Search again* and
*Forget*, and *Search all*; Search again on a work with no Wikidata item first
offers Wikidata's matches to pick from (`build-plan-after-review.md` Chunks 03-05).

Cards are stubbed, as the review grid's tests stub them; the Wanted page runs
against the real server over works this file wants through the service, so the
listing, the counts and Forget are the real ones.
"""

import json

import pytest
from payloads import a_candidate, a_candidate_page, a_card, an_instance, an_instance_listing

from arrt.persistence.discovery_records import InitiatedBy

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"


def nothing_found(**fields):
    """A card whose search finished and found no scan: the case Want exists for."""
    return a_card(a_candidate(resolution_status="unresolved", **fields), shown=None)


def posted(ui, pattern):
    """Record each request whose URL contains `pattern`, as (method, url, body), in the order sent."""
    seen = []

    def watch(request):
        if pattern in request.url:
            seen.append((request.method, request.url, request.post_data))

    ui.page.on("request", watch)
    return seen


# -- the review card ------------------------------------------------------------


def test_a_work_its_search_found_nothing_for_offers_want_and_forget_not_accept(ui):
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([nothing_found()]))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Want')")

    buttons = ui.page.locator("li.card .row button").all_inner_texts()
    assert buttons == ["Want", "Forget"]


def test_a_work_whose_search_is_still_running_is_not_offered_want_yet(ui):
    card = a_card(a_candidate(resolution_status="pending"), shown=None)
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([card]))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    assert ui.page.locator("li.card button:text-is('Want')").count() == 0


def test_a_work_standing_on_a_scan_is_offered_accept_and_reject_not_want(ui):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    assert ui.page.locator("li.card button:text-is('Want')").count() == 0
    assert ui.page.locator("li.card button:text-is('Forget')").count() == 0


def test_want_records_the_verdict_and_the_card_says_where_the_work_went(ui):
    wanted = nothing_found(verdict="wanted")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([nothing_found()]))
    ui.serve("**/api/candidates/work-1/want", wanted.work.model_dump(mode="json"))
    ui.serve("**/api/candidates/work-1", wanted.model_dump(mode="json"))
    requests = posted(ui, "/candidates/work-1/want")

    ui.open(f"#review/{RUN_ID}")
    ui.page.click("li.card button:text-is('Want')")
    ui.page.wait_for_selector("li.card:has-text('It waits in Activity › Wanted')")

    assert [method for method, _, _ in requests] == ["POST"]
    # Already wanted, so Want is not offered again; Forget still is.
    assert ui.page.locator("li.card .row button").all_inner_texts() == ["Forget"]


def test_forget_is_a_rejection(ui):
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([nothing_found()]))
    ui.serve("**/api/candidates/work-1/verdict", {"work": nothing_found(verdict="rejected").work.model_dump(mode="json")})
    ui.serve("**/api/candidates/work-1", nothing_found(verdict="rejected").model_dump(mode="json"))
    requests = posted(ui, "/verdict")

    ui.open(f"#review/{RUN_ID}")
    ui.page.click("li.card button:text-is('Forget')")
    ui.page.wait_for_function("() => document.querySelector('li.card .badge-rejected') !== null")

    assert json.loads(requests[0][2])["verdict"] == "rejected"


def test_turning_down_the_scan_on_offer_says_the_work_waits_in_wanted_and_an_alternate_s_does_not(ui):
    """Only the scan on offer makes the work wanted, so only its control and its outcome say so."""
    on_offer = an_instance(image_id="image-1", is_selected=True)
    alternate = an_instance(image_id="image-2", is_selected=False, url="https://museum.example/other")
    wanting = a_candidate(verdict="wanted")
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))
    ui.serve("**/api/candidates/work-1/images", an_instance_listing([on_offer, alternate]))
    ui.serve("**/api/candidate-images/image-1/reject", wanting.model_dump(mode="json"))
    ui.serve("**/api/candidates/work-1", a_card(work=wanting).model_dump(mode="json"))

    ui.open(f"#review/{RUN_ID}")
    ui.page.click("summary")
    ui.page.wait_for_selector("tr.alternate >> nth=1")
    names = ui.page.locator("tr.alternate button:text-is('Turn it down')").evaluate_all(
        "(buttons) => buttons.map((button) => button.getAttribute('aria-label'))"
    )
    assert "will wait in Wanted" in names[0]
    assert "Wanted" not in names[1], "turning down an alternate does not make the work wanted"

    ui.page.locator("tr.alternate button:text-is('Turn it down')").first.click()
    ui.page.wait_for_selector("li.card:has-text('it waits in Activity › Wanted for a better scan')")


# -- Activity › Wanted, over the real listing -------------------------------------


@pytest.fixture
def wanted(discovery, propose, resolved_work):
    """One work wanted with no scan and one whose scan on offer was turned down."""
    nothing = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")
    discovery.record_resolution(nothing.id)
    discovery.want(nothing.id)
    turned = resolved_work("The Persistence of Memory", proposed_artist="Salvador Dalí")
    discovery.set_wikidata_item(turned.id, "Q25729")
    [scan] = discovery.list_candidate_images(turned.id)
    discovery.reject_image(scan.id)
    return nothing, turned


def open_wanted(ui):
    ui.open("#wanted")
    ui.page.wait_for_selector("h2:has-text('Wanted')")


def test_wanted_lists_both_kinds_saying_which(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    rows = ui.page.locator(".wanted tbody tr").all_inner_texts()
    lobster = next(row for row in rows if "Lobster Telephone" in row)
    memory = next(row for row in rows if "The Persistence of Memory" in row)
    assert "No scan found" in lobster and "No item" in lobster
    assert "1 scan turned down" in memory and "Q25729" in memory
    assert "spends nothing" in ui.text()


def test_the_wanted_link_appears_with_its_count_once_something_is_wanted(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_function("() => document.querySelector(\"[data-count-slot='wanted']\").textContent === '2'")

    assert ui.page.locator("#sidebar ul.pages li:has([data-count-slot='wanted'])").is_visible()


def test_with_nothing_wanted_the_link_is_hidden_and_the_page_says_how_a_work_gets_here(ui):
    open_wanted(ui)
    ui.page.wait_for_selector(".panel.empty")

    assert "Nothing is wanted." in ui.text()
    ui.page.wait_for_function("() => document.querySelector(\"#sidebar ul.pages li:has([data-count-slot='wanted'])\").hidden")
    # Not only marked hidden: a stylesheet giving the item a display would show it anyway.
    assert ui.page.locator("#sidebar ul.pages li:has([data-count-slot='wanted'])").is_hidden()


def test_forget_takes_a_work_off_the_list(ui, wanted, discovery):
    nothing, _ = wanted
    open_wanted(ui)

    ui.page.click("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")
    ui.page.wait_for_function("() => !document.querySelector('.wanted')?.innerText.includes('Lobster Telephone')")

    assert str(discovery.get_candidate_work(nothing.id).verdict) == "rejected"


def test_search_again_on_a_work_with_an_item_re_searches_it_and_opens_the_run(ui, wanted):
    _, turned = wanted
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-1"})
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    ui.page.click("button[aria-label='Search again for The Persistence of Memory']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/resolve-1')")

    assert json.loads(requests[0][2]) == {"work_ids": [turned.id]}


def test_search_again_on_a_work_with_no_item_offers_wikidata_s_matches_and_picks_before_searching(ui, wanted):
    nothing, _ = wanted
    ui.serve(
        f"**/api/candidates/{nothing.id}/wikidata-matches",
        {
            "work_id": nothing.id,
            "title": "Lobster Telephone (1938)",
            "state": "known",
            "note": None,
            "matches": [
                {
                    "qid": "Q2990594",
                    "title": "Lobster Telephone",
                    "creator": "Salvador Dalí",
                    "sitelinks": 13,
                    "has_image": True,
                    "by_proposed_artist": True,
                },
                {
                    "qid": "Q63109663",
                    "title": "Lobster Telephone",
                    "creator": "Salvador Dalí",
                    "sitelinks": 0,
                    "has_image": False,
                    "by_proposed_artist": True,
                },
            ],
        },
    )
    ui.serve(f"**/api/candidates/{nothing.id}/wikidata-item", {"work_id": nothing.id})
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-2"})
    calls = posted(ui, "/api/")

    open_wanted(ui)
    ui.page.click("button[aria-label='Search again for Lobster Telephone (1938)']")
    ui.page.wait_for_selector(".picker li")
    picker = ui.page.inner_text(".picker")
    assert "Which is Lobster Telephone (1938)?" in picker
    assert "has a picture" in picker and "no picture on Wikidata" in picker

    ui.page.click("button[aria-label='Pick Q2990594, Lobster Telephone by Salvador Dalí']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/resolve-2')")

    writes = [(method, url.split("/api/")[1]) for method, url, _ in calls if method in ("PUT", "POST")]
    assert writes == [
        ("PUT", f"candidates/{nothing.id}/wikidata-item"),
        ("POST", "runs/resolve"),
    ], "the pick comes before the search"
    put_body = next(body for method, _, body in calls if method == "PUT")
    assert json.loads(put_body) == {"qid": "Q2990594"}


def test_search_all_starts_one_re_search_per_search_the_works_came_from_then_opens_queue(ui, wanted, discovery, propose):
    other_run = discovery.start_discovery_run(intent_text="Magritte", initiated_by=InitiatedBy.WEB_UI)
    elsewhere = propose("The Son of Man", run_id=other_run.id, proposed_artist="René Magritte")
    discovery.record_resolution(elsewhere.id)
    discovery.want(elsewhere.id)
    ui.serve("**/api/runs/resolve", [{"run_id": "resolve-a"}, {"run_id": "resolve-b"}])
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    assert "One re-search for each of the 2 searches" in ui.text()
    ui.page.click("button:text-is('Search all')")
    ui.page.wait_for_function("() => window.location.hash === '#queue'")

    covered = sorted(sorted(json.loads(body)["work_ids"]) for _, _, body in requests)
    assert covered == sorted([sorted([wanted[0].id, wanted[1].id]), [elsewhere.id]])


def test_with_wikidata_off_the_picker_says_why_and_still_searches_without_an_item(ui, wanted):
    """The only way to search again for a work with no item, on a deployment with no WIKIDATA_USER_AGENT."""
    nothing, _ = wanted
    note = "Matching a work to Wikidata needs WIKIDATA_USER_AGENT, which this deployment has not set."
    ui.serve(
        f"**/api/candidates/{nothing.id}/wikidata-matches",
        {"work_id": nothing.id, "title": nothing.proposed_title, "state": "not_configured", "note": note, "matches": []},
    )
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-3"})
    calls = posted(ui, "/api/")

    open_wanted(ui)
    ui.page.click("button[aria-label='Search again for Lobster Telephone (1938)']")
    ui.page.wait_for_selector(".picker")
    assert note in ui.page.inner_text(".picker")
    assert ui.page.locator(".picker button:text-is('This one')").count() == 0
    assert ui.page.evaluate("() => document.activeElement.classList.contains('picker-heading')"), "the picker took no focus"

    ui.page.click(".picker button:text-is('Search without an item')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/resolve-3')")

    writes = [(method, url.split("/api/")[1]) for method, url, _ in calls if method in ("PUT", "POST")]
    assert writes == [("POST", "runs/resolve")], "searching without an item picks nothing first"


def test_search_all_over_one_search_opens_that_re_search(ui, wanted):
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-one"})
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    assert "One re-search for each" not in ui.text()
    ui.page.click("button:text-is('Search all')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#run/resolve-one')")

    assert [method for method, _, _ in requests if method == "POST"] == ["POST"], "one search, one re-search"


def test_search_all_tries_every_search_and_says_which_could_not_start(ui, wanted, discovery, propose):
    """The ordinary case just after Search again on one row: that work's search is already running."""
    other_run = discovery.start_discovery_run(intent_text="Magritte", initiated_by=InitiatedBy.WEB_UI)
    elsewhere = propose("The Son of Man", run_id=other_run.id, proposed_artist="René Magritte")
    discovery.record_resolution(elsewhere.id)
    discovery.want(elsewhere.id)
    refusal = "A re-search is already running for 'Lobster Telephone (1938)'. Wait for it to finish, or cancel it."
    ui.serve("**/api/runs/resolve", [(400, {"error": refusal}), {"run_id": "resolve-b"}])
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    ui.page.click("button:text-is('Search all')")
    ui.page.wait_for_selector(".search-all-outcome")

    assert [method for method, _, _ in requests if method == "POST"] == ["POST", "POST"], "a refusal stopped the rest"
    outcome = ui.page.inner_text(".search-all-outcome")
    assert "Started 1 re-search. 1 other could not start:" in outcome
    assert refusal in outcome
    assert ui.page.evaluate("() => window.location.hash") == "#wanted", "the page left before saying what was refused"
