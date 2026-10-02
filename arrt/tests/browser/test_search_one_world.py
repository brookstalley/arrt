"""The top-bar search covers one world, in a real browser against a real server.

Ruling 2: below the library's matches, Wikidata's artists and works, each with
its state. They arrive after the library's rows and never hold them back; a
match the library's rows already show is not shown twice; and their arrival is
announced rather than focused. The registry is a fake installed where the entry
point builds Wikidata's.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry  # noqa: E402  (after the skip guard)

from arrt.library.registry import RegistryCreator, RegistryPerson, RegistryWorkMatch  # noqa: E402

LISTBOX = "#search-suggestions"
DALI = "Q5577"
PERSISTENCE = "Q25729"
GIRAFFE = "Q1062364"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/G.jpg"


@pytest.fixture
def registry():
    return FakeRegistry(
        people={
            "dali": [
                RegistryPerson(qid=DALI, label="Salvador Dalí", born=1904, died=1989),
                RegistryPerson(qid="Q4", label="Gala Dalí", born=1894, died=1982),
            ],
            "markup": [RegistryPerson(qid="Q6", label='Eve <img src=x onerror="window.pwned=1">')],
        },
        matches={
            "dali": [
                RegistryWorkMatch(
                    qid=PERSISTENCE,
                    title="The Persistence of Memory",
                    sitelinks=48,
                    creator=RegistryCreator(qid=DALI, name="Salvador Dalí"),
                ),
                RegistryWorkMatch(
                    qid=GIRAFFE,
                    title="The Burning Giraffe",
                    sitelinks=9,
                    image=COMMONS,
                    creator=RegistryCreator(qid=DALI, name="Salvador Dalí"),
                ),
                # Neither held nor with an image: the third state a row can be in.
                RegistryWorkMatch(
                    qid="Q99", title="Crucifixion", sitelinks=7, creator=RegistryCreator(qid=DALI, name="Salvador Dalí")
                ),
            ],
        },
    )


@pytest.fixture
def matched(services, seeded_service):
    """The seeded Dalí and his work, matched to the QIDs the fake registry finds."""
    dali = next(artist for artist in seeded_service.list_artists() if artist.name == "Salvador Dalí")
    work = next(e.artwork for e in seeded_service.list_artworks().entries if e.artwork.title == "The Persistence of Memory")
    services.identity.set_artist_identity(dali.id, DALI)
    services.identity.set_work_identity(work.id, PERSISTENCE)
    services.display.add_theme(name="Dalí and friends")
    return dali, work


def _type(ui, words):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    ui.page.click("#search")
    ui.page.keyboard.type(words)
    ui.page.wait_for_selector(f"{LISTBOX}:not([hidden]) [role='option']")


def _options(ui):
    """Each row's words, with the line breaks a badge's parts are laid out on folded to spaces."""
    return [" ".join(text.split()) for text in ui.page.locator(f"{LISTBOX} [role='option']").all_inner_texts()]


def _wait_for_registry(ui):
    ui.page.wait_for_selector(
        f"{LISTBOX} [aria-labelledby='suggestions-registry-works'], {LISTBOX} .search-suggestions-registry-note"
    )


def test_wikidata_follows_the_library_and_shows_nothing_twice(ui, matched):
    _type(ui, "dali")
    _wait_for_registry(ui)

    assert _options(ui) == [
        "Salvador Dalí — artist",
        "The Persistence of Memory — Salvador Dalí",
        "Dalí and friends — theme",
        "Gala Dalí (1894–1982) — artist ○ Not held",
        "The Burning Giraffe — Salvador Dalí ◐ Image found",
        "Crucifixion — Salvador Dalí ○ Not held",
        "Search museums for “dali”",
    ]
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    assert listbox.get_by_role("group", name="Wikidata: artists").get_by_role("option").count() == 1
    assert listbox.get_by_role("group", name="Wikidata: works").get_by_role("option").count() == 2
    # Glyph, word and colour, as every state mark here carries one (`accessibility-spec.md`).
    badge = ui.page.locator(f"{LISTBOX} [role='option']:has-text('The Burning Giraffe') .badge-image-found")
    assert badge.locator(".glyph").inner_text() == "◐"
    assert badge.locator(".glyph").get_attribute("aria-hidden") == "true"


def test_a_held_match_the_library_rows_do_not_show_says_so_and_opens_the_library(ui, matched):
    """The library's rows show its first few works; a held work not among them is still marked held."""
    _dali, work = matched
    ui.page.route(
        "**/api/works?q=*",
        lambda route: route.fulfill(status=200, content_type="application/json", body='{"works": [], "total": 0}'),
    )
    _type(ui, "dali")
    _wait_for_registry(ui)

    row = f"{LISTBOX} [role='option']:has-text('The Persistence of Memory')"
    assert " ".join(ui.page.locator(row).inner_text().split()) == "The Persistence of Memory — Salvador Dalí ● In your library"
    assert ui.page.locator(f"{row} .badge-held .glyph").inner_text() == "●"
    ui.page.click(row)
    ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#work/${id}`)", arg=work.id)


def test_choosing_an_unheld_work_opens_its_page_here(ui, matched):
    _type(ui, "dali")
    _wait_for_registry(ui)

    ui.page.click(f"{LISTBOX} [role='option']:has-text('The Burning Giraffe')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=GIRAFFE)


def test_arrow_keys_reach_wikidatas_rows_and_stay_put_when_they_arrive(ui, matched):
    held = []
    ui.page.route("**/api/registry/search?*", lambda route: held.append(route))
    _type(ui, "dali")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("ArrowDown")
    before = ui.page.get_attribute("#search", "aria-activedescendant")

    held[0].continue_()
    _wait_for_registry(ui)

    assert ui.page.get_attribute("#search", "aria-activedescendant") == before
    for _ in range(2):
        ui.page.keyboard.press("ArrowDown")
    assert ui.page.get_attribute("#search", "aria-activedescendant") == "suggestion-registry-artist-0"
    assert ui.page.evaluate("() => document.activeElement.id") == "search"


def test_their_arrival_is_announced(ui, matched):
    _type(ui, "dali")
    _wait_for_registry(ui)

    assert ui.page.locator("#search-suggestions + [aria-live='polite']").inner_text() == "Wikidata: 5 matches."


def test_registry_text_arrives_as_words_not_markup(ui, seeded_service):
    _type(ui, "markup")
    ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-artists']")

    assert any("<img" in text for text in _options(ui))
    assert ui.page.locator(f"{LISTBOX} img").count() == 0
    assert ui.page.evaluate("() => window.pwned") is None


def test_an_outage_leaves_the_library_rows_and_says_so(ui, matched, registry):
    registry.failing = True
    _type(ui, "dali")
    _wait_for_registry(ui)

    assert _options(ui)[:2] == ["Salvador Dalí — artist", "The Persistence of Memory — Salvador Dalí"]
    assert (
        ui.page.locator(f"{LISTBOX} .search-suggestions-registry-note").inner_text() == "Wikidata could not be searched just now."
    )
    # Not the library's note: the library was searched.
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-note").count() == 0


def test_two_letters_ask_wikidata_nothing(ui, matched, registry):
    _type(ui, "da")
    ui.page.wait_for_timeout(500)

    assert registry.searched == [] and registry.matched == []
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-registry-note").count() == 0


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_it_says_only_the_library_was_searched(self, ui, seeded_service):
        _type(ui, "dali")
        _wait_for_registry(ui)

        assert "only your library is searched" in ui.page.locator(f"{LISTBOX} .search-suggestions-registry-note").inner_text()
        assert _options(ui)[0] == "Salvador Dalí — artist"


def test_a_new_query_starts_with_nothing_highlighted_so_enter_searches_artworks(ui, matched):
    """A highlight kept by position would land on whatever the next query puts there, and Enter would open it."""
    _type(ui, "dal")
    announced = "() => document.querySelector('#search-suggestions + [aria-live]').textContent.startsWith('Wikidata')"
    ui.page.wait_for_function(announced)
    ui.page.keyboard.press("ArrowDown")
    assert ui.page.get_attribute("#search", "aria-activedescendant") == "suggestion-artist-0"

    ui.page.keyboard.type("i")
    ui.page.wait_for_selector(f"{LISTBOX} [role='option']:has-text('Search museums for “dali”')")
    assert ui.page.get_attribute("#search", "aria-activedescendant") is None
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_function("() => window.location.hash.startsWith('#collection') && window.location.hash.includes('q=dali')")


def test_choosing_a_theme_opens_it(ui, services, matched):
    theme = next(t for t in services.display.list_themes() if t.name == "Dalí and friends")
    _type(ui, "friends")

    ui.page.click(f"{LISTBOX} [role='option']:has-text('Dalí and friends — theme')")
    ui.page.wait_for_function("(id) => window.location.hash.split('?')[0] === `#theme/${id}`", arg=theme.id)
