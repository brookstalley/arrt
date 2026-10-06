"""Library › Artists and the Artist page, in a real browser against a real server.

The hub (ruling 4): who the artist is, what the library holds of theirs, what
Wikidata lists with the held ones marked, and which collections hold their work.
The registry is a fake installed where the entry point builds Wikidata's, so
every state its half can be in is reachable: answering, down, and silent about
an artist the library has not matched.

**Registry text is written by anyone**, so one test hands the page a description
carrying markup and asserts it arrives as words, not as an element.
"""

from dataclasses import replace

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import ItemId, RegistryArtist, RegistryHolding, RegistryPerson, RegistryText, RegistryWorkEntry

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
    # Library › Artists became Lidarr's poster index, in surname order (the
    # owner's ruling on #173). The table it was is the second view, so the old
    # "listed with counts" test is replaced by one per view rather than dropped.

    def test_held_artists_are_posters_in_surname_order_and_open_their_page(self, ui, rothko, seeded_service):
        artist, work = rothko
        ui.serve_image(f"**/api/works/{work.id}/thumbnail*")
        ui.open("#artist")
        ui.page.wait_for_selector("ul.artist-posters li.card")

        names = ui.page.locator("ul.artist-posters .card-title").all_inner_texts()
        assert names == ["Salvador Dalí", "Charles Demuth", "Mark Rothko"]
        rothko_card = ui.page.locator(f"li.card[data-artist='{artist.id}']")
        assert rothko_card.locator(".card-meta").inner_text() == "1903–1970 · 1 work"
        assert rothko_card.locator("img").get_attribute("src") == f"/api/works/{work.id}/thumbnail"

        ui.page.click("ul.artist-posters button:has-text('Mark Rothko')")
        ui.page.wait_for_selector("#view h2:has-text('Mark Rothko')")
        assert ui.page.evaluate("() => window.location.hash") == f"#artist/{artist.id}"

    def test_the_table_view_is_the_same_order_and_is_kept_in_the_address(self, ui, rothko, seeded_service):
        ui.open("#artist")
        ui.page.wait_for_selector("ul.artist-posters")
        ui.page.click("button.menu-button-trigger:has-text('View')")
        ui.page.click("[role='menuitemradio']:has-text('Table')")
        ui.page.wait_for_selector("#view table tbody tr")

        assert ui.page.evaluate("() => window.location.hash") == "#artist?view=table"
        assert ui.page.locator("button.menu-button-trigger", has_text="View").inner_text().startswith("View: Table")
        assert ui.page.locator("#view tbody td:first-child").all_inner_texts() == [
            "Salvador Dalí",
            "Charles Demuth",
            "Mark Rothko",
        ]
        ui.page.reload()
        ui.page.wait_for_selector("#view table tbody tr")
        assert ui.page.locator("ul.artist-posters").count() == 0

    def test_every_artist_is_reached_by_keyboard(self, ui, rothko, seeded_service):
        """The picture is a pointer's shortcut; the name is the control, and Tab reaches each one."""
        ui.open("#artist")
        ui.page.wait_for_selector("ul.artist-posters li.card")
        ui.page.focus("button.menu-button-trigger")

        reached = []
        for _ in range(6):
            ui.page.keyboard.press("Tab")
            reached.append(ui.page.evaluate("() => document.activeElement.textContent"))

        assert reached[:3] == ["Salvador Dalí", "Charles Demuth", "Mark Rothko"]

    @pytest.mark.parametrize(("width", "fewest", "most"), [(1280, 5, 99), (390, 2, 2)], ids=["desktop", "phone"])
    def test_the_posters_fill_the_width_and_pair_on_a_phone(self, ui, rothko, seeded_service, width, fewest, most):
        """Several to a row on a desktop, two on a phone (Lidarr's poster index), never past the page edge."""
        ui.page.set_viewport_size({"width": width, "height": 900})
        ui.open("#artist")
        ui.page.wait_for_selector("ul.artist-posters li.card")

        tracks = ui.page.evaluate(
            "() => getComputedStyle(document.querySelector('ul.artist-posters')).gridTemplateColumns.split(' ').length"
        )
        assert fewest <= tracks <= most
        grid = ui.page.locator("ul.artist-posters").bounding_box()
        assert grid["x"] + grid["width"] <= width, "the grid runs past the page"

    def test_a_picture_that_fails_to_load_says_so_and_keeps_the_card(self, ui, rothko, seeded_service):
        """The case the owner's catalogue meets: a pictured work whose master has not arrived, so its thumbnail fails."""
        artist, work = rothko
        ui.serve(f"**/api/works/{work.id}/thumbnail*", (404, {"error": "No image yet."}))
        ui.open("#artist")
        ui.page.wait_for_selector(f"li.card[data-artist='{artist.id}'] .card-image-absent")

        card = ui.page.locator(f"li.card[data-artist='{artist.id}']")
        assert card.locator(".card-image-absent").inner_text() == "No picture"
        assert card.locator("img").count() == 0, "a broken image was left in the card"
        assert card.locator(".card-title").inner_text() == "Mark Rothko"
        assert card.locator(".card-meta").inner_text() == "1903–1970 · 1 work"

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

    def test_their_work_marks_a_wanted_one_wanted_and_draws_each_picture_in_its_style(self, ui, rothko, want_item, pictures_load):
        artist, _work = rothko
        want_item("Q17038023", "No 1")
        _page(ui, artist)
        _registry_answered(ui)

        marks = {
            row.locator("td").nth(1).inner_text(): row.locator("td").nth(3)
            for row in ui.page.locator("section[aria-labelledby='their-work'] tbody tr").all()
        }
        assert " ".join(marks["No 1"].inner_text().split()) == "◑ Wanted"
        assert marks["Untitled (Purple, White, and Red)"].locator(".work-pic-held img").count() == 1
        assert marks["Rothko Chapel"].locator(".work-pic-not-held img").count() == 1

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
        assert states["Rothko Chapel"].endswith("Not held · Image found")
        # A work with neither says so in glyph and word, as every state does,
        # rather than a dash (the owner's ruling on #172).
        assert " ".join(states["No 1"].split()) == "○ Not held"
        assert "No English title (Q16682090)" in states
        assert "1276" in ui.page.locator("section[aria-labelledby='their-work'] caption").inner_text()

        ui.page.click("section[aria-labelledby='their-work'] .badge-held")
        ui.page.wait_for_selector(f"#view h2:has-text('{work.title}')")

    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "phone"])
    def test_their_work_shows_each_picture_large_enough_to_choose_by(self, ui, rothko, registry, pictures_load, width):
        """The picture is what a curator picks a work to Get by, so a phone shows it too
        (`information-architecture.md` § A work's mark), and the table still fits the panel:
        with a title longer than a phone is wide, as Dalí has, and a year before the common era."""
        listed = registry.artists[ROTHKO]
        registry.artists[ROTHKO] = replace(
            listed,
            works=(
                *listed.works,
                RegistryWorkEntry(qid="Q1", title="Galacidalacidesoxyribonucleicacid", sitelinks=0, year=1963),
                RegistryWorkEntry(qid="Q2", title="A fresco", sitelinks=0, year=-50),
            ),
        )
        ui.page.set_viewport_size({"width": width, "height": 900})
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)
        section = "section[aria-labelledby='their-work']"

        # The frame is sized by the style, whether or not the picture has arrived;
        # one hidden by the style has no box at all.
        for style in ("held", "not-held"):
            box = ui.page.locator(f"{section} .work-pic-{style}").bounding_box()
            assert box is not None, f"the {style} picture is not drawn"
            assert min(box["width"], box["height"]) >= 48, f"the {style} picture is too small to tell works apart"
        fits = ui.page.evaluate(
            "(s) => { const c = document.querySelector(`${s} .artist-works`); return c.scrollWidth <= c.clientWidth; }",
            section,
        )
        assert fits, "the table scrolls sideways"
        # The phone folds the Year column under the title rather than losing it.
        chapel = ui.page.locator(f"{section} tbody tr", has_text="Rothko Chapel")
        column, under = chapel.locator("td.year-col"), chapel.locator(".year-under")
        shown, folded = (under, column) if width < 640 else (column, under)
        assert shown.is_visible()
        assert shown.inner_text() == "1971"
        assert not folded.is_visible()
        fresco = ui.page.locator(f"{section} tbody tr", has_text="A fresco")
        assert fresco.locator(".year-under" if width < 640 else "td.year-col").inner_text() == "50 BCE"

    def test_an_image_found_is_a_commons_thumbnail_that_sends_no_referrer(self, ui, rothko):
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        thumb = ui.page.locator(".badge-image-found img")
        # Why 250: `FOUND_WIDTH` in `core/registry.js`.
        assert thumb.get_attribute("src") == f"{COMMONS}?width=250"
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
        _artist, _work = rothko
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


LUCY_BULL = "Q123365005"


def _their_work(ui):
    return ui.page.locator("section[aria-labelledby='their-work']")


class TestAnUnlinkedArtist:
    """An artist the library holds with no Wikidata item: who they might be, and a click to say which.

    The owner's case: the library's Franz Kline was never matched, so his page
    listed nothing of Wikidata's, while search showed Wikidata's Kline beside him.
    """

    @pytest.fixture
    def unlinked(self, service, registry):
        painter = service.add_artist(name="Mark Rothko", born=1903, died=1970)
        service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=painter.id)
        registry.people["Mark Rothko"] = [
            RegistryPerson(qid=ItemId("Q900001"), label=RegistryText("Mark Rothko"), born=1850, died=1900),
            RegistryPerson(qid=ItemId(ROTHKO), label=RegistryText("Mark Rothko"), born=1903, died=1970),
        ]
        return painter

    def test_the_candidates_are_named_and_this_is_them_lists_their_work(self, ui, unlinked):
        _page(ui, unlinked)
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] button:text-is('This is them')")

        rows = [" ".join(text.split()) for text in _their_work(ui).locator("li").all_inner_texts()]
        assert rows == [
            f"Mark Rothko 1903–1970 · {ROTHKO} · their years agree This is them",
            "Mark Rothko 1850–1900 · Q900001 This is them",
        ]
        _their_work(ui).locator("li").first.locator("button").click()
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")

        assert "Rothko Chapel" in _their_work(ui).inner_text()
        assert _their_work(ui).locator("button:text-is('This is them')").count() == 0
        assert "set by you" in ui.page.locator(".identity-now").inner_text()

    def test_a_candidate_taken_since_the_page_was_drawn_is_refused_and_nothing_is_stored(self, ui, services, service, unlinked):
        """The list is read once; another artist may take the item before the click. The route refuses it, and says why."""
        _page(ui, unlinked)
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] button:text-is('This is them')")
        other = service.add_artist(name="Someone Else")
        services.identity.set_artist_identity(other.id, ROTHKO)

        _their_work(ui).locator("li").first.locator("button").click()
        ui.page.wait_for_selector("#error:not([hidden])")

        assert "already" in ui.page.inner_text("#error")
        assert services.artists.get(unlinked.id).artist.wikidata_qid is None

    def test_linking_a_namesake_to_a_taken_item_is_refused_and_stays_on_the_page(self, ui, registry, services, service, unlinked):
        registry.artists[ROTHKO] = replace(registry.artists[ROTHKO], name="Mark Rothko", born=1903, died=1970)
        ui.open(f"#artist/{ROTHKO}")
        ui.page.wait_for_selector("#view .namesake")
        other = service.add_artist(name="Someone Else")
        services.identity.set_artist_identity(other.id, ROTHKO)

        ui.page.click("#view button:text-is('Link them to this item')")
        ui.page.wait_for_selector("#error:not([hidden])")

        assert ui.page.evaluate("() => window.location.hash") == f"#artist/{ROTHKO}"
        assert services.artists.get(unlinked.id).artist.wikidata_qid is None

    def test_after_there_is_none_nobody_is_offered(self, ui, services, unlinked):
        services.identity.set_artist_identity(unlinked.id, None)
        _page(ui, unlinked)
        _registry_answered(ui)

        assert "You said Wikidata has no item" in _their_work(ui).locator("p.note").inner_text()
        assert _their_work(ui).locator("button:text-is('This is them')").count() == 0

    def test_their_page_by_qid_offers_to_link_them_and_then_is_theirs(self, ui, registry, unlinked):
        registry.artists[ROTHKO] = replace(registry.artists[ROTHKO], name="Mark Rothko", born=1903, died=1970)
        ui.open(f"#artist/{ROTHKO}")
        ui.page.wait_for_selector("#view .namesake")

        assert "Your library has Mark Rothko (1903–1970), not linked to Wikidata." in ui.page.locator(".namesake").inner_text()
        ui.page.click("#view button:text-is('Link them to this item')")
        ui.page.wait_for_function("(id) => window.location.hash === `#artist/${id}`", arg=unlinked.id)
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")

        assert "Rothko Chapel" in _their_work(ui).inner_text()

    def test_a_linked_artists_namesake_page_offers_no_link(self, ui, registry, rothko):
        """The paired negative: the page by QID of someone the library holds linked forwards, and offers nothing."""
        ui.open(f"#artist/{ROTHKO}")
        ui.page.wait_for_selector("#view h2:has-text('Mark Rothko')")
        _registry_answered(ui)

        assert ui.page.locator("#view .namesake").count() == 0


class TestWhenWikidataListsNoWorks:
    """Lucy Bull: Wikidata knows her, and lists no works, holdings or similar painters.

    The page said so and stopped. Ask is how a living painter's work is found.
    """

    @pytest.fixture
    def lucy_bull(self, registry):
        registry.artists[LUCY_BULL] = RegistryArtist(qid=LUCY_BULL, name="Lucy Bull", born=1990)

    def test_her_page_by_qid_offers_ask_filled_in_and_not_started(self, ui, lucy_bull):
        ui.open(f"#artist/{LUCY_BULL}")
        ui.page.wait_for_selector("#view button:text-is('Ask for their work')")

        ui.page.click("#view button:text-is('Ask for their work')")
        ui.page.wait_for_selector("#view textarea#intent")

        assert ui.page.evaluate("() => window.location.hash") == "#discover?term=Paintings%20by%20Lucy%20Bull"
        assert ui.page.input_value("#intent") == "Paintings by Lucy Bull"

    def test_a_held_artist_wikidata_lists_nothing_for_offers_it_too(self, ui, services, service, lucy_bull):
        painter = service.add_artist(name="Lucy Bull", born=1990)
        service.add_artwork(title="The Bottoms", artist_id=painter.id)
        services.identity.set_artist_identity(painter.id, LUCY_BULL)
        _page(ui, painter)

        ui.page.wait_for_selector("section[aria-labelledby='their-work'] button:text-is('Ask for their work')")

    def test_an_artist_wikidata_lists_works_for_is_not_offered_it(self, ui, rothko):
        """The paired negative: Ask is the way on from nothing, not a button on every page."""
        artist, _work = rothko
        _page(ui, artist)
        _registry_answered(ui)

        assert ui.page.locator("#view button:text-is('Ask for their work')").count() == 0


def test_an_empty_artist_index_offers_ask(ui):
    """With no artists yet, the index sends the curator where works come from."""
    ui.serve("**/api/artists", {"artists": []})
    ui.open("#artist")
    button = ui.page.locator("#view button:text-is('Ask')")

    button.click()

    ui.page.wait_for_selector("#view h2:text-is('Ask')")
