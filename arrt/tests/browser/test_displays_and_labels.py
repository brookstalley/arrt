"""Displays and label outputs on Settings › Clients and Walls, in a real browser.

A client reports its screens and its label panels; the server keeps each as a
record, and a curator maps a panel to any wall from the client's panel on
Settings › Clients, where walls are assigned too. Walls says which labels caption
each wall, and says so of a display two clients report, which neither shows.

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


def panel(ui, client):
    return ui.page.locator(f"section.client[data-client='{client.id}']")


def open_clients(ui):
    ui.open("#clients")
    ui.page.wait_for_selector("section.client .client-labels")


def wall_card(ui, wall):
    return ui.page.locator(f"section.wall[data-wall='{wall.id}']")


def open_walls(ui):
    ui.open("#walls")
    ui.page.wait_for_selector("section.wall .wall-controls")


def caption(ui, client, wall):
    labels = panel(ui, client).locator(".client-labels")
    labels.get_by_label(f"Wall for {client.name}'s label").select_option(label=wall.name)
    labels.get_by_role("button", name=f"Caption a wall with {client.name}'s label").click()
    # The sentence itself, not any status line: a Stop just before leaves one.
    ui.page.wait_for_selector(f"section.client[data-client='{client.id}'] [data-said]:has-text('now captions {wall.name}')")


def test_the_panel_is_listed_with_its_kind_and_state_and_captions_no_wall(ui, services, hall, three_walls):
    open_clients(ui)

    labels = panel(ui, hall).locator(".client-labels")
    headers = labels.locator("thead th").all_text_contents()
    assert headers == ["Label output", "Kind", "Panel", "Size", "Captions"]
    [row] = labels.locator("tbody tr").all_inner_texts()
    assert row.split("\t") == ["epd-0", "E-paper panel", "● answering", "800 × 480", "No wall"]
    # The displays stay in the outputs table, the Frame among them.
    outputs = panel(ui, hall).locator(".client-outputs tbody tr").all_inner_texts()
    assert [each.split("\t")[0] for each in outputs] == ["hdmi-a-1", "hdmi-a-2", "frame"]
    assert "Samsung Frame" in outputs[2]


def test_the_panel_captions_each_display_in_turn(ui, services, hall, three_walls):
    """Mapped from Settings › Clients, followed on Walls, moved by the page alone: never an edit on the host."""
    previous = None
    for wall in three_walls:
        open_clients(ui)
        if previous is not None:
            panel(ui, hall).get_by_role("button", name=f"Stop epd-0 on Hall Pi captioning {previous.name}").click()
            ui.page.wait_for_selector(f"section.client[data-client='{hall.id}'] [data-said]")
            assert f"epd-0 no longer captions {previous.name}." in panel(ui, hall).inner_text()
        caption(ui, hall, wall)

        assert f"epd-0 on Hall Pi now captions {wall.name}." in panel(ui, hall).inner_text()
        assert panel(ui, hall).locator(".client-labels tbody tr").inner_text().split("\t")[-1] == wall.name
        open_walls(ui)
        line = wall_card(ui, wall).locator(".wall-labels")
        assert line.inner_text().startswith("Captioned by epd-0 on Hall Pi.")
        for other in three_walls:
            if other is not wall:
                assert wall_card(ui, other).locator(".wall-labels").count() == 0
        previous = wall


def test_a_label_already_captioning_a_wall_is_refused_for_a_second(ui, services, hall, three_walls):
    living, study, _ = three_walls
    services.clients.add_label(living.id, client_id=hall.id, output="epd-0")
    open_clients(ui)

    option = panel(ui, hall).get_by_label("Label output of Hall Pi").locator("option").inner_text()
    assert option == f"epd-0, captions {living.name}"
    caption_attempt = panel(ui, hall).locator(".client-labels")
    caption_attempt.get_by_label("Wall for Hall Pi's label").select_option(label=study.name)
    caption_attempt.get_by_role("button", name="Caption a wall with Hall Pi's label").click()

    # Refused beside the control the curator pressed (`core/acting.js`), and nothing moved.
    failure = caption_attempt.locator(".act-failure")
    failure.wait_for()
    assert failure.inner_text().startswith(f"Couldn't caption {study.name} with epd-0 on Hall Pi")
    assert "Nothing was changed." in failure.inner_text()
    [label] = services.clients.get_client_view(hall.id).label_outputs
    assert label.wall_id == living.id
    open_walls(ui)
    assert wall_card(ui, living).locator(".wall-labels").count() == 1
    assert wall_card(ui, study).locator(".wall-labels").count() == 0


def test_a_client_with_no_panel_says_it_has_nothing_to_caption_with(ui, services, hall):
    report(services, hall, {"outputs": EVERYTHING["outputs"][:1]})
    open_clients(ui)

    text = panel(ui, hall).locator(".client-labels").inner_text()
    assert "Hall Pi reported no label output, so it has nothing to caption a wall with." in text
    assert panel(ui, hall).locator(".client-labels table").count() == 0


def test_a_frame_two_clients_report_is_a_fault_both_pages_name(ui, services, hall, three_walls):
    living, *_ = three_walls
    study_mac = services.clients.add_client(name="Study Mac")
    report(services, study_mac, {"outputs": [EVERYTHING["outputs"][2]]})

    open_clients(ui)
    for client in (hall, study_mac):
        fault = panel(ui, client).locator(".client-fault")
        assert fault.count() == 1
        assert "Hall Pi and Study Mac both report" in fault.inner_text()
        assert fault.inner_text().startswith("▲ ")

    open_walls(ui)
    line = wall_card(ui, living).locator(".wall-client")
    assert "Hall Pi and Study Mac both report" in line.inner_text()
    # Neither shows it, whatever the wall's record still names.
    assert "Shown by" not in line.inner_text()
    assert "Assigned to" not in line.inner_text()
    assert wall_card(ui, living).locator(".wall-now").get_attribute("data-state") in (None, "unassigned")
