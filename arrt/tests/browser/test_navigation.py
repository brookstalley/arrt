"""Navigation: a link where it goes somewhere, the top of the page where it lands,
the place it left where Back returns, and a name for every page.

`information-architecture.md` § Direction rules that navigation is a link and an
act is a button. The walkthrough that led to the rule (`ux-review-2026-10.md`
findings 4, 5 and 21) found three costs of the buttons it replaced, and each is
pinned here at the screen where it was found: a work opened from low on
Artworks opened part-way down its own page, Back to Artworks returned to the top
of the grid rather than to the card, and every page in the browser's tabs and
history read "Arrt".
"""

import re
import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

#: The route table as `app.js` declares it, read from the file rather than
#: copied, so a screen added tomorrow is in these tests the day it is routed.
ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))

#: The card a curator opens from well below the fold. Twenty, because that is
#: the card the walkthrough measured Back losing (68 Tabs from the top).
CARD = 20


@pytest.fixture
def a_long_artworks(service, seeded_service):
    """Enough works that card 20 sits below the fold of a desktop window."""
    for number in range(40):
        service.add_artwork(title=f"Study number {number:03d}")


def card_link(ui, number):
    """The title link of the `number`th card, counting from one."""
    return ui.page.locator("ul.grid li.card").nth(number - 1).locator(".card-title a")


def test_every_card_opens_its_work_through_a_link(ui, a_long_artworks):
    """A card's title is an `<a href>` to the work's own address, and no card
    opens its work by a button.

    Not only clickable: an `href` is what opens in a new tab, copies as an
    address and is announced as a link, which is what the norm is for.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    first = ui.page.locator("ul.grid li.card").first
    work_id = first.get_attribute("data-artwork")

    assert first.locator(".card-title a").get_attribute("href") == f"#work/{work_id}"
    assert ui.page.locator("li.card .card-title button, li.card button.card-image").count() == 0


def test_a_cards_picture_opens_its_work_through_a_link(ui, work_with_an_image):
    """The picture as well as the title, for the curator who points at the art."""
    work = work_with_an_image()
    ui.open("#collection")
    ui.page.wait_for_selector(f"li.card[data-artwork='{work.id}'] img")
    assert ui.page.locator(f"li.card[data-artwork='{work.id}'] a.card-image").get_attribute("href") == f"#work/{work.id}"


def test_a_work_opened_from_card_20_opens_at_its_title(ui, a_long_artworks):
    """The page lands at its top, with the work's title in view and focus on the view.

    Before, the new screen kept the scroll of the grid it replaced, so a work
    opened from low on the list opened at its sources table.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    target = card_link(ui, CARD)
    title = target.inner_text()
    target.scroll_into_view_if_needed()
    assert ui.page.evaluate("() => window.scrollY") > 0, "card 20 was above the fold, so this test cannot see a scroll kept"

    target.click()
    ui.page.wait_for_selector(f"#view h1:text-is('{title}')")
    ui.page.wait_for_function("() => document.activeElement && document.activeElement.id === 'view'")

    assert ui.page.evaluate("() => window.scrollY") == 0
    heading_top = ui.page.locator("#view h1").evaluate("(node) => node.getBoundingClientRect().top")
    assert 0 <= heading_top < ui.page.viewport_size["height"], "the work's title is not on screen"


def test_back_returns_to_card_20_with_focus_on_it(ui, a_long_artworks):
    """Back puts the curator where they were, on the card they opened.

    Both halves: the grid is scrolled back to where it was, and the keyboard is
    on the link that was followed — not at the top of a forty-card grid.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    target = card_link(ui, CARD)
    title = target.inner_text()
    target.scroll_into_view_if_needed()
    left_at = ui.page.evaluate("() => window.scrollY")

    target.click()
    ui.page.wait_for_selector(f"#view h1:text-is('{title}')")
    ui.page.go_back()
    ui.page.wait_for_function(
        "(title) => document.activeElement && document.activeElement.closest('.card-title')"
        " && document.activeElement.textContent === title",
        arg=title,
    )

    assert ui.page.evaluate("() => window.scrollY") == left_at
    box = card_link(ui, CARD).bounding_box()
    assert box is not None
    assert 0 <= box["y"] < ui.page.viewport_size["height"], "card 20 has focus but is off screen"


def test_the_way_back_link_returns_to_card_20_as_back_does(ui, a_long_artworks):
    """*← Artworks* is Back when Artworks is the entry behind: the same sort, the
    same scroll, and the card that was opened in focus."""
    ui.open("#collection?sort=newest")
    ui.page.wait_for_selector("ul.grid li.card")
    target = card_link(ui, CARD)
    title = target.inner_text()
    target.scroll_into_view_if_needed()
    left_at = ui.page.evaluate("() => window.scrollY")
    target.click()
    ui.page.wait_for_selector(f"#view h1:text-is('{title}')")

    ui.page.click("#view a:text-is('← Artworks')")
    ui.page.wait_for_function(
        "(title) => document.activeElement && document.activeElement.textContent === title"
        " && document.activeElement.closest('.card-title')",
        arg=title,
    )

    assert ui.page.url.endswith("#collection?sort=newest")
    assert ui.page.evaluate("() => window.scrollY") == left_at


def test_the_way_back_link_from_a_bookmark_is_a_plain_link(ui, service, seeded_service):
    """With no Artworks behind it, the link goes to Artworks rather than back out of the product."""
    work = service.add_artwork(title="Bookmarked")
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector("#view h1:text-is('Bookmarked')")
    ui.page.click("#view a:text-is('← Artworks')")
    ui.page.wait_for_selector("ul.grid li.card")
    assert ui.page.url.endswith("#collection")


def test_a_new_arrival_starts_at_the_top_and_does_not_restore(ui, a_long_artworks):
    """A page arrived at afresh starts at its top, whatever the last visit left.

    The member that makes restoration wrong if it over-fires: the same screen
    reached by a link rather than by Back.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    target = card_link(ui, CARD)
    title = target.inner_text()
    target.scroll_into_view_if_needed()
    target.click()
    ui.page.wait_for_selector(f"#view h1:text-is('{title}')")

    # Artworks again, by the sidebar's link: a new history entry.
    ui.page.click("nav.sidebar a.section-link[data-view='collection']")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.wait_for_function("() => document.activeElement && document.activeElement.id === 'view'")

    assert ui.page.evaluate("() => window.scrollY") == 0


def test_a_link_opened_with_a_modifier_is_left_to_the_browser(ui, a_long_artworks):
    """Ctrl-click or Cmd-click is a new tab, so this page stays where it is."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    target = card_link(ui, 1)
    with ui.page.context.expect_page() as opened:
        target.click(modifiers=["ControlOrMeta"])
    work_id = ui.page.locator("ul.grid li.card").first.get_attribute("data-artwork")

    assert opened.value.url.endswith(f"#work/{work_id}")
    assert ui.page.url.endswith("#collection")


# -- titles and headings ------------------------------------------------------


def declared_title(key):
    """The title a route declares: its own `title`, else its sidebar `page` label.

    Read from the entry in `app.js`, so the expectation is the table's and not a
    second list written here.
    """
    body = ux_walk._object_literal(ux_walk._without_comments(ux_walk.APP_JS.read_text(encoding="utf-8")), "const ROUTES = ")
    opener = re.search(rf"\b{key}\s*:\s*\{{", body)
    entry = ux_walk._object_literal(body[opener.start() :], f"{key}:")
    found = re.search(r'\btitle\s*:\s*"([^"]+)"', entry) or re.search(r'\bpage\s*:\s*"([^"]+)"', entry)
    return found.group(1) if found else None


def address(route):
    """An address that opens `route`: a placeholder id where one is required."""
    return f"#{route.key}/not-a-real-id" if route.detail == "required" else f"#{route.key}"


def test_every_route_declares_a_title_no_other_route_has():
    titles = {key: declared_title(key) for key in ROUTES}
    assert all(titles.values()), f"routes with no title: {[k for k, t in titles.items() if not t]}"
    assert len(set(titles.values())) == len(titles), f"routes sharing a title: {titles}"


@pytest.mark.parametrize("route", list(ROUTES.values()), ids=list(ROUTES))
def test_every_route_sets_its_own_title(ui, route):
    """Every routed screen names the page, so a tab, a bookmark and a history list
    can tell it from the others — rather than all reading "Arrt".

    Required-id routes are opened at an id nothing has: the title a screen has
    before it knows what it shows is the route's, and that is what is pinned.
    """
    ui.open(address(route))
    ui.page.wait_for_function("(title) => document.title === title", arg=f"{declared_title(route.key)} - Arrt")


@pytest.mark.parametrize("route", [r for r in ROUTES.values() if r.page], ids=[k for k, r in ROUTES.items() if r.page])
def test_each_page_heading_is_its_one_h1(ui, route):
    """The screen's own heading is the document's only `h1`; the product name is not one."""
    ui.open(address(route))
    ui.page.wait_for_selector("#view h1")
    assert ui.page.locator("h1").count() == 1
    assert ui.page.locator(".topbar .brand").evaluate("(node) => node.tagName") != "H1"


def test_a_work_page_is_titled_by_the_work(ui, a_long_artworks):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("li.card .card-title a:text-is('Nighthawks')")
    ui.page.wait_for_function("() => document.title === 'Nighthawks - Arrt'")
    assert ui.page.locator("#view h1").inner_text() == "Nighthawks"


def test_an_artist_page_is_titled_by_the_artist(ui, seeded_service):
    ui.open("#artist")
    ui.page.click("a:text-is('Salvador Dalí')")
    ui.page.wait_for_function("() => document.title === 'Salvador Dalí - Arrt'")


def test_a_paint_that_lost_its_view_does_not_retitle_the_next(ui, service, seeded_service):
    """A slow work page finishing after the curator moved on keeps its name to itself."""
    work = service.add_artwork(title="Slow to arrive")
    held = []

    # A function of our own rather than `held.append`: Playwright wraps the
    # handler it is given, and a builtin cannot be wrapped.
    def hold(route):
        held.append(route)

    ui.page.route(f"**/api/works/{work.id}", hold)
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_function("() => document.title === 'Work - Arrt'")
    ui.page.click("nav.sidebar a.section-link[data-view='walls']")
    ui.page.wait_for_function("() => document.title === 'Walls - Arrt'")

    with ui.page.expect_response(f"**/api/works/{work.id}"):
        held[0].continue_()
    # The response has landed; give its paint the turn it would take.
    ui.page.evaluate("() => new Promise((resolve) => setTimeout(resolve, 100))")
    assert ui.page.title() == "Walls - Arrt"
