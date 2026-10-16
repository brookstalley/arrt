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
    RegistryImageSize,
    RegistryWork,
    RegistryWorkEntry,
)

ROTHKO = "Q160149"
BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
HELD_ROTHKO = "Q20270685"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
UNSIZED = "https://commons.wikimedia.org/wiki/Special:FilePath/Unsized.jpg"
POSTCARD = "https://commons.wikimedia.org/wiki/Special:FilePath/Postcard.jpg"


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
        "height_cm": 117.0,
        "width_cm": 162.0,
    }
    return RegistryWork(**(work | changes))


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: _hunters(),
            "Q7": _hunters(qid="Q7", title='Snow <img src=x onerror="window.pwned=1">', image=None),
            "Q8": _hunters(qid="Q8", title="A Rothko of theirs", creators=(RegistryCreator(qid=ROTHKO, name="Mark Rothko"),)),
            # Measured by Wikidata in one dimension only, with a picture Commons cannot size.
            "Q9": _hunters(qid="Q9", title="Half measured", image=UNSIZED, width_cm=None),
            "Q10": _hunters(qid="Q10", title="A postcard of it", image=POSTCARD, height_cm=None, width_cm=None),
        },
        image_sizes={COMMONS: RegistryImageSize(width=6000, height=4400), POSTCARD: RegistryImageSize(width=300, height=200)},
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


def _fact(ui, term):
    """The value beside `term` in the page's facts, or None when the page states no such fact."""
    terms = ui.page.locator("#view dl.facts dt", has_text=term)
    if terms.count() == 0:
        return None
    return terms.first.locator("xpath=following-sibling::dd[1]").inner_text()


class TestAWorkNotHeld:
    def test_it_shows_what_wikidata_says_and_how_to_find_it(self, ui):
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view h1:text-is('The Hunters in the Snow')")

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

    def test_it_says_how_big_the_work_is_and_how_big_its_picture_is(self, ui):
        """Size among the facts, as a museum label gives it; the picture's pixels and fit under it,
        as a review card gives a scan's."""
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view .picture-size")

        assert _fact(ui, "Size") == "117 × 162 cm (46.1 × 63.8 in)"
        size = ui.page.locator("#view .picture-size")
        # Meeting the minimum is not news, so no badge follows the pixels.
        assert " ".join(size.inner_text().split()) == "6,000 × 4,400 px"
        assert " ".join(ui.page.locator("#view .card-footer").inner_text().split()) == "◐ Not held · Image found"

    def test_a_picture_too_small_for_the_wall_says_so(self, ui):
        ui.open("#work/Q10")
        ui.page.wait_for_selector("#view .picture-size")

        assert " ".join(ui.page.locator("#view .picture-size").inner_text().split()) == "300 × 200 px ▲ below minimum"
        assert _fact(ui, "Size") is None

    def test_with_one_dimension_and_no_picture_size_it_says_only_what_it_knows(self, ui):
        ui.open("#work/Q9")
        ui.page.wait_for_selector("#view h1:text-is('Half measured')")

        assert _fact(ui, "Size") == "117 cm high (46.1 in)"
        assert ui.page.locator("#view .picture-size").count() == 0

    def test_it_says_whose_picture_this_is_and_what_get_asks(self, ui):
        """The picture is Wikidata's choice, not necessarily what a Get will bring back."""
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view button:text-is('Get this work')")

        assert ui.page.locator("#view p.muted", has_text="Wikidata").filter(has_text="every image source").count() == 1

    def test_it_offers_get_rather_than_a_museum_search(self, ui):
        """Ruling 3 replaced the seeded museum search with Get; `test_getting.py` drives it."""
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("#view button:text-is('Get this work')")

        # Neither the old wording nor today's for a search in words: this page gets.
        assert ui.page.locator("#view button:has-text('Search museums'), #view :is(a, button):has-text('Ask about')").count() == 0

    def test_the_rest_of_their_work_follows_without_this_one(self, ui):
        ui.open(f"#work/{HUNTERS}")
        ui.page.wait_for_selector("section[aria-labelledby='more-by'] table")

        assert ui.page.locator("#more-by").inner_text() == "More by Pieter Brueghel the Elder"
        titles = ui.page.locator("section[aria-labelledby='more-by'] tbody td:first-child").all_inner_texts()
        assert titles == ["The Harvesters"]

        ui.page.click("section[aria-labelledby='more-by'] a:has-text('The Harvesters')")
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
        ui.page.click("#view dl.facts a:has-text('Pieter Brueghel the Elder')")

        ui.page.wait_for_selector("#view h1:text-is('Pieter Brueghel the Elder')")
        assert _hash(ui).split("?")[0] == f"#artist/{BRUEGEL}"

    def test_a_held_artist_opens_the_library_page(self, ui, rothko):
        artist, _work = rothko
        ui.open("#work/Q8")
        ui.page.click("#view dl.facts a:has-text('Mark Rothko')")

        ui.page.wait_for_function("(id) => window.location.hash.split('?')[0] === `#artist/${id}`", arg=artist.id)

    def test_registry_text_arrives_as_words_not_markup(self, ui):
        ui.open("#work/Q7")
        ui.page.wait_for_selector("#view h1")

        assert "<img" in ui.page.locator("#view h1").inner_text()
        assert ui.page.locator("#view h1 img").count() == 0
        assert ui.page.evaluate("() => window.pwned") is None
        assert ui.page.locator("#view .card-footer").inner_text().strip().endswith("Not held")

    def test_an_item_wikidata_does_not_have_says_so(self, ui):
        ui.open("#work/Q999999")
        ui.page.wait_for_selector("#view h1:text-is('Wikidata has no such work')")

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
        ui.page.wait_for_selector(f"#view h1:text-is('{work.title}')")
        ui.page.go_back()
        ui.page.wait_for_function("() => window.location.hash.startsWith('#collection')")

    def test_their_work_on_the_artist_page_opens_the_unheld_ones_here(self, ui):
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.click("section[aria-labelledby='their-work'] a:has-text('The Harvesters')")

        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#work/${qid}`", arg=HARVESTERS)


class TestAnArtistNotHeld:
    def test_it_shows_the_registry_half_and_says_nothing_is_held(self, ui):
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.wait_for_selector("#view h1:text-is('Pieter Brueghel the Elder')")
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
        ui.page.wait_for_selector("#view h2:has-text('In your library')")

    def test_an_outage_says_so_under_the_header(self, ui, registry):
        registry.failing = True
        ui.open(f"#artist/{BRUEGEL}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

        assert "could not be asked" in ui.page.locator("section[aria-labelledby='their-work'] p.note").inner_text()
