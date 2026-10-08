"""Wanting a work, and the Wanted section, in a real browser.

The owner's ruling on #168 (2026-10-02): a work its search found no scan for
offers **Want** and **Forget** in place of Accept and Reject; wanted works, with
or without a scan, wait in **Wanted**, each with *Get again* and *Forget*, and
*Get all again*; Get again on a work with no Wikidata item first offers
Wikidata's matches to pick from (`build-plan-after-review.md` Chunks 03-05).
Wanted is always in the sidebar, counted when something is wanted (ruling 5 of
2026-10-07), and Forget is held for Undo as a review card's verdict is.

Cards are stubbed, as the review grid's tests stub them; the Wanted page runs
against the real server over works this file wants through the service, so the
listing, the counts and Forget are the real ones.
"""

import json

import pytest
from payloads import a_candidate, a_candidate_page, a_card, an_instance, an_instance_listing

from arrt.http.models import FitOut, WantedListingOut, WantedWorkOut
from arrt.library.services.display_fit import DisplayFit
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
    ui.page.wait_for_selector("li.card:has-text('It waits in Wanted')")

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


#: A museum's web-size picture of a work in copyright: far below the floor.
TOO_SMALL = an_instance(
    is_selected=False,
    width=567,
    height=625,
    fit=FitOut(verdict=DisplayFit.BELOW_FLOOR.value, rendered_width=567, rendered_height=625, rendered_long_edge_inches=7.5),
)


def test_a_wanted_work_is_pictured_by_its_too_small_scan_and_says_so(ui):
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=TOO_SMALL)))

    open_wanted(ui)
    picture = ui.page.wait_for_selector(".wanted tbody tr .wanted-picture img")

    assert picture.get_attribute("alt") == "Blue Green Red, by Ellsworth Kelly"
    assert "/api/candidate-images/image-1/preview" in picture.get_attribute("src")
    row = ui.page.locator(".wanted tbody tr").inner_text()
    assert "below floor" in row
    assert "Found only too small" in row
    assert "No scan found" not in row, "a picture never sits beside a claim that nothing was found"


def test_pressing_a_wanted_work_s_picture_enlarges_it(ui):
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=TOO_SMALL)))

    open_wanted(ui)
    ui.page.click("button[aria-label='Enlarge the picture of Blue Green Red']")

    dialog = ui.page.wait_for_selector("dialog[open] img")
    assert "size=large" in dialog.get_attribute("src")


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

    assert ui.page.locator(".wanted .wanted-picture img").count() == 0
    rows = ui.page.locator(".wanted tbody tr").all_inner_texts()
    nothing = next(row for row in rows if "Nothing Found" in row)
    turned = next(row for row in rows if "All Turned Down" in row)
    assert "No scan found." in nothing
    assert "Every scan found was turned down." in turned
    assert "2 scans turned down" in turned
    assert "too small" not in turned


def test_a_wanted_work_holding_a_scan_on_offer_does_not_say_none_was_found(ui):
    """Wanted naming no scan, from a card standing on one: the scan is still there."""
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=an_instance())))

    open_wanted(ui)
    ui.page.wait_for_selector(".wanted tbody tr .wanted-picture img")

    row = ui.page.locator(".wanted tbody tr").inner_text()
    assert "One still on offer" in row
    assert "No scan found" not in row


def test_a_wanted_work_s_unselected_scan_of_unknown_size_is_not_called_on_offer(ui):
    """On offer means selected, as on the card; a scan nobody chose is only found."""
    ui.serve_image("**/api/candidate-images/*/preview*")
    unsized = an_instance(is_selected=False, width=None, height=None, fit=None, fit_note="Its size was never recorded.")
    ui.serve("**/api/wanted", a_wanted_listing(a_wanted(shown=unsized)))

    open_wanted(ui)
    ui.page.wait_for_selector(".wanted tbody tr .wanted-picture img")

    row = ui.page.locator(".wanted tbody tr").inner_text()
    assert "One found, not on offer" in row
    assert "still on offer" not in row


def test_wanted_lists_both_kinds_saying_which(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    rows = ui.page.locator(".wanted tbody tr").all_inner_texts()
    lobster = next(row for row in rows if "Lobster Telephone" in row)
    memory = next(row for row in rows if "The Persistence of Memory" in row)
    assert "No scan found" in lobster
    assert "No item" in lobster
    assert "1 scan turned down" in memory
    assert "Q25729" in memory
    assert "spends nothing" in ui.text()


def test_the_wanted_section_shows_its_count_once_something_is_wanted(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_function("() => document.querySelector(\"[data-count-slot='wanted']\").textContent === '2'")

    assert ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])").is_visible()


def test_with_nothing_wanted_the_section_is_shown_uncounted_and_the_page_names_the_controls_that_add_one(ui):
    open_wanted(ui)
    ui.page.wait_for_selector(".panel.empty")

    empty = ui.page.inner_text(".panel.empty")
    assert "Nothing is wanted." in empty
    # The controls that really put a work here, by the words they carry.
    assert "press Want on its review card" in empty
    assert "Turn it down" in empty
    section = ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])")
    assert section.is_visible()
    assert ui.page.inner_text("[data-count-slot='wanted']") == "", "a zero says nothing a curator acts on"


def test_the_wanted_section_is_shown_before_its_count_arrives(ui, wanted):
    """Shown from the first paint, whatever the count will say: the section is always there."""
    held = []

    def hold(route) -> None:
        held.append(route)

    ui.page.route("**/api/wanted", hold)
    ui.open("#collection")
    ui.page.wait_for_selector("nav.sidebar a.section-link")
    ui.page.wait_for_function("() => document.querySelector('nav.sidebar [data-count-slot=wanted]') !== null")

    assert ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])").is_visible()
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

    assert ui.page.locator("nav.sidebar a[data-view='wanted'][aria-current='page']").is_visible()


def test_a_count_that_cannot_be_read_shows_the_section_rather_than_hiding_it(ui, wanted):
    """Hiding on a failed read would say "nothing is wanted", which the client does not know."""
    ui.page.route("**/api/wanted", lambda route: route.fulfill(status=503, body="unwell"))
    ui.open("#collection")
    ui.page.wait_for_selector("nav.sidebar a.section-link")

    ui.page.wait_for_function("() => !document.querySelector(\"#sidebar li.section:has([data-count-slot='wanted'])\").hidden")
    assert ui.page.locator("#sidebar li.section:has([data-count-slot='wanted'])").is_visible()


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
    assert undo.is_visible()
    ui.page.wait_for_timeout(1000)
    assert sent == [], "nothing is sent while Undo can still take it back"
    undo.click()
    ui.page.wait_for_timeout(6000)

    assert sent == []
    assert str(discovery.get_candidate_work(nothing.id).verdict) == "wanted"
    assert ui.page.locator("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']").is_visible()


def test_a_row_drawn_again_while_its_forget_is_held_shows_the_hold(ui, wanted, discovery):
    """Another row's Forget repaints the page; the held row keeps its Undo, and Undo still works."""
    _, turned = wanted
    open_wanted(ui)

    ui.page.click("button[aria-label='Forget Lobster Telephone (1938): stop proposing it']")
    ui.page.wait_for_timeout(1500)
    ui.page.click("button[aria-label='Forget The Persistence of Memory: stop proposing it']")
    # Lobster's hold runs out and lands, and the page repaints with the other row still held.
    ui.page.wait_for_function("() => !document.querySelector('.wanted')?.innerText.includes('Lobster Telephone')", timeout=15000)
    undo = ui.page.locator('button[aria-label="Undo: don\'t forget The Persistence of Memory"]')
    assert undo.is_visible()
    undo.click()
    ui.page.wait_for_timeout(6000)

    assert str(discovery.get_candidate_work(turned.id).verdict) == "wanted"


def test_get_again_carries_its_tier(ui, wanted):
    open_wanted(ui)
    ui.page.wait_for_selector(".wanted table")

    row = ui.page.locator(".wanted tbody tr", has_text="Lobster Telephone")
    assert row.locator(".badge-tier").inner_text().endswith("Free")


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
    picker = ui.page.inner_text(".picker")
    assert "Which is Lobster Telephone (1938)?" in picker
    assert "has a picture" in picker
    assert "no picture on Wikidata" in picker

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
    assert "One Get for each of the 2 Gets" in ui.text()
    ui.page.click("button:text-is('Get all again')")
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
    ui.page.click("button[aria-label='Get Lobster Telephone (1938) again']")
    ui.page.wait_for_selector(".picker")
    assert note in ui.page.inner_text(".picker")
    assert ui.page.locator(".picker button:text-is('This one')").count() == 0
    assert ui.page.evaluate("() => document.activeElement.classList.contains('picker-heading')"), "the picker took no focus"

    ui.page.click(".picker button:text-is('Get without an item')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#get/resolve-3')")

    writes = [(method, url.split("/api/")[1]) for method, url, _ in calls if method in ("PUT", "POST")]
    assert writes == [("POST", "runs/resolve")], "searching without an item picks nothing first"


def test_search_all_over_one_search_opens_that_re_search(ui, wanted):
    ui.serve("**/api/runs/resolve", {"run_id": "resolve-one"})
    requests = posted(ui, "/api/runs/resolve")

    open_wanted(ui)
    assert "One Get for each" not in ui.text()
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
    outcome = ui.page.inner_text(".search-all-outcome")
    assert "Started 1 Get. 1 other could not start:" in outcome
    assert refusal in outcome
    assert ui.page.evaluate("() => window.location.hash") == "#wanted", "the page left before saying what was refused"
