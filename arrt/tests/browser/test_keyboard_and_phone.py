"""Keyboard and phone: where the focus is, what it is called, and a page a phone can hold.

The accessibility lens of the first UX walkthrough (`ux-review-2026-10.md`
findings 14, 15 and 30) found a focus ring clipped on card pictures, a facet
click that threw the keyboard to the top, same-titled works with the same name,
a live region that re-announced itself on every page, and at 390 px a To review
whose only action sat past the screen's edge. Each is pinned here where it was
found. The phone checks run at 390 × 844, an iPhone 14's CSS viewport, which is
the width the walkthrough photographed.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_facet_group, a_facet_option, a_listing, a_run

from arrt.http.models import RunListOut

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

#: Read from `app.js`, so a screen routed tomorrow is measured at phone width
#: the day it is routed.
ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))

PHONE = {"width": 390, "height": 844}


def address(route):
    return f"#{route.key}/not-a-real-id" if route.detail == "required" else f"#{route.key}"


def awaiting(runs, counts) -> dict:
    return RunListOut(
        runs=runs,
        count=len(runs),
        total=len(runs),
        truncated=False,
        awaiting_works=sum(counts.values()),
        awaiting=counts,
    ).model_dump(mode="json")


def sideways(ui) -> int:
    """How far the page itself scrolls sideways, in CSS pixels; 0 when it does not."""
    return ui.page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def past_the_edge(ui) -> list[str]:
    """The innermost elements reaching past the screen's right edge, to name in a failure."""
    return ui.page.evaluate("""() => {
          const edge = document.documentElement.clientWidth;
          const past = [...document.body.querySelectorAll('*')].filter((n) => n.getBoundingClientRect().right > edge + 0.5);
          return past.filter((n) => !past.some((m) => m !== n && n.contains(m))).slice(0, 6)
            .map((n) => `${n.tagName.toLowerCase()}.${[...n.classList].join('.')}#${n.id} ${Math.round(n.getBoundingClientRect().right)}`);
        }""")


# -- a phone ----------------------------------------------------------------------


@pytest.mark.parametrize("route", list(ROUTES.values()), ids=list(ROUTES))
def test_no_page_scrolls_sideways_on_a_phone(ui, route, work_with_an_image, display):
    """Document width within the viewport on every routed page at 390 px.

    A held work with a real picture is in the library and in a theme, so the
    pages that list works and themes draw a picture, its badges, a theme's
    members and its *Add a work* picker, rather than an empty state. The title
    is long because the picker's options were what made Themes 497 px wide.
    """
    work = work_with_an_image("A title long enough to wrap on the narrowest phone a curator carries about with them")
    work_with_an_image("Another work, so the picker has something not yet in the theme to offer, also with a long title")
    theme = display.add_theme(name="Quiet interiors")
    display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    ui.page.set_viewport_size(PHONE)
    ui.open(address(route))
    ui.page.wait_for_load_state("networkidle")
    assert sideways(ui) <= 0, f"#{route.key} scrolls {sideways(ui)}px sideways at 390 px, past the edge: {past_the_edge(ui)}"


@pytest.mark.parametrize("screen", ["theme", "work", "artist"])
def test_a_page_about_one_thing_does_not_scroll_sideways_on_a_phone(ui, screen, service, work_with_an_image, display):
    """The routes above opened at an id something has, which an id nothing has cannot reach."""
    artist = service.add_artist(name="An artist whose name runs on as some museums record it in full")
    work = work_with_an_image("A title long enough to wrap on the narrowest phone a curator carries about with them")
    service.add_artwork(title="Their work, under a title as long as the others here, with no picture yet", artist_id=artist.id)
    theme = display.add_theme(name="Quiet interiors")
    display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    target = {"theme": f"#theme/{theme.id}", "work": f"#work/{work.id}", "artist": f"#artist/{artist.id}"}[screen]
    ui.page.set_viewport_size(PHONE)
    ui.open(target)
    ui.page.wait_for_load_state("networkidle")
    assert sideways(ui) <= 0, f"{target} scrolls {sideways(ui)}px sideways at 390 px, past the edge: {past_the_edge(ui)}"


def test_to_review_s_action_is_on_screen_on_a_phone(ui):
    """The page's only action, Review, sat at x=512 in a 390 px screen."""
    ui.serve(
        "**/api/runs?awaiting=true",
        awaiting(
            [
                a_run(run_id="get-1", kind="get", intent=None),
                a_run(run_id="search-1", intent="Quiet interiors by lamplight in the evening"),
            ],
            {"get-1": 2, "search-1": 1},
        ),
    )
    ui.page.set_viewport_size(PHONE)
    ui.open("#to_review")
    ui.page.wait_for_selector("#view a.row-link")

    for review in ui.page.locator("#view a.row-link").all():
        box = review.bounding_box()
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= PHONE["width"], "Review is past the screen's edge"
    assert sideways(ui) <= 0


def test_on_a_phone_an_activity_row_is_a_card_and_the_whole_card_opens_it(ui):
    """Stacked cards, each cell under its heading, the row itself the link."""
    ui.serve("**/api/runs?awaiting=true", awaiting([a_run(run_id="search-1", intent="Quiet interiors")], {"search-1": 1}))
    ui.page.set_viewport_size(PHONE)
    ui.open("#to_review")
    ui.page.wait_for_selector("#view a.row-link")

    row = ui.page.locator("#view tbody tr").first
    assert row.evaluate("(tr) => getComputedStyle(tr).display") == "block"
    headings = row.locator("td").evaluate_all("(tds) => tds.map((td) => getComputedStyle(td, '::before').content)")
    assert '"Asked for"' in headings, f"a cell lost the heading that says what it is: {headings}"
    # A point on the card well away from the link itself lands on the link.
    box = row.bounding_box()
    hit = ui.page.evaluate(
        "([x, y]) => { const n = document.elementFromPoint(x, y); return n && n.closest('a') ? n.closest('a').className : null; }",
        [box["x"] + 12, box["y"] + 12],
    )
    assert hit and "row-link" in hit, "the card is not the link"
    ui.page.mouse.click(box["x"] + 12, box["y"] + 12)
    ui.page.wait_for_function("() => location.hash.startsWith('#review/search-1')")


def test_at_desktop_width_an_activity_table_is_still_a_table(ui):
    """The cards are a phone's; a wide screen scans across the row."""
    ui.serve("**/api/runs?awaiting=true", awaiting([a_run(run_id="search-1", intent="Quiet interiors")], {"search-1": 1}))
    ui.page.set_viewport_size({"width": 1280, "height": 800})
    ui.open("#to_review")
    ui.page.wait_for_selector("#view a.row-link")
    assert ui.page.locator("#view tbody tr").first.evaluate("(tr) => getComputedStyle(tr).display") == "table-row"


def test_the_top_bar_is_one_row_on_a_phone(ui):
    ui.page.set_viewport_size(PHONE)
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state]")
    tops = ui.page.evaluate(
        "() => [...document.querySelector('header.topbar').children]"
        ".filter((n) => n.offsetParent !== null).map((n) => Math.round(n.getBoundingClientRect().top))"
    )
    assert len(tops) >= 3, "the bar lost one of its parts rather than fitting them"
    assert max(tops) - min(tops) <= 8, f"the top bar wraps onto more than one row: {tops}"
    assert ui.page.locator("#status").is_visible(), "the indicator was pushed off rather than fitted"


# -- the keyboard ------------------------------------------------------------------


def ring_is_whole(ui, locator) -> bool:
    """Whether the focused control's ring is drawn where nothing clips it.

    The ring is either the element's own outline, which must sit inside every
    ancestor that clips, or an inset ring painted inside the element.
    """
    return locator.evaluate("""(node) => {
          const inset = getComputedStyle(node, '::after').boxShadow;
          if (inset && inset.includes('inset')) return true;
          const style = getComputedStyle(node);
          if (style.outlineStyle === 'none') return false;
          const grow = parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset);
          const r = node.getBoundingClientRect();
          for (let up = node.parentElement; up; up = up.parentElement) {
            const s = getComputedStyle(up);
            if (s.overflow === 'visible' && s.overflowX === 'visible') continue;
            const c = up.getBoundingClientRect();
            if (r.left - grow < c.left || r.top - grow < c.top || r.right + grow > c.right || r.bottom + grow > c.bottom) return false;
          }
          return true;
        }""")


def test_a_posters_tile_s_picture_shows_its_whole_focus_ring(ui, work_with_an_image):
    """On Posters the picture is the tile's only way in, and its ring was clipped on three sides."""
    work = work_with_an_image("Nighthawks")
    ui.open("#collection?density=contact")
    picture = ui.page.locator(f"li.tile[data-artwork='{work.id}'] a.card-image")
    picture.focus()
    ui.page.keyboard.press("Shift+Tab")
    ui.page.keyboard.press("Tab")
    assert picture.evaluate("(a) => a === document.activeElement && a.matches(':focus-visible')")
    assert ring_is_whole(ui, picture)


def test_a_review_card_s_picture_shows_its_whole_focus_ring(ui):
    """The same clip on Review's `.card`, where the picture is a button that enlarges it."""
    from payloads import a_candidate_page, a_card

    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/search-1/candidates*", a_candidate_page([a_card()]))
    ui.open("#review/search-1")
    picture = ui.page.locator("li.card button.card-image.enlargeable").first
    picture.focus()
    ui.page.keyboard.press("Shift+Tab")
    ui.page.keyboard.press("Tab")
    assert picture.evaluate("(b) => b === document.activeElement && b.matches(':focus-visible')")
    assert ring_is_whole(ui, picture)


def test_an_overview_card_is_one_tab_stop_to_its_work(ui, work_with_an_image):
    """Picture and title both opened the work: two stops to one place, a third of every card's."""
    work = work_with_an_image("Nighthawks")
    ui.open("#collection?density=catalogue")
    card = ui.page.locator(f"li.card[data-artwork='{work.id}']")
    card.wait_for()
    stops = card.evaluate(
        "(li) => [...li.querySelectorAll('a[href], button, input, [tabindex]')]"
        ".filter((n) => n.tabIndex >= 0 && !n.disabled && n.offsetParent !== null)"
        ".map((n) => n.getAttribute('href'))"
    )
    to_the_work = [href for href in stops if href and work.id in href]
    assert len(to_the_work) == 1, f"the card reaches its work by {len(to_the_work)} Tab stops"
    # Still a way in for a pointer: the picture opens the work.
    assert card.locator("a.card-image").get_attribute("href") == card.locator(".card-title a").get_attribute("href")


def test_two_works_sharing_a_title_have_different_names(ui, service, seeded_service):
    """'Untitled' by two artists: a reader moving link by link heard the same word twice."""
    rothko = service.add_artist(name="Mark Rothko")
    martin = service.add_artist(name="Agnes Martin")
    service.add_artwork(title="Untitled", artist_id=rothko.id, date_created="1969")
    service.add_artwork(title="Untitled", artist_id=martin.id, date_created="1977")
    ui.open("#collection?density=catalogue")
    ui.page.wait_for_selector("li.card .card-title a:text-is('Untitled')")

    names = [
        link.evaluate("(a) => a.getAttribute('aria-label') || a.textContent")
        for link in ui.page.locator("li.card .card-title a:text-is('Untitled')").all()
    ]
    assert len(names) == 2
    assert len(set(names)) == 2, f"two works answer to one name: {names}"
    assert all(name.startswith("Untitled") for name in names), "the name no longer starts with what is seen"


def test_a_facet_click_keeps_the_keyboard_on_the_facet(ui):
    """Choosing a facet repainted the rail and dropped focus to the top of the view."""
    ui.serve(
        "**/api/works?*",
        a_listing(
            [],
            total=0,
            facets=[a_facet_group("movement", [a_facet_option("Baroque", 51), a_facet_option("Rococo", 3)])],
        ),
    )
    ui.open("#collection")
    baroque = ui.page.locator("button.facet-option", has_text="Baroque")
    baroque.focus()
    ui.page.evaluate("() => { window.__before = document.activeElement; }")
    ui.page.keyboard.press("Enter")
    # The new paint's button, not the old one still holding focus before it.
    ui.page.wait_for_function(
        "() => document.activeElement !== window.__before && document.activeElement.isConnected"
        " && document.activeElement.dataset.focusKey === 'facet:movement:Baroque'"
    )


def test_the_status_indicator_is_written_only_when_it_changes(ui, seeded_service):
    """A live region rewritten with its own words re-announces them on every page."""
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state]")
    ui.page.evaluate(
        "() => { window.__writes = 0;"
        " new MutationObserver((m) => { window.__writes += m.length; })"
        ".observe(document.getElementById('status'), { childList: true, subtree: true, characterData: true }); }"
    )
    for view in ("walls", "history", "collection"):
        # Through the router, as a click on the sidebar is, so the page is not reloaded.
        ui.page.evaluate("(view) => { location.hash = '#' + view; }", view)
        ui.page.wait_for_function("(view) => document.title !== '' && location.hash === '#' + view", arg=view)
        ui.page.wait_for_load_state("networkidle")
    assert ui.page.evaluate("() => window.__writes") == 0, "the indicator was rewritten with the words it held"


def test_the_status_indicator_still_says_a_change(ui, seeded_service, a_health_reading):
    """The other half: a reading that moves is written, so the region still speaks."""
    ui.serve("**/api/health", [a_health_reading(), a_health_reading(walls=[])])
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='well']")
    ui.page.evaluate("() => { location.hash = '#walls'; }")
    ui.page.wait_for_selector("#status[data-state='unwell']")


def test_a_review_note_field_is_named_for_its_work(ui):
    """Every card's field was "Why (optional)", once per card."""
    from payloads import a_candidate, a_candidate_page, a_card

    cards = [
        a_card(work=a_candidate(work_id="work-1", title="Nighthawks")),
        a_card(work=a_candidate(work_id="work-2", title="Automat")),
    ]
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/search-1/candidates*", a_candidate_page(cards))
    ui.open("#review/search-1")
    ui.page.wait_for_selector("#reason-work-1")
    names = [ui.page.get_by_label(f"Why (optional), for {title}").count() for title in ("Nighthawks", "Automat")]
    assert names == [1, 1]
    # What is seen is unchanged: the title is in a visually hidden part of the label.
    assert ui.page.locator("label[for='reason-work-1']").evaluate("(l) => l.firstChild.textContent") == "Why (optional)"


def test_a_table_wider_than_its_box_takes_the_keyboard(ui, a_health_reading):
    """A box that scrolls is a Tab stop, named by its caption; one that fits is not."""
    ui.serve("**/api/runs?awaiting=true", awaiting([a_run(run_id="search-1", intent="Quiet interiors")], {"search-1": 1}))
    ui.page.set_viewport_size({"width": 1280, "height": 800})
    ui.open("#to_review")
    box = ui.page.locator("#view .table-scroll").first
    box.wait_for()
    assert box.get_attribute("tabindex") is None, "a table that fits became a stop on nothing"
    ui.page.evaluate("() => { document.querySelector('#view .table-scroll table').style.minWidth = '3000px'; }")
    ui.page.wait_for_function("() => document.querySelector('#view .table-scroll').getAttribute('tabindex') === '0'")
    assert box.get_attribute("role") == "region"
    assert box.get_attribute("aria-label") == "Every run with works waiting for your verdict, newest first."
