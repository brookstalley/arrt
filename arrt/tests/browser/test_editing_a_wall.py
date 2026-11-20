"""A wall's Edit… dialog and Add wall…, in a real browser against a real server.

The owner's rulings of 2026-10-27 (`ia-proposal.md`, rulings 1 and 4) put a wall's
settings in one dialog opened from its card, and gave the page a way to add a
wall. Each part of the dialog is set by its own act; every test here reads the
result back from the server rather than from the page, with a value that is not
the default, so a control that changed only the page would fail.
"""

import json
import re
from datetime import UTC, datetime

import httpx
import pytest

from arrt.persistence.records import MatMethod, RenditionKind
from arrt.programming.client_heartbeat import client_heartbeat_path_in

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

REPORT = {
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


@pytest.fixture
def hall(services, settings):
    """A Player that has reported its two screens, and shows no wall yet."""
    client = services.clients.add_client(name="Hall Pi")
    services.access.issue(client.id)
    document = REPORT | {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")}
    client_heartbeat_path_in(settings.art_root, client.id).write_text(json.dumps(document), encoding="utf-8")
    return client


def walls_read(ui):
    """What the server says of every wall, read as the page reads it."""
    return {wall["wall_id"]: wall for wall in ui.page.evaluate("() => fetch('/api/walls').then((r) => r.json())")["walls"]}


def card(ui, wall_name):
    return ui.page.locator("section.wall", has=ui.page.locator(f"h2.wall-title:text-is('{wall_name}')"))


def open_edit(ui, wall_name):
    ui.open("#walls")
    card(ui, wall_name).get_by_role("button", name=f"Edit {wall_name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()
    return dialog


def test_renaming_from_the_dialog_renames_the_wall_and_repaints_the_card(ui, services, the_wall):
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("The hall")
    dialog.get_by_role("button", name=f"Rename {the_wall.name}").click()

    ui.page.locator("h2.wall-title:text-is('The hall')").wait_for()
    assert services.display.get_wall(the_wall.id).name == "The hall"
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)


def test_a_taken_name_is_refused_beside_the_field_and_nothing_changes(ui, services, the_wall):
    services.display.add_wall(name="Study")
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("Study")
    dialog.get_by_role("button", name=f"Rename {the_wall.name}").click()

    failure = dialog.locator(".act-failure")
    failure.wait_for()
    expect(failure).to_contain_text("Another wall is already called 'Study'.", use_inner_text=True)
    assert services.display.get_wall(the_wall.id).name == the_wall.name


def test_where_it_shows_puts_the_wall_on_a_players_screen_and_none_takes_it_off(ui, services, the_wall, hall):
    dialog = open_edit(ui, the_wall.name)
    player = dialog.get_by_label(f"Player for {the_wall.name}", exact=True)
    expect(player).to_have_value("")
    player.select_option(hall.id)
    screen = dialog.get_by_label("Screen", exact=True)
    # In a person's words (`information-architecture.md` § Vocabulary), the port
    # the value the server is sent.
    expect(screen.locator("option")).to_have_text(["HDMI 1", "HDMI 2 · nothing connected"], use_inner_text=True)
    # Not the first screen offered, so a picker that sent its default would fail.
    screen.select_option("hdmi-a-2")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    read = walls_read(ui)[the_wall.id]
    assert (read["client_id"], read["output"]) == (hall.id, "hdmi-a-2")
    # The card is repainted from that, and no longer says no Player shows it.
    card(ui, the_wall.name).locator(".wall-problem").wait_for(state="detached")

    dialog = open_edit(ui, the_wall.name)
    expect(dialog.get_by_label(f"Player for {the_wall.name}", exact=True)).to_have_value(hall.id)
    expect(dialog.get_by_label("Screen", exact=True)).to_have_value("hdmi-a-2")
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option("")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert walls_read(ui)[the_wall.id]["client_id"] is None
    problem = card(ui, the_wall.name).locator(".wall-problem")
    problem.wait_for()
    expect(problem).to_have_text(re.compile(r"^No Player shows this wall\."), use_inner_text=True)


FRAME = {
    "name": "frame",
    "kind": "frame",
    "connected": True,
    "screen": [3840, 2160],
    "identity": "uuid:00000000-0000-4000-8000-000000000009",
}


def test_a_placement_the_server_cannot_confirm_is_said_in_the_dialog_which_stays_open(ui, services, settings, the_wall, hall):
    """The server keeps an assignment it cannot confirm and says why in `notice`.

    A Frame two Players both report shows no wall, so putting this one on it is
    kept but shows nothing: the dialog says the server's sentence where the act
    was made, rather than closing over it. Settings › Players said it until
    ruling 7 of 2026-10-27 took assigning off that page.
    """
    stamp = {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")}
    study_mac = services.clients.add_client(name="Study Mac")
    services.access.issue(study_mac.id)
    for client in (hall, study_mac):
        document = stamp | {"outputs": [*REPORT["outputs"], FRAME]}
        client_heartbeat_path_in(settings.art_root, client.id).write_text(json.dumps(document), encoding="utf-8")
        services.clients.record_heartbeat(client.id, document)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option(hall.id)
    screens = dialog.get_by_label("Screen", exact=True)
    # A Frame is named by its kind on Walls too, never by its port (§ Vocabulary).
    # One option whose whole text is that, wherever it stands in the list: a
    # subsequence of one, which is how a list holds an item.
    expect(screens.locator("option")).to_contain_text([re.compile("^Samsung Frame$")], use_inner_text=True)
    screens.select_option("frame")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()

    notice = dialog.locator(".wall-notice:not([hidden])")
    notice.wait_for()
    expect(notice).to_contain_text("Hall Pi and Study Mac both report", use_inner_text=True)
    expect(dialog).to_be_visible()
    # Kept: the wall's record names the Player and the Frame, though neither
    # Player shows it while both report that display.
    assert walls_read(ui)[the_wall.id]["output"] == "frame"
    # Closed, the card catches up with what was kept.
    ui.page.keyboard.press("Escape")
    dialog.wait_for(state="detached")
    card(ui, the_wall.name).locator(".wall-fault").wait_for()


def test_a_placement_the_server_confirms_says_nothing_and_closes(ui, services, the_wall, hall):
    """The paired case: no notice, no line, and the dialog closes as before."""
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option(hall.id)
    dialog.get_by_label("Screen", exact=True).select_option("hdmi-a-1")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()
    dialog.wait_for(state="detached")
    expect(ui.page.locator(".wall-notice:not([hidden])")).to_have_count(0)


def test_a_screen_showing_another_wall_is_named_and_a_second_wall_is_refused_beside_the_act(ui, services, the_wall, hall):
    """Carried from Settings › Clients' assign (retired with ruling 7 of 2026-10-27),
    where assigning now is: a screen showing another wall is offered with that
    wall's name, and the server's refusal of a second is said beside *Show it
    there*, with nothing moved."""
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    study = services.display.add_wall(name="Study")

    dialog = open_edit(ui, study.name)
    dialog.get_by_label(f"Player for {study.name}", exact=True).select_option(hall.id)
    screen = dialog.get_by_label("Screen", exact=True)
    expect(screen.locator("option")).to_have_text(
        [f"HDMI 1 · shows {the_wall.name}", "HDMI 2 · nothing connected"], use_inner_text=True
    )
    screen.select_option("hdmi-a-1")
    show = dialog.get_by_role("button", name=f"Show {study.name} there")
    show.click()

    assert "already shows" in ui.said_beside(show)
    assert walls_read(ui)[study.id]["client_id"] is None
    assert walls_read(ui)[the_wall.id]["output"] == "hdmi-a-1"
    # The wall's own screen is not called taken in its own dialog.
    ui.page.keyboard.press("Escape")
    dialog = open_edit(ui, the_wall.name)
    options = dialog.get_by_label("Screen", exact=True).locator("option")
    # Its own screen is offered, plain: that is what shows the list has been drawn,
    # so that no option says "shows" is not met by an empty list. The filter is
    # `has_text` (a case-insensitive substring of the raw text), which only chooses
    # the options to count; the claim is that none of them is one.
    expect(options.first).to_have_text(re.compile(r"^HDMI 1"), use_inner_text=True)
    expect(options.filter(has_text="shows")).to_have_count(0)


def test_a_label_panel_is_added_from_the_dialog_and_stopped_there(ui, services, settings, the_wall, hall):
    # A label panel the Player has, captioning nothing: added, then stopped, which
    # leaves it recorded (`remove_label`), as a Player that reported one would.
    # Reported, too: a panel its report does not list is kept with a notice, and
    # the dialog stays open to say it (the test beside this one's subject).
    panel = {"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}
    document = REPORT | {"label_outputs": [panel], "reported_at": datetime.now(UTC).isoformat(timespec="seconds")}
    client_heartbeat_path_in(settings.art_root, hall.id).write_text(json.dumps(document), encoding="utf-8")
    labelled = services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    services.clients.remove_label(the_wall.id, label_id=labelled.label.id)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label(f"Caption {the_wall.name} with", exact=True).select_option(label="the label panel on Hall Pi")
    dialog.get_by_role("button", name=f"Caption {the_wall.name} with this label panel").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    [label] = walls_read(ui)[the_wall.id]["labels"]
    assert (label["output"], label["client_id"]) == ("epd-0", hall.id)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_role("button", name=f"Stop the label panel on Hall Pi captioning {the_wall.name}").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")
    assert walls_read(ui)[the_wall.id]["labels"] == []


def test_a_label_panel_the_report_does_not_list_is_kept_and_said_in_the_dialog(ui, services, the_wall, hall):
    """Hall Pi reported its screens and no label panel, so a panel recorded for it
    is kept with the server's notice, said in the dialog that captioned with it."""
    labelled = services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    services.clients.remove_label(the_wall.id, label_id=labelled.label.id)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label(f"Caption {the_wall.name} with", exact=True).select_option(label="the label panel on Hall Pi")
    dialog.get_by_role("button", name=f"Caption {the_wall.name} with this label panel").click()

    notice = dialog.locator(".wall-notice:not([hidden])")
    notice.wait_for()
    expect(notice).to_have_text(
        "Hall Pi last reported these label outputs: none. 'epd-0' is not among them, "
        "so nothing captions this wall there until the Player has a label output by that name.",
        use_inner_text=True,
    )
    expect(notice).not_to_contain_text("client", use_inner_text=True)
    [label] = walls_read(ui)[the_wall.id]["labels"]
    assert label["output"] == "epd-0"


def test_a_label_panel_captioning_another_wall_is_not_offered(ui, services, the_wall, hall):
    """The server refuses a panel that captions another wall, so the picker offers
    only the free one; with two on the Player, each is told apart by its port."""
    study = services.display.add_wall(name="Study")
    services.clients.add_label(study.id, client_id=hall.id, output="epd-0")
    freed = services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-1")
    services.clients.remove_label(the_wall.id, label_id=freed.label.id)

    dialog = open_edit(ui, the_wall.name)
    offered = dialog.get_by_label(f"Caption {the_wall.name} with", exact=True).locator("option")
    expect(offered).to_have_text(["label panel epd-1 on Hall Pi"], use_inner_text=True)


def test_a_rotation_set_in_the_dialog_is_on_the_card_once_it_closes(ui, services, the_wall, a_theme_to_hang):
    services.display.activate_theme(a_theme_to_hang.id, wall_id=the_wall.id)
    dialog = open_edit(ui, the_wall.name)
    changes = card(ui, the_wall.name).locator(".wall-hanging dt:text-is('Changes') + dd")
    # What the card said before is asserted before the act, rather than read and
    # compared after it: the card is there (it says something), and not yet "7 minutes".
    expect(changes).to_be_visible()
    expect(changes).not_to_contain_text("7 minutes", use_inner_text=True)
    dialog.get_by_label(f"Minutes each work stays up on {the_wall.name}", exact=True).fill("7")
    dialog.get_by_role("button", name=f"Set the rotation on {the_wall.name}").click()
    dialog.locator(".wall-said", has_text="Rotation on").wait_for()
    # Left open to go on working in: the card catches up when it closes.
    ui.page.keyboard.press("Escape")
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert services.display.get_wall(the_wall.id).rotation_interval_seconds == 7 * 60
    card(ui, the_wall.name).locator(".wall-hanging dt:text-is('Changes') + dd", has_text="7 minutes").wait_for()


def test_close_and_cancel_change_nothing(ui, services, the_wall, hall):
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("Not saved")
    dialog.get_by_role("button", name="Close").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")
    assert services.display.get_wall(the_wall.id).name == the_wall.name

    ui.page.get_by_role("button", name="Add wall…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.get_by_label("Name", exact=True).fill("Study")
    dialog.get_by_role("button", name="Cancel").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")
    assert [view.wall.name for view in services.display.survey_walls()] == [the_wall.name]


def test_escape_closes_the_dialog_and_changes_nothing(ui, services, the_wall, hall):
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("Not saved")
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option(hall.id)
    ui.page.keyboard.press("Escape")
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert services.display.get_wall(the_wall.id).name == the_wall.name
    assert walls_read(ui)[the_wall.id]["client_id"] is None


def test_the_dialog_has_one_filled_act_and_it_is_show_it_there(ui, services, the_wall, hall, a_theme_to_hang):
    """One filled act per region (`design-direction.md` § Buttons; audit 2026-11-19, finding 7).

    Every section is drawn: a hung wall, so its rotation, shapes and mat are
    offered, and a Player with a free label panel, so *Caption it* is too.
    Five were filled; *Show it there* is the one, and every other commit is quiet.
    """
    services.display.activate_theme(a_theme_to_hang.id, wall_id=the_wall.id)
    # A panel recorded for Hall Pi and captioning nothing, so *Caption it* is offered.
    labelled = services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    services.clients.remove_label(the_wall.id, label_id=labelled.label.id)
    dialog = open_edit(ui, the_wall.name)
    expect(dialog.get_by_role("button", name=f"Caption {the_wall.name} with this label panel")).to_be_visible()

    filled = dialog.locator("button.action:not(.quiet)")
    expect(filled).to_have_count(1)
    expect(filled).to_have_accessible_name(f"Show {the_wall.name} there")
    for name in (
        f"Rename {the_wall.name}",
        f"Caption {the_wall.name} with this label panel",
        f"Set the rotation on {the_wall.name}",
        f"Set the shapes on {the_wall.name}",
        f"Set the mat on {the_wall.name}",
    ):
        expect(dialog.get_by_role("button", name=name)).to_have_class(re.compile(r"(^|\s)quiet(\s|$)"))


def test_close_names_the_sections_it_would_leave_unset(ui, services, the_wall, hall, a_theme_to_hang):
    """Audit 2026-11-19, finding 7: edit two sections, set one, and Close could not say which was saved.

    The line above *Close* names each section whose fields differ from what the
    server last took, in the dialog's order; setting one takes it off the line,
    and putting a field back takes its section off too.
    """
    services.display.activate_theme(a_theme_to_hang.id, wall_id=the_wall.id)
    dialog = open_edit(ui, the_wall.name)
    unsaved = dialog.locator("p.wall-unsaved")
    expect(unsaved).to_be_hidden()

    dialog.get_by_label(f"Mat on {the_wall.name}", exact=True).select_option("none")
    dialog.get_by_label("Name", exact=True).fill("The hall")
    expect(unsaved).to_have_text("Not set yet: Name and Mat. Close leaves them as they were.")
    close = dialog.get_by_role("button", name="Close")
    expect(close).to_have_attribute(
        "aria-describedby", unsaved.get_attribute("id")
    )  # one-shot: the id the line must be described by

    dialog.get_by_role("button", name=f"Set the mat on {the_wall.name}").click()
    expect(unsaved).to_have_text("Not set yet: Name. Close leaves it as it was.")
    assert services.display.get_wall(the_wall.id).mat_mode == "none"

    dialog.get_by_label("Name", exact=True).fill(the_wall.name)
    expect(unsaved).to_be_hidden()


@pytest.fixture
def a_theme_to_hang(services, work_with_an_image, service, settings, decodable_jpeg):
    """A theme holding one work that really reaches a wall."""
    artwork = work_with_an_image(title="Nighthawks")
    service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    presented = f"presentation/{artwork.id}.jpg"
    decodable_jpeg(settings.art_root / presented, width=400, height=300)
    service.record_rendition(
        artwork_id=artwork.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=presented
    )
    theme = services.display.add_theme(name="Winter")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=artwork.id)
    return theme


def test_a_wall_added_here_can_be_put_on_a_screen_and_hung_and_its_feed_is_published(
    ui, services, server_url, hall, a_theme_to_hang
):
    """Add wall…, then its Edit… and its Hanging picker: the new wall's feed, read as
    its Player reads it, carries the work hung. The Player itself is arrt-player's,
    walked on the real wall by the plan's operator walk."""
    ui.open("#walls")
    ui.page.get_by_role("button", name="Add wall…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.get_by_label("Name", exact=True).fill("Study")
    dialog.get_by_role("button", name="Add wall").click()
    card(ui, "Study").wait_for()
    study = next(view.wall for view in services.display.survey_walls() if view.wall.name == "Study")

    dialog = open_edit(ui, "Study")
    dialog.get_by_label("Player for Study", exact=True).select_option(hall.id)
    dialog.get_by_label("Screen", exact=True).select_option(label="HDMI 1")
    dialog.get_by_role("button", name="Show Study there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    ui.page.select_option(f"select#hang-{study.id}", a_theme_to_hang.id)
    ui.page.locator("dialog.confirm[open]").get_by_role("button", name="Hang").click()
    card(ui, "Study").locator(".wall-hanging dt:text-is('Changes')").wait_for()

    assert walls_read(ui)[study.id]["client_id"] == hall.id
    assert services.display.hanging_on(study.id).id == a_theme_to_hang.id
    token = services.access.issue(hall.id).token
    answer = httpx.get(f"{server_url}/walls/{study.id}/manifest/v2", headers={"Authorization": f"Bearer {token}"})
    assert answer.status_code == 200
    assert [work["label"]["title"] for work in answer.json()["works"].values()] == ["Nighthawks"]


def test_adding_a_wall_with_a_taken_name_is_refused_in_the_dialog(ui, services, the_wall):
    ui.open("#walls")
    ui.page.get_by_role("button", name="Add wall…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.get_by_label("Name", exact=True).fill(the_wall.name)
    dialog.get_by_role("button", name="Add wall").click()

    failure = dialog.locator(".act-failure")
    failure.wait_for()
    expect(failure).to_contain_text(f"Another wall is already called '{the_wall.name}'.", use_inner_text=True)
    assert len(services.display.survey_walls()) == 1


# -- read when pressed ---------------------------------------------------------
#
# Edit… reads the wall, its Players and its feed when pressed. The tests below
# hold that read open with a route the test releases itself, so what happens
# while it is out is asked about at a moment the test chooses.


def holding(ui, pattern):
    """Hold requests matching `pattern`. Answers (held, stop, release).

    `stop()` lets later requests through; `release()` also sends on the held ones.
    Each first waits until a request has been held, for at least five seconds, and
    raises by name if none was.
    """
    held = []
    holding_now = [True]

    def hold(route):
        if holding_now[0]:
            held.append(route)
        else:
            route.continue_()

    def until_held():
        # A click returns once it is dispatched, before its fetch reaches the route
        # handler, so turning holding off at once can let the very request a test
        # meant to hold straight through. The sync API runs `hold` only while this
        # side is inside a Playwright call, so the wait is a short one, repeated.
        for _ in range(500):  # 500 waits of 10 ms, plus each round trip: at least five seconds
            if held:
                return
            ui.page.wait_for_timeout(
                10
            )  # sleep: paces a poll of `held`, which only fills while Playwright runs the route handler
        raise AssertionError(f"no {pattern} request was held")

    def stop():
        until_held()
        holding_now[0] = False

    def release():
        until_held()
        holding_now[0] = False
        for route in held:
            route.continue_()

    ui.page.route(pattern, hold)
    return held, stop, release


def test_a_second_press_while_the_read_is_out_opens_one_dialog(ui, the_wall):
    ui.open("#walls")
    held, _, release = holding(ui, "**/api/walls")
    edit = card(ui, the_wall.name).get_by_role("button", name=f"Edit {the_wall.name}…")
    edit.click()
    edit.click()
    release()

    ui.page.locator("dialog.panel-dialog").wait_for()
    assert len(held) == 1
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(1)


def test_a_read_that_returns_after_leaving_walls_opens_nothing_on_the_next_page(ui, the_wall):
    ui.open("#walls")
    held, stop, release = holding(ui, "**/api/walls")
    card(ui, the_wall.name).get_by_role("button", name=f"Edit {the_wall.name}…").click()
    stop()
    ui.page.evaluate("() => { location.hash = '#clients'; }")
    ui.page.wait_for_selector("#view h1:text-is('Players')")
    assert len(held) == 1
    with ui.page.expect_response("**/api/walls"):
        release()
    # The read's other half, the Players, answers after the walls; past it the
    # handler has nothing left to wait on.
    ui.page.wait_for_load_state("networkidle")

    # Still on Players once the late read has been answered: the page this read
    # came back to, which is the one it must not open a dialog on.
    expect(ui.page.locator("#view h1")).to_have_text("Players", use_inner_text=True)
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)


def test_a_feed_that_cannot_be_read_is_said_in_the_dialog(ui, services, the_wall, a_theme_to_hang):
    services.display.activate_theme(a_theme_to_hang.id, wall_id=the_wall.id)
    ui.open("#walls")
    ui.page.route(
        "**/api/manifest?*",
        lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "the feed is unreadable"}'),
    )
    card(ui, the_wall.name).get_by_role("button", name=f"Edit {the_wall.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()

    expect(dialog.locator(".panel h3")).to_have_text(["Name", "Where it shows", "Label panel", "Delete"])
    said = dialog.locator(".wall-feed-unread")
    expect(said).to_have_text(
        re.compile("^" + re.escape("Its rotation, shapes and mat cannot be set here: the wall's feed could not be read")),
        use_inner_text=True,
    )
    expect(said).to_contain_text("the feed is unreadable", use_inner_text=True)


def test_a_wall_gone_since_the_page_painted_is_said_beside_its_edit_and_opens_nothing(ui, services, the_wall):
    study = services.display.add_wall(name="Study")
    ui.open("#walls")
    # Painted before it is deleted, as the name says: `open` returns once the
    # client has started, not once Walls has read its walls, and a read that
    # lands after the delete paints no Study to press Edit on.
    card(ui, "Study").wait_for()
    services.display.delete_wall(study.id)

    edit = card(ui, "Study").get_by_role("button", name="Edit Study…")
    edit.click()

    said = card(ui, "Study").get_by_text("Couldn't open Study's settings")
    said.wait_for()
    expect(said).to_contain_text("it is no longer recorded; reload the page", use_inner_text=True)
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)


def test_choose_its_player_and_edit_pressed_together_open_one_dialog(ui, the_wall):
    ui.open("#walls")
    held, _, release = holding(ui, "**/api/walls")
    head = card(ui, the_wall.name)
    head.get_by_role("button", name=f"Choose the Player for {the_wall.name}…").click()
    head.get_by_role("button", name=f"Edit {the_wall.name}…").click()
    release()

    ui.page.locator("dialog.panel-dialog").wait_for()
    assert len(held) == 1
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(1)


def test_a_read_that_returns_after_leaving_and_coming_back_opens_nothing(ui, the_wall):
    ui.open("#walls")
    held, stop, release = holding(ui, "**/api/walls")
    card(ui, the_wall.name).get_by_role("button", name=f"Edit {the_wall.name}…").click()
    stop()
    ui.page.evaluate("() => { location.hash = '#clients'; }")
    ui.page.wait_for_selector("#view h1:text-is('Players')")
    ui.page.evaluate("() => { location.hash = '#walls'; }")
    ui.page.wait_for_selector("section.wall .wall-title")
    assert len(held) == 1
    with ui.page.expect_response("**/api/walls"):
        release()
    ui.page.wait_for_load_state("networkidle")

    # Walls painted again once the late read has been answered: the page this read
    # came back to, which is the one it must not open a dialog on.
    expect(ui.page.locator("section.wall .wall-title")).to_have_text(the_wall.name, use_inner_text=True)
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)


# -- Delete… -------------------------------------------------------------------


def _confirm(ui):
    dialog = ui.page.locator("dialog.confirm[open]")
    dialog.wait_for()
    return dialog


def test_delete_names_what_goes_and_what_stays_and_the_wall_is_gone(ui, services, settings, the_wall, hall, a_theme_to_hang):
    study = services.display.add_wall(name="Study")
    services.display.activate_theme(a_theme_to_hang.id, wall_id=study.id)
    services.clients.record_heartbeat(
        hall.id,
        REPORT
        | {
            "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}],
        },
    )
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(study.id, client_id=hall.id, output="epd-0")

    dialog = open_edit(ui, "Study")
    expect(dialog.locator(".panel h3").last).to_have_text("Delete")
    dialog.get_by_role("button", name="Delete Study…").click()
    confirm = _confirm(ui)

    # Read at the moment the question stands: the claim is that the Edit… dialog is
    # already closed when it is asked, and a retrying count would pass a dialog
    # that closed a moment after.
    assert (
        ui.page.locator("dialog.panel-dialog").count() == 0
    ), "asked with the Edit… dialog closed"  # one-shot: simultaneity, closed as the question opens
    expect(confirm.locator(".confirm-title")).to_have_text("Delete Study?", use_inner_text=True)
    expect(confirm.locator(".confirm-consequence")).to_have_text(
        "It hangs Winter, which stays in your themes. Hall Pi stops showing it. "
        "Its label panel stops captioning. Its history stays. The wall cannot be brought back.",
        use_inner_text=True,
    )
    confirm.get_by_role("button", name="Delete Study").click()
    card(ui, "Study").wait_for(state="detached")

    assert set(walls_read(ui)) == {the_wall.id}
    assert services.display.get_theme(a_theme_to_hang.id).name == "Winter"
    players = ui.page.evaluate("() => fetch('/api/clients').then((r) => r.json())")["clients"]
    assert [label["wall_id"] for label in players[0]["label_outputs"]] == [None], "the panel stays, captioning nothing"
    expect(card(ui, the_wall.name)).to_have_count(1)


def test_cancel_deletes_nothing(ui, services, the_wall):
    services.display.add_wall(name="Study")
    dialog = open_edit(ui, "Study")
    dialog.get_by_role("button", name="Delete Study…").click()
    confirm = _confirm(ui)
    expect(confirm.locator(".confirm-consequence")).to_have_text(
        "Its history stays. The wall cannot be brought back.", use_inner_text=True
    )
    confirm.get_by_role("button", name="Cancel").click()
    confirm.wait_for(state="detached")

    assert {wall["name"] for wall in walls_read(ui).values()} == {the_wall.name, "Study"}


def test_the_last_wall_deleted_leaves_a_page_that_offers_add_wall_and_it_works(ui, services, the_wall):
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_role("button", name=f"Delete {the_wall.name}…").click()
    _confirm(ui).get_by_role("button", name=f"Delete {the_wall.name}").click()

    empty = ui.page.locator("#view .empty")
    empty.wait_for()
    # Its two sentences and nothing else: each on a line of its own, with only
    # blank lines around and between them (the read dropped the empty lines).
    sentences = ["No wall is recorded, so there is nowhere to hang anything.", "Add a wall to give art a place to hang."]
    expect(empty).to_have_text(
        re.compile(r"^\n*" + r"\n+".join(re.escape(line) for line in sentences) + r"\n*$"), use_inner_text=True
    )
    assert walls_read(ui) == {}

    ui.page.get_by_role("button", name="Add wall…").click()
    added = ui.page.locator("dialog.panel-dialog")
    added.get_by_label("Name", exact=True).fill("Study")
    added.get_by_role("button", name="Add wall").click()
    card(ui, "Study").wait_for()
    assert [wall["name"] for wall in walls_read(ui).values()] == ["Study"]


def test_delete_says_a_selection_goes_and_counts_label_panels(ui, services, the_wall, hall, work_with_an_image):
    study = services.display.add_wall(name="Study")
    services.display.hang_selection([work_with_an_image(title="Golconda").id], wall_id=study.id)
    panels = [{"name": f"epd-{n}", "kind": "epaper", "connected": True, "size": [800, 480]} for n in (0, 1)]
    services.clients.record_heartbeat(
        hall.id, REPORT | {"reported_at": datetime.now(UTC).isoformat(timespec="seconds"), "label_outputs": panels}
    )
    for panel in panels:
        services.clients.add_label(study.id, client_id=hall.id, output=panel["name"])

    dialog = open_edit(ui, "Study")
    dialog.get_by_role("button", name="Delete Study…").click()

    expect(_confirm(ui).locator(".confirm-consequence")).to_have_text(
        "It hangs a selection, which goes once no wall hangs it. Its 2 label panels stop captioning. "
        "Its history stays. The wall cannot be brought back.",
        use_inner_text=True,
    )


def test_delete_names_no_player_it_could_not_read(ui, services, the_wall, hall):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.open("#walls")
    ui.page.route(
        "**/api/clients", lambda route: route.fulfill(status=500, content_type="application/json", body='{"error": "down"}')
    )

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_role("button", name=f"Delete {the_wall.name}…").click()

    expect(_confirm(ui).locator(".confirm-consequence")).to_have_text(
        "Its Player stops showing it. Its history stays. The wall cannot be brought back.", use_inner_text=True
    )
