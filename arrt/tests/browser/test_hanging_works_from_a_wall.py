"""Hanging chosen works on a wall, started from that wall's card on Walls.

The owner's ruling of 2026-11-20 (`.prawduct/owner-rulings.md`, a hang can be started
from Walls): a wall's Hanging line offers *Choose works* beside its themes, which opens
Artworks selecting for that wall; the selection's *Hang…* then hangs there without asking
which wall (`build-plan-audit-wave-2b.md` Chunk 57).

**The claim is the request and what the server then holds**, as in
`test_hanging_a_selection.py`: a page that named the right wall and sent the works to
another would pass a check of its words alone.

**The "for this wall" state is the address** (`?hang_on=<wall id>`, `screens/collection.js`
`chosenFor`). Each way off it is held here: what the page says after it, and whether a
later *Hang…* still asks which wall. Every test has two walls, so a *Hang…* that asks is a
dialog of walls and one that does not is the question about one wall.
"""

import json
import re

import httpx
import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

SELECTION = re.compile(r"/api/walls/[^/]+/selection$")


@pytest.fixture
def api(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def walls(services):
    """The catalogue's own wall and a second, so an ordinary *Hang…* asks which."""
    hall = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="The study")
    return hall, study


@pytest.fixture
def two_works(work_with_an_image):
    return [work_with_an_image("Study A"), work_with_an_image("Study B")]


def hanging_on(api, wall_id):
    """The works the server says hang on a wall, in order, or none."""
    wall = next(wall for wall in api.get("/api/walls").json()["walls"] if wall["wall_id"] == wall_id)
    if wall["theme"] is None:
        return []
    return [work["artwork_id"] for work in api.get(f"/api/themes/{wall['theme']['theme_id']}").json()["works"]]


def selection_posts(ui):
    return [url for url in ui.requests if SELECTION.search(url)]


def card(ui, wall):
    return ui.page.locator(f"#view section.wall[data-wall='{wall.id}']")


def choose_works_for(ui, wall):
    """From Walls, press the wall's *Choose works*, and wait for Artworks selecting for it."""
    ui.open("#walls")
    card(ui, wall).locator("a.wall-choose-works").click()
    expect(ui.page.locator("#view .hang-for-wall")).to_be_visible()
    expect(ui.page.locator("#view button.select-toggle")).to_have_text("Stop selecting", use_inner_text=True)


def tick(ui, work):
    ui.page.check(f"#view [data-artwork='{work.id}'] input[type='checkbox']")


def hang_button(ui):
    return ui.page.locator("#view .selection button.selection-hang")


def asks_which_wall(ui):
    """Press *Hang…* with a work ticked, and see the dialog of walls rather than a question."""
    hang_button(ui).click()
    expect(ui.page.locator("dialog.panel-dialog[open] .wall-choices button")).to_have_count(2)
    expect(ui.page.locator("dialog.confirm")).to_have_count(0)


def start_an_ordinary_selection(ui, work):
    ui.page.locator("#view button.select-toggle:visible").wait_for()
    expect(ui.page.locator("#view .hang-for-wall")).to_have_count(0)
    ui.page.click("#view button.select-toggle")
    tick(ui, work)
    expect(hang_button(ui)).to_have_text("Hang…", use_inner_text=True)


# -- the flow ------------------------------------------------------------------


def test_choosing_works_for_a_wall_hangs_them_there_without_asking_which(ui, api, walls, two_works):
    hall, study = walls
    choose_works_for(ui, study)
    for work in two_works:
        tick(ui, work)
    expect(hang_button(ui)).to_have_text("Hang on The study…", use_inner_text=True)

    hang_button(ui).click()
    # The question, about that wall: no dialog of walls first, and it still says what happens.
    ui.page.locator("dialog.confirm[open]").wait_for()
    expect(ui.page.locator(".wall-choices")).to_have_count(0)
    expect(ui.page.locator(".confirm-title")).to_have_text("Hang 2 works on The study?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text("The study shows them until something else is hung there")
    with ui.page.expect_request(lambda request: bool(SELECTION.search(request.url)) and request.method == "POST") as sent:
        ui.page.click(".confirm-actions button:text-is('Hang')")

    assert sent.value.url.endswith(f"/api/walls/{study.id}/selection")
    assert json.loads(sent.value.post_data) == {"artwork_ids": [work.id for work in two_works]}  # one-shot: the body sent
    assert len(selection_posts(ui)) == 1
    # Back on Walls, at that wall, which shows what it now hangs, with the keyboard on its card.
    expect(ui.page).to_have_url(re.compile(rf"#walls\?wall={study.id}$"))
    expect(card(ui, study).locator(".wall-hanging")).to_have_text(re.compile(r"^Hanging a selection\."), use_inner_text=True)
    expect(ui.page.locator(f"#view section.wall[data-wall='{study.id}'] h2.wall-title")).to_be_focused()
    assert hanging_on(api, study.id) == [work.id for work in two_works]
    assert hanging_on(api, hall.id) == []


def test_the_page_says_which_wall_and_a_screen_reader_hears_it_as_selection_starts(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)

    note = ui.page.locator("#view .hang-for-wall")
    expect(note).to_contain_text("Choosing works to hang on The study.", use_inner_text=True)
    # The keyboard, and so a screen reader, arrives on the words naming the wall.
    expect(note).to_be_focused()


def test_leaving_without_hanging_sends_nothing_and_returns_to_the_wall_s_picker(ui, api, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)
    tick(ui, two_works[0])

    ui.page.locator("#view .hang-for-wall a.hang-for-wall-leave").click()

    expect(ui.page).to_have_url(re.compile(r"#walls$"))
    expect(card(ui, study).locator("a.wall-choose-works")).to_be_focused()
    assert selection_posts(ui) == []
    assert hanging_on(api, study.id) == []


def test_the_way_in_and_out_work_by_keyboard_alone(ui, api, walls, two_works):
    _, study = walls
    ui.open("#walls")
    card(ui, study).locator("a.wall-choose-works").focus()
    ui.page.keyboard.press("Enter")
    note = ui.page.locator("#view .hang-for-wall")
    expect(note).to_be_focused()

    ui.page.keyboard.press("Tab")
    expect(ui.page.locator("#view a.hang-for-wall-leave")).to_be_focused()
    ui.page.keyboard.press("Enter")

    expect(card(ui, study).locator("a.wall-choose-works")).to_be_focused()
    assert selection_posts(ui) == []


def test_the_words_for_the_wall_leave_select_last_on_the_right_on_a_phone(ui, walls, two_works):
    _, study = walls
    ui.page.set_viewport_size({"width": 390, "height": 844})
    choose_works_for(ui, study)

    # Above the toolbar, not in it: the toolbar's last control is still *Select*'s toggle.
    expect(ui.page.locator("#view .page-toolbar .hang-for-wall")).to_have_count(0)
    last = ui.page.locator("#view .page-toolbar-controls > *:visible").last
    expect(last).to_have_class(re.compile(r"\bselect-toggle\b"))
    width = ui.page.evaluate("() => document.documentElement.scrollWidth")
    assert width <= 390


def test_a_wall_renamed_while_choosing_is_named_as_it_is_now_by_the_question(ui, services, walls, two_works):
    """The note says the name read when the page was drawn; the question reads the walls when pressed."""
    _, study = walls
    choose_works_for(ui, study)
    tick(ui, two_works[0])
    services.display.rename_wall(study.id, name="The library")

    hang_button(ui).click()

    expect(ui.page.locator(".confirm-title")).to_have_text("Hang 1 work on The library?", use_inner_text=True)


# -- every way off the address ends it, or shows it ---------------------------


def test_after_back_to_walls_a_selection_on_artworks_asks_which_wall(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)
    ui.page.go_back()
    card(ui, study).locator("a.wall-choose-works").wait_for()

    ui.page.locator("nav.sidebar a[data-view='collection']").first.click()
    start_an_ordinary_selection(ui, two_works[0])
    asks_which_wall(ui)


def test_the_sidebar_s_artworks_is_an_ordinary_selection(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)

    ui.page.locator("nav.sidebar a[data-view='collection']").first.click()
    expect(ui.page).to_have_url(re.compile(r"#collection$"))
    start_an_ordinary_selection(ui, two_works[0])
    asks_which_wall(ui)


def test_a_reload_keeps_it_and_says_so(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)

    ui.page.reload()

    expect(ui.page.locator("#view .hang-for-wall")).to_contain_text("Choosing works to hang on The study.", use_inner_text=True)
    expect(ui.page.locator("#view button.select-toggle")).to_have_text("Stop selecting", use_inner_text=True)
    tick(ui, two_works[0])
    hang_button(ui).click()
    expect(ui.page.locator(".confirm-title")).to_have_text("Hang 1 work on The study?", use_inner_text=True)


def test_back_from_a_work_opened_from_a_tile_shows_it_again(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)

    ui.page.locator(f"#view [data-artwork='{two_works[0].id}'] a[href^='#work/']").first.click()
    ui.page.locator("#view a.back-link").wait_for()
    ui.page.locator("#view a.back-link").click()

    expect(ui.page.locator("#view .hang-for-wall")).to_contain_text("Choosing works to hang on The study.", use_inner_text=True)
    tick(ui, two_works[0])
    hang_button(ui).click()
    expect(ui.page.locator(".confirm-title")).to_have_text("Hang 1 work on The study?", use_inner_text=True)


def test_stop_selecting_ends_choosing_for_the_wall(ui, walls, two_works):
    _, study = walls
    choose_works_for(ui, study)

    ui.page.click("#view button.select-toggle")

    expect(ui.page).to_have_url(re.compile(r"#collection$"))
    start_an_ordinary_selection(ui, two_works[0])
    asks_which_wall(ui)


def test_an_address_naming_a_wall_not_recorded_says_so_and_asks(ui, walls, two_works):
    ui.open("#collection?hang_on=wall-that-is-gone")

    expect(ui.page.locator("#view .hang-for-wall-gone")).to_contain_text("is not recorded", use_inner_text=True)
    start_an_ordinary_selection(ui, two_works[0])
    asks_which_wall(ui)


def test_a_wall_deleted_while_choosing_is_said_before_the_others_are_offered(ui, services, walls, two_works):
    hall, study = walls
    choose_works_for(ui, study)
    tick(ui, two_works[0])
    services.display.delete_wall(study.id)

    hang_button(ui).click()

    dialog = ui.page.locator("dialog.panel-dialog[open]")
    gone = "The wall these were chosen for is no longer recorded."
    expect(dialog.locator(".panel-dialog-lead")).to_have_text(gone, use_inner_text=True)
    expect(dialog.locator(".wall-choices button")).to_have_text([hall.name], use_inner_text=True)
