"""Collection's rails, its density control, and its three different empties.

`test_the_grid.py` beside this covers the grid's paging loop, its dead tiles and
where focus lands after a navigation — the behaviours the screen had before it
grew anything to narrow it with. This file covers what Collection became: a
density that is a control rather than a decision, two rails that filter, the
membership editing that happens against the works being organised, and the three
empty states that are three facts rather than one.

**The three empties get three tests, and each asserts the other two are absent.**
One test that finds "nothing here" satisfied by any of them is exactly the shape
that reads as coverage and is not: conflating the first two tells a curator with
3,000 works that they own nothing, and conflating the third with the second
reports the expected result of following a suggestion as a failed query.
"""

import json
import re

import pytest
from payloads import (
    a_catalogue_work,
    a_facet_group,
    a_facet_option,
    a_listing,
)

from arrt.library.readiness import not_in_catalogue
from arrt.persistence.records import FacetDerivation, VocabularyKind

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

#: The three headlines, so a test asserting one can assert the absence of the
#: others by name rather than by an "empty" class every branch would share.
NOTHING_HELD = "Nothing is held yet."
NOTHING_MATCHES = "Nothing held matches this filter."


def artist_headline(name: str) -> str:
    return f"Nothing by {name} yet."


# -- the three empties --------------------------------------------------------


def test_a_collection_holding_nothing_at_all_invites_the_curator_into_discover(ui):
    """The first empty: there is nothing, and the way out is acquiring something.

    Stubbed, and this is the one place in this file that has to be: `server_url`
    boots on `seeded_service`, so the real server this suite runs against always
    holds three works. An empty catalogue is a state it cannot be asked for.
    """
    ui.serve("**/api/works?*", a_listing([]))

    ui.open("#collection")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text(NOTHING_HELD, use_inner_text=True)
    expect(ui.view).not_to_contain_text(NOTHING_MATCHES, use_inner_text=True)
    expect(ui.view).not_to_contain_text("Nothing by", use_inner_text=True)
    # The invitation, not merely the statement: an empty state that names no next
    # move is a dead end with better wording.
    expect(ui.page.locator("a:has-text('Go to Ask')")).to_have_count(1)


def test_a_filter_matching_nothing_names_the_filter_and_offers_a_way_out(ui):
    """The second empty: there is plenty, and this narrowing found none of it."""
    ui.open("#collection?q=aubergine")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text(NOTHING_MATCHES, use_inner_text=True)
    expect(ui.view).not_to_contain_text(NOTHING_HELD, use_inner_text=True)
    expect(ui.view).not_to_contain_text("Nothing by", use_inner_text=True)
    # The filter itself, said back. "No results" without saying what was asked
    # for leaves a curator guessing which narrowing did it.
    expect(ui.view).to_contain_text("the search “aubergine”", use_inner_text=True)
    expect(ui.page.locator("a:has-text('Show everything')")).to_have_count(1)


def test_filtering_to_one_artist_and_holding_none_says_so_as_a_normal_state(ui):
    """The third empty, and the one Ask makes common.

    The artists Ask surfaces are often ones the curator could not have named,
    so a collection holding nothing by them is the overwhelmingly common
    outcome. Reporting that as "nothing matches these filters" would be
    true and useless.
    """
    ui.open("#collection?artist=Wassily%20Kandinsky")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text(artist_headline("Wassily Kandinsky"), use_inner_text=True)
    expect(ui.view).not_to_contain_text(NOTHING_HELD, use_inner_text=True)
    expect(ui.view).not_to_contain_text(NOTHING_MATCHES, use_inner_text=True)
    # Named as normal rather than broken, and the offer is the search that would
    # actually find some — the collection holds none, so searching the collection
    # is not it.
    expect(ui.page.locator("a:has-text('Ask for some')")).to_have_count(1)


def test_an_artist_filter_with_a_search_beside_it_is_the_filter_empty(ui):
    """The pair that keeps the third empty from swallowing the second.

    "Nothing by Kandinsky yet" is a statement about the collection. With a search
    term also in force it would be a statement about the collection that the
    curator's own query might be the cause of, and the honest answer names both.
    """
    ui.open("#collection?artist=Wassily%20Kandinsky&q=aubergine")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text(NOTHING_MATCHES, use_inner_text=True)
    expect(ui.view).not_to_contain_text(artist_headline("Wassily Kandinsky"), use_inner_text=True)
    expect(ui.view).to_contain_text("the search “aubergine”", use_inner_text=True)
    expect(ui.view).to_contain_text("artist “Wassily Kandinsky”", use_inner_text=True)


# -- density ------------------------------------------------------------------


def test_the_default_at_the_prototype_scale_is_the_contact_sheet(ui):
    """Above a few hundred works the grid opens as pictures and nothing else.

    Stubbed at the total rather than seeded: the acceptance criterion is about
    2,000 works, seeding 2,000 rows costs minutes per test, and what is under
    test is the client's threshold — which reads `total` and nothing else.
    """
    ui.serve(
        "**/api/works?*",
        a_listing([a_catalogue_work(artwork_id="a", title="Nighthawks")], total=2000),
    )

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    expect(ui.page.locator("ul.grid.contact-sheet")).to_have_count(1)
    expect(ui.page.locator("li.tile")).to_have_count(1)
    # The paired negative: the catalogue card's own body must not be there, or
    # "contact sheet" would be a class name over the same tile.
    expect(ui.page.locator("li.card")).to_have_count(0)


def test_the_default_at_a_small_collection_is_the_catalogue(ui):
    """The paired negative, against the real server's three works.

    A default written as a constant would pass the test above and hand a curator
    with forty works a wall of anonymous thumbnails.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    expect(ui.page.locator("li.card")).to_have_count(3)
    expect(ui.page.locator("ul.grid.contact-sheet")).to_have_count(0)


def test_a_density_in_the_address_survives_a_reload_and_a_link(ui):
    """The whole of "remembered": the address is the memory.

    Opening the fragment *is* following a link; reloading is the other half. Both
    have to land on the density the curator chose rather than on the one the size
    of the collection would have picked.
    """
    ui.open("#collection?density=contact")
    ui.page.wait_for_selector("ul.grid")
    expect(ui.page.locator("ul.grid.contact-sheet")).to_have_count(1)

    ui.page.reload()
    ui.page.wait_for_selector("ul.grid")

    expect(ui.page.locator("ul.grid.contact-sheet")).to_have_count(1)
    expect(ui.page.locator("li.card")).to_have_count(0)


def test_choosing_a_view_writes_it_into_the_address(ui):
    """A control whose state is not in the URL is a control no link carries.

    The density buttons became the toolbar's View menu with the *arr navigation;
    Posters is what was the contact sheet, and the address keeps its spelling.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.click("button.menu-button-trigger:has-text('View')")
    ui.page.click("[role='menuitemradio']:has-text('Posters')")
    ui.page.wait_for_selector("ul.grid.contact-sheet")

    expect(ui.page).to_have_url(re.compile("density=contact"))


def test_every_posters_tile_shows_its_title_and_artist_beneath_it_on_a_phone(ui, service):
    """Posters, the default above a few hundred works, would show
    a work's words only as an overlay on hover or focus, so on a phone, with no
    hover, every tile was anonymous. The label is beneath the picture, on the
    page's ground, untouched by any pointer (`design-direction.md` § Tiles).

    Read from what is drawn: an overlay at opacity 0 is still "visible" to
    Playwright, so the label's opacity and its place under the picture are what
    is asserted, on every tile, with the pointer parked off the grid. A title too
    long for its line is the case that keeps the label from growing its row."""
    service.add_artwork(
        title="A title far longer than any Posters tile is wide, so it has to be clipped to its line",
        date_created="1900",
    )
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#collection?density=contact")
    tiles = ui.page.locator("ul.grid.contact-sheet li.tile")
    expect(tiles.first).to_be_visible()
    ui.page.mouse.move(0, 0)

    expect(tiles.nth(3), "the seeded works and the long title are all on the page").to_be_attached()
    count = tiles.count()  # one-shot: how many tiles to walk, read once the four it must hold are drawn
    for index in range(count):
        tile = tiles.nth(index)
        caption = tile.locator(".tile-caption")
        expect(caption).to_have_css("opacity", "1")
        expect(caption.locator(".tile-title")).not_to_have_text("")
        expect(caption.locator(".tile-artist")).not_to_have_text("")
        picture = tile.locator(".card-image").bounding_box()  # one-shot: geometry, read once the caption is shown
        label = caption.bounding_box()  # one-shot: geometry, read once the caption is shown
        assert picture is not None
        assert label is not None
        assert label["y"] >= picture["y"] + picture["height"] - 1, f"tile {index}'s label is over its picture"
    # One row height for every tile, the long title's included.
    heights = {
        round(box["height"])
        for box in (tiles.nth(i).bounding_box() for i in range(count))  # one-shot: geometry, read once every caption is shown
        if box
    }
    assert len(heights) == 1, f"Posters rows are not uniform: {sorted(heights)}"


PROTOTYPE_SCALE = 2000


def test_the_prototype_scale_opens_as_a_contact_sheet_and_stays_legible(ui, service, seed_the_served_catalogue):
    """The acceptance criterion, against a real catalogue rather than a number.

    The threshold test above stubs `total` behind one work, which is the right
    shape for pinning a branch and cannot answer this: legibility is a claim about
    two thousand tiles actually laid out by a real browser, and a stub renders
    one. `build_large_catalogue` exists precisely so the claim can be measured.

    **And every work is reachable.** The grid once walked to `PAGE_CEILING` and
    stopped at 1,250 works, and this test pinned that the stop was *audible* —
    the heading said how many of how many, and the note how many were not
    shown. Artworks now
    pages from the server as the curator scrolls, so the claim is the stronger
    one the note stood in for: the heading names the whole catalogue, every work
    arrives by *Show more*, and the shortfall note never appears.
    """
    seed_the_served_catalogue(size=PROTOTYPE_SCALE)
    # Asked rather than assumed: `server_url` boots on `seeded_service`, so the
    # catalogue this server holds is the seeded three plus what was just built.
    # A hard-coded total would be a test asserting against its own arithmetic.
    held = service.list_artworks(limit=1).total
    assert held >= PROTOTYPE_SCALE

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.tile")

    # The default at this scale is the contact sheet — image only, uniform tiles.
    expect(ui.page.locator("ul.grid.contact-sheet")).to_have_count(1)
    expect(ui.page.locator("li.card")).to_have_count(0)
    # In the facts line, in the empty state's words, since the heading became the
    # page's name (ruling 1 of 2026-10-27).
    expect(ui.page.locator("#view .page-facts")).to_have_text(f"{held:,} works", use_inner_text=True)
    # One page at first, so reaching the rest is something the screen has to do:
    # the last work's tile is not among those drawn.
    expect(ui.page.locator("ul.grid li.tile").nth(held - 1)).to_have_count(0)

    ui.show_more()

    expect(ui.page.locator("ul.grid li.tile")).to_have_count(held)
    expect(ui.view).not_to_contain_text("not on this page", use_inner_text=True)
    ids = ui.page.eval_on_selector_all("ul.grid li.tile", "nodes => nodes.map((n) => n.dataset.artwork)")
    assert len(set(ids)) == held, "a work was drawn twice, so another was never drawn"

    # Legible: every tile the same size, and big enough to judge a picture in.
    # Sampled rather than measured over every tile — a thousand
    # `getBoundingClientRect` calls tell you nothing the first fifty do not.
    boxes = ui.page.eval_on_selector_all(
        "ul.grid li.tile .card-image",
        "nodes => nodes.slice(0, 50).map(n => { const r = n.getBoundingClientRect();"
        " return [Math.round(r.width), Math.round(r.height)]; })",
    )
    widths = {box[0] for box in boxes}
    heights = {box[1] for box in boxes}
    assert max(widths) - min(widths) <= 1, f"tiles were not uniform across a row: {sorted(widths)}"
    assert max(heights) - min(heights) <= 1, f"tiles were not uniform down the grid: {sorted(heights)}"
    assert min(widths) >= 100, f"a contact sheet at this scale collapsed to {min(widths)}px tiles"


# -- the loading state and the grid's geometry --------------------------------


def test_the_loading_state_does_not_guess_a_geometry_it_cannot_know(ui):
    """No skeleton until the total is in, because the total is what sizes it.

    The density default is a function of how many works there are, and nothing
    knows that until the first page answers. A placeholder painted before then can
    only guess — and an earlier draft of this screen guessed contact sheet, which
    is wrong for every collection under a few hundred works and so jumped from
    twelve small tiles to N wide cards on the commonest path there is.
    """
    held = []
    ui.page.route(
        "**/api/works?*", lambda route: held.append(route)  # noqa: PLW0108 -- Playwright passes a builtin method two arguments
    )

    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")

    expect(ui.view).to_contain_text("Loading Artworks", use_inner_text=True)
    expect(ui.page.locator("ul.grid-skeleton"), "the placeholder guessed a geometry it could not know").to_have_count(0)
    expect(ui.page.locator("ul.grid")).to_have_count(0)

    for route in held:
        route.abort()


def test_the_skeleton_stands_at_the_tile_geometry_the_grid_will_have(ui):
    """ "Skeletons occupy the final geometry" — asserted as tile boxes, not as classes.

    Two pages, the second held open, so the placeholder is on screen long enough
    to be measured against the grid that replaces it. Held rather than raced: the
    skeleton exists for a slow answer, and a test that had to win a race would
    report a green meaning only that the machine was slow that time.

    The tile's own width and height are what is compared. A placeholder that drew
    faithful tiles and then spanned the whole page while the grid sat beside a
    13rem rail would pass a class check and fail a reader's eyes.
    """
    answered = {"count": 0}
    held = []
    first = a_listing(
        [a_catalogue_work(artwork_id="a", title="First")],
        total=2000,
        truncated=True,
    )

    def handler(route):
        answered["count"] += 1
        if answered["count"] == 1:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(first))
        else:
            held.append(route)

    ui.page.route("**/api/works?*", handler)

    # The paging loop has to ask for a second page before it can be released:
    # waited on that request, armed before the page is opened.
    with ui.page.expect_request(lambda request: "/api/works?" in request.url and "offset=1" in request.url):
        ui.open("#collection")
        ui.page.wait_for_selector("ul.grid-skeleton > li")
        # 2,000 works is above the threshold, so the placeholder is the contact sheet
        # the grid will be — the density is read from the same total by the same
        # function, which is what makes the two agree by construction.
        expect(ui.page.locator("ul.grid-skeleton.contact-sheet")).to_have_count(1)
        # It says nothing to a screen reader: twelve empty tiles announced as list
        # items is noise over the announcement that matters.
        expect(ui.page.locator("ul.grid-skeleton")).to_have_attribute("aria-hidden", "true")

    # Measured with the second page's request held, so the placeholder is still
    # the one on screen; this call is also the turn on which the handler has
    # been given that request.
    box = "n => { const r = n.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }"
    skeleton_tile = ui.page.eval_on_selector("ul.grid-skeleton > li", box)
    assert held, "the paging loop never asked for a second page"

    for route in held:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(a_listing([], total=2000, truncated=False, offset=1)),
        )
    ui.page.wait_for_selector("ul.grid > li")

    grid_tile = ui.page.eval_on_selector("ul.grid > li", box)
    assert skeleton_tile == grid_tile, f"the skeleton stood at {skeleton_tile} and the grid arrived at {grid_tile}"


def test_the_tiles_do_not_reflow_as_the_pictures_arrive(ui, work_with_an_image):
    """The defect this client has already shipped: a grid of art that jumps.

    Three works of three different shapes. If a tile took the shape of its own
    picture the three would differ, and every one of them would change height at
    the moment its image decoded.
    """
    work_with_an_image(title="A tall one", width=800, height=1600)
    work_with_an_image(title="A wide one", width=1600, height=600)
    work_with_an_image(title="A square one", width=1200, height=1200)

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    def heights():
        return ui.page.eval_on_selector_all(
            "ul.grid li.card .card-image",
            "nodes => nodes.map(node => Math.round(node.getBoundingClientRect().height))",
        )

    before = heights()
    ui.page.wait_for_function(
        "() => Array.from(document.querySelectorAll('ul.grid img')).every(img => img.complete && img.naturalWidth > 0)"
    )
    after = heights()

    assert len(before) == 6, "the three seeded works and the three with pictures did not all render"
    # Within a pixel, not identical to the pixel: the columns are fractional, so
    # a box sized by `aspect-ratio` lands on either side of a rounding boundary.
    # A tile taking the shape of its own picture would differ by hundreds.
    assert max(after) - min(after) <= 1, f"tiles took the shape of their own pictures: {after}"
    assert before == after, f"the grid reflowed as the images arrived: {before} then {after}"


# -- the facet rail -----------------------------------------------------------


def a_page_with_facets(*options):
    return a_listing(
        [a_catalogue_work(artwork_id="a", title="Nighthawks")],
        total=1,
        facets=[
            a_facet_group(
                "movement",
                list(options) or [a_facet_option("Baroque", 51), a_facet_option("Rococo", 0)],
            ),
        ],
    )


def test_a_facet_option_that_would_select_nothing_is_disabled_and_still_counted(ui):
    """Disabled, not hidden — and the count inside the control's own name.

    A disabled control is skipped by the tab sequence, so a count living in
    adjacent text is a count a screen-reader user never hears. And a vocabulary
    that shrank as filters were applied would read as the collection having lost
    values rather than as an empty intersection.
    """
    ui.serve("**/api/works?*", a_page_with_facets())

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")

    rococo = ui.page.locator("button.facet-option", has_text="Rococo")
    expect(rococo, "a zero-count option was hidden rather than disabled").to_have_count(1)
    expect(rococo).to_be_disabled()
    expect(rococo).to_have_text("Rococo (0)", use_inner_text=True)

    baroque = ui.page.locator("button.facet-option", has_text="Baroque")
    expect(baroque).to_be_enabled()
    expect(baroque).to_have_text("Baroque (51)", use_inner_text=True)


def test_choosing_a_facet_narrows_at_the_server_as_its_own_parameter(ui):
    """The filter goes to the server, spelled the way the route spells it.

    One repeated parameter per kind, never comma-joined: a facet value may itself
    contain a comma, and a separator a value can hold is a parser that goes wrong
    on the catalogue rather than on the request.
    """
    ui.serve("**/api/works?*", a_page_with_facets())

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")

    # **Armed before the click, and waited on.** This asserted on the recorded
    # request list after waiting for the address bar, which is a different event:
    # `go` writes `location.hash` synchronously and the fetch is issued from the
    # `hashchange` task after it, so the wait could return before the request
    # existed. It did — reliably at module scope and not at suite scope, which is
    # the worst kind of green. Waiting for the request itself is both correct and
    # a stronger claim: the test now fails if no narrowed request is ever sent,
    # rather than if none had been sent yet.
    def a_narrowed_works_request(request):
        return "/api/works?" in request.url and "movement=" in request.url

    with ui.page.expect_request(a_narrowed_works_request) as narrowed:
        ui.page.click("button.facet-option:has-text('Baroque')")

    assert "movement=Baroque" in narrowed.value.url
    assert all("movement=Baroque" in url for url in ui.requests_matching("/api/works?") if "movement=" in url)


def test_a_facet_value_holding_the_separator_survives_the_address(ui):
    """The fragment joins several values with a pipe; a value may contain one.

    That is the failure the wire's own rule is about — a facet value may hold a
    comma, so the route takes one repeated parameter per kind rather than a
    comma-joined list — and picking a rarer character for the fragment would only
    have made the same bet at longer odds. The values are escaped before they are
    joined, so the separator is the only bare pipe the string can hold, and this
    is the test that says so: one value, one parameter, both halves intact.
    """
    ui.serve("**/api/works?*", a_page_with_facets(a_facet_option("Ochre | Umber", 7)))

    ui.open("#collection")
    ui.page.wait_for_selector(".facet-option")

    def a_narrowed_works_request(request):
        return "/api/works?" in request.url and "movement=" in request.url

    with ui.page.expect_request(a_narrowed_works_request) as narrowed:
        ui.page.click("button.facet-option:has-text('Ochre')")

    # One parameter carrying the whole value, not two carrying half each.
    assert narrowed.value.url.count("movement=") == 1
    assert "movement=Ochre%20%7C%20Umber" in narrowed.value.url

    # And the address round-trips it: pressing the same option again *removes* it.
    # That is the assertion that actually exercises the escaping — if the pipe had
    # been lost the client would read two values back out of one, not recognise
    # the option as chosen, and add a second copy instead of clearing it.
    def a_works_request(request):
        return "/api/works?" in request.url

    with ui.page.expect_request(a_works_request) as again:
        ui.page.click("button.facet-option:has-text('Ochre')")

    assert "movement=" not in again.value.url, "choosing the value twice added a second copy instead of clearing it"


# -- the Theme filter, and membership edited in Select mode -------------------
#
# The owner ruled on #169 for Radarr's pattern: a theme is one more group in the
# *Filter* rail, composing with the facets, and adding and removing appear only
# in a *Select* mode. Three tests of the old rail are retired with it, each
# replaced by the contract the new design owes:
#   - "a theme chip filters the grid" → `test_a_theme_in_the_filter_rail_narrows_the_grid`;
#   - "the rail's filter and its opener are separate controls" → the two acts
#     are now filtering and membership, and
#     `test_filtering_by_a_theme_and_changing_its_members_are_different_controls`
#     holds them apart;
#   - "the opener goes to the theme" → the opener is gone by the ruling (themes
#     are reached from Library › Themes); what the rail owes instead is that a
#     theme composes with a facet and counts like one,
#     `test_a_theme_composes_with_a_facet_and_counts_like_one`.


@pytest.fixture
def a_theme_holding_one_work(display, seeded_service):
    """A real theme with one of the three seeded works in it."""
    theme = display.add_theme(name="Baroque")
    works = [entry.artwork for entry in seeded_service.list_artworks().entries]
    display.add_to_theme(theme_id=theme.id, artwork_id=works[0].id)
    return theme, works


def theme_option(ui, theme):
    return ui.page.locator(f"button.facet-option[data-theme='{theme.id}']")


def enter_select_mode(ui):
    ui.page.click("button.select-toggle")
    ui.page.wait_for_selector(".selection", state="visible")


def test_a_theme_in_the_filter_rail_narrows_the_grid(ui, a_theme_holding_one_work):
    theme, _ = a_theme_holding_one_work
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    expect(ui.page.locator("ul.grid li.card")).to_have_count(3)

    expect(theme_option(ui, theme)).to_have_text("Baroque (1)", use_inner_text=True)
    theme_option(ui, theme).click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    # In the facts line, in the empty state's words, since the heading became the
    # page's name (ruling 1 of 2026-10-27).
    expect(ui.page.locator("#view .page-facts")).to_have_text("1 work · filtered by the theme “Baroque”", use_inner_text=True)
    expect(theme_option(ui, theme)).to_have_attribute("aria-pressed", "true")
    # Pressing it again is how it is turned off.
    theme_option(ui, theme).click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 3")


def test_filtering_by_a_theme_and_changing_its_members_are_different_controls(ui, a_theme_holding_one_work):
    """The confusion #169 was filed for: the theme dropdown read as a filter and was an editor.

    Outside *Select* mode, nothing on the screen changes a theme's members:
    no tick on any tile and no theme picker. The rail's theme options are
    toggles (`aria-pressed`), and the picker, once shown, has a visible name.

    The *Select* toggle says which mode the page is in by its label — "Select",
    then "Stop selecting" — because every list has one selection model, not an
    `aria-pressed` toggle reading "Select" in both states. The claim is unchanged: the mode is readable
    from the control.
    """
    theme, works = a_theme_holding_one_work
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    # The grid is drawn whole, so a tick or a picker that is out of sight is out of sight on a drawn grid.
    expect(ui.page.locator("ul.grid li.card")).to_have_count(3)
    expect(ui.page.locator("input.tile-select:visible")).to_have_count(0)
    expect(ui.page.locator("#add-to-theme:visible")).to_have_count(0)
    expect(theme_option(ui, theme)).to_have_attribute("aria-pressed", "false")
    expect(ui.page.locator("button.select-toggle")).to_have_text("Select", use_inner_text=True)

    enter_select_mode(ui)

    expect(ui.page.locator("button.select-toggle")).to_have_text("Stop selecting", use_inner_text=True)
    expect(ui.page.locator("input.tile-select:visible")).to_have_count(3)
    # Nothing ticked, so Add can do nothing yet; and with no theme in the
    # filter there is no theme to remove from, so Remove is not drawn at all.
    expect(ui.page.locator("button.selection-remove")).to_have_count(0)
    expect(ui.page.locator("button.selection-add")).to_be_disabled()
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    # The theme is chosen in the dialog *Add to theme…* opens, since the acts
    # moved into the toolbar (ruling 1 of 2026-10-27), and the dialog's button
    # says the whole act: how many, and into what.
    ui.page.click("button.selection-add")
    expect(ui.page.locator("dialog label[for='add-to-theme']")).to_have_text("Theme", use_inner_text=True)
    expect(ui.page.locator("dialog button.add-confirm")).to_have_text("Add 2 works to Baroque", use_inner_text=True)


def test_leaving_select_mode_hides_the_ticks_and_drops_them(ui, a_theme_holding_one_work):
    """A selection nobody can see would be acted on the next time the mode is entered."""
    _, works = a_theme_holding_one_work
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")

    ui.page.click("button.select-toggle")

    # Out of the mode (its toggle says so) before what the mode showed is asked after.
    expect(ui.page.locator("button.select-toggle")).to_have_text("Select", use_inner_text=True)
    expect(ui.page.locator("input.tile-select:visible")).to_have_count(0)
    expect(ui.page.locator(".selection")).to_be_hidden()
    enter_select_mode(ui)
    expect(ui.page.locator(".selection-status")).to_contain_text("No works selected.", use_inner_text=True)
    expect(ui.page.locator("input.tile-select:checked")).to_have_count(0)


def test_a_theme_composes_with_a_facet_and_counts_like_one(ui, display, seeded_service, a_theme_holding_one_work):
    """Theme and facet narrow together, and a theme the facet empties is disabled, not hidden.

    *Baroque* holds the first work; a second theme, *Elsewhere*, holds the
    second. Realism is recorded on the first and third works, so under Realism
    *Baroque* still selects one and *Elsewhere* none.
    """
    theme, works = a_theme_holding_one_work
    elsewhere = display.add_theme(name="Elsewhere")
    display.add_to_theme(theme_id=elsewhere.id, artwork_id=works[1].id)
    for work in (works[0], works[2]):
        seeded_service.record_facet(
            artwork_id=work.id, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.INFERRED
        )

    ui.open("#collection?movement=Realism")
    ui.page.wait_for_selector("ul.grid li.card")
    expect(ui.page.locator("ul.grid li.card")).to_have_count(2)
    expect(theme_option(ui, elsewhere)).to_have_text("Elsewhere (0)", use_inner_text=True)
    expect(theme_option(ui, elsewhere)).to_be_disabled()

    theme_option(ui, theme).click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    # Both narrowings still in force and still shown as chosen.
    expect(ui.page.locator("button.facet-option[aria-pressed='true']", has_text="Realism")).to_have_count(1)
    expect(theme_option(ui, theme)).to_have_attribute("aria-pressed", "true")
    # In the facts line, in the empty state's words, since the heading became the
    # page's name (ruling 1 of 2026-10-27).
    # Both narrowings, since the line names each one; the heading named the theme alone.
    expect(ui.page.locator("#view .page-facts")).to_have_text(
        "1 work · filtered by the theme “Baroque”, and movement “Realism”", use_inner_text=True
    )
    # A theme filtered here is in the Sort menu's order, so the menu is offered.
    expect(ui.page.locator(".page-toolbar button", has_text="Sort")).to_have_count(1)


STALE_THEME = "The theme this address names is not in the Library"


def test_an_address_naming_a_deleted_theme_shows_the_works_and_says_so(ui, a_theme_holding_one_work):
    """A bookmark outlives the theme it names, and the home page must survive it.

    The listing refuses an unknown theme, rightly: answering with the whole
    catalogue under the theme's name would be a lie. The screen must not pass that
    refusal on as a dead page, though. It shows what the address's other filters
    select, with its rail, and says the theme is gone.
    """
    theme, _ = a_theme_holding_one_work
    ui.open("#collection?theme=no-such-theme")
    ui.page.wait_for_selector("ul.grid li.card")

    expect(ui.page.locator("ul.grid li.card")).to_have_count(3)
    expect(ui.view).to_contain_text(STALE_THEME, use_inner_text=True)
    expect(theme_option(ui, theme)).to_have_text("Baroque (1)", use_inner_text=True)
    expect(theme_option(ui, theme)).to_have_attribute("aria-pressed", "false")
    expect(ui.page.locator("#error:not([hidden])")).to_have_count(0)


def test_a_deleted_theme_beside_a_facet_keeps_the_facet(ui, seeded_service, a_theme_holding_one_work):
    _theme, works = a_theme_holding_one_work
    seeded_service.record_facet(
        artwork_id=works[2].id, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.INFERRED
    )
    ui.open("#collection?theme=no-such-theme&movement=Realism")
    ui.page.wait_for_selector("ul.grid li.card")

    expect(ui.page.locator("ul.grid li.card")).to_have_count(1)
    expect(ui.view).to_contain_text(STALE_THEME, use_inner_text=True)
    expect(ui.page.locator("button.facet-option[aria-pressed='true']", has_text="Realism")).to_have_count(1)


def test_a_theme_that_exists_draws_no_stale_theme_sentence(ui, a_theme_holding_one_work):
    theme, _ = a_theme_holding_one_work
    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    expect(ui.view).not_to_contain_text(STALE_THEME, use_inner_text=True)


def test_adding_moves_the_rails_count_without_a_repaint(ui, display, a_theme_holding_one_work):
    """Nothing repaints, so the count beside the rail has to move where it stands."""
    theme, works = a_theme_holding_one_work
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.click("button.selection-add")
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque.')")

    expect(theme_option(ui, theme)).to_have_text("Baroque (2)", use_inner_text=True)


def test_membership_is_edited_from_the_grid_without_leaving_it(ui, display, a_theme_holding_one_work):
    """Organising happens in the collection, against the works being organised."""
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)

    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    expect(ui.view).to_contain_text("2 selected.", use_inner_text=True)

    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 2 works to Baroque.')")

    # Still on the screen it started on, with the same works under it.
    expect(ui.page).to_have_url(re.compile(r"#collection$"))
    expect(ui.page.locator("ul.grid li.card")).to_have_count(3)
    # And the server really holds it, rather than the page having said so.
    assert len(display.theme_work_ids(theme.id)) == 3


def test_editing_membership_does_not_drop_the_keyboard_to_the_top_of_the_page(ui, display, a_theme_holding_one_work):
    """The curator is standing on the control they just pressed.

    An edit that repainted the screen would destroy it, and finishing the edit
    disables it — either way the keyboard lands back on the document, several
    hundred tiles above where the work was happening. Focus goes to the outcome
    sentence instead, which is inside the toolbar the curator is using.
    """
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque.')")

    assert ui.focused() == "Added 1 work to Baroque."


def test_removing_from_a_theme_takes_the_tiles_out_and_says_what_is_left(ui, display, a_theme_holding_one_work):
    """The count over the grid must not outlive the tiles it counted."""
    theme, works = a_theme_holding_one_work
    display.add_to_theme(theme_id=theme.id, artwork_id=works[1].id)

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    expect(ui.page.locator("ul.grid li.card")).to_have_count(2)
    enter_select_mode(ui)

    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    expect(ui.page.locator("button.selection-remove")).to_have_text("Remove 1 work from Baroque", use_inner_text=True)
    ui.page.click("button.selection-remove")
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    # In the facts line, in the empty state's words, since the heading became the
    # page's name (ruling 1 of 2026-10-27).
    expect(ui.page.locator("#view .page-facts")).to_have_text("1 work · filtered by the theme “Baroque”", use_inner_text=True)
    # The rail is recounted by the server after the tile goes, so its count is
    # waited for: read at once, it races the recount and can see the old one.
    # A rail that never recounts still fails here, by timing out.
    ui.page.wait_for_selector(f"button.facet-option[data-theme='{theme.id}']:text-is('Baroque (1)')")
    assert len(display.theme_work_ids(theme.id)) == 1


def test_removing_recounts_the_facets_so_none_leads_to_an_empty_grid(ui, display, seeded_service, a_theme_holding_one_work):
    """A removal changes the theme's slice, and the facet counts beside it must follow.

    Two works in *Baroque*; Realism is recorded only on the one removed. Left
    at its old count, Realism would stay enabled beside a slice in which it
    selects nothing — the dead end the rail forbids.
    """
    theme, works = a_theme_holding_one_work
    display.add_to_theme(theme_id=theme.id, artwork_id=works[1].id)
    seeded_service.record_facet(
        artwork_id=works[0].id, kind=VocabularyKind.MOVEMENT, value="Realism", derivation=FacetDerivation.INFERRED
    )
    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    realism = ui.page.locator("button.facet-option", has_text="Realism")
    expect(realism).to_have_text("Realism (1)", use_inner_text=True)

    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.click("button.selection-remove")
    ui.page.wait_for_function(
        "() => [...document.querySelectorAll('button.facet-option')].some((b) => b.textContent === 'Realism (0)')"
    )

    expect(realism).to_be_disabled()
    expect(theme_option(ui, theme)).to_have_text("Baroque (1)", use_inner_text=True)


def test_a_refused_removal_keeps_its_own_reason_when_the_recount_fails_too(ui, display, a_theme_holding_one_work):
    """The server's reason for stopping is what the curator needs; a recount failing after it must not replace it.

    Only the two failures are stubbed: the first removal goes to the real route,
    so there is something to recount.
    """
    theme, works = a_theme_holding_one_work
    display.add_to_theme(theme_id=theme.id, artwork_id=works[1].id)
    refusal = "The second work could not be taken out."
    deletes = []

    def refuse_the_second_delete(route):
        deletes.append(route.request.url)
        if len(deletes) == 2:
            route.fulfill(status=400, content_type="application/json", body=json.dumps({"error": refusal}))
        else:
            route.continue_()

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.route(f"**/api/themes/{theme.id}/works/*", refuse_the_second_delete)
    ui.page.route(
        "**/api/works?limit=1*",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body=json.dumps({"error": "The recount failed."})
        ),
    )
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.click("button.selection-remove")

    said = ui.said_beside(ui.page.locator("button.selection-remove"))
    assert refusal in said
    assert "The recount failed." not in said


def test_a_collection_with_no_themes_offers_select_with_something_behind_it(ui, seeded_service):
    """A control with nothing behind it is the dead end the facet rules forbid.

    This was "with no theme, no *Select* at all", when adding to an existing
    theme was the only act a selection had. Since one selection model gave it
    *New theme…* and *Archive*, a selection always has something to do, so *Select* is offered — and
    the claim it kept is that what it offers can act: the picker starts on *New
    theme…* rather than on nothing, and Archive is there.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    # The picker is in the dialog *Add to theme…* opens, which a tick enables.
    ui.page.locator("input.tile-select").first.check()
    ui.page.click("button.selection-add")

    picker = ui.page.locator("dialog #add-to-theme")
    expect(picker.locator("option")).to_have_text(["New theme…"], use_inner_text=True)
    expect(picker).to_have_value("new")
    expect(ui.page.locator("button.selection-archive")).to_have_count(1)


def test_the_theme_being_shown_is_not_offered_as_somewhere_to_add(ui, a_theme_holding_one_work):
    """Every work on screen is already in it, so that control could only refuse.

    The picker defaulting to the first theme is what made this reachable in one
    move: showing a theme, pressing Add, and being told the work is already there.
    The picker is drawn now, since *New theme…* is somewhere to add; the theme
    being shown is still not in it.
    """
    theme, _works = a_theme_holding_one_work

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    # The picker is in the dialog *Add to theme…* opens, which a tick enables;
    # Remove is in the toolbar behind it.
    ui.page.locator("input.tile-select").first.check()
    expect(ui.page.locator("button.selection-remove")).to_have_count(1)
    ui.page.click("button.selection-add")

    # The picker's options are drawn (the one it does offer is there) before the one it must not is asked after.
    expect(ui.page.locator("#add-to-theme option")).to_have_text(["New theme…"], use_inner_text=True)
    expect(ui.page.locator(f"#add-to-theme option[value='{theme.id}']")).to_have_count(0)


def test_typing_the_shown_themes_name_joins_it_rather_than_making_another(ui, display, a_theme_holding_one_work):
    """Not offered is not unknown: a new theme typed with the shown theme's name, in
    other capitals, joins it, where checking only the offered themes made a second."""
    theme, works = a_theme_holding_one_work

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.locator("input.tile-select").first.check()
    ui.page.click("button.selection-add")
    ui.page.fill("#add-to-theme-name", theme.name.upper())
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(f".selection-status:has-text('{theme.name}')")

    assert [t.name for t in display.list_themes()] == [theme.name]
    assert display.theme_work_ids(theme.id) == [works[0].id]


def test_adding_a_work_the_theme_already_holds_is_not_an_error(ui, display, a_theme_holding_one_work):
    """The store refuses a duplicate, so the loop must not walk into one.

    Selecting a work already in the theme alongside one that is not would, with a
    naive loop, apply part of the edit and then report a refusal — a half-applied
    change with nothing saying which half. What the theme already holds is read
    first and skipped, and the sentence says so rather than staying quiet about it.
    """
    theme, works = a_theme_holding_one_work

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque. 1 was already in it.')")

    expect(ui.page.locator("#error"), "a duplicate in the selection was reported as a failure").to_be_hidden()
    assert len(display.theme_work_ids(theme.id)) == 2


def test_a_refusal_partway_through_leaves_exactly_the_works_that_did_not_go(ui, display, a_theme_holding_one_work):
    """The loop can stop halfway, and what it leaves behind has to be the retry.

    Reading the theme first removes the refusal the client can foresee; it cannot
    remove the one it cannot — here the second work is deleted from the catalogue
    between that read and its own write. Two half-states are then available and
    both are wrong: a selection cleared, which loses the record of which works did
    not go, and a selection left whole, which carries the work that already landed
    back into the retry. Exactly the works that did not go stay ticked, and the
    retry sends exactly those.

    **Only the refusal is stubbed.** Accepting one write and refusing the next is
    what no server can be asked for on purpose; both other writes go to the real
    route, so what the theme holds after each press is the store's own answer
    rather than this test's — and the read in front of the retry is filtering
    against a theme that really did take one work and really did not take the
    other.
    """
    theme, works = a_theme_holding_one_work
    # What the server answers for a work it does not hold: 404, in the
    # sentence `themes.py` raises, which is readiness's own.
    refusal = not_in_catalogue(works[2].id).detail
    writes = []

    def refuse_the_second_write(route):
        writes.append(json.loads(route.request.post_data)["artwork_id"])
        if len(writes) == 2:
            route.fulfill(status=404, content_type="application/json", body=json.dumps({"error": refusal}))
        else:
            route.continue_()

    ui.page.route(f"**/api/themes/{theme.id}/works", refuse_the_second_write)

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[1].id}'] input.tile-select")
    ui.page.check(f"li.card[data-artwork='{works[2].id}'] input.tile-select")
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    # The live region holds one sentence, and before the click it is this one — so
    # the outcome waited for below is text only the refusal can have produced.
    expect(ui.view).to_contain_text("2 selected.", use_inner_text=True)

    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 of 2 to Baroque.')")

    # Read whole rather than by substring: how far the loop got and what pressing
    # Add again will do are one sentence, and a client that dropped the second
    # half would leave the curator to guess whether retrying repeats the work.
    expect(ui.page.locator(".selection-status")).to_have_text(
        "Added 1 of 2 to Baroque. The rest are still selected, so pressing Add again retries only those.",
        use_inner_text=True,
    )

    # Why it stopped is the server's sentence, not one composed here: the failure
    # is rethrown precisely so it is said beside Add, in the server's own words,
    # under the region's account of how far the loop got. Beside the dialog's
    # Add, which stays open so the retry is the same press.
    assert (
        ui.said_beside(ui.page.locator("dialog button.add-confirm"))
        == f"Couldn't add 2 works to Baroque: {refusal} Nothing was changed."
    )

    # Exactly the work that did not go, and only it. Clearing the selection and
    # leaving it whole both satisfy "something is ticked"; neither is this.
    expect(ui.page.locator("input.tile-select:checked")).to_have_count(1)
    expect(ui.page.locator(f"li.card[data-artwork='{works[2].id}'] input.tile-select")).to_be_checked()
    assert writes == [works[1].id, works[2].id]
    assert set(display.theme_work_ids(theme.id)) == {works[0].id, works[1].id}
    # The rail's count moved by the one that landed, not by the two asked for and
    # not by none: the stale count its handler exists to refuse.
    expect(theme_option(ui, theme)).to_have_text("Baroque (2)", use_inner_text=True)

    # The retry is pressing the same button, so it has to still be pressable.
    expect(ui.page.locator("dialog button.add-confirm")).to_be_enabled()
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Baroque.')")

    # The clause that matters: one further write, carrying the work that was
    # refused and not the one that landed. Whole again rather than by substring —
    # a retry that offered the landed work back would be skipped by the read in
    # front of the loop and say so, and " 1 was already in it." is the only trace
    # of a selection that was never reduced.
    assert writes == [works[1].id, works[2].id, works[2].id]
    expect(ui.page.locator(".selection-status")).to_have_text("Added 1 work to Baroque.", use_inner_text=True)
    expect(ui.page.locator("input.tile-select:checked")).to_have_count(0)
    assert set(display.theme_work_ids(theme.id)) == {work.id for work in works}
    expect(theme_option(ui, theme)).to_have_text("Baroque (3)", use_inner_text=True)


def test_removing_a_theme_s_last_member_leaves_a_sentence_not_a_blank(ui, a_theme_holding_one_work):
    """An empty grid with nothing said is indistinguishable from a broken screen."""
    theme, works = a_theme_holding_one_work

    ui.open(f"#collection?theme={theme.id}")
    ui.page.wait_for_selector("ul.grid li.card")
    enter_select_mode(ui)
    ui.page.check(f"li.card[data-artwork='{works[0].id}'] input.tile-select")
    ui.page.click("button.selection-remove")
    ui.page.wait_for_selector(".empty")

    expect(ui.view).to_contain_text(NOTHING_MATCHES, use_inner_text=True)
    expect(ui.view).to_contain_text("the theme \u201cBaroque\u201d", use_inner_text=True)
    # In the facts line since the heading became the page's name (ruling 1 of
    # 2026-10-27); the count still follows the removal.
    expect(ui.page.locator("#view .page-facts")).to_have_text(
        "0 works \u00b7 filtered by the theme \u201cBaroque\u201d", use_inner_text=True
    )


def test_a_repaint_that_is_not_a_navigation_does_not_move_focus(ui):
    """The rule that binds every live region here, asserted at its own level.

    `refresh()` is what a poll would call — the same repaint, without the
    navigation that earns a focus move. A view that always focused itself would
    take the keyboard away from whatever the curator was standing on, every
    time.
    """
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    ui.page.focus("button.menu-button-trigger")
    ui.page.evaluate("() => refresh()")
    ui.page.wait_for_selector("ul.grid")

    assert ui.focused() != "view"


def test_a_count_of_two_thousand_reads_two_thousand_with_its_comma_everywhere_in_artworks(ui):
    """ "2,000 works" beside "Select all 2000 works" and "Starry (2000)" is four ways of writing one number: one way here.

    One page of the 2,000 is stubbed (the client reads `total` and each option's
    `count`), with a facet that holds all of them. Every place Artworks prints
    that number says it through `number`/`counted` in `core/counting.js`: the
    facts line, the rail's option, *Select all*, and the showing note.
    """
    works = [a_catalogue_work(artwork_id=f"w{n}", title=f"Work {n}") for n in range(25)]
    ui.serve(
        "**/api/works?*",
        a_listing(works, total=2000, truncated=True, facets=[a_facet_group("movement", [a_facet_option("Baroque", 2000)])]),
    )

    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    expect(ui.page.locator("#view .page-facts")).to_contain_text("2,000 works", use_inner_text=True)
    expect(ui.page.locator("button.facet-option")).to_have_text("Baroque (2,000)", use_inner_text=True)
    ui.page.click("#view button.select-toggle")
    expect(ui.page.locator("#view .selection .select-all, #view button:has-text('Select all')").first).to_have_text(
        "Select all 2,000 works", use_inner_text=True
    )
    expect(ui.view).not_to_contain_text(re.compile(r"\b2000\b"))


# -- the way past the filters ---------------------------------------------------------


def test_a_tab_from_the_skip_filters_link_reaches_the_first_tile_past_every_facet(ui):
    """About eighty facet buttons stood between the keyboard and the first work; one link steps over them.

    The link is the rail's first stop, so a keyboard reaches it before the facets;
    activated, it leaves the address alone and puts focus on the works, so the
    next Tab is the first tile and not a facet.
    """
    # Stubbed: the seeded works carry no facet, and a rail that is only its note has nothing to step over.
    options = [a_facet_option(f"Movement {n}", 5) for n in range(20)]
    ui.serve(
        "**/api/works?*",
        a_listing(
            [a_catalogue_work(artwork_id=f"w{n}", title=f"Work {n}") for n in range(3)],
            facets=[a_facet_group("movement", options)],
        ),
    )
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li[data-artwork]")
    skip = ui.page.locator("aside.rails a.skip-filters")
    expect(skip).to_have_count(1)
    # Reached before any facet: the first thing in the rail the keyboard can stop on.
    first_stop = ui.page.evaluate(
        "() => document.querySelector('aside.rails').querySelector('a[href], button:not([disabled])').className"
    )
    assert first_stop == "skip-filters", f"the rail's first stop is {first_stop!r}, not the skip link"
    before = ui.page.evaluate("() => window.location.hash")

    skip.focus()
    expect(skip).to_be_visible()
    ui.page.keyboard.press("Enter")
    ui.page.keyboard.press("Tab")

    landed = ui.page.evaluate(
        "() => ({ inTile: Boolean(document.activeElement.closest('ul.grid li[data-artwork]')),"
        " inRail: Boolean(document.activeElement.closest('aside.rails')) })"
    )
    assert landed == {"inTile": True, "inRail": False}, f"Tab after the skip landed on {landed}"
    assert ui.page.evaluate("() => window.location.hash") == before


def test_a_rail_with_nothing_to_filter_by_has_nothing_to_skip(ui, seeded_service):
    """The paired negative: the seeded works carry no facet, so the rail is its note alone and offers no link."""
    ui.open("#collection")
    ui.page.wait_for_selector("aside.rails .rail-note")

    expect(ui.page.locator("a.skip-filters")).to_have_count(0)


def test_with_the_filters_put_away_there_is_nothing_to_skip(ui, seeded_service):
    """The paired negative: no rail, no link to step over it."""
    ui.open("#collection?filters=hidden")
    ui.page.wait_for_selector("ul.grid li[data-artwork]")

    expect(ui.page.locator("a.skip-filters")).to_have_count(0)
