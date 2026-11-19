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
from playwright.sync_api import expect

from arrt.library.registry import RegistryCreator, RegistryPerson, RegistryWorkMatch

DALI = "Q5577"
PERSISTENCE = "Q25729"
GIRAFFE = "Q1062364"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/G.jpg"

#: The seeded Persistence of Memory, which has no master: under *Held*, said
#: once by the heading and never again on the row (audit 6, finding 14), and
#: its picture's place saying it has none, as its own page does. Until
#: 2026-11-19 the row ended "● Held" and said nothing of the picture.
HELD_WITHOUT_A_PICTURE = ["No picture The Persistence of Memory — Salvador Dalí"]


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
    """One kind's rows in one group, `half` being `held` or `not-held`. `to_have_text([...])` folds a row's breaks."""
    return ui.page.locator(f"section[aria-labelledby='results-{half}-{kind}'] li")


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
    expect(ui.page.locator("#view p a").first).to_have_text("← Walls", use_inner_text=True)


def test_enter_in_the_search_box_opens_it_and_it_returns_where_it_was_opened(ui, matched):
    """The owner's ruling of 2026-10-06: Enter opens the results page, not Artworks."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.page.click("#search")
    ui.page.keyboard.type("dali")
    ui.page.wait_for_selector("#search-suggestions:not([hidden]) [role='option']")
    # Anchored by the dropdown's options, which have just appeared.
    expect(ui.page.locator("#search"), "nothing highlighted, or Enter opens that row").not_to_have_attribute(
        "aria-activedescendant"
    )
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_selector("#view h1:text-is('Results for “dali”')")
    hash_now = ui.page.evaluate("() => window.location.hash")
    assert hash_now.startswith("#search?")
    assert "q=dali" in hash_now
    assert "from=walls" in hash_now
    expect(ui.page.locator("#search-suggestions")).to_be_hidden()
    ui.page.click("#view p a:text-is('← Walls')")
    ui.page.wait_for_selector("#view h1:has-text('Walls')")


def test_held_then_not_held_marked_only_where_the_group_does_not_say_and_nothing_twice(ui, matched):
    _results(ui, "dali")
    _answered(ui)

    expect(ui.page.locator("#view h2")).to_have_text(["Held", "Not held"], use_inner_text=True)
    expect(_rows(ui, "held", "artists")).to_have_text(["Salvador Dalí 1904–1989"], use_inner_text=True)
    expect(_rows(ui, "held", "works")).to_have_text(HELD_WITHOUT_A_PICTURE, use_inner_text=True)
    expect(_rows(ui, "not-held", "artists")).to_have_text(
        [
            "Gala Dalí 1894–1982",
            "Ana María Dalí 1908–1989",
            "Dalibor Chatrný 1925–2012",
        ],
        use_inner_text=True,
    )
    expect(_rows(ui, "not-held", "works")).to_have_text(
        [
            "The Burning Giraffe — Salvador Dalí ◐ Image found",
            "Crucifixion — Salvador Dalí ○ No image known",
        ],
        use_inner_text=True,
    )
    # Inside a group a mark says only what the heading does not (the owner,
    # 2026-10-06): no artist row is marked, and no row says "Not held" again.
    # (The rows above are drawn, so each absence below is of a settled page.)
    expect(_group(ui, "held").locator(".results-kind:has(h3:has-text('Artists')) .state-mark")).to_have_count(0)
    expect(_group(ui, "not-held").locator(".results-kind:has(h3:has-text('Artists')) .state-mark")).to_have_count(0)
    expect(_group(ui, "not-held").locator(".results-list")).not_to_contain_text(["Not held"], use_inner_text=True)
    # Each kind is headed inside its group, and the heading carries the group's
    # name, unseen, so a reader hears which half a kind is in. (Its text content,
    # which includes the unseen words: no `use_inner_text`.)
    expect(_group(ui, "held").locator("h3")).to_have_text(["Held: Artists", "Held: Works"])
    # The row's title is the way in, so its mark is not a second button to the same work.
    expect(ui.page.locator("#view .results-list button.state-mark")).to_have_count(0)
    # Two artists carry "dali": no single one leads.
    expect(ui.page.locator("#results-top")).to_have_count(0)
    # The switch that narrowed the page is gone: the groups are the narrowing.
    expect(ui.page.locator("#view [role='group'][aria-label='Show']")).to_have_count(0)
    expect(ui.page.locator("#view button[aria-pressed]")).to_have_count(0)


def test_held_is_said_once_by_its_group_and_a_held_row_says_whether_it_has_a_picture(ui, service, work_with_an_image):
    """Audit 6, finding 14. Two held works the words find, one with its master on
    disk and one without: the Held group's heading is the only "Held" in it, and
    only the work with nothing to show says *No picture*, in its picture's place.
    The pictured one is the case that keeps the placeholder from being drawn on
    every row; the other is the case that keeps it from being drawn on none."""
    work_with_an_image("Study in Blue")
    service.add_artwork(title="Study in Grey", date_created="1901")

    _results(ui, "study")
    _answered(ui)

    held = _group(ui, "held")
    pictured = held.locator("li:has(.row-title:text-is('Study in Blue'))")
    bare = held.locator("li:has(.row-title:text-is('Study in Grey'))")
    expect(pictured.locator(".work-pic-held img")).to_have_count(1)
    expect(bare.locator(".work-pic .no-picture")).to_have_text("No picture")
    expect(pictured.locator(".no-picture")).to_have_count(0)
    # "Held" once in the group: its heading (the kinds' unseen prefixes aside).
    expect(held.locator(".results-list")).not_to_contain_text("Held")
    expect(held.locator(".badge-held")).to_have_count(0)
    # The page's count, in its line of facts above the toolbar, as on every list.
    expect(ui.page.locator("#view .page-facts")).to_have_text("2 held: 2 works")


def test_nothing_held_is_one_line_and_wikidatas_works_are_under_not_held(ui, matched):
    """The owner's case: a work not held, which Artworks could never show."""
    _results(ui, "giraffe")
    _answered(ui)

    held = _group(ui, "held")
    expect(held).to_have_text("Held Nothing you hold matches.", use_inner_text=True)
    expect(held.locator(".results-none")).to_be_visible()
    expect(_rows(ui, "not-held", "works")).to_have_text(
        ["The Burning Giraffe — Salvador Dalí ◐ Image found"], use_inner_text=True
    )
    # No kind says it is empty, in either group.
    expect(ui.view).not_to_contain_text("No artists", use_inner_text=True)
    expect(ui.view).not_to_contain_text("No works", use_inner_text=True)
    # And the work can be got from here.
    expect(_group(ui, "not-held").locator("li input[type='checkbox']")).to_have_count(1)


def test_something_held_hides_the_nothing_held_line(ui, matched):
    """The paired negative: the one line is for an empty group only."""
    _results(ui, "dali")
    _answered(ui)

    expect(ui.page.locator("#view .results-none")).to_be_hidden()


def test_a_query_matching_only_held_things_shows_nothing_twice_and_says_so(ui, matched):
    _results(ui, "salvador%20dali")
    _answered(ui)

    expect(_rows(ui, "held", "artists")).to_have_text(["Salvador Dalí 1904–1989"], use_inner_text=True)
    expect(_rows(ui, "held", "works")).to_have_text(HELD_WITHOUT_A_PICTURE, use_inner_text=True)
    expect(_note(ui)).to_have_text("Wikidata has nothing more.", use_inner_text=True)
    expect(_group(ui, "not-held").locator("li")).to_have_count(0)
    # Wikidata found something, all of it held: no Ask, which is for finding nothing.
    expect(ui.page.locator("#view a:has-text('Ask about')")).to_have_count(0)


def test_a_held_match_the_librarys_rows_do_not_show_is_under_held(ui, matched):
    """Wikidata can find a held work the library's own search did not: it is held, so it is not under Not held."""
    _dali, work = matched
    ui.page.route(
        "**/api/works?q=*",
        lambda route: route.fulfill(status=200, content_type="application/json", body='{"works": [], "total": 0}'),
    )
    _results(ui, "dali")
    _answered(ui)

    # Held with no master, so it says *No picture* in its picture's place, as the
    # library's own rows do (audit 6 finding 14). Until 2026-11-19 a row folded
    # in from Wikidata's results asked for a thumbnail the server refuses, and
    # the picture's frame went with the failed load, leaving the title alone.
    expect(_rows(ui, "held", "works")).to_have_text(["No picture The Persistence of Memory — Salvador Dalí"], use_inner_text=True)
    expect(_rows(ui, "not-held", "works")).not_to_contain_text(["The Persistence of Memory"], use_inner_text=True)
    ui.page.click("section[aria-labelledby='results-held-works'] a:has-text('The Persistence of Memory')")
    ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#work/${id}`)", arg=work.id)


def test_an_old_view_in_the_address_is_ignored_and_both_groups_show(ui, matched, registry):
    """`view=library` once hid Wikidata's half and asked it nothing."""
    _results(ui, "dali", "&view=library")
    _answered(ui)

    expect(_rows(ui, "held", "artists")).to_have_text(["Salvador Dalí 1904–1989"], use_inner_text=True)
    expect(_rows(ui, "not-held", "works")).to_have_count(2)
    assert registry.searched, "Wikidata was not asked, so the old view still narrows the page"


def test_words_naming_one_artist_put_them_first(ui, matched):
    dali, _work = matched
    _results(ui, "salvador%20dali")
    _answered(ui)

    top = ui.page.locator("section[aria-labelledby='results-top']")
    expect(top.locator("p")).to_have_text("Salvador Dalí 1904–1989 ● In your library", use_inner_text=True)
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

    expect(_note(ui)).to_have_text("Wikidata has nothing for “vermeer”.", use_inner_text=True)
    expect(_group(ui, "held").locator(".results-none")).to_be_visible()
    ui.page.click("#view a:has-text('Ask about “vermeer”')")
    ui.page.wait_for_function("() => window.location.hash.startsWith('#discover')")


def test_an_outage_leaves_the_held_group_and_says_so(ui, matched, registry):
    registry.failing = True
    _results(ui, "dali")
    _answered(ui)

    expect(_note(ui)).to_have_text("Wikidata could not be searched just now.", use_inner_text=True)
    # Said in the Not held group, where Wikidata's rows would be.
    expect(_group(ui, "not-held").locator("p[aria-live]")).to_have_count(1)
    expect(_rows(ui, "held", "works")).to_have_text(HELD_WITHOUT_A_PICTURE, use_inner_text=True)
    expect(_rows(ui, "held", "artists")).to_have_text(["Salvador Dalí 1904–1989"], use_inner_text=True)
    expect(_group(ui, "not-held").locator("li")).to_have_count(0)


def test_registry_text_arrives_as_words_not_markup(ui, seeded_service):
    _results(ui, "markup")
    _answered(ui)

    expect(ui.page.locator("section[aria-labelledby='results-not-held-artists']")).to_contain_text("<img", use_inner_text=True)
    expect(ui.page.locator("section[aria-labelledby='results-not-held-artists'] li img")).to_have_count(0)
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
    expect(works).to_contain_text("Your library has 120 matching works; the first 1 are here.", use_inner_text=True)
    works.locator("a:text-is('All 120 in Artworks')").click()
    ui.page.wait_for_function("() => window.location.hash === '#collection?q=dali'")


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_it_says_only_the_library_was_searched(self, ui, seeded_service):
        _results(ui, "dali")
        _answered(ui)

        expect(_note(ui)).to_contain_text("only your library is searched", use_inner_text=True)
        expect(_rows(ui, "held", "artists")).to_have_text(["Salvador Dalí 1904–1989"], use_inner_text=True)


def test_a_failed_library_search_is_an_error_not_an_empty_page(ui, seeded_service):
    ui.page.route(
        "**/api/works?q=*", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}')
    )
    ui.open("#search?q=dali")

    ui.page.wait_for_selector("#error:not([hidden])")
    # The library's own words, which say what failed, not a generic apology.
    expect(ui.page.locator("#error")).to_have_text("boom", use_inner_text=True)


def test_each_kinds_region_names_its_half(ui, matched):
    """A screen reader lists regions by name; "Artists" twice says nothing of which half."""
    _results(ui, "dali")
    _answered(ui)

    expect(ui.page.get_by_role("region", name="Held: Artists", exact=True)).to_have_count(1)
    expect(ui.page.get_by_role("region", name="Held: Works", exact=True)).to_have_count(1)
    expect(ui.page.get_by_role("region", name="Not held: Works", exact=True)).to_have_count(1)
    expect(ui.page.get_by_role("region", name="Artists", exact=True)).to_have_count(0)


def test_a_failed_topic_listing_leaves_the_held_artists_and_works_standing(ui, matched):
    ui.page.route(
        "**/api/topics", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "boom"}')
    )
    _results(ui, "dali")
    _answered(ui)

    expect(_rows(ui, "held", "works")).to_have_text(HELD_WITHOUT_A_PICTURE, use_inner_text=True)
    expect(_group(ui, "held").locator(".results-topics-failed")).to_have_text(
        "Your topics could not be listed just now.", use_inner_text=True
    )
    # After the page's own words are in, so a banner raised along the way would be up.
    expect(ui.page.locator("#error")).to_be_hidden()


def test_the_topic_failure_line_is_absent_when_topics_answer(ui, matched):
    _results(ui, "dali")
    _answered(ui)

    expect(_group(ui, "held").locator(".results-topics-failed")).to_have_count(0)


def test_too_few_letters_says_why_wikidata_was_not_asked(ui, seeded_service, registry):
    _results(ui, "da")
    _answered(ui)

    expect(_note(ui)).to_have_text("Wikidata is searched from three letters.", use_inner_text=True)
    assert registry.searched == []
