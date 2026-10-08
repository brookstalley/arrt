"""The top-bar search covers one world, in a real browser against a real server.

Ruling 2: below the library's matches, Wikidata's artists and works, each with
its state. They arrive after the library's rows and never hold them back; a
match the library's rows already show is not shown twice; and their arrival is
announced rather than focused. Since the owner's ruling of 2026-10-06 the list
is in two halves, *Held* then *Not held*, each group named for its half, and a
held match of Wikidata's is under Held. The registry is a fake installed where
the entry point builds Wikidata's.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import (
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
    ui.page.wait_for_selector("#view h1")
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
        "Gala Dalí (1894–1982) — artist",
        "The Burning Giraffe — Salvador Dalí ◐ Image found",
        "Crucifixion — Salvador Dalí ○ No image known",
        "Ask about “dali”",
        "All results for “dali”",
    ]
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    assert listbox.get_by_role("group", name="Not held: artists", exact=True).get_by_role("option").count() == 1
    assert listbox.get_by_role("group", name="Not held: works", exact=True).get_by_role("option").count() == 2
    # Glyph, word and colour, as every state mark here carries one (`accessibility-spec.md`).
    badge = ui.page.locator(f"{LISTBOX} [role='option']:has-text('The Burning Giraffe') .badge-image-found")
    assert badge.locator(".glyph").inner_text() == "◐"
    assert badge.locator(".glyph").get_attribute("aria-hidden") == "true"


def test_a_wanted_match_says_wanted_and_only_the_unheld_picture_is_hatched(ui, matched, want_item, pictures_load):
    """The typeahead's half of #172: *Image found* no longer reads as if it might mean held."""
    want_item("Q99", "Crucifixion")
    _type(ui, "dali")
    _wait_for_registry(ui)

    assert "Crucifixion — Salvador Dalí ◑ Wanted" in _options(ui)
    giraffe = ui.page.locator(f"{LISTBOX} [role='option']", has_text="The Burning Giraffe")
    assert giraffe.locator(".work-pic-not-held img").count() == 1
    assert ui.page.locator(f"{LISTBOX} .work-pic-not-held").count() == 1


def test_no_suggestion_holds_a_control_of_its_own(ui, matched, seeded_service, services):
    """A held Wikidata match marks itself without a button.

    An option holding a control is invalid ARIA, and Tab would land in it.
    """
    work = next(e.artwork for e in seeded_service.list_artworks().entries if e.artwork.title == "I Saw the Figure 5 in Gold")
    services.identity.set_work_identity(work.id, GIRAFFE)
    _type(ui, "dali")
    _wait_for_registry(ui)

    assert ui.page.locator(f"{LISTBOX} [role='option'] .badge-held").count() >= 1
    assert ui.page.locator(f"{LISTBOX} [role='option'] button").count() == 0


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
    assert " ".join(ui.page.locator(row).inner_text().split()) == "The Persistence of Memory — Salvador Dalí ● Held"
    # Held, so in the Held half, not among what Wikidata has that you do not hold.
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    held_works = listbox.get_by_role("group", name="Held: works", exact=True).get_by_role("option").all_inner_texts()
    assert [" ".join(text.split()) for text in held_works] == ["The Persistence of Memory — Salvador Dalí ● Held"]
    not_held = listbox.get_by_role("group", name="Not held: works", exact=True).get_by_role("option").all_inner_texts()
    assert not any("Persistence" in text for text in not_held)
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
    ui.page.route(
        "**/api/registry/search?*",
        lambda route: held.append(route),  # noqa: PLW0108 -- Playwright passes a builtin method two arguments
    )
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


def test_every_group_says_its_half_in_its_name(ui, matched):
    """A listbox cannot nest groups, so the half a row is in rides in its group's name."""
    _type(ui, "dali")
    _wait_for_registry(ui)

    names = ui.page.locator(f"{LISTBOX} [role='group']").evaluate_all(
        "groups => groups.map(group => document.getElementById(group.getAttribute('aria-labelledby')).textContent)"
    )
    assert names == [
        "Held: artists",
        "Held: works",
        "Held: themes",
        "Not held: artists",
        "Not held: works",
        "Ask",
        "Search",
    ]
    # Drawn above each half for the eye, and only for the eye.
    halves = ui.page.locator(f"{LISTBOX} .search-suggestions-half")
    assert halves.all_inner_texts() == ["Held", "Not held"]
    assert halves.evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-hidden'))") == ["true", "true"]


class TestWhenWikidataFindsOnlyWhatIsHeld:
    @pytest.fixture
    def registry(self):
        dali = RegistryPerson(qid=DALI, label="Salvador Dalí", born=1904, died=1989)
        persistence = RegistryWorkMatch(
            qid=PERSISTENCE,
            title="The Persistence of Memory",
            sitelinks=48,
            creator=RegistryCreator(qid=DALI, name="Salvador Dalí"),
        )
        return FakeRegistry(people={"salvador": [dali]}, matches={"salvador": [persistence]})

    def test_the_not_held_half_is_one_line_once_wikidata_has_answered(self, ui, matched):
        """Everything Wikidata found is already under Held: no heading over empty kinds, one line, and not before it answers."""
        held = []
        ui.page.route(
            "**/api/registry/search?*",
            lambda route: held.append(route),  # noqa: PLW0108 -- Playwright passes a builtin method two arguments
        )
        _type(ui, "salvador")
        ui.page.wait_for_selector(PENDING)
        assert ui.page.locator(f"{LISTBOX} .search-suggestions-none").count() == 0, "said before Wikidata answered"

        held[0].continue_()
        ui.page.wait_for_selector(PENDING, state="detached")

        assert _options(ui) == [
            "Salvador Dalí — artist",
            "The Persistence of Memory — Salvador Dalí",
            "Ask about “salvador”",
            "All results for “salvador”",
        ]
        assert ui.page.locator(f"{LISTBOX} [aria-labelledby^='suggestions-registry-']").count() == 0
        assert ui.page.locator(f"{LISTBOX} .search-suggestions-none").all_inner_texts() == ["Wikidata has nothing more."]


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
    # Said under Not held, where Wikidata's rows would be, and not as "nothing more".
    assert ui.page.locator(
        f"{LISTBOX} .search-suggestions-half:text-is('Not held') ~ .search-suggestions-registry-note"
    ).is_visible()
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-none").count() == 0
    # Not the library's note: the library was searched.
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-note").count() == 0


def test_two_letters_ask_wikidata_nothing(ui, matched, registry):
    _type(ui, "da")
    ui.page.wait_for_timeout(500)

    assert registry.searched == []
    assert registry.matched == []
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


def test_a_new_query_starts_with_nothing_highlighted_so_enter_opens_the_results(ui, matched):
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

    ui.page.wait_for_function("() => window.location.hash.startsWith('#search?') && window.location.hash.includes('q=dali')")
    ui.page.wait_for_selector("#view h1:text-is('Results for “dali”')")


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
        ui.page.route(
            route_glob, lambda route: held.append(route)  # noqa: PLW0108 -- Playwright passes a builtin method two arguments
        )
        return held

    def test_artists_and_works_are_shown_while_the_topic_search_is_held(self, ui, matched):
        held = self._hold(ui, "**/api/registry/topics?*")
        _type(ui, "dali")

        ui.page.wait_for_selector(f"{LISTBOX} [aria-labelledby='suggestions-registry-works']", timeout=5000)
        listbox = ui.page.get_by_role("listbox", name="Suggestions")
        assert listbox.get_by_role("group", name="Not held: artists", exact=True).get_by_role("option").count() == 1
        assert listbox.get_by_role("group", name="Not held: works", exact=True).get_by_role("option").count() == 2
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

        assert listbox.get_by_role("group", name="Not held: topics", exact=True).get_by_role("option").all_inner_texts() == [
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
        assert "Surrealism" in texts
        assert "Ask about “dali”" in texts
        assert ui.page.locator(ANNOUNCED).inner_text() == "Wikidata: 6 matches."
