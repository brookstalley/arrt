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

from arrt.library.registry import (  # noqa: E402
    ItemId,
    RegistryCreator,
    RegistryPerson,
    RegistryText,
    RegistryTopic,
    RegistryWorkMatch,
    TopicKind,
)

LISTBOX = "#search-suggestions"
PENDING = f"{LISTBOX} .search-suggestions-pending"
ANNOUNCED = "#search-suggestions + [aria-live='polite']"
DALI = "Q5577"
PERSISTENCE = "Q25729"
GIRAFFE = "Q1062364"
SURREALISM = "Q39427"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/G.jpg"


def _registry(**more):
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
        **more,
    )


@pytest.fixture
def registry():
    return _registry()


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
    """Until both of Wikidata's searches have answered: each paints on its own, so the first is not enough."""
    ui.page.wait_for_selector(
        f"{LISTBOX} [aria-labelledby='suggestions-registry-works'], {LISTBOX} .search-suggestions-registry-note"
    )
    ui.page.wait_for_selector(PENDING, state="detached")


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
        "Ask about “dali”",
        "All results for “dali”",
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
    ui.page.wait_for_selector(f"{LISTBOX} [role='option']:has-text('Ask about “dali”')")
    assert ui.page.get_attribute("#search", "aria-activedescendant") is None
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_function("() => window.location.hash.startsWith('#collection') && window.location.hash.includes('q=dali')")


def test_choosing_a_theme_opens_it(ui, services, matched):
    theme = next(t for t in services.display.list_themes() if t.name == "Dalí and friends")
    _type(ui, "friends")

    ui.page.click(f"{LISTBOX} [role='option']:has-text('Dalí and friends — theme')")
    ui.page.wait_for_function("(id) => window.location.hash.split('?')[0] === `#theme/${id}`", arg=theme.id)


class TestEachOfWikidatasSearchesPaintsOnItsOwn:
    """The topic search can take seconds where the artists and works take under one.

    Joined, the faster answer waited for the slower with nothing on screen saying
    anything was coming. So each paints when it arrives, *Asking Wikidata…* says
    while either is out, and the announcement is made once, when both have
    answered, with what they found between them.
    """

    @pytest.fixture
    def registry(self):
        return _registry(
            topics_found={
                "dali": [
                    RegistryTopic(
                        qid=ItemId(SURREALISM),
                        label=RegistryText("Surrealism"),
                        kinds=(TopicKind.MOVEMENT,),
                        description=RegistryText("art movement"),
                    )
                ],
                # What an earlier keystroke's topic search finds, which must never be shown for a later one.
                "dal": [RegistryTopic(qid=ItemId("Q38280"), label=RegistryText("Dalmatian"), kinds=(TopicKind.SUBJECT,))],
            }
        )

    def _hold(self, ui, route_glob):
        held = []
        ui.page.route(route_glob, lambda route: held.append(route))
        return held

    def test_artists_and_works_are_shown_while_the_topic_search_is_held(self, ui, matched):
        held = self._hold(ui, "**/api/registry/topics?*")
        _type(ui, "dali")

        ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-works']", timeout=5000)
        listbox = ui.page.get_by_role("listbox", name="Suggestions")
        assert listbox.get_by_role("group", name="Wikidata: artists").get_by_role("option").count() == 1
        assert listbox.get_by_role("group", name="Wikidata: works").get_by_role("option").count() == 2
        assert ui.page.locator(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']").count() == 0
        assert ui.page.locator(PENDING).inner_text() == "Asking Wikidata…"
        # Announced once, when both have answered: not a count of half of them.
        assert ui.page.locator(ANNOUNCED).inner_text() == ""

        # A curator who has arrowed to a row stays on it when the topics arrive.
        for _ in range(4):
            ui.page.keyboard.press("ArrowDown")
        before = ui.page.get_attribute("#search", "aria-activedescendant")
        assert before == "suggestion-registry-artist-0"

        held[0].continue_()
        ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']")

        assert listbox.get_by_role("group", name="Wikidata: topics").get_by_role("option").all_inner_texts() == [
            "Surrealism — movement · art movement"
        ]
        assert ui.page.locator(PENDING).count() == 0
        assert ui.page.get_attribute("#search", "aria-activedescendant") == before
        assert ui.page.locator(ANNOUNCED).inner_text() == "Wikidata: 6 matches."

    def test_asking_wikidata_shows_while_one_is_out_is_no_option_and_goes_when_both_answer(self, ui, matched):
        held = self._hold(ui, "**/api/registry/search?*")
        _type(ui, "dali")

        ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']", timeout=5000)
        pending = ui.page.locator(PENDING)
        assert pending.inner_text() == "Asking Wikidata…"
        assert pending.get_attribute("role") == "presentation"
        # Not an option: arrow keys visit every option once and only options, then wrap.
        options = ui.page.locator(f"{LISTBOX} [role='option']")
        ids = [options.nth(at).get_attribute("id") for at in range(options.count())]
        visited = []
        for _ in ids:
            ui.page.keyboard.press("ArrowDown")
            visited.append(ui.page.get_attribute("#search", "aria-activedescendant"))
        assert visited == ids
        ui.page.keyboard.press("ArrowDown")
        assert ui.page.get_attribute("#search", "aria-activedescendant") == ids[0]
        # Announced once, when both have answered, so not yet.
        assert ui.page.locator(ANNOUNCED).inner_text() == ""

        held[0].continue_()
        ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-works']")

        assert pending.count() == 0
        # Two artists, three works and one topic, as Wikidata answered them.
        ui.page.wait_for_function(f"() => document.querySelector(\"{ANNOUNCED}\").textContent !== ''")
        assert ui.page.locator(ANNOUNCED).inner_text() == "Wikidata: 6 matches."

    def test_a_late_topic_answer_to_an_earlier_keystroke_is_ignored(self, ui, matched):
        held = []

        def handler(route):
            if route.request.url.endswith("q=dal"):
                held.append(route)
            else:
                route.continue_()

        ui.page.route("**/api/registry/topics?*", handler)
        _type(ui, "dal")
        ui.page.wait_for_timeout(400)
        assert held, "the earlier topic search was never made, so this test cannot say anything"
        ui.page.keyboard.type("i")
        ui.page.wait_for_selector(f"{LISTBOX} [role='option']:has-text('Surrealism')")
        ui.page.wait_for_selector(PENDING, state="detached")

        held[0].continue_()
        ui.page.wait_for_timeout(300)

        texts = " ".join(_options(ui))
        assert "Dalmatian" not in texts, "the earlier keystroke's topics replaced the later one's"
        assert "Surrealism" in texts and "Ask about “dali”" in texts
        assert ui.page.locator(ANNOUNCED).inner_text() == "Wikidata: 6 matches."
