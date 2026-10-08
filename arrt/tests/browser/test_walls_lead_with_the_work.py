"""Each wall's card leads with the work its heartbeat names, in a real browser.

`ia-proposal.md` § Walls: the work on the wall now, large, with its label facts,
then what the wall draws from and "until changed", then Skip, *Not this one
again* and Change, and the wall's history from its card.

**The heartbeat is real.** Each test records the wall's heartbeat through
`record_heartbeat`, the path a Player's POST takes, so the card reads what the
health reading really carries (`reported.current_work_id`) rather than a stub's
idea of it, and a Skip's new work arrives the way a Player's next report does.
"""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.records import ArtworkStatus, MatMethod, RenditionKind


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


@pytest.fixture
def a_displayable_work(work_with_an_image, service, settings, decodable_jpeg):
    """A work that reaches a wall: master on disk, matted, rendered."""

    def _work(title):
        artwork = work_with_an_image(title=title)
        service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        rendered = f"ready/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / rendered, width=3840, height=2160)
        service.record_rendition(
            artwork_id=artwork.id, kind=RenditionKind.TV_DISPLAY, target_width=3840, target_height=2160, path=rendered
        )
        return artwork

    return _work


@pytest.fixture
def two_works(a_displayable_work):
    return a_displayable_work("Nighthawks"), a_displayable_work("Automat")


@pytest.fixture
def winter(services, the_wall, two_works):
    """Two works in Winter, hung on the wall."""
    theme = services.display.add_theme(name="Winter")
    for work in two_works:
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)
    return theme


def report(services, wall, work_id, *, ago=timedelta(seconds=5)):
    """What the wall's Player says it is showing, as of `ago` before now."""
    services.display.record_heartbeat(
        wall.id,
        {"reported_at": (datetime.now(UTC) - ago).isoformat(timespec="seconds"), "current_work_id": work_id},
    )


def card(ui, wall):
    return ui.page.locator(f"section.wall[data-wall='{wall.id}']")


def open_walls(ui):
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")


def test_the_work_the_heartbeat_names_leads_the_card(ui, services, the_wall, winter, two_works):
    _, automat = two_works
    report(services, the_wall, automat.id)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    lead.wait_for()
    assert lead.locator(".wall-now-when").inner_text() == "On the wall now"
    # The work named, not the theme's first: the fixture puts Nighthawks first.
    title = lead.get_by_role("link", name="Automat")
    assert title.get_attribute("href").startswith(f"#work/{automat.id}")
    assert lead.locator("h3").inner_text() == "Automat"
    assert lead.get_by_alt_text("Automat").count() == 1
    assert "Nighthawks" not in lead.inner_text()
    # And it leads: the first thing in the card after the wall's name.
    assert card(ui, the_wall).locator("> *").nth(1).get_attribute("class") == "wall-now"
    # What it draws from, and for how long.
    assert card(ui, the_wall).locator(".wall-source").inner_text() == "Drawing from Winter, until changed."
    assert (
        card(ui, the_wall)
        .locator(".wall-source")
        .get_by_role("link", name="Winter")
        .get_attribute("href")
        .startswith(f"#theme/{winter.id}")
    )


def test_an_old_heartbeat_still_leads_with_its_work_under_its_age(ui, services, the_wall, winter, two_works):
    """The last report is the best answer to what is on the wall, but not a claim about now."""
    report(services, the_wall, two_works[0].id, ago=timedelta(hours=5))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.locator(".wall-now-when").inner_text() == "Last reported 5 hours ago, so it may have changed since"
    assert "On the wall now" not in card(ui, the_wall).inner_text()
    assert lead.get_by_role("link", name="Nighthawks").count() == 1


def test_a_selection_is_drawn_from_as_a_selection(ui, services, the_wall, two_works):
    """A selection's theme has a made-up name, and the curator never gave it one."""
    services.display.hang_selection([two_works[0].id], wall_id=the_wall.id)
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    assert card(ui, the_wall).locator(".wall-source").inner_text() == "Drawing from a selection, until changed."
    assert "Selection for" not in ui.page.locator("#view").text_content()


def test_change_offers_themes_and_never_a_selection(ui, services, the_wall, winter, two_works):
    other = services.display.add_wall(name="Study")
    services.display.hang_selection([two_works[0].id], wall_id=other.id)
    open_walls(ui)

    change = card(ui, the_wall).locator("details.wall-change")
    assert change.get_attribute("open") is None, "Change is closed while something is hung"
    summary = change.locator("summary")
    assert summary.inner_text() == "Change"
    assert summary.get_attribute("aria-label") == f"Change what {the_wall.name} draws from"
    summary.click()
    options = change.locator("select option").all_inner_texts()
    assert options == ["Winter"]


def test_skip_writes_the_directive_and_the_card_shows_the_next_work_once_reported(ui, services, the_wall, winter, two_works):
    nighthawks, automat = two_works
    report(services, the_wall, nighthawks.id)
    before = services.display.read_directive(the_wall.id).sequence
    open_walls(ui)

    ui.page.get_by_role("button", name=f"Skip the work on {the_wall.name}").click()
    said = card(ui, the_wall).locator(".wall-said")
    said.filter(has_text="Skipped.").wait_for()
    assert services.display.read_directive(the_wall.id).sequence == before + 1
    # Until the Player reports, the card still leads with what it last said.
    assert card(ui, the_wall).locator(".wall-now h3").inner_text() == "Nighthawks"

    report(services, the_wall, automat.id)
    said.filter(has_text=f"{the_wall.name} now shows Automat.").wait_for(timeout=10_000)
    assert card(ui, the_wall).locator(".wall-now h3").inner_text() == "Automat"
    assert card(ui, the_wall).locator(".wall-now .wall-now-when").inner_text() == "On the wall now"


@pytest.mark.parametrize("scope", ["theme", "every_wall"])
def test_not_this_one_again_asks_where_and_does_that(ui, services, the_wall, winter, two_works, scope):
    """From this theme leaves the theme; from every wall keeps it off every wall and in the library."""
    nighthawks, _ = two_works
    report(services, the_wall, nighthawks.id)
    open_walls(ui)

    opener = ui.page.get_by_role("button", name=f"Not this one again on {the_wall.name}")
    assert opener.inner_text() == "Not this one again"
    assert opener.get_attribute("aria-expanded") == "false"
    opener.click()
    assert opener.get_attribute("aria-expanded") == "true"
    choice = card(ui, the_wall).locator(".not-again-choice")
    assert choice.locator("p").inner_text() == "Not Nighthawks again — from where?"

    if scope == "theme":
        choice.get_by_role("button", name="From Winter").click()
        card(ui, the_wall).locator(".wall-said", has_text="Nighthawks is out of Winter.").wait_for()
        assert nighthawks.id not in services.display.theme_work_ids(winter.id)
        assert services.display.excluded_works() == []
    else:
        choice.get_by_role("button", name="From every wall").click()
        card(ui, the_wall).locator(".wall-said", has_text="Nighthawks is kept off every wall.").wait_for()
        assert [each.artwork_id for each in services.display.excluded_works()] == [nighthawks.id]
        assert nighthawks.id in services.display.theme_work_ids(winter.id)
    # Neither is Archive.
    assert services.catalogue.get_artwork(nighthawks.id).artwork.status is ArtworkStatus.ACCEPTED


def test_not_this_one_again_is_not_offered_without_a_work_named(ui, services, the_wall, winter):
    """A display that has not said what it shows gives the act nothing to be about."""
    services.display.record_heartbeat(the_wall.id, {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")})
    open_walls(ui)

    assert ui.page.get_by_role("button", name=f"Not this one again on {the_wall.name}").count() == 0
    assert "has not said which work it is showing" in card(ui, the_wall).inner_text()


def test_the_walls_history_opens_from_its_card(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    history = card(ui, the_wall).get_by_role("link", name=f"History of {the_wall.name}")
    assert history.get_attribute("href") == f"#history?wall={the_wall.id}"
    history.click()
    ui.page.wait_for_selector(f"#view h1:text-is('History of {the_wall.name}')")
    assert f"Hung Winter on {the_wall.name}" in ui.text()


def test_a_lead_whose_image_cannot_be_loaded_says_so(ui, services, the_wall, winter, two_works):
    """A blank box where the work should be is the silence this product refuses."""
    report(services, the_wall, two_works[0].id)
    ui.page.route("**/thumbnail", lambda route: route.fulfill(status=404, body="gone"))
    ui.open("#walls")
    ui.page.wait_for_selector(".wall-now .card-image-absent")

    assert "Its image could not be loaded just now." in ui.text()
    assert ui.page.locator(".wall-now img").count() == 0


def test_a_lead_whose_image_loads_keeps_its_picture(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    ui.open("#walls")
    ui.page.wait_for_selector(".wall-now img")
    ui.page.wait_for_function(
        "() => [...document.querySelectorAll('.wall-now img')].every((i) => i.complete && i.naturalWidth > 0)"
    )

    assert "Its image could not be loaded just now." not in ui.text()
