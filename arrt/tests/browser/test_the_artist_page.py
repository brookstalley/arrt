"""Library › Artists and the Artist page, in a real browser against a real server.

The hub (ruling 4): who the artist is, what the library holds of theirs, what
Wikidata lists with the held ones marked, and which collections hold their work.
The registry is a fake installed where the entry point builds Wikidata's, so
every state its half can be in is reachable: answering, down, and silent about
an artist the library has not matched.

**Registry text is written by anyone**, so one test hands the page a description
carrying markup and asserts it arrives as words, not as an element.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry  # noqa: E402  (after the skip guard)

from arrt.library.registry import RegistryArtist, RegistryHolding, RegistryWorkEntry  # noqa: E402

ROTHKO = "Q160149"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Rothko%20chapel.jpg"


@pytest.fixture
def registry():
    return FakeRegistry(
        artists={
            ROTHKO: RegistryArtist(
                qid=ROTHKO,
                description='American painter <img src=x onerror="window.pwned=1">',
                movements=("abstract expressionism",),
                works=(
                    RegistryWorkEntry(qid="Q2956755", title="Rothko Chapel", sitelinks=13, year=1971, image=COMMONS),
                    RegistryWorkEntry(qid="Q17038023", title="No 1", sitelinks=6, year=1954),
                    # What the label service returns for an item with no label it can read.
                    RegistryWorkEntry(qid="Q16682090", title="Q16682090", sitelinks=1, year=1964),
                ),
                works_total=1276,
                holdings=(RegistryHolding(qid="Q214867", name="National Gallery of Art", works=1128),),
            )
        },
        # Not among the most renowned, as none of the owner's Rothkos is: it is
        # listed because the library holds it, which is the case that matters.
        extra_works={
            "Q20270685": RegistryWorkEntry(qid="Q20270685", title="Untitled (Purple, White, and Red)", sitelinks=2, year=1953)
        },
    )


@pytest.fixture
def rothko(services, service):
    """Rothko, matched, with one work whose QID Wikidata lists, and a theme to put it in."""
    artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    work = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=artist.id, date_created="1953")
    services.identity.set_work_identity(work.id, "Q20270685")
    services.identity.set_artist_identity(artist.id, ROTHKO)
    services.display.add_theme(name="Colour fields")
    return artist, work


def _page(ui, artist):
    ui.open(f"#artist/{artist.id}")
    ui.page.wait_for_selector(f"#view h2:has-text('{artist.name}')")


def _registry_answered(ui):
    ui.page.wait_for_selector("#view section table, #view section p.note")


class TestTheIndex:
    def test_held_artists_are_listed_with_counts_and_open_their_page(self, ui, rothko, seeded_service):
        artist, _work = rothko
        ui.open("#artist")
        ui.page.wait_for_selector("#view h2:has-text('Artists')")

        rows = ui.page.locator("tbody tr").all_inner_texts()
        assert any(row.startswith("Mark Rothko") and row.rstrip().endswith("1") for row in rows)
        assert any(row.startswith("Salvador Dalí") for row in rows)

        ui.page.click("tbody button:has-text('Mark Rothko')")
        ui.page.wait_for_selector("#view h2:has-text('Mark Rothko')")
        assert ui.page.evaluate("() => window.location.hash") == f"#artist/{artist.id}"

    def test_the_sidebar_offers_artists_under_artworks(self, ui, rothko):
        ui.open("#collection")
        ui.page.wait_for_selector("#view h2")

        ui.page.get_by_role("link", name="Artists").click()
        ui.page.wait_for_selector("#view h2:has-text('Artists')")


class TestTheArtistPage:
    def test_the_held_works_are_shown_and_only_theirs_in_circulation(self, ui, service, rothko):
        """An archived Rothko and another painter's work are both in the catalogue; neither belongs here."""
        artist, work = rothko
        gone = service.add_artwork(title="Rothko, archived", artist_id=artist.id)
        service.archive_artwork(gone.id)
        other = service.add_artist(name="Someone Else")
        service.add_artwork(title="Not a Rothko", artist_id=other.id)
        _page(ui, artist)

        assert ui.page.locator("#in-your-library").inner_text() == "In your library (1)"
        assert ui.page.locator("section[aria-labelledby='in-your-library'] .card-title").all_inner_texts() == [work.title]

    def test_two_held_works_naming_one_item_are_shown_as_a_duplicate(self, ui, services, service, rothko):
        """The duplicate a curator should see, rather than one mark that quietly picks one."""
        artist, work = rothko
        twin = service.add_artwork(title="Untitled (Purple, White, and Red), again", artist_id=artist.id)
        services.identity.set_work_identity(twin.id, "Q20270685")
        _page(ui, artist)
        _registry_answered(ui)

        badge = ui.page.locator("section[aria-labelledby='their-work'] .badge-held")
        assert badge.inner_text().strip().endswith("Held ×2")
        badge.click()
        # By address, not by heading: the twin's title contains the first's, so a
        # heading match passes whichever of the two opened.
        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#work/${id}`)", arg=work.id)
        ui.page.wait_for_selector(f"#view h2:text-is('{work.title}')")

    def test_their_work_marks_the_held_one_held_and_the_others_not(self, ui, rothko):
        artist, work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        states = {
            # The Get column comes first; the work and its state are the second and fourth.
            row.locator("td").nth(1).inner_text(): row.locator("td").nth(3).inner_text().strip()
            for row in ui.page.locator("section[aria-labelledby='their-work'] tbody tr").all()
        }
        assert states["Untitled (Purple, White, and Red)"].endswith("Held")
        assert states["Rothko Chapel"].endswith("Image found")
        assert states["No 1"] == "—"
        assert "No English title (Q16682090)" in states
        assert "1276" in ui.page.locator("section[aria-labelledby='their-work'] caption").inner_text()

        ui.page.click("section[aria-labelledby='their-work'] .badge-held")
        ui.page.wait_for_selector(f"#view h2:has-text('{work.title}')")

    def test_an_image_found_is_a_commons_thumbnail_that_sends_no_referrer(self, ui, rothko):
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        thumb = ui.page.locator(".badge-image-found img")
        assert thumb.get_attribute("src") == f"{COMMONS}?width=96"
        assert thumb.get_attribute("referrerpolicy") == "no-referrer"

    def test_registry_text_arrives_as_words_not_markup(self, ui, rothko):
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        assert ui.page.get_by_text('American painter <img src=x onerror="window.pwned=1">').count() == 1
        assert ui.page.evaluate("() => window.pwned") is None

    def test_holdings_and_movements_are_shown(self, ui, rothko):
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        assert ui.page.get_by_text("National Gallery of Art: 1128").count() == 1
        assert ui.page.get_by_text("abstract expressionism").count() == 1

    def test_a_registry_outage_leaves_the_library_half_working(self, ui, rothko, registry):
        artist, work = rothko
        registry.failing = True
        _page(ui, artist)
        _registry_answered(ui)

        assert "could not be asked" in ui.page.locator("section[aria-labelledby='their-work'] p.note").inner_text()
        assert ui.page.locator("section[aria-labelledby='in-your-library'] .card-title").all_inner_texts() == [work.title]

    def test_an_unmatched_artist_says_so(self, ui, services, service):
        painter = service.add_artist(name="Unmatched Painter")
        service.add_artwork(title="Something", artist_id=painter.id)
        _page(ui, painter)
        _registry_answered(ui)

        assert "not matched to Wikidata" in ui.page.locator("section[aria-labelledby='their-work'] p.note").inner_text()

    def test_more_like_this_writes_an_artist_affinity(self, ui, services, rothko):
        artist, _work = rothko
        _page(ui, artist)

        ui.page.click("button:has-text('More like this')")
        ui.page.wait_for_selector("text=Recorded: more like this for Mark Rothko.")

        affinities = {(view.affinity.kind, view.affinity.value): view.affinity for view in services.taste.list_affinities()}
        recorded = affinities[("artist", "Mark Rothko")]
        assert (str(recorded.sentiment), recorded.open_to_more) == ("loves", True)

    def test_a_selection_is_added_to_a_theme(self, ui, services, rothko):
        artist, work = rothko
        _page(ui, artist)

        ui.page.check(f"input[aria-label='Select {work.title}']")
        ui.page.click("section[aria-labelledby='in-your-library'] button:has-text('Add to theme')")
        ui.page.wait_for_selector("text=Added 1 work to Colour fields.")

        theme = next(t for t in services.display.list_themes() if t.name == "Colour fields")
        assert list(services.display.theme_work_ids(theme.id)) == [work.id]

    def test_a_server_fault_is_an_error_not_an_absent_artist(self, ui, rothko):
        """Only the catalogue's refusal means nobody is here; a 500 is the error banner's."""
        artist, _work = rothko
        ui.page.route(
            f"**/api/artists/{artist.id}",
            lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
        )
        ui.open(f"#artist/{artist.id}")

        ui.page.wait_for_selector("#error:not([hidden])")
        assert "500" in ui.page.inner_text("#error")
        assert ui.page.locator("#view h2:has-text('That artist is not here')").count() == 0

    def test_an_address_naming_nobody_says_so(self, ui):
        ui.open("#artist/nobody")
        ui.page.wait_for_selector("#view h2:has-text('That artist is not here')")


class TestTheWaysIn:
    def test_an_artist_name_on_a_works_card_opens_their_page(self, ui, rothko):
        artist, _work = rothko
        ui.open("#collection")
        ui.page.wait_for_selector("ul.grid li.card")

        ui.page.locator(".card-artist button", has_text="Mark Rothko").first.click()
        ui.page.wait_for_selector("#view h2:has-text('Mark Rothko')")

    def test_the_artist_on_a_work_page_opens_their_page(self, ui, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        ui.page.wait_for_selector(f"#view h2:has-text('{work.title}')")

        ui.page.click("dl.facts button:has-text('Mark Rothko')")
        ui.page.wait_for_selector("#view h2:has-text('Mark Rothko')")


def test_an_empty_artist_index_offers_ask(ui):
    """With no artists yet, the index sends the curator where works come from."""
    ui.serve("**/api/artists", {"artists": []})
    ui.open("#artist")
    button = ui.page.locator("#view button:text-is('Ask')")

    button.click()

    ui.page.wait_for_selector("#view h2:text-is('Ask')")
