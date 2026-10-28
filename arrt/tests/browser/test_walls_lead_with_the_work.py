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
    # What it hangs: the Hanging fact, whose value is the control that hangs
    # another (ruling 3 of 2026-10-27; it read "Drawing from Winter, until
    # changed." with a separate Change, and "until changed" is gone).
    picker = card(ui, the_wall).locator(f"select#hang-{the_wall.id}")
    assert picker.input_value() == winter.id
    assert "until changed" not in card(ui, the_wall).inner_text()


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

    # The Hanging fact names it a selection (ruling 3 of 2026-10-27 made the fact
    # the control; it read "Drawing from a selection, until changed."). With no
    # theme to hang instead there is no picker, and it is said in words.
    assert card(ui, the_wall).locator(".wall-hanging").inner_text().startswith("Hanging a selection.")
    assert "until changed" not in card(ui, the_wall).inner_text()
    assert "Selection for" not in ui.page.locator("#view").text_content()


def test_a_selection_with_a_theme_to_hang_instead_is_the_pickers_unchoosable_first(ui, services, the_wall, winter, two_works):
    services.display.hang_selection([two_works[0].id], wall_id=the_wall.id)
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    picker = card(ui, the_wall).locator(f"select#hang-{the_wall.id}")
    assert picker.locator("option").all_inner_texts() == ["A selection", "Winter"]
    assert picker.locator("option").first.get_attribute("disabled") is not None
    assert picker.input_value() == ""
    assert "Selection for" not in ui.page.locator("#view").text_content()


def test_change_offers_themes_and_never_a_selection(ui, services, the_wall, winter, two_works):
    other = services.display.add_wall(name="Study")
    services.display.hang_selection([two_works[0].id], wall_id=other.id)
    open_walls(ui)

    # Change became the Hanging picker (ruling 3 of 2026-10-27). It offers the
    # themes and never a selection, whichever wall is hanging one.
    picker = card(ui, the_wall).locator(f"select#hang-{the_wall.id}")
    assert picker.locator("option").all_inner_texts() == ["Winter"]
    study = card(ui, other).locator(f"select#hang-{other.id}")
    assert study.locator("option:not([disabled])").all_inner_texts() == ["Winter"]


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

    # Named Remove… by the owner's ruling 2 of 2026-10-27 ("Not this one again"
    # was too cute and too close to Skip); the question is now a dialog.
    opener = ui.page.get_by_role("button", name=f"Remove the work on {the_wall.name}…")
    assert opener.inner_text() == "Remove…"
    assert opener.get_attribute("aria-haspopup") == "dialog"
    opener.click()
    choice = ui.page.locator("dialog.panel-dialog")
    assert choice.locator("h2").inner_text() == f"Remove Nighthawks from {the_wall.name}"

    if scope == "theme":
        choice.locator("button", has_text="Take it out of Winter").click()
        card(ui, the_wall).locator(".wall-said", has_text="Nighthawks is out of Winter.").wait_for()
        assert nighthawks.id not in services.display.theme_work_ids(winter.id)
        assert services.display.excluded_works() == []
    else:
        choice.locator("button", has_text="Keep it off every wall").click()
        card(ui, the_wall).locator(".wall-said", has_text="Nighthawks is kept off every wall.").wait_for()
        assert [each.artwork_id for each in services.display.excluded_works()] == [nighthawks.id]
        assert nighthawks.id in services.display.theme_work_ids(winter.id)
    # Neither is Archive.
    assert services.catalogue.get_artwork(nighthawks.id).artwork.status is ArtworkStatus.ACCEPTED


def test_not_this_one_again_is_not_offered_without_a_work_named(ui, services, the_wall, winter):
    """A display that has not said what it shows gives the act nothing to be about."""
    services.display.record_heartbeat(the_wall.id, {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")})
    open_walls(ui)

    assert ui.page.get_by_role("button", name=f"Remove the work on {the_wall.name}…").count() == 0
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
        ("no_screen", "No screen"),
        ("unreachable", "Not known"),
        # A state from a later minor, which the server reads as unreachable.
        ("dimmed", "Not known"),
    ],
)
def test_a_screen_not_showing_art_leads_with_what_it_is_doing(ui, services, the_wall, winter, two_works, state, words):
    """Not the work: a Frame somebody is watching television on is not showing Nighthawks.

    A dark screen is not among these: it leads with the last-shown work, or the
    next, dimmed (ruling 6 of 2026-10-27), which
    `test_walls_last_and_next.py` holds.
    """
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
    assert ui.page.get_by_role("button", name=f"Remove the work on {the_wall.name}…").count() == 0


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
    assert ui.page.get_by_role("button", name=f"Remove the work on {the_wall.name}…").count() == 0


def test_a_wall_no_client_shows_leads_with_that_whatever_its_heartbeat_says(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    services.clients.unassign_wall(the_wall.id)
    open_walls(ui)

    lead = card(ui, the_wall).locator(".wall-now")
    assert lead.get_attribute("data-state") == "unassigned"
    # Said once, in the badge, with the problem line's way to fix it (a state is
    # worded once: the page rules of 2026-10-27). It read "Not assigned to a
    # screen" in the lead as well, and the work it last reported is not led with.
    assert lead.is_hidden()
    assert card(ui, the_wall).locator("figure").count() == 0
    assert card(ui, the_wall).locator(".wall-badge-unassigned").inner_text().strip().endswith("No Player")
    assert "Not assigned to a screen" not in card(ui, the_wall).inner_text()
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


def test_the_rotation_is_chosen_from_the_cards_setup(ui, services, the_wall, winter):
    """Minutes on the screen, seconds in the store; the facts are read back from the server's build."""
    open_walls(ui)
    setup = card(ui, the_wall).locator("details.wall-setup")
    setup.locator("summary").click()
    minutes = setup.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True)
    order = setup.get_by_label(f"Order on {the_wall.name}", exact=True)
    assert order.locator("option").all_inner_texts() == ["Default", "As curated", "Shuffled"]
    assert (minutes.input_value(), order.input_value()) == ("", "")
    button = setup.get_by_role("button", name=f"Set the rotation on {the_wall.name}")
    said = setup.locator(".wall-said")

    # 1.5 minutes: a value that is not whole minutes, so a lost factor of 60 or a
    # rounding to minutes shows.
    minutes.fill("1.5")
    order.select_option("false")
    button.click()
    said.filter(has_text=f"Rotation on {the_wall.name}: each work for 90 seconds, as curated.").wait_for()
    wall = services.display.get_wall(the_wall.id)
    assert (wall.rotation_interval_seconds, wall.shuffle) == (90, False)
    assert "90 seconds" in setup.locator("dl.facts").first.inner_text()
    assert setup.get_attribute("open") is not None, "the panel stays open after setting the rotation"

    minutes.fill("")
    order.select_option("")
    button.click()
    said.filter(has_text=f"Rotation on {the_wall.name}: each work for 3 minutes,").wait_for()
    wall = services.display.get_wall(the_wall.id)
    assert (wall.rotation_interval_seconds, wall.shuffle) == (None, None)


def test_a_rotation_of_no_minutes_is_refused_in_words_and_nothing_is_sent(ui, services, the_wall, winter):
    services.display.set_playback(the_wall.id, rotation_interval_seconds=931)
    open_walls(ui)
    setup = card(ui, the_wall).locator("details.wall-setup")
    setup.locator("summary").click()

    setup.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True).fill("0")
    setup.get_by_role("button", name=f"Set the rotation on {the_wall.name}").click()

    setup.locator(".wall-said").filter(has_text="Minutes must be more than zero").wait_for()
    assert services.display.get_wall(the_wall.id).rotation_interval_seconds == 931


def test_minutes_that_are_not_a_number_are_not_read_as_the_default(ui, services, the_wall, winter):
    """A number field holding "e" reports an empty value; sent, that would reset the wall to the default."""
    services.display.set_playback(the_wall.id, rotation_interval_seconds=931)
    open_walls(ui)
    setup = card(ui, the_wall).locator("details.wall-setup")
    setup.locator("summary").click()
    field = setup.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True)

    field.fill("")
    field.press_sequentially("e")
    setup.get_by_role("button", name=f"Set the rotation on {the_wall.name}").click()

    setup.locator(".wall-said").filter(has_text="Minutes must be a number").wait_for()
    assert services.display.get_wall(the_wall.id).rotation_interval_seconds == 931


@pytest.mark.parametrize(("seconds", "shown"), [(600, "10"), (931, "15.52")])
def test_a_chosen_rotation_is_the_one_the_fields_show(ui, services, the_wall, winter, seconds, shown):
    """To two places: 931 seconds is not shown as 15.516666666666667."""
    services.display.set_playback(the_wall.id, rotation_interval_seconds=seconds, shuffle=True)
    open_walls(ui)
    card(ui, the_wall).locator("details.wall-setup summary").click()

    setup = card(ui, the_wall)
    assert setup.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True).input_value() == shown
    assert setup.get_by_label(f"Order on {the_wall.name}", exact=True).input_value() == "true"


def open_setup(ui, wall):
    open_walls(ui)
    setup = card(ui, wall).locator("details.wall-setup")
    setup.locator("summary").click()
    return setup


def test_the_shapes_are_chosen_from_the_cards_setup(ui, services, the_wall, winter):
    """Both works are 4:3: landscape-and-square keeps them, portrait-and-square darkens the wall, and the panel says so."""
    setup = open_setup(ui, the_wall)
    picker = setup.get_by_label(f"Shapes on {the_wall.name}", exact=True)
    tallest = setup.get_by_label(f"Tallest on {the_wall.name}, as width:height", exact=True)
    widest = setup.get_by_label(f"Widest on {the_wall.name}, as width:height", exact=True)
    assert picker.locator("option").all_inner_texts() == ["Any shape", "Portrait and square", "Landscape and square", "Custom"]
    assert (picker.input_value(), tallest.input_value(), widest.input_value()) == ("any", "", "")
    assert "has not said its size" in setup.locator("dl.facts").nth(1).inner_text()
    button = setup.get_by_role("button", name=f"Set the shapes on {the_wall.name}")
    said = setup.locator(".wall-said")

    picker.select_option("landscape")
    assert (tallest.input_value(), widest.input_value()) == ("1:1", "")
    button.click()
    said.filter(has_text=f"{the_wall.name} shows nothing taller than 1:1. All 2 works in this theme are on the wall.").wait_for()
    wall = services.display.get_wall(the_wall.id)
    assert (wall.min_aspect_ratio, wall.max_aspect_ratio) == (1.0, None)

    picker.select_option("portrait")
    button.click()
    said.filter(has_text="2 are outside this wall's shapes, so the wall is dark.").wait_for()
    wall = services.display.get_wall(the_wall.id)
    assert (wall.min_aspect_ratio, wall.max_aspect_ratio) == (None, 1.0)
    assert "nothing wider than 1:1" in setup.locator("dl.facts").nth(1).inner_text()
    assert setup.get_attribute("open") is not None, "the panel stays open after setting the shapes"


def test_typing_a_bound_makes_the_picker_say_custom(ui, the_wall, winter):
    setup = open_setup(ui, the_wall)

    setup.get_by_label(f"Widest on {the_wall.name}, as width:height", exact=True).fill("4:5")

    assert setup.get_by_label(f"Shapes on {the_wall.name}", exact=True).input_value() == "custom"
    setup.get_by_label(f"Widest on {the_wall.name}, as width:height", exact=True).fill("1:1")
    assert setup.get_by_label(f"Shapes on {the_wall.name}", exact=True).input_value() == "portrait"


def test_setting_the_rotation_after_the_shapes_keeps_the_shapes(ui, services, the_wall, winter):
    """The two panels write one body: the second Set must send what the first one set, not the card as first drawn."""
    setup = open_setup(ui, the_wall)
    said = setup.locator(".wall-said")
    setup.get_by_label(f"Shapes on {the_wall.name}", exact=True).select_option("landscape")
    setup.get_by_role("button", name=f"Set the shapes on {the_wall.name}").click()
    said.filter(has_text="shows nothing taller than 1:1").wait_for()

    setup.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True).fill("10")
    setup.get_by_role("button", name=f"Set the rotation on {the_wall.name}").click()
    said.filter(has_text="each work for 10 minutes").wait_for()

    wall = services.display.get_wall(the_wall.id)
    assert (wall.rotation_interval_seconds, wall.min_aspect_ratio) == (600, 1.0)


def test_a_shape_that_is_not_one_is_refused_in_the_servers_words(ui, services, the_wall, winter):
    services.display.set_playback(the_wall.id, widest="16:9")
    setup = open_setup(ui, the_wall)

    setup.get_by_label(f"Widest on {the_wall.name}, as width:height", exact=True).fill("wide")
    setup.get_by_role("button", name=f"Set the shapes on {the_wall.name}").click()

    setup.locator(".act-failure").filter(has_text="width:height").wait_for()
    assert services.display.get_wall(the_wall.id).max_aspect_ratio == pytest.approx(16 / 9)


def test_chosen_shapes_are_the_ones_the_fields_show(ui, services, the_wall, winter):
    services.display.set_playback(the_wall.id, tallest="4:5", widest="16:9")
    setup = open_setup(ui, the_wall)

    assert setup.get_by_label(f"Shapes on {the_wall.name}", exact=True).input_value() == "custom"
    assert setup.get_by_label(f"Tallest on {the_wall.name}, as width:height", exact=True).input_value() == "4:5"
    assert setup.get_by_label(f"Widest on {the_wall.name}, as width:height", exact=True).input_value() == "16:9"
    assert "works from 4:5 to 16:9" in setup.locator("dl.facts").nth(1).inner_text()


def test_the_screens_own_shape_is_shown_beside_the_walls_as_a_hint(ui, services, the_wall, winter, two_works):
    report_with_screen(services, the_wall, two_works[0].id, width=1080, height=1920)
    setup = open_setup(ui, the_wall)

    assert "9:16" in setup.locator("dl.facts").nth(1).inner_text()
    # A hint only: nothing was set from it.
    assert services.display.get_wall(the_wall.id).max_aspect_ratio is None


def test_a_wall_its_shapes_have_darkened_says_so_at_the_top_of_its_card(ui, services, the_wall, winter):
    services.display.set_playback(the_wall.id, widest="1:1")
    open_walls(ui)

    warning = card(ui, the_wall).locator(".wall-dark")
    assert warning.inner_text().endswith("2 are outside this wall's shapes, so the wall is dark.")
    # The works it cannot show open from the card's foot (the page rules of
    # 2026-10-27); they were a table in the setup disclosure.
    card(ui, the_wall).locator("button.wall-kept").click()
    reasons = ui.page.locator("dialog.panel-dialog table tbody tr")
    assert set(reasons.all_inner_texts()) == {
        f"{title}\tOutside this wall's shapes\tThis wall shows nothing wider than 1:1, and this work is 4:3. "
        "Change the wall's shapes on Walls to put it back."
        for title in ("Nighthawks", "Automat")
    }


def test_a_wall_showing_works_carries_no_dark_warning(ui, the_wall, winter):
    open_walls(ui)

    # The card no longer repeats how much of the theme is on the wall when all of
    # it is (an exception stays quiet until it blocks, 2026-10-27); it says so
    # only when none of it is, and then as the dark warning.
    card(ui, the_wall).locator(".wall-controls").wait_for()
    assert card(ui, the_wall).locator(".wall-dark").count() == 0
    assert card(ui, the_wall).locator("button.wall-kept").count() == 0


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
    assert wall["sizes_judged_against"] == {"width_px": 3840, "height_px": 2160, "shape": "16:9"}
    assert wall["sizes_unjudged"] is None


# -- the state badge at the card's head (the page rules of 2026-10-27) ---------------------


def test_a_wall_showing_art_says_so_in_its_badge(ui, services, the_wall, winter, two_works):
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    badge = card(ui, the_wall).locator("header.wall-head .wall-badge")
    assert badge.inner_text().strip().endswith("Showing")
    assert card(ui, the_wall).locator(".wall-badge-unassigned").count() == 0


def test_an_assigned_wall_carries_no_no_player_badge_and_an_unassigned_one_does(ui, services, the_wall, winter, two_works):
    """The conditional half: "No Player" only where no Player is assigned."""
    # `the_wall` is assigned to Hall Pi by its fixture; the study is assigned to nothing.
    study = services.display.add_wall(name="Study")
    assert services.display.get_wall(the_wall.id).display_id is not None, "the fixture must assign the wall"
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    assert card(ui, the_wall).locator(".wall-badge-unassigned").count() == 0
    assert card(ui, the_wall).locator(".wall-problem").count() == 0
    assert card(ui, study).locator(".wall-badge-unassigned").inner_text().strip().endswith("No Player")
    assert card(ui, study).locator(".wall-problem").inner_text().startswith("No Player shows this wall.")


# -- the keyboard (Done-when 3 of `build-plan-ui-pass-walls.md` Chunk 03) ------------------


def _tab_to(ui, name, limit=60):
    """Press Tab until the focused element's accessible name is `name`; fail past `limit`."""
    for _ in range(limit):
        ui.page.keyboard.press("Tab")
        label = ui.page.evaluate(
            "() => { const n = document.activeElement;"
            " return n && (n.getAttribute('aria-label') || n.textContent || '').trim(); }"
        )
        if label == name:
            return
    raise AssertionError(f"Tab never reached {name!r}")


@pytest.mark.parametrize(
    ("opener", "safe"),
    [("Remove the work on {wall}…", "Cancel"), ("Scene…", "Close")],
)
def test_each_dialog_opens_from_the_keyboard_starts_safe_and_closes_with_escape(
    ui, services, the_wall, winter, two_works, opener, safe
):
    nighthawks, _ = two_works
    report(services, the_wall, nighthawks.id)
    before = services.display.published_manifest_v2(the_wall.id)
    open_walls(ui)

    _tab_to(ui, opener.format(wall=the_wall.name))
    ui.page.keyboard.press("Enter")
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    # Wider than a confirmation's 32rem: it holds a choice or a list (`app.css`).
    assert dialog.evaluate("(node) => getComputedStyle(node).maxWidth") == "640px"
    # Focus starts on the answer that changes nothing, as `confirm.js`'s does.
    assert ui.page.evaluate("() => document.activeElement.textContent.trim()") == safe
    ui.page.keyboard.press("Escape")
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert services.display.published_manifest_v2(the_wall.id) == before
    assert services.display.excluded_works() == []
    assert services.display.scene_draft() is None


def test_the_pages_facts_count_the_walls_and_those_showing_art(ui, services, the_wall, winter, two_works):
    """The one line under the page's name (the page rules of 2026-10-27), counted
    from each wall's display state: two walls, one of them showing art."""
    services.display.add_wall(name="Study")
    report(services, the_wall, two_works[0].id)
    open_walls(ui)

    assert ui.page.locator("#view .page-facts").inner_text() == "2 walls · 1 showing art now"
