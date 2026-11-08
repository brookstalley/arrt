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

from datetime import UTC, datetime

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

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

    assert cell(ui, hall, "Label panel").inner_text().replace("\n", "\t").split("\t") == ["● answering, 800 × 480", "No wall"]
    # The displays stay among the screens, the Frame named as one.
    screens = cell(ui, hall, "Screens").locator("li").all_inner_texts()
    named = [each.split(" · ")[0] for each in screens]
    assert named == ["HDMI 1, 1920 × 1080", "HDMI 2, 1280 × 1024", "Samsung Frame, 3840 × 2160"]


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
        assert cell(ui, hall, "Label panel").inner_text().endswith(f"Captions {wall.name}")
        for each in three_walls:
            dialog = open_walls(ui) or open_edit(ui, each)
            if each is wall:
                assert dialog.locator(".wall-labels").inner_text().startswith("Captioned by a label on Hall Pi.")
            else:
                assert dialog.locator(".wall-labels").count() == 0
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
    offered = dialog.get_by_label(f"Caption {study.name} with", exact=True).locator("option").all_inner_texts()
    assert "the label panel on Hall Pi" in offered
    ui.page.keyboard.press("Escape")
    dialog.wait_for(state="detached")

    # And the wall that lost it no longer says it is captioned.
    dialog = open_edit(ui, living)
    assert dialog.locator(".wall-labels").count() == 0


def test_a_player_with_no_panel_says_it_reported_none(ui, services, hall):
    report(services, hall, {"outputs": EVERYTHING["outputs"][:1]})
    open_players(ui)

    assert cell(ui, hall, "Label panel").inner_text() == "None reported."
    assert cell(ui, hall, "Label panel").locator("li").count() == 0


def test_a_frame_two_players_report_is_a_fault_both_pages_name(ui, services, hall, three_walls):
    living, *_ = three_walls
    study_mac = services.clients.add_client(name="Study Mac")
    report(services, study_mac, {"outputs": [EVERYTHING["outputs"][2]]})

    open_players(ui)
    # Said once under the table: the server's sentence names both Players.
    fault = ui.page.locator("#view .player-fault")
    assert fault.count() == 1
    assert "Hall Pi and Study Mac both report" in fault.inner_text()
    assert "configured on one Player" in fault.inner_text()
    assert fault.inner_text().startswith("▲ ")

    open_walls(ui)
    # A fault is a problem, so the card says it (the page rules of 2026-10-27:
    # where a wall shows is said on the card only when it is one), and sends
    # the curator to the Players it names.
    line = wall_card(ui, living).locator(".wall-problem")
    assert "Hall Pi and Study Mac both report" in line.inner_text()
    assert line.get_by_role("link", name="See Settings › Players").get_attribute("href") == "#clients"
    # Neither shows it, whatever the wall's record still names.
    assert "Shown by" not in line.inner_text()
    assert "Assigned to" not in line.inner_text()
    assert wall_card(ui, living).locator(".wall-now").get_attribute("data-state") in (None, "unassigned")
