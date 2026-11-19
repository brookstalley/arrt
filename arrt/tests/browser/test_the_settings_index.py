"""Settings opens on an index of its pages, and Taste is the last of them.

As Sonarr's and Radarr's v4 /settings: the sidebar's Settings is a page of its
own, listing Players, Sources, General and Taste in the sidebar's order, each a link with
one line saying what it holds. Taste is headed "Taste", and its help names every
control that records a judgment, by the words that control carries.
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_taste, an_affinity
from playwright.sync_api import expect

#: The pages, in the order the index and the sidebar list them.
#: Players kept its address, `#clients`, when ruling 7 of 2026-10-27 renamed it.
PAGES = [("clients", "Players"), ("sources", "Sources"), ("watches", "Watches"), ("general", "General"), ("taste", "Taste")]


def test_the_sidebars_settings_opens_the_index(ui):
    ui.open("#walls")
    ui.page.wait_for_selector("nav.sidebar a.section-link")

    ui.page.click("nav.sidebar li.section[data-section='settings'] a.section-link")
    ui.page.wait_for_selector("#view h1:text-is('Settings')")

    assert ui.page.evaluate("() => window.location.hash") == "#settings"
    # The section's link is the page's own, so it is the one marked current.
    current = ui.page.locator("nav.sidebar [aria-current='page']")
    expect(current).to_have_count(1)
    expect(current).to_have_attribute("data-view", "settings")


def test_the_index_lists_each_page_as_a_link_with_what_it_holds(ui):
    """Every page, in order, and each row a link rather than a button: it navigates."""
    ui.open("#settings")
    ui.page.wait_for_selector("ul.settings-index")

    rows = ui.page.locator("ul.settings-index > li")
    expect(rows).to_have_count(len(PAGES))
    for index, (view, label) in enumerate(PAGES):
        row = rows.nth(index)
        anchor = row.locator("a")
        expect(anchor).to_have_count(1)
        expect(anchor).to_have_text(label, use_inner_text=True)
        expect(anchor).to_have_attribute("href", f"#{view}")
        # Its one line of what the page holds: some words, not a blank.
        expect(row.locator("p")).to_have_text(re.compile(r"\S"), use_inner_text=True)
    expect(ui.page.locator("ul.settings-index button")).to_have_count(0)


def test_following_a_row_opens_its_page(ui):
    ui.open("#settings")
    ui.page.click("ul.settings-index a:text-is('Sources')")
    ui.page.wait_for_selector("#view h1:has-text('Sources')")

    assert ui.page.evaluate("() => window.location.hash").startswith("#sources")


def test_taste_is_headed_taste(ui):
    ui.serve("**/api/affinities*", a_taste([an_affinity()]))
    ui.open("#taste")
    ui.page.wait_for_selector(".affinity")

    expect(ui.page.locator("#view h1")).to_have_text("Taste", use_inner_text=True)


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

    # A way is named when an emphasis in the help says exactly those words:
    # `:text-is` is whole-text and case-sensitive, as membership of the list of
    # the emphases' texts was ("More like this" is not "more like this").
    for words in WAYS:
        named = ui.page.locator(f".taste-help em:text-is('{words}')").first
        expect(named, f"the help does not name {words!r}").to_be_attached()
    # Ask's cards stopped offering it on 2026-10-09; a help naming it sends the
    # curator looking for a control that is not there.
    expect(ui.page.locator(".taste-help em:text-is('tell me more')")).to_have_count(0)
    help_text = ui.page.locator(".taste-help")
    expect(help_text).to_contain_text("artist's page", use_inner_text=True)
    expect(help_text).to_contain_text("Ask offers", use_inner_text=True)
    expect(help_text).to_contain_text("assistant", use_inner_text=True)
