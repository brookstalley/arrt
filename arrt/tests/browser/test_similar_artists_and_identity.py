"""*Similar artists*, and setting a Wikidata item by hand, in a real browser.

Ruling 4's hub gains *Similar artists*: visual artists sharing a movement, each
with how many of their works have an image. Ruling 7's identities gain a control:
a new item is looked up and shown before it is stored, so a typo cannot pass as
an identity, and *There is none* is confirmed first. The registry is a fake
installed where the entry point builds Wikidata's.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from playwright.sync_api import expect

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistrySimilar,
    RegistryWork,
    RegistryWorkEntry,
)

ROTHKO = "Q160149"
POLLOCK = "Q37571"
NEWMAN = "Q295125"
HUNTERS = "Q500985"
HELD_ROTHKO = "Q20270685"


@pytest.fixture
def registry():
    return FakeRegistry(
        artists={
            ROTHKO: RegistryArtist(
                qid=ROTHKO,
                name="Mark Rothko",
                works=(RegistryWorkEntry(qid=HELD_ROTHKO, title="Untitled (Purple, White, and Red)", sitelinks=0, year=1953),),
            ),
            POLLOCK: RegistryArtist(qid=POLLOCK, name="Jackson Pollock", born=1912, died=1956),
        },
        similar={
            ROTHKO: [
                RegistrySimilar(qid=POLLOCK, name="Jackson Pollock", sitelinks=118, born=1912, died=1956, images=0),
                RegistrySimilar(qid=NEWMAN, name="Barnett Newman", sitelinks=37, born=1905, died=1970, images=17),
            ],
            POLLOCK: [RegistrySimilar(qid=ROTHKO, name="Mark Rothko", sitelinks=150, born=1903, died=1970, images=1)],
        },
        works={
            HUNTERS: RegistryWork(
                qid=HUNTERS,
                title="The Hunters in the Snow",
                sitelinks=39,
                year=1565,
                creators=(RegistryCreator(qid="Q43270", name="Pieter Brueghel the Elder"),),
            ),
            HELD_ROTHKO: RegistryWork(qid=HELD_ROTHKO, title="Untitled (Purple, White, and Red)", sitelinks=0, year=1953),
        },
    )


@pytest.fixture
def rothko(services, service):
    artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    work = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=artist.id, date_created="1953")
    services.identity.set_work_identity(work.id, HELD_ROTHKO)
    services.identity.set_artist_identity(artist.id, ROTHKO)
    return artist, work


def _similar(ui):
    """The section's rows, once it has answered: `to_have_text([...])` folds each row's breaks to spaces."""
    ui.page.wait_for_selector("section[aria-labelledby='similar-artists'] ul, section[aria-labelledby='similar-artists'] p.note")
    return ui.page.locator("section[aria-labelledby='similar-artists'] li")


class TestSimilarArtists:
    def test_a_held_artists_page_lists_them_with_what_can_be_seen(self, ui, rothko):
        artist, _work = rothko
        ui.open(f"#artist/{artist.id}")

        expect(_similar(ui)).to_have_text(
            [
                "Jackson Pollock 1912–1956 · 0 works with an image ○ Not held",
                "Barnett Newman 1905–1970 · 17 works with an image ○ Not held",
            ],
            use_inner_text=True,
        )
        ui.page.click("section[aria-labelledby='similar-artists'] a:has-text('Jackson Pollock')")
        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#artist/${qid}`", arg=POLLOCK)

    def test_an_unheld_artists_page_lists_them_and_marks_the_held_one(self, ui, rothko):
        artist, _work = rothko
        ui.open(f"#artist/{POLLOCK}")

        expect(_similar(ui)).to_have_text(["Mark Rothko 1903–1970 · 1 work with an image ● In your library"], use_inner_text=True)
        ui.page.click("section[aria-labelledby='similar-artists'] a:has-text('Mark Rothko')")
        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=artist.id)

    def test_an_outage_says_so_in_the_section(self, ui, rothko, registry):
        artist, _work = rothko
        registry.failing = True
        ui.open(f"#artist/{artist.id}")
        _similar(ui)

        expect(ui.page.locator("section[aria-labelledby='similar-artists'] p.note")).to_contain_text(
            "could not be asked", use_inner_text=True
        )

    def test_an_artist_with_no_item_has_no_section(self, ui, service):
        nobody = service.add_artist(name="Unmatched Painter")
        service.add_artwork(title="Something", artist_id=nobody.id)
        ui.open(f"#artist/{nobody.id}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

        # Anchored by the artist's own work section, which has answered.
        expect(ui.page.locator("section[aria-labelledby='similar-artists']")).to_have_count(0)


# Where the control is: in place on the Artist page, and on the Work page in
# the dialog *Match on Wikidata…* opens from ⋯ (ruling 8 of 2026-10-27).
ARTIST = "#view .identity"
WORK = "dialog.panel-dialog[open] .identity"


def _open_control(ui, at=ARTIST):
    if at == WORK:
        ui.page.click(".page-toolbar .action-menu-trigger")
        ui.page.click(".toolbar-menu [role='menuitem']:text-is('Match on Wikidata…')")
    else:
        ui.page.click(f"{at} button:has-text('Edit')")
    ui.page.wait_for_selector(f"{at} input:visible")


def _look_up(ui, typed, at=ARTIST):
    ui.page.fill(f"{at} input", typed)
    ui.page.click(f"{at} button:has-text('Look up')")
    ui.page.wait_for_function("(at) => !document.querySelector(`${at} [aria-live]`).textContent.startsWith('Asking')", arg=at)
    return ui.page.locator(f"{at} [aria-live]")


def _work_item(ui):
    """The Wikidata item the Work page states, once the dialog has closed: none stated is `to_have_count(0)`."""
    ui.page.wait_for_selector("dialog.panel-dialog[open]", state="detached")
    return ui.page.locator("#view .work-label dt:text-is('Wikidata') + dd")


class TestSettingAnItemByHand:
    def test_at_rest_the_control_is_the_identity_and_one_edit(self, ui, rothko):
        """The owner's ruling on #174: the item and one quiet *Edit*; the rest only once it is pressed.

        On the Artist page. Asserted as a rendered state.
        """
        artist, _work = rothko
        ui.open(f"#artist/{artist.id}")
        ui.page.wait_for_selector("#view .identity button:has-text('Edit')")

        # Anchored by the wait above for the Edit button, which only the settled page has.
        expect(ui.page.locator("#view .identity button:visible")).to_have_text(["Edit"], use_inner_text=True)
        expect(ui.page.locator("#view .identity input")).to_be_hidden()
        expect(ui.page.locator("#view .identity button:has-text('There is none')")).to_be_hidden()
        expect(ui.page.locator("#view .identity button:has-text('Edit')")).to_have_attribute("aria-expanded", "false")

        _open_control(ui)

        expect(ui.page.locator("#view .identity input")).to_be_visible()
        expect(ui.page.locator("#view .identity button:has-text('Look up')")).to_be_visible()
        expect(ui.page.locator("#view .identity button:has-text('There is none')")).to_be_visible()
        expect(ui.page.locator("#view .identity button:has-text('Edit')")).to_have_attribute("aria-expanded", "true")

    def test_on_a_work_the_control_is_open_in_its_dialog_and_says_the_item(self, ui, rothko):
        """Ruling 8 puts Match on Wikidata behind ⋯: the dialog was the asking, so
        its form is open and it has no Edit of its own."""
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        ui.page.wait_for_selector(".page-toolbar .action-menu-trigger")

        expect(_work_item(ui)).to_have_text(HELD_ROTHKO, use_inner_text=True)
        # Anchored by the work's own facts above, which have been drawn.
        expect(ui.page.locator("#view .identity")).to_have_count(0)
        _open_control(ui, WORK)

        expect(ui.page.locator(WORK)).to_contain_text("Wikidata: Q20270685 (set by you)", use_inner_text=True)
        expect(ui.page.locator(f"{WORK} button:has-text('Edit')")).to_have_count(0)
        expect(ui.page.locator(f"{WORK} button:has-text('Look up')")).to_be_visible()
        expect(ui.page.locator(f"{WORK} button:has-text('There is none')")).to_be_visible()

    def test_a_work_item_is_shown_before_it_is_stored(self, ui, service, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        _open_control(ui, WORK)

        expect(_look_up(ui, "q500985", WORK)).to_have_text(
            "Q500985 is “The Hunters in the Snow”, by Pieter Brueghel the Elder (1565).", use_inner_text=True
        )
        # Shown, not yet stored.
        assert service.get_artwork(work.id).artwork.wikidata_qid == HELD_ROTHKO
        ui.page.click(f"{WORK} button:has-text('Use Q500985')")

        expect(_work_item(ui)).to_have_text(HUNTERS, use_inner_text=True)
        assert service.get_artwork(work.id).artwork.wikidata_qid == HUNTERS
        # Back on ⋯, which opened the dialog the page repainted under.
        assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')").startswith("More acts on ")

    @pytest.mark.parametrize(
        ("typed", "said"),
        [
            ("Q12x", "That is not a Wikidata item id: a Q followed by digits, as in Q160149."),
            ("Q999999", "Wikidata has no item Q999999."),
        ],
    )
    def test_a_typo_or_a_missing_item_cannot_be_stored(self, ui, rothko, typed, said):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        _open_control(ui, WORK)

        expect(_look_up(ui, typed, WORK)).to_have_text(said, use_inner_text=True)
        expect(ui.page.locator(f"{WORK} button:has-text('Use ')")).to_be_hidden()

    def test_there_is_none_is_confirmed_and_clears_the_held_mark(self, ui, service, rothko):
        artist, work = rothko
        ui.open(f"#work/{work.id}")
        _open_control(ui, WORK)
        ui.page.click(f"{WORK} button:has-text('There is none')")
        ui.page.click("dialog.confirm button:has-text('There is none')")

        # Once the dialog is closed and the page repainted: it held an item before, so this waits for it to go.
        expect(_work_item(ui)).to_have_count(0)
        assert service.get_artwork(work.id).artwork.wikidata_qid is None

        ui.open(f"#artist/{artist.id}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")
        expect(ui.page.locator("section[aria-labelledby='their-work'] .badge-held")).to_have_count(0)

    def test_cancelling_there_is_none_changes_nothing(self, ui, service, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        _open_control(ui, WORK)
        ui.page.click(f"{WORK} button:has-text('There is none')")
        ui.page.click("dialog.confirm button:has-text('Cancel')")
        ui.page.wait_for_selector("dialog.confirm", state="detached")
        # Cancelling changes nothing, and nothing on the page marks a write that did not happen:
        # the service is asked after a pause long enough for one to have landed.
        ui.page.wait_for_timeout(300)  # sleep: proves a cancelled change is not stored for a while

        assert service.get_artwork(work.id).artwork.wikidata_qid == HELD_ROTHKO
        expect(ui.page.locator(WORK)).to_contain_text("Wikidata: Q20270685 (set by you)", use_inner_text=True)
        # Escape closes Match on Wikidata… and nothing has changed.
        ui.page.keyboard.press("Escape")
        expect(_work_item(ui)).to_have_text(HELD_ROTHKO, use_inner_text=True)
        assert service.get_artwork(work.id).artwork.wikidata_qid == HELD_ROTHKO

    def test_an_item_another_artist_holds_is_refused_with_why(self, ui, services, service, rothko):
        other = service.add_artist(name="Not Rothko")
        service.add_artwork(title="Theirs", artist_id=other.id)
        ui.open(f"#artist/{other.id}")
        _open_control(ui)

        expect(_look_up(ui, ROTHKO)).to_have_text(
            f"Another artist in your library already has {ROTHKO}. Correct that one first.", use_inner_text=True
        )
        expect(ui.page.locator("#view .identity button:has-text('Use ')")).to_be_hidden()

    def test_an_artist_item_is_shown_then_stored(self, ui, services, service):
        other = service.add_artist(name="J. Pollock")
        service.add_artwork(title="Number 1", artist_id=other.id)
        ui.open(f"#artist/{other.id}")
        _open_control(ui)

        expect(_look_up(ui, POLLOCK)).to_have_text(f"{POLLOCK} is Jackson Pollock (1912–1956).", use_inner_text=True)
        ui.page.click(f"#view .identity button:has-text('Use {POLLOCK}')")

        ui.page.wait_for_selector(f"#view .identity :text('Wikidata: {POLLOCK} (set by you)')")
        assert services.artists.get(other.id).artist.wikidata_qid == POLLOCK

    def test_an_item_with_no_english_name_can_be_stored_as_the_service_would(self, ui, services, service):
        """A Japanese painter's item may carry only a Japanese name; it is an item all the same."""
        other = service.add_artist(name="Hokusai")
        service.add_artwork(title="The Great Wave", artist_id=other.id)
        ui.open(f"#artist/{other.id}")
        _open_control(ui)

        expect(_look_up(ui, "Q777")).to_have_text(
            "Wikidata gives no English name for Q777; check it is the one you mean.", use_inner_text=True
        )
        ui.page.click("#view .identity button:has-text('Use Q777')")

        ui.page.wait_for_selector("#view .identity :text('Wikidata: Q777 (set by you)')")
        assert services.artists.get(other.id).artist.wikidata_qid == "Q777"


class TestSettingAnItemWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_the_item_is_offered_unchecked_and_stored_as_the_service_would(self, ui, service, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        _open_control(ui, WORK)

        expect(_look_up(ui, "Q500985", WORK)).to_have_text(
            "Wikidata is not configured on this server, so Q500985 cannot be checked. It can still be stored.",
            use_inner_text=True,
        )
        ui.page.click(f"{WORK} button:has-text('Use Q500985')")

        expect(_work_item(ui)).to_have_text("Q500985", use_inner_text=True)
        assert service.get_artwork(work.id).artwork.wikidata_qid == "Q500985"
