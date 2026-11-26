"""A wall, a Player or a topic named on a page that is not its own is a link to it.

`information-architecture.md` § Direction: navigation is a link. Walls and clients
were named on six screens and linked from none, and a work's topics named on its page
as plain text. A wall is addressed as Walls with that wall's card brought to the
reader (`#walls?wall=<id>`), a Player as Players with its row brought to them
(`#clients?client=<id>`, the address Clients had before ruling 7 of 2026-10-27).
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

WINTER_QID = "Q1311"


@pytest.fixture
def hall(services):
    return services.clients.add_client(name="Hall Pi")


@pytest.fixture
def the_wall(services, hall):
    wall = services.display.survey_walls()[0].wall
    services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
    return services.display.get_wall(wall.id)


@pytest.fixture
def hung(services, service, the_wall):
    """A work in a theme hung on the wall, with a topic among its facets."""
    work = service.add_artwork(title="Hunters in the Snow")
    service.record_facet(artwork_id=work.id, kind="subject", value="winter", derivation="sourced", value_qid=WINTER_QID)
    service.record_facet(artwork_id=work.id, kind="medium", value="oil on panel", derivation="sourced")
    theme = services.display.add_theme(name="Snow")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)
    return work, theme


def wall_address(wall):
    return f"#walls?wall={wall.id}"


def client_address(client):
    return f"#clients?client={client.id}"


def open_wall_setup(ui, wall):
    """Which client shows a wall, and which captions it, are in the wall's Edit…
    dialog since ruling 4 of 2026-10-27 took them off the card; opened here so
    their links can be read."""
    edit = ui.page.locator(f"#view section[data-wall='{wall.id}']").get_by_role("button", name=f"Edit {wall.name}…")
    edit.wait_for()
    edit.click()
    ui.page.locator("dialog.panel-dialog").wait_for()


def links_named(ui, scope, name):
    """Every link inside `scope` whose text is `name`."""
    ui.page.wait_for_selector(f"{scope} a:text-is('{name}')")
    return ui.page.locator(f"{scope} a:text-is('{name}')")


# -- each site ------------------------------------------------------------------------


def test_a_works_walls_and_theme_line_link_the_wall(ui, the_wall, hung):
    work, _theme = hung
    ui.open(f"#work/{work.id}")
    walls = links_named(ui, "#view", the_wall.name)
    # The Walls fact and the theme's "(on …)" each name it.
    expect(walls).to_have_count(2)
    for at in range(2):
        expect(walls.nth(at)).to_have_attribute("href", wall_address(the_wall))


def test_a_works_topic_links_to_its_topic_page(ui, hung):
    work, _theme = hung
    ui.open(f"#work/{work.id}")
    topic = links_named(ui, "#view dl.facets", "winter")
    expect(topic.first).to_have_attribute("href", re.compile("^" + re.escape(f"#topic/{WINTER_QID}")))
    # A value naming no Wikidata item stays text. (It is there, as text, before it is said not to be a link.)
    expect(ui.page.locator("#view dl.facets :text-is('oil on panel')")).to_have_count(1)
    expect(ui.page.locator("#view dl.facets a:text-is('oil on panel')")).to_have_count(0)


def test_a_theme_links_the_wall_it_hangs_on(ui, the_wall, hung):
    ui.open("#theme")
    walls = links_named(ui, "#view", the_wall.name)
    expect(walls.first).to_have_attribute("href", wall_address(the_wall))


def test_history_links_the_wall_a_theme_was_hung_on(ui, the_wall, hung):
    ui.open("#history")
    walls = links_named(ui, "#view .history-events", the_wall.name)
    expect(walls.first).to_have_attribute("href", wall_address(the_wall))


def test_a_walls_history_links_the_wall(ui, the_wall, hung):
    ui.open(f"#history?wall={the_wall.id}")
    walls = links_named(ui, "#view", f"{the_wall.name} on Walls")
    expect(walls.first).to_have_attribute("href", wall_address(the_wall))


def test_players_links_the_walls_on_its_screens_and_captioned(ui, services, the_wall, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#clients")
    walls = links_named(ui, f"#view tr[data-player='{hall.id}']", the_wall.name)
    # On its screen, and captioned by its label panel: one link in each column.
    expect(walls).to_have_count(2)
    for at in range(2):
        expect(walls.nth(at)).to_have_attribute("href", wall_address(the_wall))


def test_status_links_each_walls_reading_to_the_wall(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    walls = links_named(ui, "#view .wall-reading h2", "The living room")
    expect(walls.first).to_have_attribute("href", "#walls?wall=wall-1")


def test_walls_links_the_player_that_shows_the_wall(ui, services, the_wall, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#walls")
    open_wall_setup(ui, the_wall)
    clients = links_named(ui, "dialog.panel-dialog", hall.name)
    # The Player that shows it, and the Player whose label captions it.
    expect(clients).to_have_count(2)
    for at in range(2):
        expect(clients.nth(at)).to_have_attribute("href", client_address(hall))


# -- arriving at the one asked for ---------------------------------------------------------


def test_a_wall_link_brings_that_walls_card_to_the_reader(ui, the_wall, hung):
    work, _theme = hung
    ui.open(f"#work/{work.id}")
    links_named(ui, "#view", the_wall.name).first.click()
    ui.page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('wall-title')")
    assert ui.page.evaluate("() => document.activeElement.textContent") == the_wall.name


def test_a_player_link_brings_that_players_row_to_the_reader(ui, the_wall, hall):
    ui.open("#walls")
    open_wall_setup(ui, the_wall)
    links_named(ui, "dialog.panel-dialog", hall.name).first.click()
    ui.page.wait_for_function(
        "(id) => document.activeElement && document.activeElement.matches(`tr[data-player='${id}']`)", arg=hall.id
    )
    assert ui.page.evaluate("() => document.activeElement.tagName") == "TR"


def test_a_page_opened_without_one_asked_for_marks_none(ui, the_wall, hall):
    """The mark is the address's to set: a plain visit brings no card forward."""
    ui.open("#walls")
    ui.page.wait_for_selector(f"#view section[data-wall='{the_wall.id}']")
    expect(ui.page.locator("#view [data-arrive]")).to_have_count(0)
    ui.open("#clients")
    ui.page.wait_for_selector(f"#view tr[data-player='{hall.id}']")
    expect(ui.page.locator("#view [data-arrive]")).to_have_count(0)


def test_a_fresh_load_of_a_players_address_scrolls_to_it_and_leaves_the_focus(ui, services):
    """Loaded cold, the page scrolls to the one asked for and steals no focus."""
    clients = [services.clients.add_client(name=f"Player {number:02d}") for number in range(8)]
    last = clients[-1]
    ui.page.set_viewport_size({"width": 1280, "height": 600})
    ui.open(client_address(last))
    heading = ui.page.locator(f"#view tr[data-player='{last.id}']")
    ui.page.wait_for_function("() => window.scrollY > 0")

    box = heading.bounding_box()  # one-shot: geometry, read once the page has scrolled
    # Scrolled to its top, within a sub-pixel of it.
    assert -2 <= box["y"] < 600
    assert ui.page.evaluate("() => document.activeElement === document.body")


def test_a_label_whose_player_cannot_be_named_is_said_in_words_not_an_empty_link(ui, services, the_wall, hall):
    """The server sends an empty name for a label whose Player is gone, and a link
    with no words in it names nothing. Each label is said on its own: a named one
    beside it keeps its link."""
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-1")

    def nameless_first(route):
        body = route.fetch().json()
        for wall in body["walls"]:
            for label in wall["labels"]:
                if label["output"] == "epd-0":
                    label["client_name"] = ""
        route.fulfill(json=body)

    ui.page.route("**/api/walls", nameless_first)
    ui.open("#walls")
    open_wall_setup(ui, the_wall)
    line = ui.page.locator("dialog.panel-dialog .wall-labels")
    line.wait_for()

    expect(line).to_contain_text("a label on a Player whose name could not be read", use_inner_text=True)
    # One link in the line, the named label's, and it has words: "every link has words" over
    # a length that is known, as a pattern per link.
    expect(line.locator("a"), "a link with no words names nothing").to_have_text([re.compile(r"\S")], use_inner_text=True)
    expect(line.locator(f"a[href='{client_address(hall)}']:text-is('{hall.name}')")).to_have_count(1)
