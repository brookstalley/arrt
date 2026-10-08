"""Settings › Clients, in a real browser against a real server.

`clients.md` makes a client — an installed Player — something the server knows,
with one token, driving the walls assigned to it on its outputs. This page is
where a curator keeps them, as Radarr keeps its Download Clients.

**The token is the part worth the most care.** It exists outside its host only in
the answer that issued it, so the page must show it once, plainly, with what to
do with it — and must not show it again: not after a reload, and not on a first
paint of a client that already has one. Both halves are asserted, and each act
that issues one is checked against the Player's own route, because a token the
page displayed and the server would refuse is the failure a curator meets at the
host, a room away from this screen.

**What a client reported is seeded the way a client leaves it**: the heartbeat
file the server reads, at the path the server derives.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.programming.client_heartbeat import client_heartbeat_path_in

#: Stamped now, so the report is young enough to speak for the outputs: one
#: older than three heartbeats says nothing about now, and has its own test.
TWO_OUTPUTS = {
    "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


def report(settings, client, document=TWO_OUTPUTS):
    """What a running client's heartbeat leaves under the art root."""
    client_heartbeat_path_in(settings.art_root, client.id).write_text(json.dumps(document), encoding="utf-8")


def admitted(server_url, token) -> int:
    """The Player route's answer to this token: 200 for a client's current one, 401 otherwise."""
    return httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {token}"}).status_code


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


@pytest.fixture
def study(services):
    return services.display.add_wall(name="Study")


@pytest.fixture
def hall(services):
    return services.clients.add_client(name="Hall Pi")


def panel(ui, client):
    return ui.page.locator(f"section.client[data-client='{client.id}']")


def open_clients(ui):
    ui.open("#clients")
    ui.page.wait_for_selector("#view h1:has-text('Clients')")


# -- the page --------------------------------------------------------------------


def test_the_page_is_under_settings_and_answers_its_own_path(ui, seeded_service):
    """A bookmark is a path as well as a fragment; `pages.py` has to serve it."""
    ui.page.goto(f"{ui.base_url}/clients")
    ui.page.wait_for_selector("#view h1:has-text('Clients')")

    current = ui.page.locator("nav.sidebar a[data-view='clients'][aria-current='page']")
    assert current.inner_text() == "Clients"
    section = ui.page.locator("nav.sidebar li.section", has=ui.page.locator("a[data-view='clients']"))
    assert section.locator("a.section-link .label").inner_text() == "Settings"


def test_with_no_client_the_page_says_so_and_offers_the_add(ui, seeded_service):
    open_clients(ui)

    assert "No client is recorded yet." in ui.text()
    assert ui.page.get_by_label("Name of the new client").is_visible()
    assert ui.page.get_by_role("button", name="Add the client").is_visible()
    assert ui.page.locator("section.client").count() == 0


# -- the token, once ---------------------------------------------------------------


def test_adding_a_client_shows_its_token_once_with_what_to_do_with_it(ui, services, server_url):
    open_clients(ui)

    ui.page.get_by_label("Name of the new client").fill("  Hall Pi  ")
    ui.page.get_by_role("button", name="Add the client").click()
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    token = field.input_value()
    assert field.get_attribute("readonly") is not None
    assert ui.page.evaluate("() => document.activeElement.id") == "client-token"
    note = ui.page.locator(".token-once").inner_text()
    assert "the only time it is shown" in note
    assert "CLIENT_TOKEN" in note
    assert "SERVER_URL" in note
    assert server_url in note, "the address the host needs is not stated"
    [client] = services.clients.list_clients()
    assert client.client.name == "Hall Pi"
    assert admitted(server_url, token) == 200

    ui.page.reload()
    ui.page.wait_for_selector("section.client")
    assert ui.page.locator("#client-token").count() == 0
    assert token not in ui.page.content()
    assert "Issued " in panel(ui, client.client).inner_text()


def test_a_client_that_already_has_a_token_is_never_shown_one(ui, services, hall, server_url):
    token = services.access.issue(hall.id).token
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    assert ui.page.locator("#client-token").count() == 0
    assert token not in ui.page.content()
    assert ui.page.get_by_role("button", name="Rotate Hall Pi's token").is_visible()
    assert ui.page.get_by_role("button", name="Issue a token for Hall Pi").count() == 0


def test_a_client_with_no_token_says_so_and_issues_one_without_asking(ui, services, hall, server_url):
    """Issuing a first token refuses no Player, so there is nothing to confirm."""
    open_clients(ui)
    ui.page.wait_for_selector("section.client")
    assert "None issued yet, so it is admitted to nothing until one is." in panel(ui, hall).inner_text()

    ui.page.get_by_role("button", name="Issue a token for Hall Pi").click()
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    assert ui.page.locator("dialog.confirm").count() == 0
    assert admitted(server_url, field.input_value()) == 200


def test_declining_a_rotation_leaves_the_old_token_working(ui, services, hall, server_url):
    old = services.access.issue(hall.id).token
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_role("button", name="Rotate Hall Pi's token").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert ui.page.inner_text("dialog.confirm .confirm-title") == "Rotate Hall Pi's token?"
    assert "Hall Pi's Player is refused" in ui.page.inner_text("dialog.confirm .confirm-consequence")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert ui.page.locator("#client-token").count() == 0
    assert admitted(server_url, old) == 200


def test_confirming_a_rotation_shows_the_new_token_and_refuses_the_old(ui, services, hall, server_url):
    old = services.access.issue(hall.id).token
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_role("button", name="Rotate Hall Pi's token").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Rotate the token')")
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    new = field.input_value()
    assert new != old
    assert admitted(server_url, old) == 401
    assert admitted(server_url, new) == 200


# -- what the client reported ----------------------------------------------------------


def test_a_client_that_has_not_reported_says_so_in_words(ui, hall):
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    text = panel(ui, hall).inner_text()
    assert "It has not reported its outputs yet." in text
    assert "Hall Pi has not reported its outputs yet, so none can be listed." in text
    assert "Hall Pi has no wall assigned yet." in text


def test_a_report_is_listed_output_by_output_with_its_age(ui, settings, hall):
    report(settings, hall)
    open_clients(ui)
    ui.page.wait_for_selector("section.client table")

    rows = panel(ui, hall).locator("tbody tr").all_inner_texts()
    assert [row.split("\t")[0] for row in rows] == ["hdmi-a-1", "hdmi-a-2"]
    assert "● detected" in rows[0]
    assert "1920 × 1080" in rows[0]
    assert "○ none detected (off or unplugged)" in rows[1]
    assert "size unknown" in rows[1]
    # "connected" read as a cable fault when the usual cause is a television
    # switched off, which drops its hotplug line exactly as an unplugged one does.
    assert "connected" not in panel(ui, hall).locator("table").inner_text()
    # Text content, not inner text: the stylesheet sets headers in capitals.
    headers = panel(ui, hall).locator("thead th").all_text_contents()
    assert headers == ["Output", "Kind", "Screen", "Size"]
    assert "It last reported " in panel(ui, hall).inner_text()


def test_a_report_older_than_three_heartbeats_says_nothing_about_now(ui, services, settings, hall, the_wall):
    """A client that stopped leaves its last report saying "connected" for ever.

    So past the threshold Clients says the screen is not known now, and Walls,
    reading the same threshold, never says "Shown by" for it: the two pages agree
    on one report, in the same words for its age (#295).
    """
    old = datetime.now(UTC) - timedelta(days=5)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": old.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client table")

    text = panel(ui, hall).inner_text()
    assert "It last reported 5 days ago." in text
    assert "Hall Pi's report is older than 3 minutes, three missed reports" in text
    rows = panel(ui, hall).locator("tbody tr").all_inner_texts()
    assert "◌ not known now (was detected)" in rows[0]
    assert "● detected" not in text

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")
    line = ui.page.locator("section.wall p.wall-client").inner_text()
    assert (
        line
        == "Assigned to Hall Pi on hdmi-a-1. Hall Pi last reported 5 days ago, so whether a screen is there now is not known."
    )
    assert "Shown by" not in line


def test_a_report_just_inside_the_threshold_still_speaks_for_now(ui, services, settings, hall, the_wall):
    """The paired case: two minutes old is a report, not a stopped client."""
    recent = datetime.now(UTC) - timedelta(minutes=2)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": recent.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client table")

    assert "● detected" in panel(ui, hall).locator("tbody tr").first.inner_text()
    assert "older than" not in panel(ui, hall).inner_text()

    ui.open("#walls")
    ui.page.wait_for_selector("section.wall p.wall-client")
    assert ui.page.locator("section.wall p.wall-client").inner_text() == "Shown by Hall Pi on hdmi-a-1"


def test_a_report_that_cannot_be_read_is_said_to_be_one(ui, settings, hall):
    client_heartbeat_path_in(settings.art_root, hall.id).write_text("{not json", encoding="utf-8")
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    text = panel(ui, hall).inner_text()
    assert "Its last report could not be read: " in text
    assert "Hall Pi's last report could not be read, so its outputs are not known." in text
    assert "has not reported its outputs yet" not in text


def test_a_report_of_no_outputs_says_so_and_lists_none(ui, settings, hall):
    report(settings, hall, {"reported_at": TWO_OUTPUTS["reported_at"], "outputs": []})
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    text = panel(ui, hall).inner_text()
    assert "Hall Pi reported that it has no outputs." in text
    assert "Hall Pi reported no outputs, so type the name of the output" in text
    assert panel(ui, hall).locator("table").count() == 0
    assert "has not reported its outputs yet" not in text
    assert "could not be read" not in text


# -- assignment -----------------------------------------------------------------------


def test_assigning_a_wall_to_a_reported_output(ui, services, settings, hall, the_wall, study):
    report(settings, hall)
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_label("Wall for Hall Pi").select_option(label="Study")
    ui.page.get_by_label("Output of Hall Pi").select_option("hdmi-a-2")
    ui.page.get_by_role("button", name="Assign to Hall Pi").click()
    ui.page.wait_for_selector("section.client li:has-text('Study, on hdmi-a-2')")

    placement = services.clients.placement_of(study.id)
    assert (placement.client.id, placement.output) == (hall.id, "hdmi-a-2")
    said = panel(ui, hall).locator("[data-said]")
    assert said.inner_text() == "Study is now assigned to Hall Pi on hdmi-a-2."
    assert ui.page.evaluate("() => document.activeElement.hasAttribute('data-said')")
    # The picker offers only walls this client does not already show.
    assert ui.page.get_by_label("Wall for Hall Pi").locator("option").all_inner_texts() == [the_wall.name]


def test_assigning_to_a_typed_output_when_none_is_reported_shows_the_servers_notice(ui, services, hall, the_wall):
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    output = ui.page.get_by_label("Output of Hall Pi")
    assert output.get_attribute("placeholder") == "hdmi-a-1"
    assert output.evaluate("node => node.tagName") == "INPUT"
    assert "Hall Pi has not reported its outputs yet, so type the name of the output" in panel(ui, hall).inner_text()
    ui.page.get_by_label("Wall for Hall Pi").select_option(label=the_wall.name)
    output.fill("hdmi-a-1")
    ui.page.get_by_role("button", name="Assign to Hall Pi").click()
    ui.page.wait_for_selector(f"section.client li:has-text('{the_wall.name}, on hdmi-a-1')")

    said = panel(ui, hall).locator("[data-said]").inner_text()
    assert said.startswith(f"{the_wall.name} is now assigned to Hall Pi on hdmi-a-1. ")
    assert "Hall Pi has not reported its outputs yet, so whether it has one called 'hdmi-a-1' cannot be checked" in said
    assert services.clients.placement_of(the_wall.id).client.id == hall.id


def test_an_output_already_showing_a_wall_is_named_and_a_second_is_refused_beside_assign(
    ui, services, settings, hall, the_wall, study
):
    report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    options = ui.page.get_by_label("Output of Hall Pi").locator("option").all_inner_texts()
    assert options == [f"hdmi-a-1 (screen detected, has {the_wall.name})", "hdmi-a-2 (no screen detected)"]
    # The output showing nothing is the one offered first.
    assert ui.page.get_by_label("Output of Hall Pi").input_value() == "hdmi-a-2"
    ui.page.get_by_label("Output of Hall Pi").select_option("hdmi-a-1")
    assign = ui.page.get_by_role("button", name="Assign to Hall Pi")
    assign.click()

    assert "already shows" in ui.said_beside(assign)
    assert services.clients.placement_of(study.id).client is None


def test_unassigning_a_wall_from_the_clients_list(ui, services, hall, the_wall):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client li")

    ui.page.get_by_role("button", name=f"Unassign {the_wall.name} from Hall Pi").click()
    ui.page.wait_for_selector("section.client p:has-text('Hall Pi has no wall assigned yet.')")

    assert services.clients.placement_of(the_wall.id).client is None
    said = panel(ui, hall).locator("[data-said]").inner_text()
    assert said == f"{the_wall.name} is no longer assigned to Hall Pi. It keeps its theme."


def test_renaming_a_client_keeps_its_walls(ui, services, hall, the_wall):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_label("Name of Hall Pi").fill("Study Pi")
    ui.page.get_by_role("button", name="Rename Hall Pi").click()
    ui.page.wait_for_selector("section.client h2:has-text('Study Pi')")

    assert services.clients.get_client(hall.id).name == "Study Pi"
    assert f"{the_wall.name}, on hdmi-a-1" in panel(ui, hall).inner_text()


# -- removal ----------------------------------------------------------------------------


def test_removing_asks_first_and_names_the_walls_left_without_a_client(ui, services, hall, the_wall, study, server_url):
    token = services.access.issue(hall.id).token
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-2")
    services.display.add_wall(name="Landing")
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_role("button", name="Remove Hall Pi").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert ui.page.inner_text("dialog.confirm .confirm-title") == "Remove Hall Pi?"
    # In the order walls are listed everywhere, which is by name.
    both = " and ".join(sorted([the_wall.name, study.name]))
    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    assert f"{both} will be left without a client" in consequence
    assert "Landing" not in consequence
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Remove Hall Pi')")
    ui.page.wait_for_selector("#view p:has-text('No client is recorded yet.')")

    said = ui.page.locator("[data-said]").inner_text()
    assert said == f"Hall Pi is removed. 2 walls now have no client: {both}."
    assert services.clients.list_clients() == []
    assert services.clients.placement_of(study.id).client is None
    assert admitted(server_url, token) == 401


def test_declining_a_removal_keeps_the_client_and_its_walls(ui, services, hall, the_wall):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_role("button", name="Remove Hall Pi").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")

    assert [view.client.id for view in services.clients.list_clients()] == [hall.id]
    assert services.clients.placement_of(the_wall.id).client.id == hall.id


def test_removing_a_client_that_shows_nothing_says_no_wall_is_affected(ui, hall):
    open_clients(ui)
    ui.page.wait_for_selector("section.client")

    ui.page.get_by_role("button", name="Remove Hall Pi").click()
    ui.page.wait_for_selector("dialog.confirm[open]")

    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    assert "No wall is assigned to it, so no wall is affected." in consequence
    assert "left without a client" not in consequence
