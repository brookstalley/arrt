"""Artworks' clean-up facets in the rail: *Size* and *Not on any wall* (#288), and *Last shown* (#316).

The server's half — the counts, the composition, the seam — is
`tests/integration/test_clean_up_facet_routes.py`. This is what the rail does with
them: offers each option with its count, narrows the grid at the server when
one is chosen, keeps the choice in the address, and says it in the filter
sentence when it empties the grid. And the rail toggle that reads *Show
filters* / *Hide filters*.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import AcquisitionMethod, FetchStatus, RightsStatus, Showing, SourceClass


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


def test_size_offers_each_band_with_its_count(ui, sized):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    group = ui.page.locator("aside.rails .rail", has=ui.page.locator("h2:text-is('Size')"))
    assert group.locator("button.facet-option").all_inner_texts() == [
        "Meets minimum (1)",
        "Below minimum (1)",
        "No size known (3)",
    ]


def test_choosing_a_band_narrows_at_the_server_and_is_in_the_address(ui, sized):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    option(ui, "Below minimum").click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    assert cards(ui) == ["A tiny scan"]
    assert "fit=below_minimum" in ui.page.evaluate("() => window.location.hash")
    assert option(ui, "Below minimum").get_attribute("aria-pressed") == "true"
    assert any("fit=below_minimum" in url for url in ui.requests_matching("/api/works?"))


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
    ui.open("#collection?wall=none&fit=meets_minimum")
    ui.page.wait_for_selector("#view .empty")

    assert "Nothing held matches this filter." in ui.text()
    assert "size “Meets minimum”, and not on any wall" in ui.text()
    # Still undoable from the rail, since the chosen options stay offered.
    assert option(ui, "Meets minimum").get_attribute("aria-pressed") == "true"


def test_hidden_rails_still_say_a_clean_up_filter_is_narrowing(ui, hung):
    ui.open("#collection?wall=none&filters=hidden")
    ui.page.wait_for_selector("ul.grid li.card")

    assert ui.page.locator(".filters-hidden-note").count() == 1
    assert ui.page.locator(".page-toolbar-controls button", has_text="Show filters").count() == 1


# -- Last shown (#316) ----------------------------------------------------------------


@pytest.fixture
def shown_once(store, seeded_service, sized):
    """Five works last shown at five different distances, so every period counts differently and none counts them all.

    The large scan ten days ago, the tiny one forty, two seeded works 200 and 400
    days ago, and the third seeded work never: *Never shown* 1, *Not in the last
    month* 4, *Not in 3 months* 3, *Not in a year* 2.
    """
    seeded = [
        entry.artwork.id
        for entry in seeded_service.list_artworks().entries
        if entry.artwork.id not in {work.id for work in sized.values()}
    ]
    now = datetime.now(UTC)
    for work_id, days in ((sized["large"].id, 10), (sized["tiny"].id, 40), (seeded[0], 200), (seeded[1], 400)):
        seen = now - timedelta(days=days)
        store.save_showing(
            Showing(wall_id="the-hall", work_id=work_id, started_at=seen - timedelta(minutes=3), last_seen_at=seen)
        )
    return sized


def _last_shown(ui):
    return ui.page.locator("aside.rails .rail", has=ui.page.locator("h2:text-is('Last shown')"))


def test_last_shown_offers_each_period_with_its_count(ui, shown_once):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    assert _last_shown(ui).locator("button.facet-option").all_inner_texts() == [
        "Never shown (1)",
        "Not in the last month (4)",
        "Not in 3 months (3)",
        "Not in a year (2)",
    ]


def test_choosing_never_shown_narrows_at_the_server_and_is_in_the_address(ui, shown_once):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    option(ui, "Never shown").click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 1")

    assert "A large scan" not in cards(ui)
    assert "shown=never" in ui.page.evaluate("() => window.location.hash")
    assert option(ui, "Never shown").get_attribute("aria-pressed") == "true"
    assert option(ui, "Not in a year").get_attribute("aria-pressed") == "false"
    assert any("shown=never" in url for url in ui.requests_matching("/api/works?"))


def test_choosing_the_chosen_period_again_clears_it(ui, shown_once):
    ui.open("#collection?shown=never")
    ui.page.wait_for_selector("ul.grid li.card")

    option(ui, "Never shown").click()
    ui.page.wait_for_function("() => document.querySelectorAll('ul.grid li.card').length === 5")

    assert "shown=" not in ui.page.evaluate("() => window.location.hash")


def test_last_shown_is_not_offered_before_any_wall_has_shown_anything(ui, sized):
    """Every work is never shown then, so each option would select them all."""
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    assert _last_shown(ui).count() == 0


def test_a_last_shown_filter_that_empties_the_grid_is_named(ui, shown_once):
    ui.open("#collection?shown=never&fit=meets_minimum")
    ui.page.wait_for_selector("#view .empty")

    assert "size “Meets minimum”, and never shown" in ui.text()
    assert option(ui, "Never shown").get_attribute("aria-pressed") == "true"


def test_select_all_under_last_shown_sends_it_and_reaches_only_its_works(ui, services, shown_once):
    """*Select all* sends the filter, not the ids, so a filter body without `shown` would reach the work shown too."""
    theme = services.display.add_theme(name="Never up")
    sent: list[dict] = []
    ui.page.on("request", lambda request: sent.append(json.loads(request.post_data)) if "/works/bulk" in request.url else None)
    ui.open("#collection?shown=never")
    ui.page.wait_for_selector("ul.grid li.card")
    ui.page.click("button.select-toggle")

    ui.page.click(".selection button.select-all")
    ui.page.click("button.selection-add")
    ui.page.select_option("#add-to-theme", theme.id)
    ui.page.click("dialog button.add-confirm")
    ui.page.wait_for_selector(".selection-status:has-text('Added 1 work to Never up.')")

    assert sent[0]["filter"]["shown"] == "never"
    assert shown_once["large"].id not in services.display.theme_work_ids(theme.id)


@pytest.mark.parametrize(
    ("label", "value", "count"),
    [
        ("Never shown", "never", 1),
        ("Not in the last month", "month", 4),
        ("Not in 3 months", "quarter", 3),
        ("Not in a year", "year", 2),
    ],
)
def test_each_period_narrows_the_grid_to_its_count(ui, shown_once, label, value, count):
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")

    option(ui, label).click()
    ui.page.wait_for_function(f"() => document.querySelectorAll('ul.grid li.card').length === {count}")

    assert f"shown={value}" in ui.page.evaluate("() => window.location.hash")
    assert option(ui, label).get_attribute("aria-pressed") == "true"


def test_the_period_counts_move_with_a_search(ui, shown_once):
    """Counted over every other filter: searching for the work shown forty days ago leaves only the month counting it."""
    ui.open("#collection?q=tiny")
    ui.page.wait_for_selector("ul.grid li.card")

    assert _last_shown(ui).locator("button.facet-option").all_inner_texts() == [
        "Never shown (0)",
        "Not in the last month (1)",
        "Not in 3 months (0)",
        "Not in a year (0)",
    ]
