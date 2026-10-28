"""A wall, a client or a topic named on a page that is not its own is a link to it.

`information-architecture.md` § Direction: navigation is a link. The second UX
walk (`ux-review-2026-10.md` findings 34 and 43, #362) found walls and clients
named on six screens and linked from none, and a work's topics named on its page
as plain text. A wall is addressed as Walls with that wall's card brought to the
reader (`#walls?wall=<id>`), a client as Clients with its panel brought to them
(`#clients?client=<id>`).
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

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
    assert walls.count() == 2
    for at in range(walls.count()):
        assert walls.nth(at).get_attribute("href") == wall_address(the_wall)


def test_a_works_topic_links_to_its_topic_page(ui, hung):
    work, _theme = hung
    ui.open(f"#work/{work.id}")
    topic = links_named(ui, "#view dl.facets", "winter")
    assert topic.first.get_attribute("href").startswith(f"#topic/{WINTER_QID}")
    # A value naming no Wikidata item stays text.
    assert ui.page.locator("#view dl.facets a:text-is('oil on panel')").count() == 0
    assert ui.page.locator("#view dl.facets :text-is('oil on panel')").count() == 1


def test_a_theme_links_the_wall_it_hangs_on(ui, the_wall, hung):
    ui.open("#theme")
    walls = links_named(ui, "#view", the_wall.name)
    assert walls.first.get_attribute("href") == wall_address(the_wall)


def test_history_links_the_wall_a_theme_was_hung_on(ui, the_wall, hung):
    ui.open("#history")
    walls = links_named(ui, "#view .history-events", the_wall.name)
    assert walls.first.get_attribute("href") == wall_address(the_wall)


def test_a_walls_history_links_the_wall(ui, the_wall, hung):
    ui.open(f"#history?wall={the_wall.id}")
    walls = links_named(ui, "#view", f"{the_wall.name} on Walls")
    assert walls.first.get_attribute("href") == wall_address(the_wall)


def test_clients_links_the_walls_assigned_and_captioned(ui, services, the_wall, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#clients")
    walls = links_named(ui, f"#view section[data-client='{hall.id}']", the_wall.name)
    # Assigned to it, and captioned by its label output (the table and the list).
    assert walls.count() >= 2
    for at in range(walls.count()):
        assert walls.nth(at).get_attribute("href") == wall_address(the_wall)


def test_status_links_each_walls_reading_to_the_wall(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    walls = links_named(ui, "#view .wall-reading h2", "The living room")
    assert walls.first.get_attribute("href") == "#walls?wall=wall-1"


def test_walls_links_the_client_that_shows_the_wall(ui, services, the_wall, hall):
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#walls")
    open_wall_setup(ui, the_wall)
    clients = links_named(ui, "dialog.panel-dialog", hall.name)
    # The client that shows it, and the client whose label captions it.
    assert clients.count() == 2
    for at in range(clients.count()):
        assert clients.nth(at).get_attribute("href") == client_address(hall)


# -- arriving at the one asked for ---------------------------------------------------------


def test_a_wall_link_brings_that_walls_card_to_the_reader(ui, the_wall, hung):
    work, _theme = hung
    ui.open(f"#work/{work.id}")
    links_named(ui, "#view", the_wall.name).first.click()
    ui.page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('wall-title')")
    assert ui.page.evaluate("() => document.activeElement.textContent") == the_wall.name


def test_a_client_link_brings_that_clients_panel_to_the_reader(ui, the_wall, hall):
    ui.open("#walls")
    open_wall_setup(ui, the_wall)
    links_named(ui, "dialog.panel-dialog", hall.name).first.click()
    ui.page.wait_for_function(
        "(id) => document.activeElement && document.activeElement.closest(`section[data-client='${id}']`)", arg=hall.id
    )
    assert ui.page.evaluate("() => document.activeElement.tagName") == "H2"


def test_a_page_opened_without_one_asked_for_marks_none(ui, the_wall, hall):
    """The mark is the address's to set: a plain visit brings no card forward."""
    ui.open("#walls")
    ui.page.wait_for_selector(f"#view section[data-wall='{the_wall.id}']")
    assert ui.page.locator("#view [data-arrive]").count() == 0
    ui.open("#clients")
    ui.page.wait_for_selector(f"#view section[data-client='{hall.id}']")
    assert ui.page.locator("#view [data-arrive]").count() == 0


def test_a_fresh_load_of_a_clients_address_scrolls_to_it_and_leaves_the_focus(ui, services):
    """Loaded cold, the page scrolls to the one asked for and steals no focus."""
    clients = [services.clients.add_client(name=f"Player {number:02d}") for number in range(8)]
    last = clients[-1]
    ui.page.set_viewport_size({"width": 1280, "height": 600})
    ui.open(client_address(last))
    heading = ui.page.locator(f"#view section[data-client='{last.id}'] h2")
    ui.page.wait_for_function("() => window.scrollY > 0")

    box = heading.bounding_box()
    # Scrolled to its top, within a sub-pixel of it.
    assert -2 <= box["y"] < 600
    assert ui.page.evaluate("() => document.activeElement === document.body")


def test_a_label_whose_client_cannot_be_named_is_said_in_words_not_an_empty_link(ui, services, the_wall, hall):
    """The server sends an empty name for a label whose client is gone, and a link
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

    assert "a label on a client whose name could not be read" in line.inner_text()
    links = line.locator("a")
    assert all(links.nth(at).inner_text().strip() for at in range(links.count())), "a link with no words names nothing"
    assert line.locator(f"a[href='{client_address(hall)}']:text-is('{hall.name}')").count() == 1
