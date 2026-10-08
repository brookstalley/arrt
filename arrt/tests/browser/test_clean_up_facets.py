"""Artworks' clean-up facets in the rail: *Size on the wall* and *Not on any wall* (#288).

The server's half — the counts, the composition, the seam — is
`tests/integration/test_clean_up_facet_routes.py`. This is what the rail does with
them: offers each option with its count, narrows the grid at the server when
one is chosen, keeps the choice in the address, and says it in the filter
sentence when it empties the grid. And the rail toggle that reads *Show
filters* / *Hide filters*.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import AcquisitionMethod, FetchStatus, RightsStatus, SourceClass


def _with_master(service, title, width, height):
    artwork = service.add_artwork(title=title)
    source = service.add_source(
        artwork_id=artwork.id,
        url=f"https://museum.example/{artwork.id}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=artwork.id,
        source_id=source.id,
        path=f"raw/{artwork.id}.jpg",
        width=width,
        height=height,
        byte_size=1000,
        content_hash=f"hash-{artwork.id}",
        fetch_status=FetchStatus.OK,
    )
    return artwork


@pytest.fixture
def sized(seeded_service):
    """Beside the three seeded works, which hold no master: one large scan and one tiny one."""
    return {
        "large": _with_master(seeded_service, "A large scan", 12000, 8000),
        "tiny": _with_master(seeded_service, "A tiny scan", 120, 80),
    }


@pytest.fixture
def hung(services, sized):
    """The large scan in a theme hanging on a wall."""
    wall = services.display.add_wall(name="The hall")
    theme = services.display.add_theme(name="On show")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=sized["large"].id)
    services.display.activate_theme(theme.id, wall_id=wall.id)
    return wall


def option(ui, text):
    return ui.page.locator("aside.rails button.facet-option", has_text=text)


def cards(ui):
    return sorted(ui.page.locator("ul.grid li.card .card-title").all_inner_texts())


def test_size_on_the_wall_offers_each_band_with_its_count(ui, sized):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    group = ui.page.locator("aside.rails .rail", has=ui.page.locator("h2:text-is('Size on the wall')"))
    assert group.locator("button.facet-option").all_inner_texts() == [
        "Native (1)",
        "Matted small (0)",
        "Below floor (1)",
        "No size known (3)",
    ]
    # Disabled, not hidden, at zero, as every facet option is.
    assert option(ui, "Matted small").is_disabled()


def test_choosing_a_band_narrows_at_the_server_and_is_in_the_address(ui, sized):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    option(ui, "Below floor").click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    assert cards(ui) == ["A tiny scan"]
    assert "fit=below_floor" in ui.page.evaluate("() => window.location.hash")
    assert option(ui, "Below floor").get_attribute("aria-pressed") == "true"
    assert any("fit=below_floor" in url for url in ui.requests_matching("/api/works?"))


def test_not_on_any_wall_leaves_out_what_a_wall_plays(ui, hung):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    assert option(ui, "Not on any wall").inner_text() == "Not on any wall (4)"

    option(ui, "Not on any wall").click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 4")

    assert "A large scan" not in cards(ui)
    assert "wall=none" in ui.page.evaluate("() => window.location.hash")
    assert option(ui, "Not on any wall").get_attribute("aria-pressed") == "true"


def test_not_on_any_wall_is_not_offered_before_anything_hangs(ui, sized):
    """Every work is on no wall then, so the option would select them all: a control with nothing behind it."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    assert option(ui, "Not on any wall").count() == 0


def test_a_clean_up_filter_that_empties_the_grid_is_named(ui, hung):
    ui.open("#collection?wall=none&fit=native")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing held matches this filter." in ui.text()
    assert "size on the wall “Native”, and not on any wall" in ui.text()
    # Still undoable from the rail, since the chosen options stay offered.
    assert option(ui, "Native").get_attribute("aria-pressed") == "true"


def test_hidden_rails_still_say_a_clean_up_filter_is_narrowing(ui, hung):
    ui.open("#collection?wall=none&filters=hidden")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator(".filters-hidden-note").count() == 1
    assert ui.page.locator(".page-toolbar-controls button", has_text="Show filters").count() == 1
