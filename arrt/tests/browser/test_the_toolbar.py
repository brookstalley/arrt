"""The *arr page toolbar on Artworks, in a real browser.

`information-architecture.md` § The *arr layout: actions on the left, View, Sort
and Filter on the right. View offers Posters, Overview and Table; Sort is the
server's `WorkOrder`; Filter shows and hides the rails, which the owner ruled
stay beside the grid. Each is addressable state, so each is asserted in the
address as well as on the page.

The seeded catalogue orders three different ways — by title, by artist, and with
the unattributed work last — so a sort that did nothing, or did the wrong thing,
fails rather than passing on a fixture that could not tell.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

BY_TITLE = ["I Saw the Figure 5 in Gold", "Nighthawks", "The Persistence of Memory"]
BY_ARTIST = ["I Saw the Figure 5 in Gold", "The Persistence of Memory", "Nighthawks"]


def choose(ui, menu: str, item: str) -> None:
    ui.page.click(f"button.menu-button-trigger:has-text('{menu}')")
    ui.page.click(f"[role='menuitemradio']:has-text('{item}')")


def table_titles(ui) -> list[str]:
    return ui.page.locator("table.work-table tbody .row-title").all_inner_texts()


def wait_for_table(ui, expected: list[str]) -> None:
    """Until the table holds exactly these titles, in this order.

    A sort is a navigation that repaints, so the old table is on the page until
    the new one replaces it; waiting for "a table" finds the old one.
    """
    ui.page.wait_for_function(
        "(want) => [...document.querySelectorAll('table.work-table .row-title')]"
        ".map((e) => e.textContent).join('|') === want.join('|')",
        arg=expected,
    )


def test_artworks_has_view_sort_and_filter_on_its_toolbar(ui, seeded_service):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    controls = ui.page.locator(".page-toolbar-controls")
    assert controls.locator("button", has_text="View:").count() == 1
    assert controls.locator("button", has_text="Sort:").count() == 1
    assert controls.locator("button", has_text="Filter").get_attribute("aria-pressed") == "true"


def test_the_table_view_lists_every_work_and_opens_one(ui, seeded_service):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid")

    choose(ui, "View", "Table")
    ui.page.wait_for_selector("table.work-table")

    assert "density=table" in ui.page.url
    assert sorted(table_titles(ui)) == sorted(BY_TITLE)
    assert ui.page.locator("ul.grid").count() == 0
    ui.page.click("table.work-table .row-title:has-text('Nighthawks')")
    ui.page.wait_for_selector("#view h2:has-text('Nighthawks')")


def test_the_view_menu_names_its_choice_and_is_keyboard_driven(ui, seeded_service):
    ui.open("#collection?density=catalogue")
    ui.page.wait_for_selector("ul.grid")
    trigger = ui.page.locator("button.menu-button-trigger", has_text="View")
    assert trigger.inner_text().startswith("View: Overview")

    trigger.focus()
    ui.page.keyboard.press("ArrowDown")
    menu = ui.page.get_by_role("menu", name="View")
    assert trigger.get_attribute("aria-expanded") == "true"
    assert menu.get_by_role("menuitemradio", name="Overview").get_attribute("aria-checked") == "true"

    ui.page.keyboard.press("Escape")
    assert trigger.get_attribute("aria-expanded") == "false"
    assert ui.page.evaluate("() => document.activeElement.classList.contains('menu-button-trigger')")

    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("ArrowDown")
    ui.page.keyboard.press("Enter")
    ui.page.wait_for_selector("table.work-table")
    assert "density=table" in ui.page.url


def test_sorting_by_artist_orders_the_works_and_is_in_the_address(ui, seeded_service):
    ui.open("#collection?density=table")
    ui.page.wait_for_selector("table.work-table")
    assert table_titles(ui) == BY_TITLE

    choose(ui, "Sort", "Artist")
    wait_for_table(ui, BY_ARTIST)

    assert "sort=artist" in ui.page.evaluate("() => window.location.hash")
    assert table_titles(ui) == BY_ARTIST, "unattributed works go last, after the named ones"


def test_sorting_by_title_again_leaves_the_default_out_of_the_address(ui, seeded_service):
    ui.open("#collection?density=table&sort=artist")
    ui.page.wait_for_selector("table.work-table")

    choose(ui, "Sort", "Title")
    wait_for_table(ui, BY_TITLE)

    assert "sort=" not in ui.page.evaluate("() => window.location.hash")


def test_filter_puts_the_rails_away_and_brings_them_back(ui, seeded_service):
    ui.open("#collection")
    ui.page.wait_for_selector("aside.rails")

    ui.page.click(".page-toolbar-controls button:has-text('Filter')")
    ui.page.wait_for_function("() => window.location.hash.includes('filters=hidden')")
    # The rails going is the repaint; waiting on the grid would find the old one.
    ui.page.wait_for_selector("aside.rails", state="detached")
    ui.page.wait_for_selector("ul.grid")
    assert ui.page.locator(".page-toolbar-controls button:has-text('Filter')").get_attribute("aria-pressed") == "false"

    ui.page.click(".page-toolbar-controls button:has-text('Filter')")
    ui.page.wait_for_selector("aside.rails")
    assert "filters=" not in ui.page.evaluate("() => window.location.hash")


def test_view_sort_and_filter_survive_a_reload(ui, seeded_service):
    ui.open("#collection?density=table&sort=artist&filters=hidden")
    ui.page.wait_for_selector("table.work-table")

    assert table_titles(ui) == BY_ARTIST
    assert ui.page.locator("aside.rails").count() == 0
    assert ui.page.locator("button.menu-button-trigger", has_text="Sort").inner_text().startswith("Sort: Artist")


def test_showing_everything_keeps_how_the_page_is_shown(ui, seeded_service):
    """A reset of the narrowing, not of the view the curator chose."""
    ui.open("#collection?q=nothingmatchesthis&density=table&sort=artist&filters=hidden")
    ui.page.wait_for_selector("#view .empty")

    ui.page.click("#view button:has-text('Show everything')")
    ui.page.wait_for_selector("table.work-table")

    hash_now = ui.page.evaluate("() => window.location.hash")
    assert "q=" not in hash_now
    assert "density=table" in hash_now and "sort=artist" in hash_now and "filters=hidden" in hash_now


def test_a_theme_filtered_here_is_in_the_sort_menus_order(ui, services, seeded_service):
    """A theme is one more filter on Artworks (the owner's ruling on #169), so Sort applies to it.

    Replaces "a theme is shown in its own order, so sort is not offered": that
    was true while the rail's theme showed the theme's curated order. The
    curated order is now the theme's own page's, and here the theme's slice
    follows the Sort menu like any other filter's.
    """
    theme = services.display.add_theme(name="Late night")
    for entry in seeded_service.list_artworks().entries:
        services.display.add_to_theme(theme_id=theme.id, artwork_id=entry.artwork.id)
    ui.open(f"#collection?theme={theme.id}&density=table")
    wait_for_table(ui, BY_TITLE)

    choose(ui, "Sort", "Artist")
    wait_for_table(ui, BY_ARTIST)

    assert f"theme={theme.id}" in ui.page.evaluate("() => window.location.hash")


def test_the_table_carries_the_tick_in_select_mode_only_when_there_is_a_theme_to_add_to(ui, services, seeded_service):
    ui.open("#collection?density=table")
    ui.page.wait_for_selector("table.work-table")
    assert ui.page.locator("table.work-table input.tile-select").count() == 0
    assert ui.page.locator("button.select-toggle").count() == 0

    services.display.add_theme(name="Late night")
    # A reload, because opening the address already showing is not a navigation.
    ui.page.reload()
    ui.page.wait_for_selector("button.select-toggle")
    # Drawn, and out of sight until *Select* is pressed — the tick column too.
    assert ui.page.locator("table.work-table input.tile-select:visible").count() == 0
    assert ui.page.locator("table.work-table th.row-select:visible").count() == 0

    ui.page.click("button.select-toggle")
    assert ui.page.locator("table.work-table input.tile-select:visible").count() == 3


def test_a_rail_with_nothing_to_filter_by_says_so(ui, seeded_service):
    """No theme and no facet on any work: the rail says why it is empty rather than drawing nothing."""
    ui.open("#collection")
    ui.page.wait_for_selector("aside.rails .rail-note")

    assert ui.page.inner_text("aside.rails").startswith("Nothing to filter by yet.")


def test_hidden_rails_say_so_when_they_are_still_narrowing(ui, services, seeded_service):
    """A theme narrowing the grid with its rail put away would read as the whole
    collection. The paired case below, with nothing narrowing, says nothing."""
    theme = services.display.add_theme(name="Late night")
    ui.open(f"#collection?theme={theme.id}&filters=hidden")
    ui.page.wait_for_selector(".filters-hidden-note")

    ui.page.click(".filters-hidden-note button:has-text('Show the filters')")
    ui.page.wait_for_selector("aside.rails")
    assert "filters=" not in ui.page.evaluate("() => window.location.hash")


def test_hidden_rails_with_nothing_narrowing_say_nothing(ui, seeded_service):
    ui.open("#collection?filters=hidden")
    ui.page.wait_for_selector("ul.grid")

    assert ui.page.locator(".filters-hidden-note").count() == 0


def test_view_sort_and_filter_are_undone_by_browser_back(ui, seeded_service):
    """Promised as addressable state, so the browser's own back undoes each."""
    ui.open("#collection?density=table")
    ui.page.wait_for_selector("table.work-table")

    choose(ui, "Sort", "Artist")
    wait_for_table(ui, BY_ARTIST)
    ui.page.go_back()
    wait_for_table(ui, BY_TITLE)
    assert "sort=" not in ui.page.evaluate("() => window.location.hash")


def test_a_sort_this_client_does_not_offer_falls_back_rather_than_failing(ui, seeded_service):
    """A bookmark from a later or earlier version must not break the home page;
    an unknown density already falls back the same way."""
    ui.open("#collection?density=table&sort=colour")
    ui.page.wait_for_selector("table.work-table")

    assert table_titles(ui) == BY_TITLE
    assert ui.page.locator("#error:not([hidden])").count() == 0


def test_hidden_rails_say_so_when_a_facet_is_still_narrowing(ui, service, seeded_service):
    """The case the note exists for: a chosen facet, which unlike a theme the
    heading does not name, so with the rails away nothing else would say it."""
    work = service.list_artworks(q="Nighthawks").entries[0].artwork
    service.record_facet(artwork_id=work.id, kind="movement", value="Realism", derivation="sourced")
    ui.open("#collection?movement=Realism&filters=hidden")
    ui.page.wait_for_selector("ul.grid")

    assert ui.page.locator("ul.grid li.card").count() == 1, "the facet must actually narrow, or this tests nothing"
    assert ui.page.locator(".filters-hidden-note").count() == 1
