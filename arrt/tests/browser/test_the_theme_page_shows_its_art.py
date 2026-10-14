"""The Theme page shows its art and links it, at a few boxes a row.

The second UX walk (`ux-review-2026-10.md` finding 31, #352) found the Theme
page was a wall of buttons with no art and no links:
- 61 rows of five acts made a 7,256 px page of 305 boxes.
- Titles, artists and the wall badge were plain text, and the Size column was
  empty.
- *Add a work* on *All works* offered only works already in it.
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


def test_add_a_work_offers_only_works_not_in_the_theme(ui, evening):
    theme, _hopper, members, outside = evening
    open_theme(ui, theme)
    offered = ui.page.locator(f"#add-{theme.id} option").evaluate_all("(options) => options.map((o) => o.value)")
    assert outside.id in offered
    assert not {work.id for work in members} & set(offered)

    # Added, it leaves the picker.
    ui.page.select_option(f"#add-{theme.id}", value=outside.id)
    ui.page.click("button:text-is('Add')")
    ui.page.wait_for_function("() => document.querySelectorAll('tbody tr').length === 4")
    offered = ui.page.locator(f"#add-{theme.id} option").evaluate_all("(options) => options.map((o) => o.value)")
    assert outside.id not in offered


def test_a_theme_holding_every_work_says_so_rather_than_offering_any(ui, services, service):
    work = service.add_artwork(title="The only work")
    every = services.display.add_theme(name="All works")
    services.display.add_to_theme(theme_id=every.id, artwork_id=work.id, position=0)
    # The seeded catalogue's own works go in too, so nothing is left to add.
    for at, entry in enumerate(service.list_artworks(limit=100).entries):
        if entry.artwork.id != work.id:
            services.display.add_to_theme(theme_id=every.id, artwork_id=entry.artwork.id, position=at + 1)
    open_theme(ui, every)

    assert ui.page.locator(f"#add-{every.id}").is_hidden()
    assert ui.page.locator("#view p", has_text="Every work in the library is in All works.").is_visible()


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
