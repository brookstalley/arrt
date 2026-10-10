"""Settings opens on an index of its pages, and Taste is the last of them.

As Sonarr's and Radarr's v4 /settings: the sidebar's Settings is a page of its
own, listing Clients, Sources and Taste in the sidebar's order, each a link with
one line saying what it holds. Taste is headed "Taste", and its help names every
control that records a judgment, by the words that control carries.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_taste, an_affinity

#: The pages, in the order the index and the sidebar list them.
PAGES = [("clients", "Clients"), ("sources", "Sources"), ("taste", "Taste")]


def test_the_sidebars_settings_opens_the_index(ui):
    ui.open("#walls")
    ui.page.wait_for_selector("nav.sidebar a.section-link")

    ui.page.click("nav.sidebar li.section[data-section='settings'] a.section-link")
    ui.page.wait_for_selector("#view h1:text-is('Settings')")

    assert ui.page.evaluate("() => window.location.hash") == "#settings"
    # The section's link is the page's own, so it is the one marked current.
    current = ui.page.locator("nav.sidebar [aria-current='page']")
    assert current.count() == 1
    assert current.get_attribute("data-view") == "settings"


def test_the_index_lists_each_page_as_a_link_with_what_it_holds(ui):
    """Every page, in order, and each row a link rather than a button: it navigates."""
    ui.open("#settings")
    ui.page.wait_for_selector("ul.settings-index")

    rows = ui.page.locator("ul.settings-index > li")
    assert rows.count() == len(PAGES)
    for index, (view, label) in enumerate(PAGES):
        row = rows.nth(index)
        anchor = row.locator("a")
        assert anchor.count() == 1
        assert anchor.inner_text() == label
        assert anchor.get_attribute("href") == f"#{view}"
        assert row.locator("p").inner_text().strip()
    assert ui.page.locator("ul.settings-index button").count() == 0


def test_following_a_row_opens_its_page(ui):
    ui.open("#settings")
    ui.page.click("ul.settings-index a:text-is('Sources')")
    ui.page.wait_for_selector("#view h1:has-text('Sources')")

    assert ui.page.evaluate("() => window.location.hash").startswith("#sources")


def test_taste_is_headed_taste(ui):
    ui.serve("**/api/affinities*", a_taste([an_affinity()]))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    assert ui.page.inner_text("#view h1") == "Taste"


#: Every control that records a judgment, in its own words, with where it is.
#: Grep `recordReaction` and `/api/affinities` in the client for the list.
WAYS = [
    "more like this",  # the reactions on what Ask offers (core/taste.js CARD_REACTIONS)
    "not this",
    "More like this",  # an artist's page
    "Tell me more",
    "More of this",  # a correction on Taste itself
    "Keep showing me",
]


@pytest.mark.parametrize("held", [False, True], ids=["empty", "populated"])
def test_the_help_names_every_way_taste_is_recorded(ui, held):
    """On the empty page and the full one, since either is where the question is asked."""
    ui.serve("**/api/affinities*", a_taste([an_affinity()] if held else []))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity" if held else ".empty")

    named = ui.page.locator(".taste-help em").all_inner_texts()
    for words in WAYS:
        assert words in named, f"the help does not name {words!r}: {named}"
    # Ask's cards stopped offering it on 2026-10-09; a help naming it sends the
    # curator looking for a control that is not there.
    assert "tell me more" not in named
    help_text = ui.page.inner_text(".taste-help")
    assert "artist's page" in help_text
    assert "Ask offers" in help_text
    assert "assistant" in help_text
