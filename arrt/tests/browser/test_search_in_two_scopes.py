"""The top-bar search in two scopes, as Sonarr does it, in a real browser.

`information-architecture.md` § The *arr layout records Sonarr's pattern from
its source: typing searches the library, and the dropdown's last row offers the
same words as a search of everything, handed to Add New. Two departures, each
tested here: Add New fills the words in and does not start the search, because
a museum search is a paid run; and Enter with nothing highlighted opens Artworks
filtered to the query rather than the first match, as the owner ruled.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

LISTBOX = "#search-suggestions"


def type_into_search(ui, words: str) -> None:
    ui.page.click("#search")
    ui.page.keyboard.type(words)
    ui.page.wait_for_selector(f"{LISTBOX}:not([hidden]) [role='option']")


def options(ui) -> list[str]:
    return ui.page.locator(f"{LISTBOX} [role='option']").all_inner_texts()


def test_typing_offers_library_matches_then_a_search_of_everything(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Dalí")

    assert options(ui) == ["The Persistence of Memory — Salvador Dalí", "Search museums for “Dalí”"]
    # The groups are named through `aria-labelledby`, so a screen reader says
    # which scope an option is in: asserted by role and accessible name, which
    # visible text alone cannot prove.
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    assert listbox.get_by_role("group", name="In your library").get_by_role("option").count() == 1
    assert listbox.get_by_role("group", name="Add New").get_by_role("option").all_inner_texts() == ["Search museums for “Dalí”"]


def test_typing_without_the_accent_still_offers_the_library_match(ui, seeded_service):
    """The typeahead asks the same route as the grid, so the fold reaches it; this
    holds that it asks with the words as typed rather than reaching nothing."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "dali")

    assert options(ui) == ["The Persistence of Memory — Salvador Dalí", "Search museums for “dali”"]


def test_with_no_library_match_only_the_search_of_everything_is_offered(ui, seeded_service):
    """Sonarr leaves out the library group when nothing matches, rather than
    heading an empty list."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Vermeer")

    assert options(ui) == ["Search museums for “Vermeer”"]
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-label", has_text="library").count() == 0


def test_the_field_is_a_combobox_the_keyboard_can_drive(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    field = ui.page.locator("#search")
    assert field.get_attribute("role") == "combobox"
    assert field.get_attribute("aria-expanded") == "false"

    type_into_search(ui, "Dalí")
    assert field.get_attribute("aria-expanded") == "true"

    ui.page.keyboard.press("ArrowDown")
    first = ui.page.locator(f"{LISTBOX} [role='option']").first
    assert field.get_attribute("aria-activedescendant") == first.get_attribute("id")
    assert first.get_attribute("aria-selected") == "true"

    ui.page.keyboard.press("Escape")
    assert field.get_attribute("aria-expanded") == "false"
    assert not ui.page.locator(LISTBOX).is_visible()


def test_choosing_a_library_match_opens_that_work(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Dalí")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h2:has-text('The Persistence of Memory')")
    assert ui.page.evaluate("() => window.location.hash").startswith("#work/")


def test_searching_museums_hands_the_words_to_add_new_and_spends_nothing(ui, service, seeded_service):
    """Sonarr's lookup is free, so its Add New runs it at once; an Arrt search
    is a paid run, so Add New fills the words in and waits for the button."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Vermeer interiors")
    ui.page.click(f"{LISTBOX} [role='option']:has-text('Search museums')")

    ui.page.wait_for_selector("#view h2:has-text('Add New')")
    assert ui.page.input_value("#intent") == "Vermeer interiors"
    assert ui.page.evaluate("() => window.location.hash") == "#discover?term=Vermeer%20interiors"
    # Nothing was asked of any museum or model: no run exists.
    assert ui.page.evaluate("async () => (await (await fetch('/api/runs')).json()).total") == 0


def test_add_new_reached_without_a_term_starts_empty(ui, seeded_service):
    """The paired negative: the box is filled only from a handed-over term."""
    ui.open("#discover")
    ui.page.wait_for_selector("#view h2:has-text('Add New')")

    assert ui.page.input_value("#intent") == ""


def test_enter_with_several_matches_opens_artworks_filtered_not_the_first(ui, seeded_service):
    """The owner's ruling: an artist or a movement matches many works, so the
    first match is an arbitrary one. "the" matches two seeded works."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "the")
    assert len(options(ui)) == 3, "the fixture must match more than one work, or this cannot tell first from all"
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h2:has-text('matching')")
    assert ui.page.evaluate("() => window.location.hash") == "#collection?q=the"
    assert ui.page.locator("ul.grid li.card").count() == 2


def test_enter_with_no_match_opens_artworks_saying_so(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Vermeer")
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view .empty")
    assert ui.page.evaluate("() => window.location.hash") == "#collection?q=Vermeer"
    assert not ui.page.locator(LISTBOX).is_visible()


def test_a_failed_library_lookup_still_offers_the_search_of_everything(ui, seeded_service):
    """The dropdown is a shortcut, so a failed lookup costs the matches and says so.

    Silence would read as "nothing in your library", and the row left is a paid
    museum search for a work the curator may already own.
    """
    ui.page.route("**/api/works?q=*", lambda route: route.fulfill(status=503, body="{}"))
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Dalí")

    assert options(ui) == ["Search museums for “Dalí”"]
    assert "could not be searched" in ui.page.inner_text(LISTBOX)


def test_a_lookup_that_found_nothing_does_not_claim_it_failed(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")

    type_into_search(ui, "Vermeer")

    assert "could not be searched" not in ui.page.inner_text(LISTBOX)


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
    ui.page.wait_for_selector("#view h2")

    ui.page.click("#search")
    ui.page.keyboard.type("Nig")
    ui.page.wait_for_timeout(400)
    ui.page.keyboard.type("hthawks")
    ui.page.wait_for_selector(f"{LISTBOX} [role='option']:has-text('Nighthawks')")
    assert held, "the earlier lookup was never made, so this test cannot say anything"

    held[0].fulfill(
        status=200,
        content_type="application/json",
        body='{"works": [], "total": 0, "limit": 6, "offset": 0, "truncated": false, "facets": []}',
    )
    ui.page.wait_for_timeout(300)

    assert "Nighthawks" in " ".join(options(ui)), "the earlier, emptier answer replaced the later one"
