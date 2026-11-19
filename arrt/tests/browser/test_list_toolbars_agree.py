"""The list pages share one toolbar, and a way back is a link.

`design-direction.md` § Component Patterns, "How a page reads" (ruling 1 of
2026-10-27): acts on the left; View, Sort, Filters and Select on the right; the
count in the page's line of facts; a detail page's way back a breadcrumb link
above the name, never a button. Audit 6 (2026-11-19) found no two list pages
agreeing (finding 12) and every back link drawn as a button (finding 13).

**Read from the pages, not from a list copied here.** Each control is named by
the words on its face ("View: Posters" is View), which is what a reader goes
by and what no screen's markup chose, and the pages are held to each other: a
pair of controls two pages both show stands in one order on both. A copied list
would agree with whichever page it was copied from.
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect


@pytest.fixture
def dali(seeded_service):
    artist = next(artist for artist in seeded_service.list_artists() if artist.name == "Salvador Dalí")
    work = next(e.artwork for e in seeded_service.list_artworks().entries if e.artwork.title == "The Persistence of Memory")
    return artist, work


#: Each list page, and what it has painted once its toolbar is whole.
def list_pages(dali):
    artist, _work = dali
    return {
        "Artworks": ("#collection", "ul.grid li"),
        "Artists": ("#artist", "ul.artist-posters li"),
        "Search": ("#search?q=persistence", "#view button.select-toggle:visible"),
        "Artist": (f"#artist/{artist.id}", "#view button.select-toggle:visible"),
    }


#: What a control is, from the words on its face.
NAME_OF = """(button) => {
  const words = button.textContent.trim();
  if (words.startsWith('View:')) return 'view';
  if (words.startsWith('Sort:')) return 'sort';
  if (/^(Hide|Show) filters$/.test(words)) return 'filters';
  if (words === 'Select' || words === 'Stop selecting') return 'select';
  return `act: ${words}`;
}"""


def sides(ui):
    """The names of the visible controls on each side of the page's toolbar, in order."""
    return ui.page.locator("#view .page-toolbar").evaluate(f"""(bar) => {{
          const name = {NAME_OF};
          const read = (side) => [...side.querySelectorAll('button')]
            .filter((button) => button.offsetParent !== null && !button.closest('.selection, .toolbar-menu'))
            .map(name);
          return {{
            left: read(bar.querySelector('.page-toolbar-actions')),
            right: read(bar.querySelector('.page-toolbar-controls')),
          }};
        }}""")


def open_list(ui, address, painted):
    ui.open(address)
    expect(ui.page.locator(painted).first).to_be_visible()
    expect(ui.page.locator("#view .page-toolbar")).to_have_count(1)


def test_the_list_pages_hold_their_controls_in_one_order_on_the_right(ui, dali):
    read = {}
    for page, (address, painted) in list_pages(dali).items():
        open_list(ui, address, painted)
        read[page] = sides(ui)

    controls = {"view", "sort", "filters", "select"}
    for page, side in read.items():
        assert not controls & set(side["left"]), f"{page} has a control among its acts: {side}"
        assert all(name in controls for name in side["right"]), f"{page} has an act among its controls: {side}"
        if "select" in side["right"]:
            assert side["right"][-1] == "select", f"{page}'s Select is not last on the right: {side}"

    # The pages agree with each other: no two controls in one order on one page
    # and the other order on another.
    before = {}
    for page, side in read.items():
        for at, first in enumerate(side["right"]):
            for second in side["right"][at + 1 :]:
                before.setdefault((first, second), page)
    clashes = [(pair, page, before[pair[::-1]]) for pair, page in before.items() if pair[::-1] in before]
    assert not clashes, f"two pages order the same controls two ways: {clashes}"
    # Enough to compare: the pages between them show every control, and Select on three.
    assert set().union(*(side["right"] for side in read.values())) == controls
    assert sum("select" in side["right"] for side in read.values()) == 3


def test_each_list_page_says_its_count_once_above_its_toolbar(ui, dali):
    """The count in one place: the line of facts under the page's name, before
    its toolbar, and not again in the toolbar or beside the list."""
    for page, (address, painted) in list_pages(dali).items():
        open_list(ui, address, painted)
        facts = ui.page.locator("#view .page-facts")
        expect(facts, page).to_have_count(1)
        expect(facts, page).to_have_text(re.compile(r"^\d"))
        precedes = facts.evaluate(
            "(line) => Boolean(line.compareDocumentPosition(document.querySelector('#view .page-toolbar'))"
            " & Node.DOCUMENT_POSITION_FOLLOWING)"
        )
        assert precedes, f"{page}'s count is not above its toolbar"


@pytest.mark.parametrize(
    "opened",
    ["work from Artworks", "artist from Artists", "results from Walls"],
)
def test_no_way_back_is_drawn_as_a_button(ui, dali, opened):
    """Audit 6, finding 13: "← Artworks" and its kin were links in the act's
    bordered shape. Read from what is drawn as well as from the class, since a
    border is what makes a link look like a button."""
    artist, work = dali
    address = {
        "work from Artworks": f"#work/{work.id}",
        "artist from Artists": f"#artist/{artist.id}",
        "results from Walls": "#search?q=persistence&from=walls",
    }[opened]
    ui.open(address)
    back = ui.page.locator("#view > p:first-child a")
    expect(back).to_have_text(re.compile(r"^← "))
    expect(back).to_have_class("back-link")
    expect(back).to_have_css("border-top-width", "0px")
    expect(back).not_to_have_css("text-decoration-line", "underline")
    # A breadcrumb: the page's first thing, above its name.
    expect(ui.page.locator("#view > p.breadcrumb:first-child")).to_have_count(1)
    above = back.evaluate(
        "(link) => Boolean(link.compareDocumentPosition(document.querySelector('#view h1'))"
        " & Node.DOCUMENT_POSITION_FOLLOWING)"
    )
    assert above, "the way back is not above the page's name"
