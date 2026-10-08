"""The Themes index as cards, and the theme page's ordering, in a real browser.

`#theme` is a grid of cards, one per theme, each a link to the theme's own page,
where every act on it lives. Ten themes fit on one desktop screen, which is the
measure the index was rebuilt to: the old index expanded every theme with its
whole membership and grew by a table row per work.

The theme page orders its works with Move to top and Move to bottom beside ↑
and ↓, all of them buttons a keyboard reaches, and says whether position decides
what the wall shows first — which it does only when the theme is not shuffled.
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
    return ui.page.locator("tbody tr td:nth-child(2)").all_inner_texts()


def _first_row_becomes(ui, title):
    ui.page.wait_for_function(
        "(title) => { const cell = document.querySelector('tbody tr td:nth-child(2)');"
        " return cell && cell.textContent === title; }",
        arg=title,
    )


def _last_row_becomes(ui, title):
    ui.page.wait_for_function(
        "(title) => { const cells = document.querySelectorAll('tbody tr td:nth-child(2)');"
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
    """Rename, delete, hanging and membership are the theme page's, and only creating is here."""
    ui.open("#theme")
    ui.page.wait_for_selector("li.theme-card")

    assert ui.page.locator("#view button").all_inner_texts() == ["Create"]
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


def test_move_to_top_and_bottom_take_a_work_to_either_end(ui, winter):
    """From the middle, so neither end is where the work already was."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    ui.page.click("button[aria-label='Move Convergence to the top']")
    _first_row_becomes(ui, "Convergence")
    assert _titles(ui) == ["Convergence", "Autumn Rhythm", "Blue Poles", "Number 1"]

    ui.page.click("button[aria-label='Move Autumn Rhythm to the bottom']")
    _last_row_becomes(ui, "Autumn Rhythm")
    assert _titles(ui) == ["Convergence", "Blue Poles", "Number 1", "Autumn Rhythm"]

    # And the catalogue holds it, not just the table.
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    assert _titles(ui) == ["Convergence", "Blue Poles", "Number 1", "Autumn Rhythm"]


def test_the_moves_are_operated_from_the_keyboard(ui, winter):
    """No drag: each move is a button, reached by focus and pressed with Enter or Space."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    ui.page.focus("button[aria-label='Move Number 1 to the top']")
    ui.page.keyboard.press("Enter")
    _first_row_becomes(ui, "Number 1")

    ui.page.focus("button[aria-label='Move Number 1 to the bottom']")
    ui.page.keyboard.press("Space")
    _last_row_becomes(ui, "Number 1")

    assert _titles(ui) == list(TITLES)
    assert ui.page.locator("[draggable='true']").count() == 0


def test_the_ends_offer_no_move_to_where_a_work_already_is(ui, winter):
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    assert ui.page.is_disabled("button[aria-label='Move Autumn Rhythm to the top']")
    assert ui.page.is_disabled("button[aria-label='Move Number 1 to the bottom']")
    assert ui.page.is_enabled("button[aria-label='Move Autumn Rhythm to the bottom']")
    assert ui.page.is_enabled("button[aria-label='Move Number 1 to the top']")


POSITION_DECIDES = "Position decides what the wall shows first"
SHUFFLED = "Shown in shuffled order"


@pytest.mark.parametrize("shuffle", [False, True], ids=["shuffle-off", "shuffle-on"])
def test_the_order_copy_says_whether_position_decides(ui, services, winter, shuffle):
    """Each sentence where it is true, and absent where it is not.

    The theme's own setting, set both ways, so neither case is the deployment
    default standing in for the theme's.
    """
    services.display.update_theme(winter.id, shuffle=shuffle)
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    caption = ui.page.inner_text("table caption")

    assert (SHUFFLED in caption) is shuffle
    assert (POSITION_DECIDES in caption) is not shuffle


def test_the_copy_agrees_with_what_walls_says(ui, services, winter):
    """A theme that inherits is shuffled as the deployment is, and Walls says so too."""
    wall = services.display.survey_walls()[0].wall
    services.display.activate_theme(winter.id, wall_id=wall.id)
    shuffled = services.display.build_manifest(wall.id, winter.id).shuffle

    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")

    assert (SHUFFLED in ui.page.inner_text("table caption")) is shuffled


# -- the title follows a rename (#302) -----------------------------------------


def test_renaming_a_theme_renames_the_tab(ui, winter):
    """The tab, the history and a bookmark name the theme as its heading does."""
    ui.open(f"#theme/{winter.id}")
    ui.page.wait_for_selector("tbody tr")
    assert re.match(r"^Winter\b", ui.page.title())

    ui.page.fill(f"#rename-{winter.id}", "Late night")
    ui.page.click("button[aria-label='Rename Winter']")
    ui.page.wait_for_selector("#view h1:has-text('Late night')")

    assert re.match(r"^Late night\b", ui.page.title())
    assert "Winter" not in ui.page.title()
