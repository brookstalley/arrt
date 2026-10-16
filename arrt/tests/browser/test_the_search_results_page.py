"""The search results page, in a real browser against a real server.

Ruling 2: one page lists what a few words find in the library and in Wikidata.
The owner's ruling of 2026-10-06 groups it: **Held** then **Not held**, each with
its artists, works and topics, a group with nothing in it one line; and Enter in
the search box opens it, as the dropdown's last row does. When the words name
one artist, that artist leads. The registry is a fake installed where the entry
point builds Wikidata's.
"""

import json

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
        # "giraffe" is the owner's case: nothing held matches, and Wikidata knows the work.
        matches={"dali": _dali_works(), "salvador dali": _dali_works()[:1], "giraffe": _dali_works()[1:2]},
    )


@pytest.fixture
def matched(services, seeded_service):
    """The seeded Dalí and his work, matched to the QIDs the fake registry finds."""
    dali = next(artist for artist in seeded_service.list_artists() if artist.name == "Salvador Dalí")
    work = next(e.artwork for e in seeded_service.list_artworks().entries if e.artwork.title == "The Persistence of Memory")
    services.identity.set_artist_identity(dali.id, DALI)
    services.identity.set_work_identity(work.id, PERSISTENCE)
    return dali, work


def _results(ui, query, extra=""):
    ui.open(f"#search?q={query}{extra}")
    ui.page.wait_for_selector("#view h1:has-text('Results for')")


def _answered(ui):
    # The Not held group's own note, and only once it is drawn: read before the
    # page is, a bare `#view p[aria-live]` is null, or the page before's.
    ui.page.wait_for_function(
        "() => { const note = document.querySelector(\"section[aria-labelledby='results-not-held'] p[aria-live]\");"
        " return note !== null && !note.textContent.startsWith('Asking'); }"
    )


def _rows(ui, half, kind):
    """One kind's rows in one group, `half` being `held` or `not-held`."""
    return [
        " ".join(text.split())
        for text in ui.page.locator(f"section[aria-labelledby='results-{half}-{kind}'] li").all_inner_texts()
    ]


def _group(ui, half):
    return ui.page.locator(f"section[aria-labelledby='results-{half}']")


def _note(ui):
    """The Not held group's one line. Scoped to the group since the page's
    selection bar (`core/selecting.js`) carries live regions of its own."""
    return _group(ui, "not-held").locator("p[aria-live]")


def test_the_dropdowns_last_row_opens_it(ui, matched):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.page.click("#search")
    ui.page.keyboard.type("dali")
    ui.page.click("#search-suggestions [role='option']:has-text('All results for “dali”')")

    ui.page.wait_for_selector("#view h1:text-is('Results for “dali”')")
    assert ui.page.evaluate("() => window.location.hash").startswith("#search?")
    # Contextual: it returns to the page it was opened from, not to Artworks.
    assert "from=walls" in ui.page.evaluate("() => window.location.hash")
    assert ui.page.locator("#view p a").first.inner_text() == "← Walls"


def test_enter_in_the_search_box_opens_it_and_it_returns_where_it_was_opened(ui, matched):
    """The owner's ruling of 2026-10-06: Enter opens the results page, not Artworks."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.page.click("#search")
    ui.page.keyboard.type("dali")
    ui.page.wait_for_selector("#search-suggestions:not([hidden]) [role='option']")
    assert ui.page.get_attribute("#search", "aria-activedescendant") is None, "nothing highlighted, or Enter opens that row"
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h1:text-is('Results for “dali”')")
    hash_now = ui.page.evaluate("() => window.location.hash")
    assert hash_now.startswith("#search?")
    assert "q=dali" in hash_now
    assert "from=walls" in hash_now
    assert not ui.page.locator("#search-suggestions").is_visible()
    ui.page.click("#view p a:text-is('← Walls')")
    ui.page.wait_for_selector("#view h1:has-text('Walls')")


def test_held_then_not_held_marked_only_where_the_group_does_not_say_and_nothing_twice(ui, matched):
    _results(ui, "dali")
    _answered(ui)

    assert ui.page.locator("#view h2").all_inner_texts() == ["Held", "Not held"]
    assert _rows(ui, "held", "artists") == ["Salvador Dalí 1904–1989"]
    assert _rows(ui, "held", "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert _rows(ui, "not-held", "artists") == [
        "Gala Dalí 1894–1982",
        "Ana María Dalí 1908–1989",
        "Dalibor Chatrný 1925–2012",
    ]
    assert _rows(ui, "not-held", "works") == [
        "The Burning Giraffe — Salvador Dalí ◐ Image found",
        "Crucifixion — Salvador Dalí ○ No image known",
    ]
    # Inside a group a mark says only what the heading does not (the owner,
    # 2026-10-06): no artist row is marked, and no row says "Not held" again.
    assert _group(ui, "held").locator(".results-kind:has(h3:has-text('Artists')) .state-mark").count() == 0
    assert _group(ui, "not-held").locator(".results-kind:has(h3:has-text('Artists')) .state-mark").count() == 0
    assert "Not held" not in " ".join(_group(ui, "not-held").locator(".results-list").all_inner_texts())
    # Each kind is headed inside its group, and the heading carries the group's
    # name, unseen, so a reader hears which half a kind is in.
    assert _group(ui, "held").locator("h3").evaluate_all("nodes => nodes.map((n) => n.textContent)") == [
        "Held: Artists",
        "Held: Works",
    ]
    # The row's title is the way in, so its mark is not a second button to the same work.
    assert ui.page.locator("#view .results-list button.state-mark").count() == 0
    # Two artists carry "dali": no single one leads.
    assert ui.page.locator("#results-top").count() == 0
    # The switch that narrowed the page is gone: the groups are the narrowing.
    assert ui.page.locator("#view [role='group'][aria-label='Show']").count() == 0
    assert ui.page.locator("#view button[aria-pressed]").count() == 0


def test_nothing_held_is_one_line_and_wikidatas_works_are_under_not_held(ui, matched):
    """The owner's case: a work not held, which Artworks could never show."""
    _results(ui, "giraffe")
    _answered(ui)

    held = _group(ui, "held")
    assert " ".join(held.inner_text().split()) == "Held Nothing you hold matches."
    assert held.locator(".results-none").is_visible()
    assert _rows(ui, "not-held", "works") == ["The Burning Giraffe — Salvador Dalí ◐ Image found"]
    # No kind says it is empty, in either group.
    text = ui.page.locator("#view").inner_text()
    assert "No artists" not in text
    assert "No works" not in text
    # And the work can be got from here.
    assert _group(ui, "not-held").locator("li input[type='checkbox']").count() == 1


def test_something_held_hides_the_nothing_held_line(ui, matched):
    """The paired negative: the one line is for an empty group only."""
    _results(ui, "dali")
    _answered(ui)

    assert ui.page.locator("#view .results-none").is_hidden()


def test_a_query_matching_only_held_things_shows_nothing_twice_and_says_so(ui, matched):
    _results(ui, "salvador%20dali")
    _answered(ui)

    assert _rows(ui, "held", "artists") == ["Salvador Dalí 1904–1989"]
    assert _rows(ui, "held", "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert _group(ui, "not-held").locator("li").count() == 0
    assert _note(ui).inner_text() == "Wikidata has nothing more."
    # Wikidata found something, all of it held: no Ask, which is for finding nothing.
    assert ui.page.locator("#view a:has-text('Ask about')").count() == 0


def test_a_held_match_the_librarys_rows_do_not_show_is_under_held(ui, matched):
    """Wikidata can find a held work the library's own search did not: it is held, so it is not under Not held."""
    _dali, work = matched
    ui.page.route(
        "**/api/works?q=*",
        lambda route: route.fulfill(status=200, content_type="application/json", body='{"works": [], "total": 0}'),
    )
    _results(ui, "dali")
    _answered(ui)

    assert _rows(ui, "held", "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert "The Persistence of Memory" not in " ".join(_rows(ui, "not-held", "works"))
    ui.page.click("section[aria-labelledby='results-held-works'] a:has-text('The Persistence of Memory')")
    ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#work/${id}`)", arg=work.id)


def test_an_old_view_in_the_address_is_ignored_and_both_groups_show(ui, matched, registry):
    """`view=library` once hid Wikidata's half and asked it nothing."""
    _results(ui, "dali", "&view=library")
    _answered(ui)

    assert _rows(ui, "held", "artists") == ["Salvador Dalí 1904–1989"]
    assert len(_rows(ui, "not-held", "works")) == 2
    assert registry.searched, "Wikidata was not asked, so the old view still narrows the page"


def test_words_naming_one_artist_put_them_first(ui, matched):
    dali, _work = matched
    _results(ui, "salvador%20dali")
    _answered(ui)

    top = ui.page.locator("section[aria-labelledby='results-top']")
    assert " ".join(top.locator("p").inner_text().split()) == "Salvador Dalí 1904–1989 ● In your library"
    top.locator("a").click()
    ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=dali.id)


def test_an_unheld_result_opens_its_page_here(ui, matched):
    _results(ui, "dali")
    _answered(ui)
    ui.page.click("section[aria-labelledby='results-not-held-works'] a:has-text('The Burning Giraffe')")

    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=GIRAFFE)


def test_when_wikidata_has_nothing_it_says_so_and_offers_museums(ui, seeded_service):
    _results(ui, "vermeer")
    _answered(ui)

    assert _note(ui).inner_text() == "Wikidata has nothing for “vermeer”."
    assert _group(ui, "held").locator(".results-none").is_visible()
    ui.page.click("#view a:has-text('Ask about “vermeer”')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#discover')")


def test_an_outage_leaves_the_held_group_and_says_so(ui, matched, registry):
    registry.failing = True
    _results(ui, "dali")
    _answered(ui)

    assert _note(ui).inner_text() == "Wikidata could not be searched just now."
    # Said in the Not held group, where Wikidata's rows would be.
    assert _group(ui, "not-held").locator("p[aria-live]").count() == 1
    assert _rows(ui, "held", "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert _rows(ui, "held", "artists") == ["Salvador Dalí 1904–1989"]
    assert _group(ui, "not-held").locator("li").count() == 0


def test_registry_text_arrives_as_words_not_markup(ui, seeded_service):
    _results(ui, "markup")
    _answered(ui)

    assert "<img" in ui.page.locator("section[aria-labelledby='results-not-held-artists']").inner_text()
    assert ui.page.locator("section[aria-labelledby='results-not-held-artists'] li img").count() == 0
    assert ui.page.evaluate("() => window.pwned") is None


def test_the_librarys_matches_open_in_artworks(ui, matched):
    _results(ui, "dali")
    ui.page.click("section[aria-labelledby='results-held-works'] a:has-text('Open in Artworks')")

    ui.page.wait_for_function("() => window.location.hash === '#collection?q=dali'")


def test_more_library_matches_than_listed_are_all_one_click_away_in_artworks(ui, matched):
    """The page lists the first fifty; Artworks holds the rest and the tools to act on them."""

    def more_than_listed(route):
        answer = route.fetch()
        body = answer.json()
        body["total"] = 120
        route.fulfill(response=answer, body=json.dumps(body))

    ui.page.route("**/api/works?q=*", more_than_listed)
    _results(ui, "dali")

    works = ui.page.locator("section[aria-labelledby='results-held-works']")
    works.locator("a:text-is('All 120 in Artworks')").wait_for()
    assert "Your library has 120 matching works; the first 1 are here." in works.inner_text()
    works.locator("a:text-is('All 120 in Artworks')").click()
    ui.page.wait_for_function("() => window.location.hash === '#collection?q=dali'")


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_it_says_only_the_library_was_searched(self, ui, seeded_service):
        _results(ui, "dali")
        _answered(ui)

        assert "only your library is searched" in _note(ui).inner_text()
        assert _rows(ui, "held", "artists") == ["Salvador Dalí 1904–1989"]


def test_a_failed_library_search_is_an_error_not_an_empty_page(ui, seeded_service):
    ui.page.route(
        "**/api/works?q=*", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}')
    )
    ui.open("#search?q=dali")

    ui.page.wait_for_selector("#error:not([hidden])")
    # The library's own words, which say what failed, not a generic apology.
    assert ui.page.locator("#error").inner_text() == "boom"


def test_each_kinds_region_names_its_half(ui, matched):
    """A screen reader lists regions by name; "Artists" twice says nothing of which half."""
    _results(ui, "dali")
    _answered(ui)

    assert ui.page.get_by_role("region", name="Held: Artists", exact=True).count() == 1
    assert ui.page.get_by_role("region", name="Held: Works", exact=True).count() == 1
    assert ui.page.get_by_role("region", name="Not held: Works", exact=True).count() == 1
    assert ui.page.get_by_role("region", name="Artists", exact=True).count() == 0


def test_a_failed_topic_listing_leaves_the_held_artists_and_works_standing(ui, matched):
    ui.page.route(
        "**/api/topics", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}')
    )
    _results(ui, "dali")
    _answered(ui)

    assert ui.page.locator("#error").is_hidden()
    assert _rows(ui, "held", "works") == ["The Persistence of Memory — Salvador Dalí ● Held"]
    assert _group(ui, "held").locator(".results-topics-failed").inner_text() == "Your topics could not be listed just now."


def test_the_topic_failure_line_is_absent_when_topics_answer(ui, matched):
    _results(ui, "dali")
    _answered(ui)

    assert _group(ui, "held").locator(".results-topics-failed").count() == 0


def test_too_few_letters_says_why_wikidata_was_not_asked(ui, seeded_service, registry):
    _results(ui, "da")
    _answered(ui)

    assert _note(ui).inner_text() == "Wikidata is searched from three letters."
    assert registry.searched == []
