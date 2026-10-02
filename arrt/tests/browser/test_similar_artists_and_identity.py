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

from fakes import FakeRegistry  # noqa: E402  (after the skip guard)

from arrt.library.registry import (  # noqa: E402
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
    ui.page.wait_for_selector("section[aria-labelledby='similar-artists'] ul, section[aria-labelledby='similar-artists'] p.note")
    return [" ".join(t.split()) for t in ui.page.locator("section[aria-labelledby='similar-artists'] li").all_inner_texts()]


class TestSimilarArtists:
    def test_a_held_artists_page_lists_them_with_what_can_be_seen(self, ui, rothko):
        artist, _work = rothko
        ui.open(f"#artist/{artist.id}")

        assert _similar(ui) == [
            "Jackson Pollock 1912–1956 · 0 works with an image",
            "Barnett Newman 1905–1970 · 17 works with an image",
        ]
        ui.page.click("section[aria-labelledby='similar-artists'] button:has-text('Jackson Pollock')")
        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#artist/${qid}`", arg=POLLOCK)

    def test_an_unheld_artists_page_lists_them_and_marks_the_held_one(self, ui, rothko):
        artist, _work = rothko
        ui.open(f"#artist/{POLLOCK}")

        assert _similar(ui) == ["Mark Rothko 1903–1970 · 1 work with an image ● In your library"]
        ui.page.click("section[aria-labelledby='similar-artists'] button:has-text('Mark Rothko')")
        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=artist.id)

    def test_an_outage_says_so_in_the_section(self, ui, rothko, registry):
        artist, _work = rothko
        registry.failing = True
        ui.open(f"#artist/{artist.id}")
        _similar(ui)

        assert "could not be asked" in ui.page.locator("section[aria-labelledby='similar-artists'] p.note").inner_text()

    def test_an_artist_with_no_item_has_no_section(self, ui, service):
        nobody = service.add_artist(name="Unmatched Painter")
        service.add_artwork(title="Something", artist_id=nobody.id)
        ui.open(f"#artist/{nobody.id}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

        assert ui.page.locator("section[aria-labelledby='similar-artists']").count() == 0


def _open_control(ui):
    ui.page.click("#view .identity button:has-text('Change…')")
    ui.page.wait_for_selector("#view .identity input:visible")


def _look_up(ui, typed):
    ui.page.fill("#view .identity input", typed)
    ui.page.click("#view .identity button:has-text('Look up')")
    ui.page.wait_for_function("() => !document.querySelector('#view .identity [aria-live]').textContent.startsWith('Asking')")
    return ui.page.locator("#view .identity [aria-live]").inner_text()


class TestSettingAnItemByHand:
    def test_a_work_item_is_shown_before_it_is_stored(self, ui, service, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        assert "Wikidata: Q20270685 (set by you)" in ui.page.locator("#view .identity").inner_text()
        _open_control(ui)

        assert _look_up(ui, "q500985") == "Q500985 is “The Hunters in the Snow”, by Pieter Brueghel the Elder (1565)."
        # Shown, not yet stored.
        assert service.get_artwork(work.id).artwork.wikidata_qid == HELD_ROTHKO
        ui.page.click("#view .identity button:has-text('Use Q500985')")

        ui.page.wait_for_selector("#view .identity :text('Wikidata: Q500985 (set by you)')")
        assert service.get_artwork(work.id).artwork.wikidata_qid == HUNTERS

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
        _open_control(ui)

        assert _look_up(ui, typed) == said
        assert ui.page.locator("#view .identity button:has-text('Use ')").is_hidden()

    def test_there_is_none_is_confirmed_and_clears_the_held_mark(self, ui, service, rothko):
        artist, work = rothko
        ui.open(f"#work/{work.id}")
        ui.page.click("#view .identity button:has-text('There is none')")
        ui.page.click("dialog.confirm button:has-text('There is none')")

        ui.page.wait_for_selector("#view .identity :text('Wikidata: none (you said there is none)')")
        assert service.get_artwork(work.id).artwork.wikidata_qid is None

        ui.open(f"#artist/{artist.id}")
        ui.page.wait_for_selector("section[aria-labelledby='their-work'] table")
        assert ui.page.locator("section[aria-labelledby='their-work'] .badge-held").count() == 0

    def test_cancelling_there_is_none_changes_nothing(self, ui, service, rothko):
        _artist, work = rothko
        ui.open(f"#work/{work.id}")
        ui.page.click("#view .identity button:has-text('There is none')")
        ui.page.click("dialog.confirm button:has-text('Cancel')")
        ui.page.wait_for_selector("dialog.confirm", state="detached")
        ui.page.wait_for_timeout(300)

        assert service.get_artwork(work.id).artwork.wikidata_qid == HELD_ROTHKO
        assert "Wikidata: Q20270685 (set by you)" in ui.page.locator("#view .identity").inner_text()

    def test_an_item_another_artist_holds_is_refused_with_why(self, ui, services, service, rothko):
        other = service.add_artist(name="Not Rothko")
        service.add_artwork(title="Theirs", artist_id=other.id)
        ui.open(f"#artist/{other.id}")
        _open_control(ui)

        assert _look_up(ui, ROTHKO) == f"Another artist in your library already has {ROTHKO}. Correct that one first."
        assert ui.page.locator("#view .identity button:has-text('Use ')").is_hidden()

    def test_an_artist_item_is_shown_then_stored(self, ui, services, service):
        other = service.add_artist(name="J. Pollock")
        service.add_artwork(title="Number 1", artist_id=other.id)
        ui.open(f"#artist/{other.id}")
        _open_control(ui)

        assert _look_up(ui, POLLOCK) == f"{POLLOCK} is Jackson Pollock (1912–1956)."
        ui.page.click(f"#view .identity button:has-text('Use {POLLOCK}')")

        ui.page.wait_for_selector(f"#view .identity :text('Wikidata: {POLLOCK} (set by you)')")
        assert services.artists.get(other.id).artist.wikidata_qid == POLLOCK
