"""The top-bar search in two scopes, as Sonarr does it, in a real browser.

`information-architecture.md` § The *arr layout records Sonarr's pattern from
its source: typing searches the library, and the dropdown's last row offers the
same words as a search of everything, handed to Ask. Two departures, each
tested here: Ask fills the words in and does not start the search, because
a museum search is a paid run; and Enter with nothing highlighted opens the
Search results page rather than the first match, as the owner ruled on
2026-10-06. The library's groups sit under a *Held* heading, each named for it.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect
from scripted_model import ScriptedModel

LISTBOX = "#search-suggestions"


@pytest.fixture
def ask_model():
    """A server with a key: the dropdown offers Ask only where Ask can answer."""
    return ScriptedModel(replies=[])


def type_into_search(ui, words: str) -> None:
    ui.page.click("#search")
    ui.page.keyboard.type(words)
    # The dropdown answers the words as they stood when typing paused, and a
    # loaded machine pauses mid-word: wait for the answer to all of them, which
    # the last row names, not for the first dropdown to open.
    ui.page.wait_for_selector(f"{LISTBOX}:not([hidden]) [role='option']:text-is('All results for “{words}”')")


def options(ui):
    """Every row of the dropdown, for `to_have_text([...])`."""
    return ui.page.locator(f"{LISTBOX} [role='option']")


def test_typing_offers_library_matches_then_a_search_of_everything(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Dalí")

    # The artist first (ruling 4's hub, the IA's Artists-first ranking), then
    # the library's works, then the search of everything.
    expect(options(ui)).to_have_text(
        [
            "Salvador Dalí — artist",
            "The Persistence of Memory — Salvador Dalí",
            "Ask about “Dalí”",
            "All results for “Dalí”",
        ],
        use_inner_text=True,
    )
    # The groups are named through `aria-labelledby`, so a screen reader says
    # which scope an option is in: asserted by role and accessible name, which
    # visible text alone cannot prove.
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    held_artists = listbox.get_by_role("group", name="Held: artists", exact=True)
    expect(held_artists.get_by_role("option")).to_have_text(["Salvador Dalí — artist"], use_inner_text=True)
    expect(listbox.get_by_role("group", name="Held: works", exact=True).get_by_role("option")).to_have_count(1)
    expect(listbox.get_by_role("group", name="Ask", exact=True).get_by_role("option")).to_have_text(
        ["Ask about “Dalí”"], use_inner_text=True
    )
    # Each half is drawn once, above its groups, and hidden from a screen reader,
    # which hears it in each group's name instead. With no registry configured,
    # Not held holds only the note saying so.
    halves = ui.page.locator(f"{LISTBOX} .search-suggestions-half")
    expect(halves).to_have_text(["Held", "Not held"], use_inner_text=True)
    assert halves.evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-hidden'))") == ["true", "true"]


def test_typing_without_the_accent_still_offers_the_library_match(ui, seeded_service):
    """The typeahead asks the same route as the grid, so the fold reaches it; this
    holds that it asks with the words as typed rather than reaching nothing."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "dali")

    expect(options(ui)).to_have_text(
        [
            "Salvador Dalí — artist",
            "The Persistence of Memory — Salvador Dalí",
            "Ask about “dali”",
            "All results for “dali”",
        ],
        use_inner_text=True,
    )


def test_with_no_library_match_held_is_one_line_and_only_the_search_of_everything_is_offered(ui, seeded_service):
    """Sonarr leaves out the library group when nothing matches, rather than
    heading an empty list; here the Held half says so in one line, with no group
    for each kind it lacks (the owner, 2026-10-06)."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Vermeer")

    expect(options(ui)).to_have_text(["Ask about “Vermeer”", "All results for “Vermeer”"], use_inner_text=True)
    expect(ui.page.locator(f"{LISTBOX} .search-suggestions-label")).to_have_text(["Ask", "Search"])
    expect(ui.page.locator(f"{LISTBOX} .search-suggestions-none").first).to_have_text(
        "Nothing you hold matches.", use_inner_text=True
    )
    # Not an option: arrow keys pass over it.
    expect(ui.page.locator(f"{LISTBOX} .search-suggestions-none").first).to_have_attribute("role", "presentation")


def test_a_library_match_leaves_out_the_nothing_held_line(ui, seeded_service):
    """The paired negative: the one line is for an empty half only."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Dalí")

    # Anchored by `type_into_search`, which waited for the answer to all the words.
    expect(ui.page.locator(LISTBOX)).not_to_contain_text("Nothing you hold matches.", use_inner_text=True)


def test_the_field_is_a_combobox_the_keyboard_can_drive(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    field = ui.page.locator("#search")
    expect(field).to_have_attribute("role", "combobox")
    expect(field).to_have_attribute("aria-expanded", "false")

    type_into_search(ui, "Dalí")
    expect(field).to_have_attribute("aria-expanded", "true")

    ui.page.keyboard.press("ArrowDown")
    first = ui.page.locator(f"{LISTBOX} [role='option']").first
    first_id = first.get_attribute("id")  # one-shot: the row's own id, which the highlight is then asserted to name
    expect(field).to_have_attribute("aria-activedescendant", first_id)
    expect(first).to_have_attribute("aria-selected", "true")

    ui.page.keyboard.press("Escape")
    expect(field).to_have_attribute("aria-expanded", "false")
    expect(ui.page.locator(LISTBOX)).to_be_hidden()


def test_choosing_a_library_match_opens_that_work(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Dalí")
    # Past the artist to the work.
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h1:has-text('The Persistence of Memory')")
    assert ui.page.evaluate("() => window.location.hash").startswith("#work/")


def test_a_failed_artist_lookup_keeps_the_work_matches(ui, seeded_service):
    """The artist group is an extra; its failure must not cost the library's matches."""
    ui.page.route("**/api/artists?q=*", lambda route: route.fulfill(status=500, content_type="application/json", body="{}"))
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "dali")

    expect(options(ui)).to_have_text(
        ["The Persistence of Memory — Salvador Dalí", "Ask about “dali”", "All results for “dali”"], use_inner_text=True
    )
    expect(ui.page.locator(".search-suggestions-note")).to_have_count(0)


def test_choosing_an_artist_opens_their_page(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "dali")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h1:has-text('Salvador Dalí')")
    assert ui.page.evaluate("() => window.location.hash").startswith("#artist/")


def test_searching_museums_hands_the_words_to_add_new_and_spends_nothing(ui, service, seeded_service):
    """Sonarr's lookup is free, so its Add New runs it at once; an Arrt search
    is a paid run, so Ask fills the words in and waits for the button."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Vermeer interiors")
    ui.page.click(f"{LISTBOX} [role='option']:has-text('Ask about')")

    ui.page.wait_for_selector("#view h1:text-is('Ask')")
    expect(ui.page.locator("#ask-words")).to_have_value("Vermeer interiors")
    assert ui.page.evaluate("() => window.location.hash") == "#discover?term=Vermeer%20interiors"
    # Nothing was asked of any museum or model: no run exists.
    assert ui.page.evaluate("async () => (await (await fetch('/api/runs')).json()).total") == 0


def test_add_new_reached_without_a_term_starts_empty(ui, seeded_service):
    """The paired negative: the box is filled only from a handed-over term."""
    ui.open("#discover")
    ui.page.wait_for_selector("#view h1:text-is('Ask')")

    expect(ui.page.locator("#ask-words")).to_have_value("")


def test_enter_with_several_matches_opens_the_results_page_not_the_first(ui, seeded_service):
    """An artist or a movement matches many works, so the first match is an
    arbitrary one; Enter opens every match, on the results page (the owner,
    2026-10-06). "the" matches two seeded works."""
    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "the")
    library = ui.page.get_by_role("listbox", name="Suggestions").get_by_role("group", name="Held: works", exact=True)
    expect(
        library.get_by_role("option"), "the fixture must match more than one work, or this cannot tell first from all"
    ).to_have_count(2)
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h1:text-is('Results for “the”')")
    # Opened from Artworks, the results page's own default return, so no `from`.
    assert ui.page.evaluate("() => window.location.hash") == "#search?q=the"
    expect(ui.page.locator("section[aria-labelledby='results-held-works'] li")).to_have_count(2)


def test_enter_with_no_match_opens_the_results_page_saying_so(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Vermeer")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view .results-none")
    assert ui.page.evaluate("() => window.location.hash") == "#search?from=walls&q=Vermeer"
    expect(ui.page.locator("#view .results-none")).to_have_text("Nothing you hold matches.", use_inner_text=True)
    expect(ui.page.locator(LISTBOX)).to_be_hidden()


def test_a_failed_library_lookup_still_offers_the_search_of_everything(ui, seeded_service):
    """The dropdown is a shortcut, so a failed lookup costs the matches and says so.

    Silence would read as "nothing in your library", and the row left is a paid
    museum search for a work the curator may already own.
    """
    ui.page.route("**/api/works?q=*", lambda route: route.fulfill(status=503, body="{}"))
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Dalí")

    # The artist lookup is a separate request and answered, so the artist is still
    # offered; only the works could not be searched, and the dropdown says so.
    expect(options(ui)).to_have_text(
        ["Salvador Dalí — artist", "Ask about “Dalí”", "All results for “Dalí”"], use_inner_text=True
    )
    expect(ui.page.locator(LISTBOX)).to_contain_text("could not be searched", use_inner_text=True)


def test_a_lookup_that_found_nothing_does_not_claim_it_failed(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    type_into_search(ui, "Vermeer")

    # Anchored by `type_into_search`, which waited for the answer to all the words.
    expect(ui.page.locator(LISTBOX)).not_to_contain_text("could not be searched", use_inner_text=True)


def test_a_slow_answer_to_an_earlier_keystroke_does_not_replace_a_later_one(ui, seeded_service):
    """The first lookup is held until the second has painted, then released."""
    held = []

    def handler(route):
        if "q=Nig" in route.request.url and "Nighthawks" not in route.request.url:
            held.append(route)
        else:
            route.continue_()

    ui.page.route("**/api/works?q=*", handler)
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    ui.page.click("#search")
    # The earlier lookup is made, and held, before the next keystroke: that is
    # what the test is about, so it is waited on by its request.
    with ui.page.expect_request(lambda request: "/api/works" in request.url and "q=Nig&" in request.url):
        ui.page.keyboard.type("Nig")
    ui.page.keyboard.type("hthawks")
    ui.page.wait_for_selector(f"{LISTBOX} [role='option']:has-text('Nighthawks')")
    assert held, "the earlier lookup was never made, so this test cannot say anything"

    with ui.page.expect_response(lambda response: "/api/works" in response.url and "q=Nig&" in response.url):
        held[0].fulfill(
            status=200,
            content_type="application/json",
            body='{"works": [], "total": 0, "limit": 6, "offset": 0, "truncated": false, "facets": []}',
        )
    # The answer is in; if it were taken for the latest, the rows would go with it. Nothing
    # changes on a page that ignores it, so there is no condition to wait on.
    ui.page.wait_for_timeout(300)  # sleep: proves the late, emptier answer, once in, replaces nothing

    expect(options(ui), "the earlier, emptier answer replaced the later one").to_contain_text(["Nighthawks"], use_inner_text=True)
