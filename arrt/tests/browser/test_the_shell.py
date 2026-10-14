"""The shell as drawn: the sidebar's edge runs the page's whole length, and the
search's magnifier is a button with a name.

The sidebar is sticky, so it is only as tall as the window. Its edge used to be
a border on the sidebar itself, and on any page longer than the window it
stopped partway down. Nothing in the DOM says so, because the elements are
all present and correct, so the first test reads the pixels.
"""

import io

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from PIL import Image


def test_the_sidebar_edge_reaches_the_bottom_of_a_page_longer_than_the_window(ui):
    # A short window makes the suite's small library a page several windows long.
    ui.page.set_viewport_size({"width": 1280, "height": 360})
    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")
    ui.page.wait_for_load_state("networkidle")
    edge, border, height = ui.page.evaluate("""() => {
          const probe = document.createElement('span');
          probe.style.color = 'var(--border)';
          document.body.append(probe);
          const border = getComputedStyle(probe).color.match(/\\d+/g).slice(0, 3).map(Number);
          probe.remove();
          const sidebar = document.querySelector('nav.sidebar').getBoundingClientRect();
          return [Math.round(sidebar.right) - 1, border, document.documentElement.scrollHeight];
        }""")
    assert height > 360 + 120, "the page must be longer than the window, or this proves nothing"
    shot = Image.open(io.BytesIO(ui.page.screenshot(full_page=True))).convert("RGB")
    near_the_bottom = shot.getpixel((edge, shot.height - 4))
    assert list(near_the_bottom) == border


def test_the_magnifier_is_the_search_button_and_says_so(ui):
    ui.open("#collection")
    button = ui.page.locator("#search-form").get_by_role("button", name="Search")
    assert button.count() == 1
    assert button.is_visible()
    ui.page.fill("#search", "chicago")
    button.click()
    ui.page.wait_for_url("**#search*")


def test_a_search_pressed_while_the_client_starts_is_still_a_search(ui):
    """The search box answers from the moment the client runs, not after its start-up reads.

    The client reads the installed sources' names before its first paint. A
    search pressed while that read was still out went to the browser, which
    submitted the form as a page load (`/?q=…`) instead of opening the results.
    Held here by answering that read only after the search is pressed.
    """
    held = []
    ui.page.route("**/api/sources", lambda route: held.append(route))
    ui.page.goto(f"{ui.base_url}/#collection")
    # The client is running once it has asked for the sources.
    while not held:
        ui.page.wait_for_timeout(50)
    ui.page.fill("#search", "chicago")
    ui.page.locator("#search-form").get_by_role("button", name="Search").click()
    for route in held:
        route.continue_()
    ui.page.unroute("**/api/sources")
    ui.page.wait_for_url("**#search*")
    assert "q=chicago" in ui.page.evaluate("() => window.location.hash")
