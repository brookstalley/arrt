"""Displays and label panels on Settings › Players and Walls, in a real browser.

A Player reports its screens and its label panels; the server keeps each as a
record. A curator captions a wall with a panel in that wall's *Edit…* on Walls,
and Settings › Players says which wall each panel captions (ruling 7 of
2026-10-27: until then Clients mapped panels too). Both pages say so of a
display two Players report, which neither shows.

**Reports are recorded the way a client's arrive**, through the service the
heartbeat route calls, so the records the page reads are the ones a running
client would have left.
"""

import re
from datetime import UTC, datetime

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

FRAME_ID = "uuid:00000000-0000-4000-8000-000000000001"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


#: Two HDMI outputs, a Frame and one panel: every kind of surface a client has.
EVERYTHING = {
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": True, "screen": [1280, 1024]},
        {"name": "frame", "kind": "frame", "connected": True, "screen": [3840, 2160], "identity": FRAME_ID},
    ],
    "label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}],
}


def report(services, client, document=EVERYTHING):
    services.clients.record_heartbeat(client.id, {"reported_at": _now(), **document})


@pytest.fixture
def hall(services):
    return services.clients.add_client(name="Hall Pi")


@pytest.fixture
def three_walls(services, hall):
    """One wall on each of the client's three displays."""
    living = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="Study")
    landing = services.display.add_wall(name="Landing")
    report(services, hall)
    for wall, output in ((living, "frame"), (study, "hdmi-a-1"), (landing, "hdmi-a-2")):
        services.clients.assign_wall(wall.id, client_id=hall.id, output=output)
    return living, study, landing


def row(ui, client):
    return ui.page.locator(f"tr[data-player='{client.id}']")


def cell(ui, client, column):
    return row(ui, client).locator(f"td[data-label='{column}']")


def open_players(ui):
    ui.open("#clients")
    ui.page.wait_for_selector("#view tr[data-player]")


def wall_card(ui, wall):
    return ui.page.locator(f"section.wall[data-wall='{wall.id}']")


def open_walls(ui):
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")


def open_edit(ui, wall):
    wall_card(ui, wall).get_by_role("button", name=f"Edit {wall.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()
    return dialog


def test_the_panel_is_listed_with_its_state_and_captions_no_wall(ui, services, hall, three_walls):
    open_players(ui)

    # The state and the wall it captions, two parts split by one line break (the
    # read split on it, and a tab as well).
    expect(cell(ui, hall, "Label panel")).to_have_text(re.compile(r"^● answering, 800 × 480[\n\t]No wall$"), use_inner_text=True)
    # The displays stay among the screens, the Frame named as one: each item is
    # its name, then either nothing or " · " and more (the read kept what came
    # before the first " · ").
    named = ["HDMI 1, 1920 × 1080", "HDMI 2, 1280 × 1024", "Samsung Frame, 3840 × 2160"]
    expect(cell(ui, hall, "Screens").locator("li")).to_have_text(
        [re.compile("^" + re.escape(each) + "(?: · |$)") for each in named], use_inner_text=True
    )


def test_the_panel_captions_each_display_in_turn(ui, services, hall, three_walls):
    """Captioned from each wall's Edit…, followed on Players, moved by the page alone: never an edit on the Player."""
    previous = None
    for wall in three_walls:
        open_walls(ui)
        if previous is not None:
            stale = wall_card(ui, wall).element_handle()
            dialog = open_edit(ui, previous)
            dialog.get_by_role("button", name=f"Stop the label panel on Hall Pi captioning {previous.name}").click()
            dialog.wait_for(state="detached")
            # The cards repaint once the dialog closes; waiting for it means the
            # Edit… pressed next is on the new card, not one about to be replaced.
            stale.wait_for_element_state("hidden")
        dialog = open_edit(ui, wall)
        dialog.get_by_label(f"Caption {wall.name} with", exact=True).select_option(label="the label panel on Hall Pi")
        dialog.get_by_role("button", name=f"Caption {wall.name} with this label panel").click()
        dialog.wait_for(state="detached")

        open_players(ui)
        expect(cell(ui, hall, "Label panel")).to_have_text(
            re.compile(re.escape(f"Captions {wall.name}") + "$"), use_inner_text=True
        )
        for each in three_walls:
            dialog = open_walls(ui) or open_edit(ui, each)
            if each is wall:
                expect(dialog.locator(".wall-labels")).to_have_text(
                    re.compile("^" + re.escape("Captioned by a label on Hall Pi.")), use_inner_text=True
                )
            else:
                # The dialog's Label panel section first: it is drawn with the rest
                # of the dialog, so the absence is not met by a dialog on its way.
                expect(dialog.get_by_role("heading", name="Label panel")).to_be_visible()
                expect(dialog.locator(".wall-labels")).to_have_count(0)
            ui.page.keyboard.press("Escape")
            dialog.wait_for(state="detached")
        previous = wall


def test_edit_opened_before_the_page_repaints_offers_what_is_true_now(ui, services, hall, three_walls):
    """*Edit…* reads the wall and its Players when pressed, not from the page's last paint.

    The panel is stopped with the request *Stop captioning* sends, from the page
    but outside any dialog, so no repaint follows it: this page does not poll, and
    a dialog built from the paint before the stop would still see the panel
    captioning Living and offer it to no other wall.
    """
    living, study, _ = three_walls
    label = services.clients.add_label(living.id, client_id=hall.id, output="epd-0").label
    open_walls(ui)
    stopped = ui.page.evaluate(
        "(path) => fetch(path, { method: 'DELETE' }).then((r) => r.status)",
        f"/api/walls/{living.id}/labels/{label.id}",
    )
    assert stopped == 200

    dialog = open_edit(ui, study)
    offered = dialog.get_by_label(f"Caption {study.name} with", exact=True).locator("option")
    # One option whose whole text is that, wherever it stands in the list: a
    # subsequence of one, which is how a list holds an item.
    expect(offered).to_contain_text([re.compile("^the label panel on Hall Pi$")], use_inner_text=True)
    ui.page.keyboard.press("Escape")
    dialog.wait_for(state="detached")

    # And the wall that lost it no longer says it is captioned.
    dialog = open_edit(ui, living)
    expect(dialog.get_by_role("heading", name="Label panel")).to_be_visible()
    expect(dialog.locator(".wall-labels")).to_have_count(0)


def test_a_player_with_no_panel_says_it_reported_none(ui, services, hall):
    report(services, hall, {"outputs": EVERYTHING["outputs"][:1]})
    open_players(ui)

    expect(cell(ui, hall, "Label panel")).to_have_text("None reported.", use_inner_text=True)
    expect(cell(ui, hall, "Label panel").locator("li")).to_have_count(0)


def test_a_frame_two_players_report_is_a_fault_both_pages_name(ui, services, hall, three_walls):
    living, *_ = three_walls
    study_mac = services.clients.add_client(name="Study Mac")
    report(services, study_mac, {"outputs": [EVERYTHING["outputs"][2]]})

    open_players(ui)
    # Said once under the table: the server's sentence names both Players.
    fault = ui.page.locator("#view .player-fault")
    expect(fault).to_have_count(1)
    expect(fault).to_contain_text("Hall Pi and Study Mac both report", use_inner_text=True)
    expect(fault).to_contain_text("configured on one Player", use_inner_text=True)
    expect(fault).to_have_text(re.compile("^▲ "), use_inner_text=True)

    open_walls(ui)
    # A fault is a problem, so the card says it (the page rules of 2026-10-27:
    # where a wall shows is said on the card only when it is one), and sends
    # the curator to the Players it names.
    line = wall_card(ui, living).locator(".wall-problem")
    expect(line).to_contain_text("Hall Pi and Study Mac both report", use_inner_text=True)
    expect(line.get_by_role("link", name="See Settings › Players")).to_have_attribute("href", "#clients")
    # Neither shows it, whatever the wall's record still names.
    expect(line).not_to_contain_text("Shown by", use_inner_text=True)
    expect(line).not_to_contain_text("Assigned to", use_inner_text=True)
    # Absent, or "unassigned": a state that is anything else is refused, and an
    # attribute that is not there passes, as `None` did.
    expect(wall_card(ui, living).locator(".wall-now")).not_to_have_attribute("data-state", re.compile(r"^(?!unassigned$)"))
