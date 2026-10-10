"""Each wall's card leads with what its screen is doing, in a real browser.

`ia-proposal.md` § Walls: the work on the wall now, large, with its label facts,
then what the wall draws from and "until changed", then Skip, *Not this one
again* and Change, and the wall's history from its card. `labels-and-surfaces.md`
§ Display state: when the screen is not showing art, the card says what it is
doing instead, in words.

**The heartbeat is real.** Each test records the wall's heartbeat through
`record_heartbeat`, the path a Player's POST takes, so the card reads the
`display_state` the server derives from it rather than a stub's idea of it, and a
Skip's new work arrives the way a Player's next report does. `report` writes a
heartbeat as a Player before minor 3 does (`current_work_id` alone);
`report_state` writes minor 3's `display_state`.

**The wall is assigned to a client output**, because a wall no client shows is
`unassigned` whatever its heartbeat file says.
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
    wall = services.display.survey_walls()[0].wall
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
    return services.display.get_wall(wall.id)


@pytest.fixture
def a_displayable_work(work_with_an_image, service, settings, decodable_jpeg):
    """A work that reaches a wall: image on disk, a mat, and a presentation master."""

    def _work(title):
        artwork = work_with_an_image(title=title)
        service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        presented = f"presentation/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / presented, width=400, height=300)
        service.record_rendition(
            artwork_id=artwork.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=presented
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


def report_state(services, wall, state, work_id=None, *, since="2026-10-08T19:30:00+00:00", ago=timedelta(seconds=5)):
    """What a minor 3 Player says its wall's screen is doing."""
    services.display.record_heartbeat(
        wall.id,
        {
            "reported_at": (datetime.now(UTC) - ago).isoformat(timespec="seconds"),
            "current_work_id": "not-what-the-card-reads",
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": state, "work_id": work_id, "since": since},
        },
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


def test_an_old_heartbeat_still_leads_with_its_work_under_when_it_was_last_heard_from(ui, services, the_wall, winter, two_works):
    """The last report is the best answer to what is on the wall, but not a claim about now.

    Reworded from "Last reported 5 hours ago, so it may have changed since" when
    the server began calling such a wall `silent`: the card now says when the wall
    was last heard from, with the date (`core/dates.js`) and the age.
    """
    report(services, the_wall, two_works[0].id, ago=timedelta(hours=5))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    when = lead.locator(".wall-now-when").inner_text()
    assert when.startswith("Not heard from since ")
    assert when.endswith("(5 hours ago), so this may have changed since")
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


def test_skip_republishes_the_wall_and_the_card_shows_the_next_work_once_reported(ui, services, the_wall, winter, two_works):
    nighthawks, automat = two_works
    report(services, the_wall, nighthawks.id)
    before = services.display.published_manifest_v2(the_wall.id)
    open_walls(ui)

    ui.page.get_by_role("button", name=f"Skip the work on {the_wall.name}").click()
    said = card(ui, the_wall).locator(".wall-said")
    said.filter(has_text="Skipped.").wait_for()
    assert services.display.published_manifest_v2(the_wall.id) != before
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
    ui.page.route("**/thumbnail*", lambda route: route.fulfill(status=404, body="gone"))
    ui.open("#walls")
    ui.page.wait_for_selector(".wall-now .card-image-absent")

    assert "Its image could not be loaded just now." in ui.text()
    assert ui.page.locator(".wall-now img").count() == 0


def test_the_lead_asks_for_the_large_bare_work_not_the_tile(ui, services, the_wall, winter, two_works):
    """Drawn up to 48rem wide, the 480 px tile is soft on a 2x screen; the canvas would show the mat."""
    report(services, the_wall, two_works[0].id)
    open_walls(ui)
    image = card(ui, the_wall).locator(".wall-now img")
    image.wait_for()
    assert image.get_attribute("src") == f"/api/works/{two_works[0].id}/thumbnail?size=large"


def test_a_lead_whose_image_loads_keeps_its_picture(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    ui.open("#walls")
    ui.page.wait_for_selector(".wall-now img")
    ui.page.wait_for_function(
        "() => [...document.querySelectorAll('.wall-now img')].every((i) => i.complete && i.naturalWidth > 0)"
    )

    assert "Its image could not be loaded just now." not in ui.text()


# -- the states that are not a work -------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "words"),
    [
        ("in_use", "Somebody is using the screen"),
        ("dark", "Its screen is off"),
        ("no_screen", "No screen"),
        ("unreachable", "Not known"),
        # A state from a later minor, which the server reads as unreachable.
        ("dimmed", "Not known"),
    ],
)
def test_a_screen_not_showing_art_leads_with_what_it_is_doing(ui, services, the_wall, winter, two_works, state, words):
    """Not the work: a Frame somebody is watching television on is not showing Nighthawks."""
    report_state(services, the_wall, state)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.get_attribute("data-state") == ("unreachable" if state == "dimmed" else state)
    assert lead.locator(".wall-now-state").inner_text() == words
    assert "Since " in lead.inner_text()
    # The sentence for a Player before display state is not said of one that
    # reports state: an unreachable Frame has lost its set, not its words.
    assert "has not said which work it is showing" not in lead.inner_text()
    # The server reads a state it has no name for as unreachable, so the
    # sentence is one true of both: never "cannot reach its screen", which
    # would be false of a screen in a state this server cannot name.
    if state in ("unreachable", "dimmed"):
        assert "cannot say what its screen is showing" in lead.inner_text()
    assert "cannot reach its screen" not in lead.inner_text()
    assert lead.locator("img").count() == 0
    assert "On the wall now" not in lead.inner_text()
    # The lead still leads the card.
    assert card(ui, the_wall).locator("> *").nth(1).get_attribute("class") == "wall-now"
    # Nothing on screen to be tired of.
    assert ui.page.get_by_role("button", name=f"Not this one again on {the_wall.name}").count() == 0


def test_minor_3_is_read_over_current_work_id(ui, services, the_wall, winter, two_works):
    """The card reads the state, never `current_work_id` alone: here it names a work and the screen is in use."""
    services.display.record_heartbeat(
        the_wall.id,
        {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "current_work_id": two_works[0].id,
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": "in_use", "work_id": None, "since": "2026-10-08T19:30:00+00:00"},
        },
    )
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.locator(".wall-now-state").inner_text() == "Somebody is using the screen"
    assert "Nighthawks" not in lead.inner_text()


def test_a_minor_3_wall_showing_a_work_leads_with_it(ui, services, the_wall, winter, two_works):
    _, automat = two_works
    report_state(services, the_wall, "showing_art", automat.id)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.locator(".wall-now-when").inner_text() == "On the wall now"
    assert lead.locator("h3").inner_text() == "Automat"


def test_a_picture_this_wall_did_not_put_there_reads_as_one(ui, services, the_wall, winter):
    """A remote-control change to art the wall cannot name: showing art, and not one of ours."""
    report_state(services, the_wall, "showing_art", None)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.locator(".wall-now-when").inner_text() == "On the wall now"
    assert lead.locator(".wall-now-state").inner_text() == f"A picture {the_wall.name} did not put there"
    assert lead.locator("img").count() == 0
    assert ui.page.get_by_role("button", name=f"Not this one again on {the_wall.name}").count() == 0


def test_a_wall_no_client_shows_leads_with_that_whatever_its_heartbeat_says(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    services.clients.unassign_wall(the_wall.id)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.get_attribute("data-state") == "unassigned"
    assert lead.locator(".wall-now-state").inner_text() == "Not assigned to a screen"
    assert "Nighthawks" not in lead.inner_text()
    # The way to fix it is the assignment line's link, still beneath.
    assert card(ui, the_wall).get_by_role("link", name="Assign it in Settings › Clients").count() == 1


def test_a_silent_wall_says_when_it_was_last_heard_from_and_what_it_said(ui, services, the_wall, winter):
    report_state(services, the_wall, "dark", ago=timedelta(hours=2))
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.get_attribute("data-state") == "silent"
    when = lead.locator(".wall-now-when").inner_text()
    assert when.startswith("Not heard from since ")
    assert when.endswith("(2 hours ago)")
    assert "When it last reported: Its screen is off." in lead.inner_text()


def test_a_skip_watched_through_a_minor_3_report(ui, services, the_wall, winter, two_works):
    """The watch after Skip reads the state too: a report naming the next work replaces the lead."""
    nighthawks, automat = two_works
    report_state(services, the_wall, "showing_art", nighthawks.id)
    open_walls(ui)

    ui.page.get_by_role("button", name=f"Skip the work on {the_wall.name}").click()
    said = card(ui, the_wall).locator(".wall-said")
    said.filter(has_text="Skipped.").wait_for()
    report_state(services, the_wall, "showing_art", automat.id)
    said.filter(has_text=f"{the_wall.name} now shows Automat.").wait_for(timeout=10_000)
    assert card(ui, the_wall).locator(".wall-now h3").inner_text() == "Automat"


def test_the_mat_is_chosen_from_the_cards_setup_and_handed_back_to_the_player(ui, services, the_wall, winter):
    open_walls(ui)
    setup = card(ui, the_wall).locator("details.wall-setup")
    setup.locator("summary").click()
    picker = setup.get_by_label(f"Mat on {the_wall.name}", exact=True)
    assert picker.locator("option").all_inner_texts() == [
        "Player's own choice",
        "Mat around the work",
        "Mat to the edges",
        "No mat",
    ]
    assert picker.input_value() == ""
    button = setup.get_by_role("button", name=f"Set the mat on {the_wall.name}")
    said = setup.locator(".wall-said")

    picker.select_option("full")
    button.click()
    said.filter(has_text=f"Mat on {the_wall.name}: to the edges.").wait_for()
    assert services.display.get_wall(the_wall.id).mat_mode == "full"
    assert setup.get_attribute("open") is not None, "the panel stays open after setting the mat"

    picker.select_option("")
    button.click()
    said.filter(has_text=f"Mat on {the_wall.name}: left to its Player.").wait_for()
    assert services.display.get_wall(the_wall.id).mat_mode is None


def test_a_chosen_mat_is_the_one_the_picker_shows(ui, services, the_wall, winter):
    services.display.set_mat_mode(the_wall.id, "none")
    open_walls(ui)
    card(ui, the_wall).locator("details.wall-setup summary").click()

    assert card(ui, the_wall).get_by_label(f"Mat on {the_wall.name}", exact=True).input_value() == "none"


@pytest.fixture
def with_master(service, settings, decodable_jpeg):
    """Give a work a presentation master of a size of its own, so the wall's feed carries it."""

    def _give(work, *, width, height):
        path = f"masters/{work.id}.jpg"
        decodable_jpeg(settings.art_root / path, width=width, height=height)
        service.record_rendition(
            artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
        )
        return work

    return _give


def report_with_screen(services, wall, work_id, *, width=3840, height=2160):
    """A minor 3 report that also says how big the wall's screen is (minor 2's capabilities)."""
    services.display.record_heartbeat(
        wall.id,
        {
            "reported_at": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(timespec="seconds"),
            "current_work_id": work_id,
            "schema": {"major": 1, "minor": 3},
            "display_state": {"state": "showing_art", "work_id": work_id, "since": "2026-10-09T19:30:00+00:00"},
            "capabilities": {
                "screen": {"width_px": width, "height_px": height},
                "backend": "framebuffer",
                "label_modes": ["none"],
                "manifest_majors": [2, 1],
            },
        },
    )


@pytest.fixture
def small_and_large(services, the_wall, two_works, with_master):
    """Nighthawks with a small master and Automat with a large one, hung on the wall."""
    nighthawks, automat = two_works
    with_master(nighthawks, width=1000, height=700)
    with_master(automat, width=6000, height=4000)
    theme = services.display.add_theme(name="Sizes")
    for work in two_works:
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=the_wall.id)
    return theme


def test_a_work_too_small_for_the_walls_screen_says_so_under_it(ui, services, the_wall, two_works, small_and_large):
    nighthawks, _ = two_works
    report_with_screen(services, the_wall, nighthawks.id)
    open_walls(ui)

    note = card(ui, the_wall).locator(".wall-now .wall-now-small")
    expected = f"Too small for {the_wall.name}: it fills less than half of the space inside the mat. A larger scan would fix it."
    assert note.inner_text() == expected


def test_a_work_large_enough_carries_no_note(ui, services, the_wall, two_works, small_and_large):
    _, automat = two_works
    report_with_screen(services, the_wall, automat.id)
    open_walls(ui)

    assert card(ui, the_wall).locator(".wall-now h3").inner_text() == "Automat"
    assert card(ui, the_wall).locator(".wall-now-small").count() == 0


def test_the_theme_page_marks_a_work_too_small_for_the_wall_hanging_it(ui, services, the_wall, two_works, small_and_large):
    _, automat = two_works
    report_with_screen(services, the_wall, automat.id)
    ui.open(f"#theme/{small_and_large.id}")
    ui.page.wait_for_selector("table tbody tr")

    rows = ui.page.locator("table tbody tr")
    small_row = rows.filter(has_text="Nighthawks")
    large_row = rows.filter(has_text="Automat")
    assert small_row.locator(".badge", has_text=f"too small for {the_wall.name}").count() == 1
    assert large_row.locator(".badge", has_text="too small").count() == 0


def test_the_walls_api_says_what_the_judgement_was_made_against(ui, services, the_wall, two_works, small_and_large):
    nighthawks, _ = two_works
    report_with_screen(services, the_wall, nighthawks.id, width=3840, height=2160)

    walls = ui.page.request.get(f"{ui.base_url}/api/walls").json()["walls"]

    wall = next(entry for entry in walls if entry["wall_id"] == the_wall.id)
    assert wall["too_small"] == [nighthawks.id]
    assert wall["sizes_judged_against"] == {"width_px": 3840, "height_px": 2160}
    assert wall["sizes_unjudged"] is None
