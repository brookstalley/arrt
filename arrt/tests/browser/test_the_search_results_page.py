"""The search results page, in a real browser against a real server.

Ruling 2: one page lists what a few words find in the library and in Wikidata,
each with its state, artists first; *All*, *In your library* and *Not held*
narrow it; and when the words name one artist, that artist leads. It is reached
from the dropdown's last row, and Enter still opens Artworks (the owner,
2026-10-01). The registry is a fake installed where the entry point builds
Wikidata's.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import RegistryCreator, RegistryPerson, RegistryWorkMatch

DALI = "Q5577"
PERSISTENCE = "Q25729"
GIRAFFE = "Q1062364"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/G.jpg"


def _dali_works():
    by = RegistryCreator(qid=DALI, name="Salvador Dalí")
    return [
        RegistryWorkMatch(qid=PERSISTENCE, title="The Persistence of Memory", sitelinks=48, creator=by),
        RegistryWorkMatch(qid=GIRAFFE, title="The Burning Giraffe", sitelinks=9, image=COMMONS, creator=by),
        RegistryWorkMatch(qid="Q99", title="Crucifixion", sitelinks=7, creator=by),
    ]


@pytest.fixture
def registry():
    dali = RegistryPerson(qid=DALI, label="Salvador Dalí", born=1904, died=1989)
    return FakeRegistry(
        people={
            # Four, past the dropdown's three: the page asks for the wider list.
            "dali": [
                dali,
                RegistryPerson(qid="Q4", label="Gala Dalí", born=1894, died=1982),
                RegistryPerson(qid="Q8", label="Ana María Dalí", born=1908, died=1989),
                RegistryPerson(qid="Q9", label="Dalibor Chatrný", born=1925, died=2012),
            ],
            "salvador dali": [dali],
            "markup": [RegistryPerson(qid="Q6", label='Eve <img src=x onerror="window.pwned=1">')],
        },
        matches={"dali": _dali_works(), "salvador dali": _dali_works()[:1]},
    )


@pytest.fixture
def matched(services, seeded_service):
    """The seeded Dalí and his work, matched to the QIDs the fake registry finds."""
    dali = next(artist for artist in seeded_service.list_artists() if artist.name == "Salvador Dalí")
    work = next(e.artwork for e in seeded_service.list_artworks().entries if e.artwork.title == "The Persistence of Memory")
    services.identity.set_artist_identity(dali.id, DALI)
    services.identity.set_work_identity(work.id, PERSISTENCE)
    return dali, work


def _results(ui, query, view=None):
    ui.open(f"#search?q={query}" + (f"&view={view}" if view else ""))
    ui.page.wait_for_selector("#view h2:has-text('Results for')")


def _answered(ui):
    ui.page.wait_for_function("() => !document.querySelector('#view p[aria-live]').textContent.startsWith('Asking')")


def _rows(ui, section):
    return [
        " ".join(text.split()) for text in ui.page.locator(f"section[aria-labelledby='results-{section}'] li").all_inner_texts()
    ]


def test_the_dropdowns_last_row_opens_it(ui, matched):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    ui.page.click("#search")
    ui.page.keyboard.type("dali")
    ui.page.click("#search-suggestions [role='option']:has-text('All results for “dali”')")

    ui.page.wait_for_selector("#view h2:text-is('Results for “dali”')")
    assert ui.page.evaluate("() => window.location.hash").startswith("#search?")
    # Contextual: it returns to the page it was opened from, not to Artworks.
    assert "from=walls" in ui.page.evaluate("() => window.location.hash")
    assert ui.page.locator("#view p a, #view p button").first.inner_text() == "← Walls"


def test_all_shows_the_library_then_wikidata_each_marked_and_nothing_twice(ui, matched):
    _results(ui, "dali")
    _answered(ui)

    assert _rows(ui, "artists") == [
        "Salvador Dalí 1904–1989 ● In your library",
        "Gala Dalí 1894–1982 ○ Not held",
        "Ana María Dalí 1908–1989 ○ Not held",
        "Dalibor Chatrný 1925–2012 ○ Not held",
    ]
    assert _rows(ui, "works") == [
        "The Persistence of Memory — Salvador Dalí ● Held",
        "The Burning Giraffe — Salvador Dalí ◐ Not held · Image found",
        "Crucifixion — Salvador Dalí ○ Not held",
    ]
    # The row's title is the way in, so its mark is not a second button to the same work.
    assert ui.page.locator("section[aria-labelledby='results-works'] button.state-mark").count() == 0
    # Two artists carry "dali": no single one leads.
    assert ui.page.locator("#results-top").count() == 0
    assert ui.page.locator("#view [role='group'][aria-label='Show'] [aria-pressed='true']").inner_text() == "All"
    # The others say they are not pressed, rather than not saying.
    assert ui.page.locator("#view [role='group'][aria-label='Show'] [aria-pressed='false']").all_inner_texts() == [
        "In your library",
        "Not held",
    ]


def test_in_your_library_shows_only_the_library_and_asks_wikidata_nothing(ui, matched, registry):
    _results(ui, "dali", "library")

    assert _rows(ui, "artists") == ["Salvador Dalí 1904–1989 ● In your library"]
    assert _rows(ui, "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert registry.searched == []
    assert registry.matched == []


def test_not_held_shows_only_what_the_library_does_not_hold(ui, matched):
    _results(ui, "dali", "not_held")
    _answered(ui)

    assert _rows(ui, "artists") == [
        "Gala Dalí 1894–1982 ○ Not held",
        "Ana María Dalí 1908–1989 ○ Not held",
        "Dalibor Chatrný 1925–2012 ○ Not held",
    ]
    assert _rows(ui, "works") == [
        "The Burning Giraffe — Salvador Dalí ◐ Not held · Image found",
        "Crucifixion — Salvador Dalí ○ Not held",
    ]


def test_switching_view_keeps_the_query(ui, matched):
    _results(ui, "dali")
    ui.page.click("#view [role='group'][aria-label='Show'] button:has-text('Not held')")

    ui.page.wait_for_function("() => window.location.hash.includes('view=not_held') && window.location.hash.includes('q=dali')")


def test_words_naming_one_artist_put_them_first(ui, matched):
    dali, _work = matched
    _results(ui, "salvador dali")
    _answered(ui)

    top = ui.page.locator("section[aria-labelledby='results-top']")
    assert " ".join(top.locator("p").inner_text().split()) == "Salvador Dalí 1904–1989 ● In your library"
    top.locator("button").click()
    ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=dali.id)


def test_an_unheld_result_opens_its_page_here(ui, matched):
    _results(ui, "dali")
    _answered(ui)
    ui.page.click("section[aria-labelledby='results-works'] button:has-text('The Burning Giraffe')")

    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=GIRAFFE)


def test_when_wikidata_has_nothing_it_says_so_and_offers_museums(ui, seeded_service):
    _results(ui, "vermeer")
    _answered(ui)

    assert ui.page.locator("#view p[aria-live]").inner_text() == "Wikidata has nothing for “vermeer”."
    ui.page.click("#view button:has-text('Ask about “vermeer”')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#discover')")


def test_an_outage_leaves_the_librarys_results(ui, matched, registry):
    registry.failing = True
    _results(ui, "dali")
    _answered(ui)

    assert ui.page.locator("#view p[aria-live]").inner_text() == "Wikidata could not be searched just now."
    assert _rows(ui, "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]


def test_registry_text_arrives_as_words_not_markup(ui, seeded_service):
    _results(ui, "markup")
    _answered(ui)

    assert "<img" in ui.page.locator("section[aria-labelledby='results-artists']").inner_text()
    assert ui.page.locator("section[aria-labelledby='results-artists'] li img").count() == 0
    assert ui.page.evaluate("() => window.pwned") is None


def test_the_librarys_matches_open_in_artworks(ui, matched):
    _results(ui, "dali")
    ui.page.click("#view button:has-text('Open them in Artworks')")

    ui.page.wait_for_function("() => window.location.hash === '#collection?q=dali'")


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_it_says_only_the_library_was_searched(self, ui, seeded_service):
        _results(ui, "dali")
        _answered(ui)

        assert "only your library is searched" in ui.page.locator("#view p[aria-live]").inner_text()
        assert _rows(ui, "artists") == ["Salvador Dalí 1904–1989 ● In your library"]


def test_a_failed_library_search_is_an_error_not_an_empty_page(ui, seeded_service):
    ui.page.route(
        "**/api/works?q=*", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}')
    )
    ui.open("#search?q=dali")

    ui.page.wait_for_selector("#error:not([hidden])")
    # The library's own words, which say what failed, not a generic apology.
    assert ui.page.locator("#error").inner_text() == "boom"


def test_too_few_letters_says_why_wikidata_was_not_asked(ui, seeded_service, registry):
    _results(ui, "da")
    _answered(ui)

    assert ui.page.locator("#view p[aria-live]").inner_text() == "Wikidata is searched from three letters."
    assert registry.searched == []
