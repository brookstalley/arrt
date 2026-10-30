"""The Themes index as cards, and the theme page's ordering, in a real browser.

`#theme` is a grid of cards, one per theme, each a link to the theme's own page,
where every act on it lives. Ten themes fit on one desktop screen, which is the
measure the index was rebuilt to: the old index expanded every theme with its
whole membership and grew by a table row per work.

The theme page orders its works with Move to top and Move to bottom beside ↑
and ↓, all of them buttons a keyboard reaches. A theme has an order and is never
shuffled, so its page says nothing of shuffle; that is the wall's setting.
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

#: A desktop screen: the size the sidebar's own desktop checks use.
DESKTOP = {"width": 1280, "height": 800}

TITLES = ("Autumn Rhythm", "Blue Poles", "Convergence", "Number 1")


def _titles(ui):
    return ui.page.locator("tbody tr td[data-label='Title']").all_inner_texts()


def _first_row_becomes(ui, title):
    ui.page.wait_for_function(
        "(title) => { const cell = document.querySelector(\"tbody tr td[data-label='Title']\");"
        " return cell && cell.textContent === title; }",
        arg=title,
    )


def _last_row_becomes(ui, title):
    ui.page.wait_for_function(
        "(title) => { const cells = document.querySelectorAll(\"tbody tr td[data-label='Title']\");"
        " return cells.length && cells[cells.length - 1].textContent === title; }",
        arg=title,
    )


@pytest.fixture
def winter(services, service):
    """A theme of four works in a known order, hanging nowhere."""
    theme = services.display.add_theme(name="Winter")
    for position, title in enumerate(TITLES):
        work = service.add_artwork(title=title)
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
    return theme


# -- the index -----------------------------------------------------------------


@pytest.fixture
def ten_themes(services, work_with_an_image):
    """Ten themes as tall as a card gets: four pictures, a long name, and a badge each.

    Each hangs on a wall of its own, so every card carries its badge line; a
    grid row is as tall as its tallest card, and a fixture where only one card
    had one would measure a shorter page than ten real themes can make.
    """
    pictures = [work_with_an_image(f"Picture {number}") for number in range(4)]
    themes = []
    for number in range(10):
        theme = services.display.add_theme(name=f"Evenings in the long room {number + 1}")
        for position, picture in enumerate(pictures):
            services.display.add_to_theme(theme_id=theme.id, artwork_id=picture.id, position=position)
        wall = services.display.add_wall(name=f"Room {number + 1}")
        services.display.activate_theme(theme.id, wall_id=wall.id)
        themes.append(theme)
    services.display.make_default(themes[0].id)
    return themes


def _every_card_is_on_screen(ui):
    return ui.page.evaluate("""() => {
          window.scrollTo(0, 0);
          const cards = [...document.querySelectorAll('#view li.theme-card')];
          return [cards.length, Math.max(...cards.map((card) => card.getBoundingClientRect().bottom)), window.innerHeight];
        }""")


@pytest.mark.parametrize("wider_type", [False, True], ids=["this-machine's-fonts", "wider-fonts"])
def test_ten_themes_fit_on_one_desktop_screen(ui, ten_themes, wider_type):
    """The measure the index was rebuilt to, taken with every card at its tallest.

    Again with every letter spaced a tenth of an em wider, because CI's fonts set
    wider than this Mac's: a fit that holds only for the fonts it was measured
    with is a fit by luck.
    """
    ui.page.set_viewport_size(DESKTOP)
    ui.open("#theme")
    ui.page.wait_for_selector("li.theme-card")
    if wider_type:
        ui.page.add_style_tag(content="* { letter-spacing: 0.1em !important; }")
    ui.page.wait_for_function("() => document.querySelectorAll('li.theme-card img').length === 40")

    count, lowest, height = _every_card_is_on_screen(ui)

    assert count == 10
    assert lowest <= height, f"the last card ends at {lowest}px on a {height}px screen"


def test_a_card_says_what_the_theme_is_and_links_to_it(ui, services, ten_themes):
    """Name, count, pictures and where it hangs, and the name is the link."""
    first = ten_themes[0]
    ui.open("#theme")
    card = ui.page.locator(f"li.theme-card[data-theme='{first.id}']")
    card.wait_for()

    assert card.locator("h2 a").inner_text() == first.name
    assert card.locator("h2 a").get_attribute("href") == f"#theme/{first.id}"
    assert card.locator(".card-meta").inner_text() == "4 works"
    assert card.locator(".theme-card-pictures img").count() == 4
    assert card.locator(".badge", has_text="on Room 1").count() == 1
    assert card.locator(".badge-default").count() == 1
    # The default mark is on the default's card and no other.
    assert ui.page.locator("li.theme-card .badge-default").count() == 1


def test_the_pictures_are_one_tab_stop_with_the_name_not_a_second(ui, ten_themes):
    """As on Artists' cards: the picture strip opens the page to a pointer only."""
    ui.open("#theme")
    strip = ui.page.locator("li.theme-card .theme-card-pictures").first
    strip.wait_for()

    assert strip.get_attribute("tabindex") == "-1"
    assert strip.get_attribute("aria-hidden") == "true"
    assert strip.get_attribute("href") == ui.page.locator("li.theme-card h2 a").first.get_attribute("href")


def test_following_a_card_opens_that_theme(ui, winter, services):
    """Two themes, so arriving at the one clicked is not arriving at the only one."""
    services.display.add_theme(name="Late night")
    ui.open("#theme")
    ui.page.click("li.theme-card h2 a:text-is('Winter')")
    ui.page.wait_for_selector("#view h1:has-text('Winter')")

    assert ui.page.evaluate("() => window.location.hash") == f"#theme/{winter.id}"
    assert _titles_after_paint(ui) == list(TITLES)


def _titles_after_paint(ui):
    ui.page.wait_for_selector("tbody tr")
    return _titles(ui)


def test_the_index_offers_no_act_on_a_theme(ui, winter):
    """Rename, delete, hanging and membership are the theme page's, and only creating is here,
    behind *New theme…* since ruling 9 of 2026-10-27 (it was a field and *Create* above the cards)."""
    ui.open("#theme")
    ui.page.wait_for_selector("li.theme-card")

    assert ui.page.locator("#view button").all_inner_texts() == ["New theme…"]
    assert ui.page.locator("#view input").count() == 0
    assert ui.page.locator("#view select").count() == 0
    assert ui.page.locator("#view table").count() == 0


def test_a_theme_with_works_and_no_pictures_says_so(ui, winter):
    """An empty strip on a theme of four works must not read as an empty theme."""
    ui.open("#theme")
    card = ui.page.locator(f"li.theme-card[data-theme='{winter.id}']")
    card.wait_for()

    assert card.locator(".card-meta").inner_text() == "4 works · no pictures yet"
    assert card.locator("img").count() == 0


def test_an_empty_theme_does_not_claim_its_pictures_are_missing(ui, services):
    """The paired negative: no works is no pictures, and saying both is saying it twice."""
    quiet = services.display.add_theme(name="Quiet")
    ui.open("#theme")
    card = ui.page.locator(f"li.theme-card[data-theme='{quiet.id}']")
    card.wait_for()

    assert card.locator(".card-meta").inner_text() == "0 works"


# -- ordering on the theme page ------------------------------------------------
#
# A drag handle per row since ruling 9 of 2026-10-27 (a Position field per row
# from #352 until then, and four buttons before that). The handle is a button,
# so the keyboard moves a work too: the arrows one place, Home and End to the
# ends.


def _handle(ui, title):
    return ui.page.locator(f"button.drag-handle[aria-label='Move {title}']")


def test_home_and_end_take_a_work_to_either_end(ui, winter):
    """From the middle, so neither end is where the work already was."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    _handle(ui, "Convergence").press("Home")
    _first_row_becomes(ui, "Convergence")
    assert _titles(ui) == ["Convergence", "Autumn Rhythm", "Blue Poles", "Number 1"]

    _handle(ui, "Autumn Rhythm").press("End")
    _last_row_becomes(ui, "Autumn Rhythm")
    assert _titles(ui) == ["Convergence", "Blue Poles", "Number 1", "Autumn Rhythm"]

    # And the catalogue holds it, not just the table.
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    assert _titles(ui) == ["Convergence", "Blue Poles", "Number 1", "Autumn Rhythm"]


def test_the_keyboard_stays_on_the_work_it_moves_and_hears_where_it_landed(ui, winter):
    """Each press is one move, repainted from the answer; the keyboard is put back
    on the moved work's handle, so the next press moves the same work, and the
    live region says where it landed."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    _handle(ui, "Number 1").focus()
    ui.page.keyboard.press("Home")
    _first_row_becomes(ui, "Number 1")
    ui.page.wait_for_function("() => document.activeElement.getAttribute('aria-label') === 'Move Number 1'")
    assert ui.page.locator("#view [aria-live='polite']", has_text="Number 1 moved to 1 of 4.").count() == 1

    ui.page.keyboard.press("ArrowDown")
    ui.page.wait_for_function(
        "() => document.querySelectorAll(\"tbody tr td[data-label='Title']\")[1].textContent === 'Number 1'"
    )
    ui.page.wait_for_function("() => document.activeElement.getAttribute('aria-label') === 'Move Number 1'")
    assert len(ui.requests_matching("/position")) == 2
    assert _titles(ui) == ["Autumn Rhythm", "Number 1", "Blue Poles", "Convergence"]


def test_dragging_a_handle_drops_the_work_where_the_pointer_leaves_it(ui, winter):
    """By pointer, onto the first row: the work lands there, read back from the server."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    start = _handle(ui, "Convergence").bounding_box()
    target = ui.page.locator("tbody tr").first.bounding_box()
    ui.page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    ui.page.mouse.down()
    ui.page.mouse.move(start["x"] + start["width"] / 2, target["y"] + 4, steps=8)
    # Marked where it will land before it is let go, on the side it lands.
    assert ui.page.locator("tbody tr.drop-target").count() == 1
    assert ui.page.locator("tbody tr.drop-target.drop-below").count() == 0
    ui.page.mouse.up()
    _first_row_becomes(ui, "Convergence")

    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    assert _titles(ui) == ["Convergence", "Autumn Rhythm", "Blue Poles", "Number 1"]
    # A finger drags the handle rather than scrolling the page.
    assert _handle(ui, "Convergence").evaluate("(node) => getComputedStyle(node).touchAction") == "none"


def test_a_drag_let_go_where_it_started_sends_nothing(ui, winter):
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    start = _handle(ui, "Blue Poles").bounding_box()
    ui.page.mouse.move(start["x"] + 5, start["y"] + 5)
    ui.page.mouse.down()
    ui.page.mouse.move(start["x"] + 6, start["y"] + 6, steps=3)
    ui.page.mouse.up()
    ui.page.wait_for_timeout(300)

    assert ui.requests_matching("/position") == []
    assert ui.page.locator("tbody tr.drop-target").count() == 0


def test_the_ends_offer_no_move_to_where_a_work_already_is(ui, winter):
    """Home on the first work and End on the last send nothing."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    _handle(ui, "Autumn Rhythm").press("Home")
    _handle(ui, "Number 1").press("End")
    ui.page.wait_for_timeout(300)
    assert ui.requests_matching("/position") == []


def test_the_order_copy_says_only_that_the_theme_is_in_order(ui, services, winter):
    """A theme is never shuffled, so its page does not speak of shuffle — even when the wall hanging it shuffles.

    The wall shuffles here so the case where a stale caption would say
    "shuffled" is the one exercised; and position deciding what "the wall"
    shows first would be false of that wall.
    """
    wall = services.display.survey_walls()[0].wall
    services.display.set_playback(wall.id, shuffle=True)
    services.display.activate_theme(winter.id, wall_id=wall.id)
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    caption = ui.page.inner_text("table caption")

    assert caption == "In curated order."
    assert "shuffle" not in ui.page.inner_text("main").lower()


# -- the title follows a rename (#302) -----------------------------------------


def test_renaming_a_theme_renames_the_tab(ui, winter):
    """The tab, the history and a bookmark name the theme as its heading does."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    assert re.match(r"^Winter\b", ui.page.title())

    # In the theme's *Edit…* since ruling 9 of 2026-10-27.
    ui.page.click("#view .page-toolbar button[aria-label='Edit Winter…']")
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill("Late night")
    dialog.get_by_role("button", name="Save Winter").click()
    ui.page.wait_for_selector("#view h1:has-text('Late night')")

    assert re.match(r"^Late night\b", ui.page.title())
    assert "Winter" not in ui.page.title()


def test_a_refused_move_is_said_beside_its_handle_and_moves_nothing(ui, winter):
    """The server refused it: the order stays, one request was sent, and the reason
    is said beside the handle that asked (`core/acting.js`)."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    ui.serve("**/api/themes/*/works/*/position", [(400, {"error": "That move was refused."})])

    handle = _handle(ui, "Number 1")
    handle.press("Home")

    assert ui.said_beside(handle).startswith("Couldn't move Number 1 to position 1: That move was refused.")
    assert len(ui.requests_matching("/position")) == 1
    assert _titles(ui) == list(TITLES)


# -- the page's head and New theme… (ruling 9 of 2026-10-27) -------------------------


def test_the_index_opens_with_its_name_its_facts_and_its_toolbar(ui, services, winter):
    """The page rules: the name, one line of facts, then the toolbar, and no form above the cards."""
    all_works = services.display.add_theme(name="All works")
    services.display.make_default(all_works.id)
    ui.open("#theme")
    ui.page.wait_for_selector("li.theme-card")

    order = ui.page.locator("#view").evaluate(
        "node => [...node.children].filter((child) => child.tagName !== 'P' || child.classList.contains('page-facts'))"
        ".slice(0, 4).map((child) => child.tagName + '.' + child.className)"
    )
    assert order[0].startswith("H1")
    assert "page-facts" in order[1]
    assert "page-toolbar" in order[2]
    assert "theme-cards" in order[3]
    assert ui.page.locator("#view .page-facts").inner_text() == "2 themes · All works is the default"


@pytest.mark.parametrize("described", [True, False])
def test_new_theme_creates_it_with_its_description_and_opens_it(ui, services, described):
    ui.open("#theme")
    ui.page.get_by_role("button", name="New theme…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill("  Late night  ")
    if described:
        dialog.get_by_label("Description", exact=True).fill("After hours, low light")
    else:
        # Spaces alone are no description, not one of nothing.
        dialog.get_by_label("Description", exact=True).fill("   ")
    dialog.get_by_role("button", name="Create").click()
    dialog.wait_for(state="detached")

    ui.page.wait_for_selector("#view h1:has-text('Late night')")
    [made] = [theme for theme in services.display.list_themes() if theme.name == "Late night"]
    assert made.description == ("After hours, low light" if described else None)
    assert ui.page.evaluate("() => window.location.hash") == f"#theme/{made.id}"


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_leaving_new_theme_creates_nothing(ui, services, winter, leave):
    before = {theme.id for theme in services.display.list_themes()}
    ui.open("#theme")
    ui.page.get_by_role("button", name="New theme…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill("Late night")
    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        dialog.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="detached")

    assert {theme.id for theme in services.display.list_themes()} == before
    assert ui.page.evaluate("() => document.activeElement.textContent") == "New theme…"


def test_a_refused_name_is_said_in_the_dialog_and_nothing_is_made(ui, services, winter):
    before = {theme.id for theme in services.display.list_themes()}
    ui.open("#theme")
    ui.page.get_by_role("button", name="New theme…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill("   ")
    create = dialog.get_by_role("button", name="Create")
    create.click()

    assert "Couldn't create the theme" in ui.said_beside(create)
    assert dialog.is_visible()
    assert {theme.id for theme in services.display.list_themes()} == before
