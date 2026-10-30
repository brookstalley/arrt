"""The Theme page shows its art and links it, at a few boxes a row.

The second UX walk (`ux-review-2026-10.md` finding 31, #352) found the Theme
page was a wall of buttons with no art and no links:
- 61 rows of five acts made a 7,256 px page of 305 boxes.
- Titles, artists and the wall badge were plain text, and the Size column was
  empty.
- *Add a work* on *All works* offered only works already in it (the picker went
  on 2026-10-29: works are added from Artworks).
- On a phone the acts were off-screen in a sideways scroller.
Ruling 2 of 2026-10-11 settled that a theme is never shuffled.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

PHONE = {"width": 390, "height": 844}


@pytest.fixture
def evening(services, service, work_with_an_image):
    """A theme of three: one with its master on disk, two with none, two by an artist."""
    hopper = service.add_artist(name="Edward Hopper", born=1882, died=1967)
    pictured = work_with_an_image(title="Nighthawks")
    automat = service.add_artwork(title="Automat", artist_id=hopper.id)
    office = service.add_artwork(title="Office at Night", artist_id=hopper.id)
    outside = service.add_artwork(title="Not in the theme")
    theme = services.display.add_theme(name="Evening")
    for position, work in enumerate([pictured, automat, office]):
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    return theme, hopper, (pictured, automat, office), outside


def open_theme(ui, theme):
    ui.open(f"#theme/{theme.id}")
    ui.page.wait_for_selector("tbody tr")


def test_every_member_row_shows_a_picture_and_links_its_work_and_artist(ui, evening):
    theme, hopper, (pictured, automat, office), _outside = evening
    open_theme(ui, theme)

    rows = ui.page.locator("tbody tr")
    assert rows.count() == 3
    for at, work in enumerate((pictured, automat, office)):
        row = rows.nth(at)
        assert row.locator(f"a[href^='#work/{work.id}']").inner_text() == work.title
        assert row.locator(".member-picture img, .member-picture .card-image-absent").count() == 1
    assert rows.nth(0).locator(".member-picture img").count() == 1
    for at in (1, 2):
        assert rows.nth(at).locator(f"a[href^='#artist/{hopper.id}']").inner_text() == "Edward Hopper"
        assert rows.nth(at).locator(".member-picture .card-image-absent").inner_text().strip() == "No picture"
    ui.page.wait_for_load_state("networkidle")
    assert ui.requests_matching(f"/api/works/{automat.id}/thumbnail") == []


def test_a_row_costs_two_boxes_not_five(ui, evening):
    theme, *_ = evening
    open_theme(ui, theme)
    per_row = ui.page.locator("tbody tr").evaluate_all(
        "(rows) => rows.map((row) => row.querySelectorAll('button, input, select').length)"
    )
    assert per_row == [2, 2, 2]


def test_works_are_added_from_artworks_and_the_page_has_no_picker(ui, evening):
    """*Add a work* offered every work in the library and *Add*; on *All works*,
    which holds them, it offered only works already in it (finding 31). The
    owner ruled on 2026-10-29 (`ia-proposal.md` § Rulings (2026-10-27)) that a
    theme's page has no picker: *Add works* goes to Artworks, where *Add to
    theme…* acts on a selection. The two tests that held what the picker offered
    went with it."""
    theme, *_ = evening
    open_theme(ui, theme)

    assert ui.page.locator("#view select").count() == 0
    assert ui.page.locator("#view button:text-is('Add')").count() == 0
    add = ui.page.locator("#view .page-toolbar").get_by_role("link", name="Add works")
    assert add.get_attribute("href") == "#collection"


def test_nothing_on_the_page_speaks_of_shuffle(ui, evening):
    theme, *_ = evening
    open_theme(ui, theme)
    assert "shuffl" not in ui.page.locator("#view").inner_text().lower()


def test_the_size_column_is_there_only_when_it_has_something_to_say(ui, evening, services, work_with_an_image):
    theme, *_ = evening
    open_theme(ui, theme)
    headings = [heading.lower() for heading in ui.page.locator("thead th").all_inner_texts()]
    assert "size" in headings, "two works with no size known have something to say"

    large = work_with_an_image(title="Large enough", width=8000, height=6000)
    plenty = services.display.add_theme(name="Plenty")
    services.display.add_to_theme(theme_id=plenty.id, artwork_id=large.id, position=0)
    ui.open(f"#theme/{plenty.id}")
    # Waited on by its own row: the address changes only its hash, so the table
    # of the theme before stays on screen until this one paints.
    ui.page.wait_for_selector("tbody td[data-label='Title']:has-text('Large enough')")
    headings = [heading.lower() for heading in ui.page.locator("thead th").all_inner_texts()]
    assert "size" not in headings, "a column empty on every row is a heading over nothing"


def test_on_a_phone_every_act_is_reachable_without_a_sideways_scroll(ui, evening):
    theme, *_ = evening
    ui.page.set_viewport_size(PHONE)
    open_theme(ui, theme)
    report = ui.page.evaluate("""() => ({
          scrollers: [...document.querySelectorAll('#view .table-scroll')]
            .filter((n) => n.scrollWidth > n.clientWidth + 1).length,
          offscreen: [...document.querySelectorAll('#view tbody :is(button, input)')]
            .filter((n) => n.getBoundingClientRect().right > window.innerWidth).length,
          caption: (() => { const c = document.querySelector('#view table caption');
            return c ? c.scrollWidth <= c.clientWidth + 1 : true; })(),
        })""")
    assert report == {"scrollers": 0, "offscreen": 0, "caption": True}


def test_on_a_phone_a_member_is_one_compact_card(ui, evening):
    """Found by photograph (2026-10-29): each member was a column of labelled cells,
    about 300 px a work, and "No picture" broke mid-word in its square. A member
    is now one card, the picture beside its title, with no heading over each
    value, and the placeholder's words whole."""
    theme, *_ = evening
    ui.page.set_viewport_size(PHONE)
    open_theme(ui, theme)
    report = ui.page.evaluate("""() => {
          const rows = [...document.querySelectorAll('#view tbody tr')];
          const labels = [...document.querySelectorAll('#view tbody td')]
            .map((td) => getComputedStyle(td, '::before').content)
            .filter((content) => content && content !== 'none' && content !== 'normal');
          const broken = [...document.querySelectorAll('#view .member-picture .card-image-absent span')].filter((span) => {
            const range = document.createRange();
            range.selectNodeContents(span);
            const words = span.textContent.split(' ').length;
            return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size > words;
          }).length;
          const sideBySide = rows.every((row) => {
            const picture = row.querySelector("td[data-label='Picture']").getBoundingClientRect();
            const title = row.querySelector("td[data-label='Title']").getBoundingClientRect();
            return title.left >= picture.right && Math.abs(title.top - picture.top) < 24;
          });
          const tallest = Math.max(...rows.map((row) => row.getBoundingClientRect().height));
          return { tallest, labels: labels.length, broken, sideBySide };
        }""")
    assert report["tallest"] < 140, report
    assert report == {"tallest": report["tallest"], "labels": 0, "broken": 0, "sideBySide": True}


def test_on_a_phone_the_pages_own_acts_step_out_while_selecting(ui, evening):
    """Found by photograph: *Hang…*, *Edit…* and *Add works* beside the selection's
    acts made the sticky toolbar six rows on a phone. They step out while *Select*
    is on, as Artworks' View and Sort do, and come back with *Stop selecting*."""
    theme, *_ = evening
    ui.page.set_viewport_size(PHONE)
    open_theme(ui, theme)
    toolbar = ui.page.locator("#view .page-toolbar")
    hang = toolbar.locator("button", has_text="Hang…")
    assert hang.is_visible()

    toolbar.locator("button.select-toggle").click()
    assert hang.is_hidden()
    assert toolbar.get_by_role("link", name="Add works").is_hidden()
    assert toolbar.locator("button.selection-remove").is_visible()

    toolbar.locator("button.select-toggle").click()
    assert hang.is_visible()
