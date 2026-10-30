"""Settings › Players, in a real browser against a real server.

`clients.md` makes a Player something the server knows, with one token, showing
the walls set on its screens. This page is where a curator keeps them, as Radarr
keeps its Download Clients: one row per Player, its settings in its *Edit…*
(ruling 7 of 2026-10-27, `ia-proposal.md`). It was Settings › Clients, a panel
per client that assigned walls as well, until that ruling; its address kept its
spelling, `#clients`, as every renamed page's has.

**The token is the part worth the most care.** It exists outside its Player only
in the answer that issued it, so the page must show it once, plainly, with what
to do with it — and must not show it again: not after a reload, and not on a
first paint of a Player that already has one. Both halves are asserted, and each
act that issues one is checked against the Player's own route, because a token
the page displayed and the server would refuse is the failure a curator meets at
the Player, a room away from this screen.

**What a Player reported is seeded the way a Player leaves it**: the heartbeat
file the server reads, at the path the server derives.
"""

import json
import re
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

#: A report of two outputs. `reported_at` is stamped when `report` writes it,
#: never at import: one older than three heartbeats says nothing about now, and
#: a stamp taken when the module loaded is that old by the time a long serial
#: run reaches a test that reads it.
TWO_OUTPUTS = {
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


#: The same, with one label panel.
WITH_A_PANEL = TWO_OUTPUTS | {"label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}]}


def report(settings, client, document=TWO_OUTPUTS):
    """What a running Player's heartbeat leaves under the art root, stamped now unless the document says when."""
    stamped = {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")} | document
    client_heartbeat_path_in(settings.art_root, client.id).write_text(json.dumps(stamped), encoding="utf-8")


def admitted(server_url, token) -> int:
    """The Player route's answer to this token: 200 for a Player's current one, 401 otherwise."""
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


def row(ui, client):
    return ui.page.locator(f"tr[data-player='{client.id}']")


def cell(ui, client, column):
    return row(ui, client).locator(f"td[data-label='{column}']")


def open_players(ui):
    ui.open("#clients")
    ui.page.wait_for_selector("#view h1:has-text('Players')")


def edit(ui, client):
    """Open a Player's *Edit…* and return the dialog."""
    row(ui, client).get_by_role("button", name=f"Edit {client.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    return dialog


def add(ui, name):
    ui.page.get_by_role("button", name="Add Player…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill(name)
    dialog.get_by_role("button", name="Add Player", exact=True).click()


# -- the page --------------------------------------------------------------------


def test_the_page_is_under_settings_and_answers_its_own_path(ui, seeded_service):
    """A bookmark is a path as well as a fragment; `pages.py` has to serve it."""
    ui.page.goto(f"{ui.base_url}/clients")
    ui.page.wait_for_selector("#view h1:has-text('Players')")

    current = ui.page.locator("nav.sidebar a[data-view='clients'][aria-current='page']")
    assert current.inner_text() == "Players"
    section = ui.page.locator("nav.sidebar li.section", has=ui.page.locator("a[data-view='clients']"))
    assert section.locator("a.section-link .label").inner_text() == "Settings"


def test_the_page_opens_with_its_name_its_facts_and_its_toolbar(ui, services, settings, hall):
    """Ruling 1 of 2026-10-27: the name, one line of facts, then the toolbar, and nothing else above the table."""
    other = services.clients.add_client(name="Study Mac")
    services.access.issue(hall.id)
    services.access.issue(other.id)
    report(settings, hall)
    open_players(ui)

    view = ui.page.locator("#view")
    tags = view.evaluate("node => [...node.children].slice(0, 4).map((child) => child.tagName + '.' + child.className)")
    assert tags[0].startswith("H1")
    assert "page-facts" in tags[1]
    assert "page-toolbar" in tags[2]
    assert "table-scroll" in tags[3]
    assert view.locator(".page-facts").inner_text() == "2 Players · 1 reporting"
    headers = view.locator("thead th").all_text_contents()
    assert headers == ["Player", "Status", "Screens", "Label panel", "Settings"]


def test_with_no_player_the_page_says_so_and_offers_the_add(ui, seeded_service):
    open_players(ui)

    assert "No Player is recorded yet." in ui.text()
    assert "set in that wall's Edit…" in ui.text()
    assert ui.page.get_by_role("button", name="Add Player…").is_visible()
    assert ui.page.locator("tr[data-player]").count() == 0
    assert ui.page.locator(".page-facts").inner_text() == "0 Players"


def test_a_row_offers_only_edit_and_never_assigns_or_captions(ui, services, settings, hall, the_wall):
    """Ruling 7: a wall's screen and label are the wall's settings, in its Edit… on Walls, and only said here."""
    report(settings, hall, WITH_A_PANEL)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_players(ui)

    assert row(ui, hall).get_by_role("button").all_inner_texts() == ["Edit…"]
    assert ui.page.locator("#view select").count() == 0
    for word in ("Assign", "Unassign", "Caption a wall", "Stop captioning"):
        assert word not in ui.text()
    dialog = edit(ui, hall)
    assert dialog.locator("select").count() == 0
    assert dialog.get_by_role("button").all_inner_texts() == ["Rename", "Issue a token", "Remove…", "Close"]


def test_no_page_calls_a_player_a_client(ui, services, settings, hall, the_wall):
    """§ Vocabulary: a Player is never a client on a screen a person reads.

    Every page the sidebar lists, read with a Player that reports, shows a wall
    and captions it, so the Walls card and its dialog have something to say
    about it. The address and the routes keep `client`; only text is read.
    """
    report(settings, hall, WITH_A_PANEL)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#walls")
    views = ui.page.evaluate("() => [...document.querySelectorAll('nav.sidebar a[data-view]')].map((link) => link.dataset.view)")
    assert "clients" in views
    assert "walls" in views
    for view in views:
        ui.open(f"#{view}")
        ui.page.wait_for_selector("#view h1")
        found = re.findall(r"\bclients?\b", ui.page.inner_text("body"), flags=re.IGNORECASE)
        assert not found, f"#{view} says {found}"
    ui.open("#walls")
    ui.page.click("section.wall button.wall-edit")
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    assert not re.findall(r"\bclients?\b", dialog.inner_text(), flags=re.IGNORECASE)


# -- the token, once ---------------------------------------------------------------


def test_adding_a_player_shows_its_token_once_with_what_to_do_with_it(ui, services, server_url):
    open_players(ui)

    add(ui, "  Hall Pi  ")
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    token = field.input_value()
    assert field.get_attribute("readonly") is not None
    assert ui.page.evaluate("() => document.activeElement.id") == "player-token"
    note = ui.page.locator(".token-once").inner_text()
    assert "the only time it is shown" in note
    assert "CLIENT_TOKEN" in note
    assert "SERVER_URL" in note
    assert server_url in note, "the address the Player needs is not stated"
    # One dialog, the token's: the add's own closed as it issued.
    assert ui.page.locator("dialog.panel-dialog").count() == 1
    [client] = services.clients.list_clients()
    assert client.client.name == "Hall Pi"
    assert admitted(server_url, token) == 200

    ui.page.get_by_role("button", name="Done").click()
    row(ui, client.client).wait_for()
    assert cell(ui, client.client, "Player").inner_text() == "Hall Pi"
    assert token not in ui.page.content()
    ui.page.reload()
    row(ui, client.client).wait_for()
    assert ui.page.locator("#player-token").count() == 0
    assert token not in ui.page.content()
    assert "Issued " in edit(ui, client.client).inner_text()


def test_a_player_that_already_has_a_token_is_never_shown_one(ui, services, hall, server_url):
    token = services.access.issue(hall.id).token
    open_players(ui)

    assert ui.page.locator("#player-token").count() == 0
    assert token not in ui.page.content()
    dialog = edit(ui, hall)
    assert dialog.get_by_role("button", name="Rotate Hall Pi's token…").is_visible()
    assert dialog.get_by_role("button", name="Issue a token for Hall Pi").count() == 0
    assert token not in ui.page.content()


def test_a_player_with_no_token_says_so_and_issues_one_without_asking(ui, services, hall, server_url):
    """Issuing a first token refuses no Player, so there is nothing to confirm."""
    open_players(ui)
    assert cell(ui, hall, "Status").inner_text().startswith("○ No token")

    dialog = edit(ui, hall)
    assert "None issued yet, so it is admitted to nothing until one is." in dialog.inner_text()
    dialog.get_by_role("button", name="Issue a token for Hall Pi").click()
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    assert ui.page.locator("dialog.confirm").count() == 0
    assert admitted(server_url, field.input_value()) == 200


def decline(ui, leave):
    """Answer the open question no, with its Cancel or with Escape."""
    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_declining_a_rotation_leaves_the_old_token_working(ui, services, hall, server_url, leave):
    old = services.access.issue(hall.id).token
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Rotate Hall Pi's token…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert ui.page.inner_text("dialog.confirm .confirm-title") == "Rotate Hall Pi's token?"
    assert "Hall Pi is refused" in ui.page.inner_text("dialog.confirm .confirm-consequence")
    # The question is the only dialog on the page: Edit… closed as it asked.
    assert ui.page.locator("dialog.panel-dialog").count() == 0
    decline(ui, leave)

    assert ui.page.locator("#player-token").count() == 0
    assert admitted(server_url, old) == 200


def test_confirming_a_rotation_shows_the_new_token_and_refuses_the_old(ui, services, hall, server_url):
    old = services.access.issue(hall.id).token
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Rotate Hall Pi's token…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Rotate the token')")
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    new = field.input_value()
    assert new != old
    assert admitted(server_url, old) == 401
    assert admitted(server_url, new) == 200


# -- what the Player reported ----------------------------------------------------------


def test_a_player_that_has_not_reported_says_so_in_words(ui, services, hall):
    services.access.issue(hall.id)
    open_players(ui)

    assert cell(ui, hall, "Status").inner_text() == "○ Never reported"
    assert cell(ui, hall, "Screens").inner_text() == "Not reported yet."
    assert cell(ui, hall, "Label panel").inner_text() == "Not known until it reports."


def test_a_report_is_listed_screen_by_screen_with_its_age(ui, services, settings, hall, the_wall):
    services.access.issue(hall.id)
    report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-2")
    open_players(ui)

    status = cell(ui, hall, "Status").inner_text()
    assert status.startswith("● Reporting")
    assert "It last reported " in status
    screens = cell(ui, hall, "Screens").locator("li").all_inner_texts()
    assert len(screens) == 2
    # A screen as a person names it (§ Vocabulary), never its port.
    assert screens[0].startswith("HDMI 1, 1920 × 1080 · ● detected")
    assert screens[0].endswith("No wall")
    assert screens[1].startswith("HDMI 2 · ○ none detected (off or unplugged)")
    assert screens[1].endswith(f"Shows {the_wall.name}")
    assert "hdmi-a" not in cell(ui, hall, "Screens").inner_text()
    # "connected" read as a cable fault when the usual cause is a television
    # switched off, which drops its hotplug line exactly as an unplugged one does.
    assert "connected" not in cell(ui, hall, "Screens").inner_text()
    wall = cell(ui, hall, "Screens").get_by_role("link", name=the_wall.name)
    assert wall.get_attribute("href") == f"#walls?wall={the_wall.id}"


def test_a_report_older_than_three_heartbeats_says_nothing_about_now(ui, services, settings, hall, the_wall):
    """A Player that stopped leaves its last report saying "connected" for ever.

    So past the threshold Players says the screen is not known now, and Walls,
    reading the same threshold, never says "Shown by" for it: the two pages agree
    on one report, in the same words for its age (#295).
    """
    services.access.issue(hall.id)
    old = datetime.now(UTC) - timedelta(days=5)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": old.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    status = cell(ui, hall, "Status").inner_text()
    assert status.startswith("◌ Not heard from since ")
    assert status.endswith("(5 days ago)")
    screens = cell(ui, hall, "Screens").inner_text()
    assert "◌ not known now (was detected)" in screens
    assert "● detected" not in screens
    assert ui.page.locator(".page-facts").inner_text() == "1 Player · 0 reporting"

    ui.open("#walls")
    # In the wall's Edit… dialog since ruling 4 of 2026-10-27, so opened first.
    ui.page.click("section.wall button.wall-edit")
    line = ui.page.locator("dialog.panel-dialog p.wall-client").inner_text()
    assert line == "Assigned to Hall Pi. Hall Pi last reported 5 days ago, so whether a screen is there now is not known."
    assert "Shown by" not in line


def test_a_report_just_inside_the_threshold_still_speaks_for_now(ui, services, settings, hall, the_wall):
    """The paired case: two minutes old is a report, not a stopped Player."""
    services.access.issue(hall.id)
    recent = datetime.now(UTC) - timedelta(minutes=2)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": recent.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    assert cell(ui, hall, "Status").inner_text().startswith("● Reporting")
    assert "● detected" in cell(ui, hall, "Screens").locator("li").first.inner_text()

    ui.open("#walls")
    # In the wall's Edit… dialog since ruling 4 of 2026-10-27, so opened first.
    ui.page.click("section.wall button.wall-edit")
    assert ui.page.locator("dialog.panel-dialog p.wall-client").inner_text() == "Shown by Hall Pi"


def test_a_report_that_cannot_be_read_is_said_to_be_one(ui, services, settings, hall):
    services.access.issue(hall.id)
    client_heartbeat_path_in(settings.art_root, hall.id).write_text("{not json", encoding="utf-8")
    open_players(ui)

    status = cell(ui, hall, "Status").inner_text()
    assert status.startswith("▲ Report unreadable")
    assert "Its last report could not be read: " in status
    assert cell(ui, hall, "Screens").inner_text() == "Not known: its last report could not be read."
    assert "Not reported yet" not in row(ui, hall).inner_text()


def test_a_report_of_no_outputs_says_so_and_lists_none(ui, services, settings, hall):
    services.access.issue(hall.id)
    report(settings, hall, {"outputs": []})
    open_players(ui)

    assert cell(ui, hall, "Screens").inner_text() == "It reported no screen."
    assert cell(ui, hall, "Label panel").inner_text() == "None reported."
    assert cell(ui, hall, "Screens").locator("li").count() == 0
    assert "Not reported yet" not in row(ui, hall).inner_text()
    assert "could not be read" not in row(ui, hall).inner_text()


def test_a_wall_set_on_a_screen_the_report_does_not_list_is_still_said(ui, services, settings, hall, the_wall):
    """A wall placed on a port before the Player reported it shows nothing there, and the row says where it is."""
    services.access.issue(hall.id)
    report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-3")
    open_players(ui)

    screens = cell(ui, hall, "Screens").locator("li").all_inner_texts()
    assert len(screens) == 3
    assert screens[2].startswith("HDMI 3 · ◌ not in its last report")
    assert screens[2].endswith(f"Shows {the_wall.name}")


def test_a_label_panel_is_listed_with_its_state_and_the_wall_it_captions(ui, services, settings, hall, the_wall):
    services.access.issue(hall.id)
    report(settings, hall, WITH_A_PANEL)
    open_players(ui)
    # One panel: its port is not named (§ Vocabulary names a panel by its Player).
    assert cell(ui, hall, "Label panel").inner_text().replace("\n", "\t").split("\t") == ["● answering, 800 × 480", "No wall"]

    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_players(ui)
    panel = cell(ui, hall, "Label panel")
    assert panel.inner_text().endswith(f"Captions {the_wall.name}")
    assert "epd-0" not in panel.inner_text()
    assert panel.get_by_role("link", name=the_wall.name).get_attribute("href") == f"#walls?wall={the_wall.id}"


# -- its settings, in its Edit… -----------------------------------------------------------


def test_renaming_a_player_keeps_its_walls(ui, services, hall, the_wall):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    dialog = edit(ui, hall)
    dialog.get_by_label("Name", exact=True).fill("Study Pi")
    dialog.get_by_role("button", name="Rename Hall Pi").click()
    dialog.wait_for(state="detached")
    ui.page.wait_for_selector("#view [data-said]")

    assert services.clients.get_client(hall.id).name == "Study Pi"
    assert cell(ui, hall, "Player").inner_text() == "Study Pi"
    assert the_wall.name in cell(ui, hall, "Screens").inner_text()
    assert ui.page.inner_text("#view [data-said]") == "Hall Pi is now called Study Pi. Its token and its walls are unchanged."


def test_a_refused_rename_is_said_in_the_dialog_and_changes_nothing(ui, services, hall):
    other = services.clients.add_client(name="Study Mac")
    open_players(ui)

    dialog = edit(ui, hall)
    dialog.get_by_label("Name", exact=True).fill("   ")
    rename = dialog.get_by_role("button", name="Rename Hall Pi")
    rename.click()
    assert "Couldn't rename Hall Pi" in ui.said_beside(rename)
    assert dialog.is_visible()
    assert {view.client.name for view in services.clients.list_clients()} == {"Hall Pi", other.name}


def test_removing_asks_first_and_names_the_walls_left_without_a_player(ui, services, hall, the_wall, study, server_url):
    token = services.access.issue(hall.id).token
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-2")
    services.display.add_wall(name="Landing")
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Remove Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert ui.page.locator("dialog.panel-dialog").count() == 0
    assert ui.page.inner_text("dialog.confirm .confirm-title") == "Remove Hall Pi?"
    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    # In the order the server lists the Player's walls.
    first, second = (shown.wall.name for shown in services.clients.get_client_view(hall.id).walls)
    both = f"{first} and {second}"
    assert f"{both} will be left without a Player" in consequence
    assert consequence.startswith("Its token stops working at once, and ")
    assert "Landing" not in consequence
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Remove Hall Pi')")
    ui.page.wait_for_selector("#view [data-said]")

    said = ui.page.inner_text("#view [data-said]")
    assert said == f"Hall Pi is removed. 2 walls now have no Player: {both}."
    assert services.clients.list_clients() == []
    assert services.clients.placement_of(study.id).client is None
    assert admitted(server_url, token) == 401


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_declining_a_removal_keeps_the_player_and_its_walls(ui, services, hall, the_wall, leave):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Remove Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    decline(ui, leave)

    assert [view.client.id for view in services.clients.list_clients()] == [hall.id]
    assert services.clients.placement_of(the_wall.id).client.id == hall.id
    assert row(ui, hall).is_visible()


def test_removing_a_player_that_shows_nothing_says_no_wall_is_affected(ui, hall):
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Remove Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    assert "It shows no wall, so no wall is affected." in consequence
    assert "left without a Player" not in consequence
    # Never issued one, so no token is said to stop.
    assert consequence.startswith("It has no token.")
    assert "token stops working" not in consequence


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_leaving_add_player_adds_nothing(ui, services, leave):
    open_players(ui)
    ui.page.get_by_role("button", name="Add Player…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill("Hall Pi")
    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        dialog.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="detached")

    assert services.clients.list_clients() == []
    assert ui.page.evaluate("() => document.activeElement.textContent") == "Add Player…"


@pytest.mark.parametrize("leave", ["Close", "Escape"])
def test_leaving_edit_changes_nothing(ui, services, hall, leave):
    token = services.access.issue(hall.id)
    open_players(ui)
    dialog = edit(ui, hall)
    dialog.get_by_label("Name", exact=True).fill("Study Pi")
    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        dialog.get_by_role("button", name="Close").click()
    dialog.wait_for(state="detached")

    assert services.clients.get_client(hall.id).name == "Hall Pi"
    assert services.clients.get_client(hall.id).token_issued_at == token.issued_at
    assert cell(ui, hall, "Player").inner_text() == "Hall Pi"
