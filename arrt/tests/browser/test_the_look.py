"""The Work page for a work not held shows what the image sources hold, before any Get.

The look is asked of `GET /api/registry/works/{qid}/look`, which answers at once
and keeps asking behind it; the page polls every two seconds while any source is
still being asked, and repaints only its own section. Most tests here serve that
route a sequence of answers, because what is under test is what the page does
*across* polls: rows filling in, a live region that says each change once, a top
picture that is never swapped, and focus that never moves. One drives the real
look end to end: *Tantra-Vision*, which Wikidata pictures with nothing and SMK
holds.
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry, a_decodable_jpeg, a_roster, an_image
from payloads import a_look, a_look_picture, a_look_source
from playwright.sync_api import expect

from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWork

TANTRA = "Q20267229"
HUNTERS = "Q500985"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
LOOK = "**/api/registry/works/*/look"
PICTURES = "**/look/pictures/**"
#: Long enough for several two-second polls on a loaded runner.
POLLS = 15_000

BILLE = RegistryCreator(qid=ItemId("Q5001"), name=RegistryText("Ejler Bille"))

#: How a find of Tantra-Vision is named: by its museum, never its plugin id.
TANTRA_NAMED = "Tantra-Vision, by Ejler Bille, from SMK, National Gallery of Denmark, 2,201 × 2,221 px"


class Smk:
    """SMK as a finder: it holds *Tantra-Vision* at 2,201 × 2,221 and serves a real JPEG."""

    provider = "smk"

    def find_images(self, query: ImageQuery) -> tuple[FoundImage, ...]:
        if query.title != "Tantra-Vision":
            return ()
        return (
            an_image(
                "Tantra-Vision",
                artist="Ejler Bille",
                width=2201,
                height=2221,
                provider="smk",
                url="https://open.smk.dk/artwork/image/KMS8010",
            ),
        )

    def fetch_preview(self, url: str) -> bytes | None:
        return a_decodable_jpeg()


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            TANTRA: RegistryWork(qid=ItemId(TANTRA), title=RegistryText("Tantra-Vision"), sitelinks=3, creators=(BILLE,)),
            HUNTERS: RegistryWork(
                qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39, image=COMMONS, creators=(BILLE,)
            ),
        }
    )


@pytest.fixture
def sources():
    return a_roster(Smk())


def _rows(ui):
    """The sources' rows, whose words `expect` compares with their whitespace folded."""
    return ui.page.locator("#view .look-source")


def _summary(ui):
    return ui.page.locator("#view .look [role=status]")


def _key(n: int) -> str:
    return f"{n:x}" * 64


# -- end to end ------------------------------------------------------------------------


def test_a_work_wikidata_pictures_with_nothing_shows_what_smk_holds_without_a_get(ui):
    """*Tantra-Vision*'s shape: no Wikidata picture, so the first find takes the top."""
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view .look-source:has-text('1 found')", timeout=POLLS)

    expect(_rows(ui)).to_have_text(["SMK, National Gallery of Denmark ● 1 found"], use_inner_text=True)
    top = ui.page.locator("#view .look-top img.detail-image")
    top.wait_for()
    expect(top).to_have_attribute("src", re.compile(re.escape("/api/registry/works/Q20267229/look/pictures/")))
    expect(top).to_have_attribute("src", re.compile(re.escape("?size=large") + "$"))
    ui.page.wait_for_function("() => document.querySelector('#view .look-top img').naturalWidth > 0")
    expect(ui.page.locator("#view .look-pictures img")).to_have_count(1)
    expect(_summary(ui)).to_have_text("1 picture found, from 1 source.", use_inner_text=True)
    assert ui.requests_matching("/api/gets") == [], "nothing was got"
    expect(ui.page.locator("#view .look-top .picture-size")).to_have_text(
        "2,201 × 2,221 px, from SMK, National Gallery of Denmark", use_inner_text=True
    )


def test_the_line_under_get_says_what_the_panel_is_and_what_a_get_adds(ui):
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view button:text-is('Get this work')")

    line = "These are what the sources hold now; getting the work records them and spends nothing."
    expect(ui.page.locator("#view p.muted", has_text=line)).to_have_count(1)
    expect(ui.page.locator("#view h2#look-heading")).to_have_text("What the image sources hold", use_inner_text=True)


# -- across polls ------------------------------------------------------------------------


def test_rows_fill_in_over_successive_polls_and_focus_never_moves(ui):
    first = a_look_picture(_key(1))
    ui.serve(
        LOOK,
        [
            a_look(TANTRA, [a_look_source("smk"), a_look_source("met")]),
            a_look(TANTRA, [a_look_source("smk", "found", found=1), a_look_source("met")], [first]),
            a_look(TANTRA, [a_look_source("smk", "found", found=1), a_look_source("met", "holds_none")], [first]),
        ],
    )
    ui.serve_image(PICTURES)
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view .look-source:has-text('Asking…')")
    expect(_rows(ui)).to_have_text(
        ["SMK, National Gallery of Denmark ◌ Asking…", "Metropolitan Museum of Art ◌ Asking…"], use_inner_text=True
    )

    button = ui.page.locator("#view .look-pictures button.enlargeable")
    button.wait_for(timeout=POLLS)
    button.focus()
    ui.page.wait_for_selector("#view .look-source:has-text('Holds none')", timeout=POLLS)

    expect(_rows(ui)).to_have_text(
        ["SMK, National Gallery of Denmark ● 1 found", "Metropolitan Museum of Art ○ Holds none"], use_inner_text=True
    )
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == (f"Enlarge {TANTRA_NAMED}")
    looks = len(ui.requests_matching("/look"))
    ui.page.wait_for_timeout(2500)  # sleep: proves a page whose sources have all answered asks no more for a poll's time
    assert len(ui.requests_matching("/look")) == looks, "once no source is asking, the page stops polling"


def test_the_live_region_says_each_change_once_and_never_the_same_text_twice(ui):
    asking = a_look(TANTRA, [a_look_source("smk"), a_look_source("met", "holds_none")])
    ui.serve(
        LOOK,
        [
            asking,
            asking,
            a_look(
                TANTRA,
                [a_look_source("smk", "holds_none"), a_look_source("met", "holds_none")],
                note="No image source holds a picture of this work now.",
            ),
        ],
    )
    ui.page.add_init_script("""
        window.said = [];
        new MutationObserver((changes) => {
          for (const change of changes) {
            const region = change.target.closest ? change.target.closest('.look [role=status]')
              : change.target.parentElement && change.target.parentElement.closest('.look [role=status]');
            if (region) window.said.push(region.textContent);
          }
        }).observe(document, { subtree: true, childList: true, characterData: true });
        """)
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view .look [role=status]:has-text('No image source holds')", timeout=POLLS)

    said = ui.page.evaluate("() => window.said")
    assert said == [
        "Asking the image sources…",
        "Asking the image sources: 1 of 2 answered.",
        "No image source holds a picture of this work now.",
    ], said
    expect(ui.page.locator("#view .look [role=status]")).to_have_count(1)


def test_the_first_picture_to_arrive_takes_the_top_and_is_never_swapped(ui):
    found_first = a_look_picture(_key(1), provider="met")
    better_later = a_look_picture(_key(2))
    ui.serve(
        LOOK,
        [
            a_look(TANTRA, [a_look_source("smk"), a_look_source("met", "found", found=1)], [found_first]),
            a_look(
                TANTRA,
                [a_look_source("smk", "found", found=1), a_look_source("met", "found", found=1)],
                [better_later, found_first],
            ),
        ],
    )
    ui.serve_image(PICTURES)
    ui.open(f"#work/{TANTRA}")
    top = ui.page.locator("#view .look-top img.detail-image")
    top.wait_for(timeout=POLLS)
    expect(top).to_have_attribute("src", re.compile(re.escape(_key(1))))

    ui.page.wait_for_selector("#view .look-source:has-text('SMK') >> text=1 found", timeout=POLLS)
    # Not swapped *yet* is the claim, so it is the old picture still there, asked
    # after the poll that brought a better one has been drawn (the row above).
    expect(top, "the top picture was swapped for a better one").to_have_attribute("src", re.compile(re.escape(_key(1))))
    cards = ui.page.locator("#view .look-pictures img")
    expect(cards.nth(0), "the better find goes in before the one drawn first").to_have_attribute(
        "src", re.compile(re.escape(_key(2)))
    )
    expect(cards.nth(1), "the better find goes in before the one drawn first").to_have_attribute(
        "src", re.compile(re.escape(_key(1)))
    )


def test_wikidata_s_picture_stays_on_top_when_there_is_one(ui, pictures_load):
    ui.serve(LOOK, a_look(HUNTERS, [a_look_source("smk", "found", found=1)], [a_look_picture(_key(3))]))
    ui.serve_image(PICTURES)
    ui.open(f"#work/{HUNTERS}")
    ui.page.wait_for_selector("#view .look-pictures img")

    tops = ui.page.locator("#view .look-top img")
    expect(tops).to_have_count(1)
    expect(tops.first).to_have_attribute("src", f"{COMMONS}?width=1200")


# -- what each source said ------------------------------------------------------------------


def test_each_source_s_answer_is_a_glyph_and_words(ui):
    ui.serve(
        LOOK,
        a_look(
            TANTRA,
            [
                a_look_source("met", "refused", refusals=["identity_refused"]),
                a_look_source("artic", "unreachable"),
                a_look_source("commons", "cannot"),
                a_look_source("moma", "holds_none", refusals=["size_unknown"]),
                a_look_source("aic", "holds_none", refusals=["not_held"]),
            ],
            note="No image source that answered holds a picture of this work now.",
        ),
    )
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view .look-source:has-text('Holds none')")

    expect(_rows(ui)).to_have_text(
        [
            "Metropolitan Museum of Art ⊘ Holds a work by this title by another artist; not shown",
            "Art Institute of Chicago ▲ Could not be asked; trying again in 10 minutes",
            "Wikimedia Commons — Can't look this work up",
            "moma ○ Holds this work but gives no size for it; not shown",
            "aic ○ Holds none",
        ],
        use_inner_text=True,
    )
    expect(_summary(ui)).to_have_text("No image source that answered holds a picture of this work now.", use_inner_text=True)
    expect(ui.page.locator("#view .look-pictures li")).to_have_count(0)
    expect(ui.page.locator("#view .look-top", has_text="No free image of this work is known.")).to_have_count(1)


@pytest.mark.parametrize(
    ("state", "note"),
    [
        ("no_sources", "No image source is configured to ask."),
        ("being_got", "A Get is already asking the sources about this work."),
    ],
)
def test_a_look_that_asks_nothing_says_why(ui, state, note):
    ui.serve(LOOK, a_look(TANTRA, state=state, note=note))
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector(f"#view .look [role=status]:has-text('{note}')")

    expect(ui.page.locator("#view .look-source")).to_have_count(0)


def test_a_look_the_server_cannot_answer_says_so_and_stops(ui):
    ui.serve(LOOK, (500, {"error": "boom"}))
    ui.open(f"#work/{TANTRA}")
    ui.page.wait_for_selector("#view .look [role=status]:has-text('could not be asked just now')")


# -- pictures ----------------------------------------------------------------------------


def test_six_pictures_are_shown_then_show_n_more(ui):
    pictures = [a_look_picture(_key(n), url=f"https://smk.example/{n}") for n in range(1, 9)]
    ui.serve(LOOK, a_look(TANTRA, [a_look_source("smk", "found", found=8)], pictures))
    ui.serve_image(PICTURES)
    ui.open(f"#work/{TANTRA}")
    more = ui.page.locator("#view .look button:text-is('Show 2 more')")
    more.wait_for()

    expect(ui.page.locator("#view .look-pictures > li:visible")).to_have_count(6)
    more.click()
    expect(ui.page.locator("#view .look-pictures > li:visible")).to_have_count(8)
    expect(more).to_be_hidden()
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')").startswith("Enlarge Tantra-Vision")


def test_a_picture_that_will_not_load_says_so_in_its_place(ui):
    ui.serve(LOOK, a_look(TANTRA, [a_look_source("smk", "found", found=1)], [a_look_picture(_key(4))]))
    ui.page.route(PICTURES, lambda route: route.fulfill(status=404, content_type="application/json", body='{"error": "x"}'))
    ui.open(f"#work/{TANTRA}")

    ui.page.wait_for_selector("#view .look-pictures :text('Its picture could not be loaded just now.')")
    expect(ui.page.locator("#view .look-pictures button.enlargeable")).to_have_count(0)


def test_a_picture_enlarges_in_place_and_escape_returns_to_it(ui):
    ui.serve(LOOK, a_look(TANTRA, [a_look_source("smk", "found", found=1)], [a_look_picture(_key(5))]))
    ui.serve_image(PICTURES)
    ui.open(f"#work/{TANTRA}")
    button = ui.page.locator("#view .look-pictures button.enlargeable")
    button.click()

    dialog = ui.page.locator("dialog.enlarged")
    dialog.wait_for()
    expect(dialog.locator("img")).to_have_attribute("src", re.compile(re.escape(f"/look/pictures/{_key(5)}?size=large") + "$"))
    expect(dialog).to_have_attribute("aria-label", TANTRA_NAMED)
    ui.page.keyboard.press("Escape")
    dialog.wait_for(state="detached")
    assert ui.page.evaluate("() => document.activeElement.classList.contains('enlargeable')")


def test_a_find_states_its_pixels_fit_source_and_why(ui):
    ui.serve(LOOK, a_look(TANTRA, [a_look_source("smk", "found", found=1)], [a_look_picture(_key(6))]))
    ui.serve_image(PICTURES)
    ui.open(f"#work/{TANTRA}")
    card = ui.page.locator("#view .look-pictures > li")
    card.wait_for()

    expect(card).to_contain_text("2,201 × 2,221 px", use_inner_text=True)
    expect(card).to_contain_text("From SMK, National Gallery of Denmark", use_inner_text=True)
    expect(card).to_contain_text("matching the requested title and artist", use_inner_text=True)
    expect(card, "a picture meeting the minimum carries no badge").not_to_contain_text("minimum", use_inner_text=True)
    expect(card.locator("img")).to_have_attribute("alt", TANTRA_NAMED)
