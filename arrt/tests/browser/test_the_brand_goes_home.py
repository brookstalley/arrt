"""The product's name in the top bar goes home, as it does in every *arr app.

`information-architecture.md` § The *arr layout: the library is the home page,
and the name in the top bar is a link to it. A link rather than a button
(§ Direction, navigation is a link), so it opens in a new tab and copies as an
address. Pressed on the home page itself it still returns the page to its
unfiltered state, as the sidebar's own link does.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

#: The route table as `app.js` declares it, read from the file, so a screen
#: routed tomorrow is in these tests the day it is routed.
ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))

#: The home page: the first sidebar page in the table, which is where the
#: router decides it.
HOME = next(key for key, route in ROUTES.items() if route.page)

BRAND = ".topbar .brand a"


def address(route):
    """An address that opens `route`: a placeholder id where one is required."""
    return f"#{route.key}/not-a-real-id" if route.detail == "required" else f"#{route.key}"


def test_home_is_artworks():
    """The test's own premise, so a reordered table fails here by name."""
    assert HOME == "collection"


def test_the_name_is_a_link_to_the_home_page(ui, seeded_service):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    brand = ui.page.locator(BRAND)
    assert brand.inner_text() == "Arrt"
    assert brand.get_attribute("href") == f"#{HOME}"
    # Still not a heading: each screen's own heading is the page's one h1.
    assert ui.page.locator(".topbar h1").count() == 0


@pytest.mark.parametrize("route", list(ROUTES.values()), ids=list(ROUTES))
def test_the_name_goes_home_from_every_route(ui, seeded_service, route):
    ui.open(address(route))
    ui.page.wait_for_selector("#view h1")

    ui.page.click(BRAND)

    ui.page.wait_for_function("(home) => window.location.hash === home", arg=f"#{HOME}")
    ui.page.wait_for_function("() => document.title === 'Artworks - Arrt'")
    ui.page.wait_for_selector("ul.grid li.card")


def test_pressed_on_a_filtered_artworks_it_clears_the_filter(ui, seeded_service):
    """No `hashchange` fires for an address already showing, so this is the
    case only the click handler's `go` can answer: the filter must go."""
    ui.open(f"#{HOME}?q=Nighthawks&sort=title")
    ui.page.wait_for_selector("ul.grid li.card")
    filtered = ui.page.locator("ul.grid li.card").count()

    ui.page.click(BRAND)

    ui.page.wait_for_function("(home) => window.location.hash === home", arg=f"#{HOME}")
    ui.page.wait_for_selector("ul.grid li.card")
    # More than the one work the search matched: the whole library is back.
    ui.page.wait_for_function("(n) => document.querySelectorAll('ul.grid li.card').length > n", arg=filtered)


def test_a_modified_click_is_left_to_the_browser(ui, seeded_service):
    """Ctrl- or Cmd-click is a new tab: the handler must not take it in place."""
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    for modifier in ("ctrlKey", "metaKey", "shiftKey"):
        taken = ui.page.evaluate(
            """([selector, modifier]) => {
                const link = document.querySelector(selector);
                let prevented = null;
                // Registered after the router's handler, so it runs after it: it
                // reads what that handler did, then keeps the browser from
                // following the link, which would open a tab mid-test.
                link.addEventListener('click', (e) => { prevented = e.defaultPrevented; e.preventDefault(); }, { once: true });
                link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, [modifier]: true }));
                return prevented;
            }""",
            [BRAND, modifier],
        )
        assert taken is False, modifier
    assert ui.page.evaluate("() => location.hash") == "#walls"


def test_on_a_phone_the_name_is_still_the_way_home(ui, seeded_service):
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")

    assert ui.page.locator(BRAND).is_visible()
    ui.page.click(BRAND)
    ui.page.wait_for_function("(home) => window.location.hash === home", arg=f"#{HOME}")


def test_pressed_on_the_home_page_itself_it_arrives_afresh(ui, seeded_service):
    """The address does not change, so no `hashchange` fires and only the click
    handler's `go` can repaint. A page arrived at afresh is out of Select mode,
    with nothing ticked; one left alone keeps both."""
    ui.open(f"#{HOME}")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("#view button.select-toggle")
    ui.page.locator("ul.grid li.card input.tile-select").first.check()
    assert ui.page.inner_text("#view button.select-toggle") == "Stop selecting"

    ui.page.click(BRAND)

    ui.page.wait_for_function("() => document.querySelector('#view button.select-toggle')?.textContent === 'Select'")
    assert ui.page.locator("ul.grid li.card input.tile-select:checked").count() == 0
    assert ui.page.evaluate("() => location.hash") == f"#{HOME}"
