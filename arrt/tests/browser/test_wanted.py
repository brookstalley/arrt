"""Wanting a work, and the Wanted section, in a real browser.

The owner's ruling on #168 (2026-10-02): a work its search found no scan for
offers **Want** and **Forget** in place of Accept and Reject; wanted works, with
or without a scan, wait in **Wanted**, each with *Get again* and *Forget*, and
*Get all again*; Get again on a work with no Wikidata item first offers
Wikidata's matches to pick from.
Wanted is always in the sidebar, counted when something is wanted (ruling 5 of
2026-10-07), and Forget is held for Undo as a review card's verdict is.

Cards are stubbed, as the review grid's tests stub them; the Wanted page runs
against the real server over works this file wants through the service, so the
listing, the counts and Forget are the real ones.
"""

import json
import re

import pytest
from payloads import a_candidate, a_candidate_page, a_card, an_instance, an_instance_listing

from arrt.http.models import FitOut, WantedListingOut, WantedWorkOut
from arrt.library.services.quality import Fit
from arrt.persistence.discovery_records import InitiatedBy

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

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
    ui.open_folds()
    ui.page.wait_for_selector("li.card button:text-is('Want')")

    expect(ui.page.locator("li.card .row button")).to_have_text(["Want", "Forget"], use_inner_text=True)


def test_a_work_whose_search_is_still_running_is_not_offered_want_yet(ui):
    card = a_card(a_candidate(resolution_status="pending"), shown=None)
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([card]))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    expect(ui.page.locator("li.card button:text-is('Want')")).to_have_count(0)


def test_a_work_standing_on_a_scan_is_offered_accept_and_reject_not_want(ui):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    expect(ui.page.locator("li.card button:text-is('Want')")).to_have_count(0)
    expect(ui.page.locator("li.card button:text-is('Forget')")).to_have_count(0)


def test_want_records_the_verdict_and_the_card_says_where_the_work_went(ui):
    wanted = nothing_found(verdict="wanted")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([nothing_found()]))
    ui.serve("**/api/candidates/work-1/want", wanted.work.model_dump(mode="json"))
    ui.serve("**/api/candidates/work-1", wanted.model_dump(mode="json"))
    requests = posted(ui, "/candidates/work-1/want")

    ui.open(f"#review/{RUN_ID}")
    ui.open_folds()
    ui.page.click("li.card button:text-is('Want')")
    ui.page.wait_for_selector("li.card:has-text('It waits in Wanted')")

    assert [method for method, _, _ in requests] == ["POST"]
    # Already wanted, so Want is not offered again; Forget still is.
    expect(ui.page.locator("li.card .row button")).to_have_text(["Forget"], use_inner_text=True)


def test_forget_is_a_rejection(ui):
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([nothing_found()]))
    ui.serve("**/api/candidates/work-1/verdict", {"work": nothing_found(verdict="rejected").work.model_dump(mode="json")})
    ui.serve("**/api/candidates/work-1", nothing_found(verdict="rejected").model_dump(mode="json"))
    requests = posted(ui, "/verdict")

    ui.open(f"#review/{RUN_ID}")
    ui.open_folds()
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
    ui.page.wait_for_selector("li.card:has-text('it waits in Wanted for a better scan')")


# -- Wanted, over the real listing -------------------------------------


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
    ui.page.wait_for_selector("h1:has-text('Wanted')")


def a_wanted_listing(*works: WantedWorkOut) -> dict:
    return WantedListingOut(works=list(works)).model_dump(mode="json")


def a_wanted(title="Blue Green Red", artist="Ellsworth Kelly", work_id="work-1", **fields) -> WantedWorkOut:
    defaults = {"run_id": RUN_ID, "wikidata_qid": "Q20189992", "scans_turned_down": 0, "shown": None}
    return WantedWorkOut(work_id=work_id, title=title, artist=artist, **(defaults | fields))


#: A museum's web-size picture of a work in copyright: far below the minimum.
TOO_SMALL = an_instance(
    is_selected=False,
    width=567,
    height=625,
    fit=FitOut(verdict=Fit.BELOW_MINIMUM.value),
)


def test_a_wanted_work_is_pictured_by_its_too_small_scan_and_says_so(ui):
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=TOO_SMALL)))

    open_wanted(ui)
    picture = ui.page.locator(".wanted tbody tr .wanted-picture img")

    expect(picture).to_have_attribute("alt", "Blue Green Red, by Ellsworth Kelly")
    expect(picture).to_have_attribute("src", re.compile(re.escape("/api/candidate-images/image-1/preview")))
    row = ui.page.locator(".wanted tbody tr")
    expect(row).to_contain_text("below minimum", use_inner_text=True)
    expect(row).to_contain_text("Found only too small", use_inner_text=True)
    expect(row, "a picture never sits beside a claim that nothing was found").not_to_contain_text(
        "No scan found", use_inner_text=True
    )


def test_pressing_a_wanted_work_s_picture_enlarges_it(ui):
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=TOO_SMALL)))

    open_wanted(ui)
    ui.page.click("button[aria-label='Enlarge the picture of Blue Green Red']")

    expect(ui.page.locator("dialog[open] img")).to_have_attribute("src", re.compile(re.escape("size=large")))


def test_a_wanted_work_with_no_scan_standing_says_why_in_words_in_place_of_a_picture(ui):
    ui.serve(
        "**/api/wanted",
        a_wanted_listing(
            a_wanted(work_id="work-1", title="Nothing Found"),
            a_wanted(work_id="work-2", title="All Turned Down", scans_turned_down=2),
        ),
    )

    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    expect(ui.page.locator(".wanted .wanted-picture img")).to_have_count(0)
    rows = ui.page.locator(".wanted tbody tr")
    nothing = rows.filter(has_text="Nothing Found")
    turned = rows.filter(has_text="All Turned Down")
    expect(nothing).to_contain_text("No scan found.", use_inner_text=True)
    expect(turned).to_contain_text("Every scan found was turned down.", use_inner_text=True)
    expect(turned).to_contain_text("2 scans turned down", use_inner_text=True)
    expect(turned).not_to_contain_text("too small", use_inner_text=True)


def test_a_wanted_work_holding_a_scan_on_offer_does_not_say_none_was_found(ui):
    """Wanted naming no scan, from a card standing on one: the scan is still there."""
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=an_instance())))

    open_wanted(ui)
    ui.page.wait_for_selector(".wanted tbody tr .wanted-picture img")

    row = ui.page.locator(".wanted tbody tr")
    expect(row).to_contain_text("One still on offer", use_inner_text=True)
    expect(row).not_to_contain_text("No scan found", use_inner_text=True)


def test_a_wanted_work_s_unselected_scan_of_unknown_size_is_not_called_on_offer(ui):
    """On offer means selected, as on the card; a scan nobody chose is only found."""
    ui.serve_image("**/api/candidate-images/*/preview*")
    unsized = an_instance(is_selected=False, width=None, height=None, fit=None, fit_note="Its size was never recorded.")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=unsized)))

    open_wanted(ui)
    ui.page.wait_for_selector(".wanted tbody tr .wanted-picture img")

    row = ui.page.locator(".wanted tbody tr")
    expect(row).to_contain_text("One found, not on offer", use_inner_text=True)
    expect(row).not_to_contain_text("still on offer", use_inner_text=True)


def test_wanted_lists_both_kinds_saying_which(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    rows = ui.page.locator(".wanted tbody tr")
    lobster = rows.filter(has_text="Lobster Telephone")
    memory = rows.filter(has_text="The Persistence of Memory")
    expect(lobster).to_contain_text("No scan found", use_inner_text=True)
    expect(lobster).to_contain_text("No item", use_inner_text=True)
    expect(memory).to_contain_text("1 scan turned down", use_inner_text=True)
    expect(memory).to_contain_text("Q25729", use_inner_text=True)
    expect(ui.view).to_contain_text("spends nothing", use_inner_text=True)


def test_the_wanted_section_shows_its_count_once_something_is_wanted(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_function("() => document.querySelector(\"[data-count-slot='wanted']\").textContent === '2'")

    expect(ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])")).to_be_visible()


def test_with_nothing_wanted_the_section_is_shown_uncounted_and_the_page_says_what_wanted_is(ui):
    open_wanted(ui)
    ui.page.wait_for_selector("#view .empty")

    empty = ui.page.locator("#view .empty")
    expect(empty).to_contain_text("Nothing is wanted.", use_inner_text=True)
    # What Wanted holds, not the clicks that fill it (no click path through a
    # review card).
    expect(empty).to_contain_text("Wanted holds the works you want and have no acceptable scan of", use_inner_text=True)
    expect(empty).to_contain_text("a Get found no scan for", use_inner_text=True)
    expect(empty).not_to_contain_text("press Want", use_inner_text=True)
    expect(empty).not_to_contain_text("Scans, then", use_inner_text=True)
    section = ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])")
    expect(section).to_be_visible()
    expect(ui.page.locator("[data-count-slot='wanted']"), "a zero says nothing a curator acts on").to_have_text(
        "", use_inner_text=True
    )


def test_the_wanted_section_is_shown_before_its_count_arrives(ui, wanted):
    """Shown from the first paint, whatever the count will say: the section is always there."""
    held = []

    def hold(route) -> None:
        held.append(route)

    ui.page.route("**/api/wanted", hold)
    ui.open("#collection")
    ui.page.wait_for_selector("nav.sidebar a.section-link")
    ui.page.wait_for_function("() => document.querySelector('nav.sidebar [data-count-slot=wanted]') !== null")

    expect(ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])")).to_be_visible()
    for route in held:
        route.continue_()
    ui.page.wait_for_function("() => document.querySelector(\"[data-count-slot='wanted']\").textContent === '2'")


@pytest.mark.parametrize("wanting", [True, False], ids=["something wanted", "nothing wanted"])
def test_on_wanted_its_section_is_lit_as_where_the_curator_is(ui, request, wanting):
    """Reached by address, Wanted is highlighted, with or without anything in it."""
    if wanting:
        request.getfixturevalue("wanted")
    open_wanted(ui)
    ui.page.wait_for_selector("#view h1:text-is('Wanted')")

    expect(ui.page.locator("nav.sidebar a[data-view='wanted'][aria-current='page']")).to_be_visible()


def test_a_count_that_cannot_be_read_shows_the_section_rather_than_hiding_it(ui, wanted):
    """Hiding on a failed read would say "nothing is wanted", which the client does not know."""
    ui.page.route("**/api/wanted", lambda route: route.fulfill(status=503, body="unwell"))
    ui.open("#collection")
    ui.page.wait_for_selector("nav.sidebar a.section-link")

    ui.page.wait_for_function("() => !document.querySelector(\"#sidebar li.section:has([data-count-slot='wanted'])\").hidden")
    expect(ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])")).to_be_visible()


def test_forget_takes_a_work_off_the_list(ui, wanted, discovery):
    nothing, _ = wanted
    open_wanted(ui)

    ui.page.click("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")
    ui.page.wait_for_function("() => !document.querySelector('.wanted')?.innerText.includes('Lobster Telephone')", timeout=15000)

    assert str(discovery.get_candidate_work(nothing.id).verdict) == "rejected"


def test_forget_waits_with_undo_and_undo_sends_nothing(ui, wanted, discovery):
    nothing, _ = wanted
    sent = posted(ui, "/verdict")
    open_wanted(ui)

    ui.page.click("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")
    undo = ui.page.locator('button[aria-label="Undo: don\'t forget Lobster Telephone (1938)"]')
    expect(undo).to_be_visible()
    ui.page.wait_for_timeout(1000)  # sleep: proves nothing is sent while Undo is on offer
    assert sent == [], "nothing is sent while Undo can still take it back"
    undo.click()
    ui.page.wait_for_timeout(6000)  # sleep: proves nothing is sent once the hold's five seconds have run

    assert sent == []
    assert str(discovery.get_candidate_work(nothing.id).verdict) == "wanted"
    expect(ui.page.locator("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")).to_be_visible()


def test_a_row_drawn_again_while_its_forget_is_held_shows_the_hold(ui, wanted, discovery):
    """Another row's Forget repaints the page; the held row keeps its Undo, and Undo still works."""
    _, turned = wanted
    open_wanted(ui)

    ui.page.click("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")
    # Staggered by the hold's own countdown, not a sleep: at "4 s" or "3 s" at
    # least one of Lobster's five seconds has gone and two are left, so its hold
    # runs out while the second is held. Two readings, not one, because
    # `expect` asks about once a second by then and one reading lasts a second.
    lobster = ui.page.locator(".wanted tbody tr", has_text="Lobster Telephone")
    expect(lobster.locator(".verdict-countdown")).to_have_text(re.compile(r"^[34] s$"), use_inner_text=True)
    ui.page.click("button[aria-label='Forget The Persistence of Memory: stop proposing it']")
    # Lobster's hold runs out and lands, and the page repaints with the other row still held.
    ui.page.wait_for_function("() => !document.querySelector('.wanted')?.innerText.includes('Lobster Telephone')", timeout=15000)
    undo = ui.page.locator('button[aria-label="Undo: don\'t forget The Persistence of Memory"]')
    expect(undo).to_be_visible()
    undo.click()
    ui.page.wait_for_timeout(6000)  # sleep: proves an undone Forget is not sent when its hold would have run out

    assert str(discovery.get_candidate_work(turned.id).verdict) == "wanted"


def test_get_again_carries_its_tier(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    row = ui.page.locator(".wanted tbody tr", has_text="Lobster Telephone")
    expect(row.locator(".badge-tier")).to_have_text(re.compile(r"Free\s*$"), use_inner_text=True)


def test_search_again_on_a_work_with_an_item_re_searches_it_and_opens_the_run(ui, wanted):
    _, turned = wanted
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-1"})
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    ui.page.click("button[aria-label='Get The Persistence of Memory again']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/resolve-1')")

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
    ui.page.click("button[aria-label='Get Lobster Telephone (1938) again']")
    ui.page.wait_for_selector(".picker li")
    picker = ui.page.locator(".picker")
    expect(picker).to_contain_text("Which is Lobster Telephone (1938)?", use_inner_text=True)
    expect(picker).to_contain_text("has a picture", use_inner_text=True)
    expect(picker).to_contain_text("no picture on Wikidata", use_inner_text=True)

    ui.page.click("button[aria-label='Pick Q2990594, Lobster Telephone by Salvador Dalí']")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/resolve-2')")

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
    expect(ui.view).to_contain_text("One Get for each of the 2 Gets", use_inner_text=True)
    ui.page.click("button:text-is('Get all again')")
    ui.page.wait_for_function("() => window.location.hash === '#queue'")

    covered = sorted(sorted(json.loads(body)["work_ids"]) for _, _, body in requests)
    assert covered == sorted([sorted([wanted[0].id, wanted[1].id]), [elsewhere.id]])


def test_with_wikidata_off_the_picker_says_why_and_still_searches_without_an_item(ui, wanted):
    """The only way to search again for a work with no item, on a deployment with no WIKIDATA_USER_AGENT."""
    nothing, _ = wanted
    note = "Wikidata is not set up on this server, so a work cannot be matched to one of its items."
    ui.serve(
        f"**/api/candidates/{nothing.id}/wikidata-matches",
        {"work_id": nothing.id, "title": nothing.proposed_title, "state": "not_configured", "note": note, "matches": []},
    )
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-3"})
    calls = posted(ui, "/api/")

    open_wanted(ui)
    ui.page.click("button[aria-label='Get Lobster Telephone (1938) again']")
    ui.page.wait_for_selector(".picker")
    expect(ui.page.locator(".picker")).to_contain_text(note, use_inner_text=True)
    expect(ui.page.locator(".picker button:text-is('This one')")).to_have_count(0)
    assert ui.page.evaluate("() => document.activeElement.classList.contains('picker-heading')"), "the picker took no focus"

    ui.page.click(".picker button:text-is('Get without an item')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/resolve-3')")

    writes = [(method, url.split("/api/")[1]) for method, url, _ in calls if method in ("PUT", "POST")]
    assert writes == [("POST", "runs/resolve")], "searching without an item picks nothing first"


def test_search_all_over_one_search_opens_that_re_search(ui, wanted):
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-one"})
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    # The works are listed once the button over them is, so the page has said
    # what it will say when "One Get for each" is found not to be there.
    expect(ui.page.locator("button:text-is('Get all again')")).to_be_visible()
    expect(ui.view).not_to_contain_text("One Get for each", use_inner_text=True)
    ui.page.click("button:text-is('Get all again')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/resolve-one')")

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
    ui.page.click("button:text-is('Get all again')")
    ui.page.wait_for_selector(".search-all-outcome")

    assert [method for method, _, _ in requests if method == "POST"] == ["POST", "POST"], "a refusal stopped the rest"
    outcome = ui.page.locator(".search-all-outcome")
    expect(outcome).to_contain_text("Started 1 Get. 1 other could not start:", use_inner_text=True)
    expect(outcome).to_contain_text(refusal, use_inner_text=True)
    assert ui.page.evaluate("() => window.location.hash") == "#wanted", "the page left before saying what was refused"


def test_search_all_says_which_work_is_gone_and_still_starts_the_rest(ui, wanted, discovery, propose):
    """A work gone between the listing and the press is not found (404), not a fault.

    Its sentence is shown where a refusal's is, and the Get after it still starts.
    The answer served for the first Get is the server's own for a candidate work
    it does not hold, asked of the real server, so the stub cannot drift from
    what it says. Asked of the work's own route, because this suite's server has
    no image provider, so its resolve route refuses before it looks a work up;
    both refuse a missing work through `DiscoveryService.get_candidate_work`.
    """
    import httpx

    other_run = discovery.start_discovery_run(intent_text="Magritte", initiated_by=InitiatedBy.WEB_UI)
    elsewhere = propose("The Son of Man", run_id=other_run.id, proposed_artist="René Magritte")
    discovery.record_resolution(elsewhere.id)
    discovery.want(elsewhere.id)
    gone = httpx.get(f"{ui.base_url}/api/candidates/no-such-work", timeout=30.0)
    assert gone.status_code == 404, gone.text
    ui.serve("**/api/runs/resolve", [(gone.status_code, gone.json()), {"run_id": "resolve-b"}])
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    ui.page.click("button:text-is('Get all again')")
    ui.page.wait_for_selector(".search-all-outcome")

    assert [method for method, _, _ in requests if method == "POST"] == ["POST", "POST"], "a missing work stopped the rest"
    outcome = ui.page.locator(".search-all-outcome")
    expect(outcome).to_contain_text("Started 1 Get. 1 other could not start:", use_inner_text=True)
    expect(outcome).to_contain_text(gone.json()["error"], use_inner_text=True)
    expect(ui.page.locator("#error:not([hidden])")).to_have_count(0)
    assert ui.page.evaluate("() => window.location.hash") == "#wanted", "the page left before saying what was refused"


# -- on a phone -------------------------------------------------------------------

PHONE = {"width": 390, "height": 844}


def test_on_a_phone_each_wanted_work_is_a_card_rather_than_a_row_that_scrolls_sideways(ui, wanted):
    """Activity's tables stack on a phone; Wanted's scrolled sideways inside its box instead.

    The page itself never scrolled, because `.table-scroll` swallows the overflow,
    so the box is measured too: a row the curator has to drag sideways to reach
    Get again is the defect, whatever the document width says.
    """
    ui.page.set_viewport_size(PHONE)
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    row = ui.page.locator(".wanted tbody tr").first
    assert row.evaluate("(tr) => getComputedStyle(tr).display") == "block"
    headings = row.locator("td").evaluate_all("(tds) => tds.map((td) => getComputedStyle(td, '::before').content)")
    for heading in ("Work", "Why", "Wikidata", "From"):
        assert f'"{heading}"' in headings, f"a cell lost the heading that says what it is: {headings}"
    scroller = ui.page.locator(".wanted .table-scroll")
    assert scroller.evaluate("(s) => s.scrollWidth - s.clientWidth") <= 0, "Wanted's table still scrolls sideways"
    expect(row.locator("button:text-is('Get again')")).to_be_visible()
    again = row.locator("button:text-is('Get again')").bounding_box()  # one-shot: geometry, measured once the button is drawn
    assert again["x"] + again["width"] <= PHONE["width"], "Get again is past the screen's edge"


def test_at_desktop_width_wanted_is_still_a_table(ui, wanted):
    """The cards are a phone's; a wide screen scans across the row."""
    ui.page.set_viewport_size({"width": 1280, "height": 800})
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")
    assert ui.page.locator(".wanted tbody tr").first.evaluate("(tr) => getComputedStyle(tr).display") == "table-row"
