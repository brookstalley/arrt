"""Pages for works and artists the library does not hold, in a real browser against a real server.

Ruling 2 puts the library and the registry in one world: a work or artist that
Wikidata knows has a page here, at `#work/Q…` or `#artist/Q…`, and the library's
own page replaces it, in place, when the library holds them. The registry is a
fake installed where the entry point builds Wikidata's.

**Registry text is written by anyone**, so a title carrying markup is shown to
arrive as words.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryWork,
    RegistryWorkEntry,
)

ROTHKO = "Q160149"
BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
HELD_ROTHKO = "Q20270685"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"


def _hunters(**changes):
    work = {
        "qid": HUNTERS,
        "title": "The Hunters in the Snow",
        "sitelinks": 39,
        "year": 1565,
        "image": COMMONS,
        "creators": (RegistryCreator(qid=BRUEGEL, name="Pieter Brueghel the Elder"),),
        "media": ("oil paint", "panel"),
        "holders": (RegistryHolder(qid="Q95569", name="Kunsthistorisches Museum", inventory="GG_1838"),),
    }
    return RegistryWork(**(work | changes))


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: _hunters(),
            "Q7": _hunters(qid="Q7", title='Snow <img src=x onerror="window.pwned=1">', image=None),
            "Q8": _hunters(qid="Q8", title="A Rothko of theirs", creators=(RegistryCreator(qid=ROTHKO, name="Mark Rothko"),)),
        },
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name="Pieter Brueghel the Elder",
                born=1525,
                died=1569,
                description="Flemish painter",
                movements=("Northern Renaissance",),
                works=(
                    RegistryWorkEntry(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, year=1565, image=COMMONS),
                    RegistryWorkEntry(qid=HARVESTERS, title="The Harvesters", sitelinks=25, year=1565),
                ),
                works_total=125,
            ),
            ROTHKO: RegistryArtist(qid=ROTHKO, name="Mark Rothko"),
        },
    )


@pytest.fixture
def rothko(services, service):
    """Rothko in the library, matched, with one held work carrying a QID."""
    artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    work = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=artist.id, date_created="1953")
    services.identity.set_work_identity(work.id, HELD_ROTHKO)
    services.identity.set_artist_identity(artist.id, ROTHKO)
    return artist, work


def _hash(ui):
    return ui.page.evaluate("() => window.location.hash")


class TestAWorkNotHeld:
    def test_it_shows_what_wikidata_says_and_how_to_find_it(self, ui):
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view h2:text-is('The Hunters in the Snow')")

        facts = ui.page.locator("#view dl.facts").inner_text()
        assert "Pieter Brueghel the Elder" in facts
        assert "1565" in facts
        assert "oil paint, panel" in facts
        assert "Kunsthistorisches Museum (GG_1838)" in facts
        assert " ".join(ui.page.locator("#view .card-footer").inner_text().split()) == "◐ Not held · Image found"
        image = ui.page.locator("#view img.detail-image")
        assert image.get_attribute("src") == f"{COMMONS}?width=1200"
        assert image.get_attribute("referrerpolicy") == "no-referrer"
        assert ui.page.locator(f"#view a[href='https://www.wikidata.org/wiki/{HUNTERS}']").count() == 1

    def test_it_offers_get_rather_than_a_museum_search(self, ui):
        """Ruling 3 replaced the seeded museum search with Get; `test_getting.py` drives it."""
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view button:text-is('Get this work')")

        # Neither the old wording nor today's for a search in words: this page gets.
        assert ui.page.locator("#view button:has-text('Search museums'), #view button:has-text('Ask about')").count() == 0

    def test_the_rest_of_their_work_follows_without_this_one(self, ui):
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("section[aria-labelledby='more-by'] table")

        assert ui.page.locator("#more-by").inner_text() == "More by Pieter Brueghel the Elder"
        titles = ui.page.locator("section[aria-labelledby='more-by'] tbody td:first-child").all_inner_texts()
        assert titles == ["The Harvesters"]

        ui.page.click("section[aria-labelledby='more-by'] button:has-text('The Harvesters')")
        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=HARVESTERS)

    def test_a_wanted_work_says_so_on_its_page_and_in_the_rest_of_their_work(self, ui, want_item):
        want_item(HUNTERS, "The Hunters in the Snow")
        want_item(HARVESTERS, "The Harvesters")
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("section[aria-labelledby='more-by'] table")

        assert " ".join(ui.page.locator("#view .card-footer").inner_text().split()) == "◑ Wanted"
        row = ui.page.locator("section[aria-labelledby='more-by'] tbody tr", has_text="The Harvesters")
        assert " ".join(row.locator(".state-mark").inner_text().split()) == "◑ Wanted"

    def test_its_unheld_artist_opens_their_page_here(self, ui):
        ui.open(f"#work/{HUNTERS}")
        ui.page.click("#view dl.facts button:has-text('Pieter Brueghel the Elder')")

        ui.page.wait_for_selector("#view h2:text-is('Pieter Brueghel the Elder')")
        assert _hash(ui).split("?")[0] == f"#artist/{BRUEGEL}"

    def test_a_held_artist_opens_the_library_page(self, ui, rothko):
        artist, _work = rothko
        ui.open("#work/Q8")
        ui.page.click("#view dl.facts button:has-text('Mark Rothko')")

        ui.page.wait_for_function("(id) => window.location.hash.split('?')[0] === `#artist/${id}`", arg=artist.id)

    def test_registry_text_arrives_as_words_not_markup(self, ui):
        ui.open("#work/Q7")
        ui.page.wait_for_selector("#view h2")

        assert "<img" in ui.page.locator("#view h2").inner_text()
        assert ui.page.locator("#view h2 img").count() == 0
        assert ui.page.evaluate("() => window.pwned") is None
        assert ui.page.locator("#view .card-footer").inner_text().strip().endswith("Not held")

    def test_an_item_wikidata_does_not_have_says_so(self, ui):
        ui.open("#work/Q999999")
        ui.page.wait_for_selector("#view h2:text-is('Wikidata has no such work')")

        assert "Q999999" in ui.page.locator("#view p.note").inner_text()

    def test_an_outage_says_so(self, ui, registry):
        registry.failing = True
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view p.note")

        assert "could not be asked" in ui.page.locator("#view p.note").inner_text()


class TestAWorkHeld:
    def test_its_qid_is_replaced_by_the_librarys_page_and_back_skips_it(self, ui, rothko):
        _artist, work = rothko
        ui.open("#collection")
        ui.page.evaluate("(qid) => { window.location.hash = `#work/${qid}`; }", HELD_ROTHKO)

        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#work/${id}`)", arg=work.id)
        ui.page.wait_for_selector(f"#view h2:text-is('{work.title}')")
        ui.page.go_back()
        ui.page.wait_for_function("() => window.location.hash.startsWith('#collection')")

    def test_their_work_on_the_artist_page_opens_the_unheld_ones_here(self, ui):
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.click("section[aria-labelledby='their-work'] button:has-text('The Harvesters')")

        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=HARVESTERS)


class TestAnArtistNotHeld:
    def test_it_shows_the_registry_half_and_says_nothing_is_held(self, ui):
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.wait_for_selector("#view h2:text-is('Pieter Brueghel the Elder')")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")

        assert "1525–1569" in ui.page.locator("#view dl.facts").inner_text()
        assert ui.page.locator("#view p.note:has-text('Nothing of theirs is in your library.')").count() == 1
        assert "Flemish painter" in ui.page.locator("#view").inner_text()
        # The second column: the first is the Get tick box.
        titles = ui.page.locator("section[aria-labelledby='their-work'] tbody td:nth-child(2)").all_inner_texts()
        assert titles == ["The Hunters in the Snow", "The Harvesters"]

    def test_it_says_where_held_work_is_filed_rather_than_that_none_is_held(self, ui, services, service):
        """A library work Wikidata lists under this artist, filed under a library artist with no item."""
        unmatched = service.add_artist(name="Bruegel, Pieter")
        work = service.add_artwork(title="The Hunters in the Snow", artist_id=unmatched.id)
        services.identity.set_work_identity(work.id, HUNTERS)
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")

        assert ui.page.locator("#view p.note").first.inner_text().startswith("Some of their work is in your library")
        assert ui.page.locator("#view p.note:has-text('Nothing of theirs')").count() == 0

    def test_a_held_artists_qid_is_replaced_by_their_library_page(self, ui, rothko):
        artist, _work = rothko
        ui.open(f"#artist/{ROTHKO}")

        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=artist.id)
        ui.page.wait_for_selector("#view h3:has-text('In your library')")

    def test_an_outage_says_so_under_the_header(self, ui, registry):
        registry.failing = True
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

        assert "could not be asked" in ui.page.locator("section[aria-labelledby='their-work'] p.note").inner_text()
