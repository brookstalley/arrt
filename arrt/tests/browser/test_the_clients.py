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
from fixed_instant import A_FIXED_NOON

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

from arrt.programming.client_heartbeat import client_heartbeat_path_in
from arrt.services.errors import ServiceError

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


def starting(text):
    """What a text begins with, as a pattern over the raw `innerText`: `startswith`'s retrying form."""
    return re.compile("^" + re.escape(text))


def ending(text):
    """What a text ends with, as a pattern over the raw `innerText`: `endswith`'s retrying form."""
    return re.compile(re.escape(text) + "$")


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
    expect(current).to_have_text("Players", use_inner_text=True)
    section = ui.page.locator("nav.sidebar li.section", has=ui.page.locator("a[data-view='clients']"))
    expect(section.locator("a.section-link .label")).to_have_text("Settings", use_inner_text=True)


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
    # The one with a token and no report is waited for, and the line says so.
    expect(view.locator(".page-facts")).to_have_text("2 Players · 1 reporting · waiting for 1 to report", use_inner_text=True)
    expect(view.locator("thead th")).to_have_text(["Player", "Status", "Screens", "Label panel", "Settings"])


def test_with_no_player_the_page_says_so_and_offers_the_add(ui, seeded_service):
    open_players(ui)

    expect(ui.view).to_contain_text("No Player is recorded yet.", use_inner_text=True)
    expect(ui.view).to_contain_text("set in that wall's Edit…", use_inner_text=True)
    expect(ui.page.get_by_role("button", name="Add Player…")).to_be_visible()
    expect(ui.page.locator("tr[data-player]")).to_have_count(0)
    expect(ui.page.locator(".page-facts")).to_have_text("0 Players", use_inner_text=True)


def test_a_row_offers_only_edit_and_never_assigns_or_captions(ui, services, settings, hall, the_wall):
    """Ruling 7: a wall's screen and label are the wall's settings, in its Edit… on Walls, and only said here."""
    report(settings, hall, WITH_A_PANEL)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_players(ui)

    expect(row(ui, hall).get_by_role("button")).to_have_text(["Edit…"], use_inner_text=True)
    expect(ui.page.locator("#view select")).to_have_count(0)
    for word in ("Assign", "Unassign", "Caption a wall", "Stop captioning"):
        expect(ui.view, word).not_to_contain_text(word, use_inner_text=True)
    dialog = edit(ui, hall)
    expect(dialog.get_by_role("button")).to_have_text(["Rename", "Issue a token", "Forget…", "Close"], use_inner_text=True)
    expect(dialog.locator("select")).to_have_count(0)


#: What each sidebar page paints only once it has its data, so a test that reads a
#: page waits for it first. `#view h1` is not that: Artworks paints its heading in
#: a loading state, and several pages paint it before their rows, so a test that
#: waited for the heading and read the page read what had not arrived.
#: A page with nothing of its own in this state anchors on the empty
#: sentence it says instead. A sidebar page missing here fails the test below.
PAINTED = {
    "collection": "#view ul.grid li[data-artwork]",
    "discover": "#view .panel.ask",
    "theme": "#view .page-facts",
    "topics": "#view :is(.empty, section)",
    "artist": "#view ul.artist-posters li.card, #view section[aria-label$='in the library']",
    "walls": "#view section.wall",
    "to_review": "#view .empty",
    "queue": "#view .panel.acquisitions",
    "history": "#view .history-events li, #view .empty",
    "settings": "#view ul.settings-index li",
    "sources": "#view li.source-entry",
    # System › Spend is in the sidebar, and a page missing here fails the check below.
    "spend": "#view .spend-month",
    "clients": "#view tr[data-player]",
    "watches": "#view .watches-standing",
    "general": "#view .settings-general",
    "taste": "#view .taste-help",
    "wanted": "#view .empty",
    "health": "#view .wall-reading",
}


def test_no_page_calls_a_player_a_client(ui, services, settings, hall, the_wall):
    """§ Vocabulary: a Player is never a client on a screen a person reads.

    Every page the sidebar lists, read with a Player that reports, shows a wall
    and captions it, so the Walls card and its dialog have something to say
    about it. The address and the routes keep `client`; only text is read.

    **Each page is read after its own data has painted** (`PAINTED`), never after
    its heading alone: Artworks draws "Loading Artworks…" under an `h1` and then
    its tiles, so a "client" in a tile painted late was passed over.
    """
    services.access.issue(hall.id)
    report(settings, hall, WITH_A_PANEL)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    ui.open("#walls")
    views = ui.page.evaluate("() => [...document.querySelectorAll('nav.sidebar a[data-view]')].map((link) => link.dataset.view)")
    assert "clients" in views
    assert "walls" in views
    assert set(views) <= set(
        PAINTED
    ), f"sidebar pages with nothing to wait for before reading them: {sorted(set(views) - set(PAINTED))}"
    for view in views:
        ui.open(f"#{view}")
        ui.page.locator(PAINTED[view]).first.wait_for()
        expect(ui.page.locator("body"), f"#{view} calls a Player a client").not_to_contain_text(
            re.compile(r"\bclients?\b", re.IGNORECASE), use_inner_text=True
        )
    ui.open("#walls")
    ui.page.click("section.wall button.wall-edit")
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    expect(dialog).not_to_contain_text(re.compile(r"\bclients?\b", re.IGNORECASE), use_inner_text=True)


# -- the token, once ---------------------------------------------------------------


def test_adding_a_player_shows_its_token_once_with_what_to_do_with_it(ui, services, server_url):
    open_players(ui)

    add(ui, "  Hall Pi  ")
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    token = field.input_value()  # one-shot: the token to look for on the page afterwards, read once the field is drawn
    expect(field).to_have_attribute("readonly")
    assert ui.page.evaluate("() => document.activeElement.id") == "player-token"
    note = ui.page.locator(".token-once")
    expect(note).to_contain_text("the only time it is shown", use_inner_text=True)
    # In the Player's own settings page's words, not the environment variables
    # behind them: its fields are *Token* and *Server
    # address* (the old names, *Client token* and *Server › Address*, would send
    # nobody anywhere).
    expect(note).to_contain_text("put this token in Token, and", use_inner_text=True)
    expect(note).to_contain_text(
        f"this server's address in Server address, as that Player reaches it — from this browser, {server_url}.",
        use_inner_text=True,
    )
    expect(note).not_to_contain_text("Client token", use_inner_text=True)
    expect(note).not_to_contain_text("Server › Address", use_inner_text=True)
    expect(note).not_to_contain_text("CLIENT_TOKEN", use_inner_text=True)
    expect(note).not_to_contain_text("SERVER_URL", use_inner_text=True)
    # One dialog, the token's: the add's own closed as it issued.
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(1)
    [client] = services.clients.list_clients()
    assert client.client.name == "Hall Pi"
    assert admitted(server_url, token) == 200

    ui.page.get_by_role("button", name="Done").click()
    row(ui, client.client).wait_for()
    expect(cell(ui, client.client, "Player")).to_have_text("Hall Pi", use_inner_text=True)
    assert token not in ui.page.content()
    ui.page.reload()
    row(ui, client.client).wait_for()
    expect(ui.page.locator("#player-token")).to_have_count(0)
    assert token not in ui.page.content()
    expect(edit(ui, client.client)).to_contain_text("Issued ", use_inner_text=True)


def test_a_player_that_already_has_a_token_is_never_shown_one(ui, services, hall, server_url):
    token = services.access.issue(hall.id).token
    open_players(ui)

    # The Player's row is drawn, so the absence of a token field is of a list that has loaded.
    expect(row(ui, hall)).to_be_visible()
    expect(ui.page.locator("#player-token")).to_have_count(0)
    assert token not in ui.page.content()
    dialog = edit(ui, hall)
    expect(dialog.get_by_role("button", name="Rotate Hall Pi's token…")).to_be_visible()
    expect(dialog.get_by_role("button", name="Issue a token for Hall Pi")).to_have_count(0)
    assert token not in ui.page.content()


def test_a_player_with_no_token_says_so_and_issues_one_without_asking(ui, services, hall, server_url):
    """Issuing a first token refuses no Player, so there is nothing to confirm."""
    open_players(ui)
    expect(cell(ui, hall, "Status")).to_have_text(starting("○ No token yet"), use_inner_text=True)

    dialog = edit(ui, hall)
    expect(dialog).to_contain_text("None issued yet, so it is admitted to nothing until one is.", use_inner_text=True)
    dialog.get_by_role("button", name="Issue a token for Hall Pi").click()
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    expect(ui.page.locator("dialog.confirm")).to_have_count(0)
    assert (
        admitted(server_url, field.input_value()) == 200
    )  # one-shot: the token to try at the route, read once the field is drawn


def decline(ui, leave):
    """Answer the open question no, with its Cancel or with Escape."""
    if leave == "Escape":
        ui.page.keyboard.press("Escape")
    else:
        ui.page.click("dialog.confirm .confirm-actions button:has-text('Cancel')")
    ui.page.wait_for_selector("dialog.confirm", state="detached")
    # A No that was ignored is a request in flight by now: once the page has
    # been quiet, what the tests read afterwards is a Player that was kept and
    # not one whose removal or new token has yet to arrive.
    ui.page.wait_for_load_state("networkidle")


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_declining_a_rotation_leaves_the_old_token_working(ui, services, hall, server_url, leave):
    old = services.access.issue(hall.id).token
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Rotate Hall Pi's token…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    expect(ui.page.locator("dialog.confirm .confirm-title")).to_have_text("Rotate Hall Pi's token?", use_inner_text=True)
    expect(ui.page.locator("dialog.confirm .confirm-consequence")).to_contain_text("Hall Pi is refused", use_inner_text=True)
    # The question is the only dialog on the page: Edit… closed as it asked.
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)
    decline(ui, leave)

    expect(ui.page.locator("#player-token")).to_have_count(0)
    assert admitted(server_url, old) == 200


def test_confirming_a_rotation_shows_the_new_token_and_refuses_the_old(ui, services, hall, server_url):
    old = services.access.issue(hall.id).token
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Rotate Hall Pi's token…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Rotate the token')")
    field = ui.page.get_by_label("Token for Hall Pi", exact=True)
    field.wait_for()

    new = field.input_value()  # one-shot: the new token, to compare with the old, read once the field is drawn
    assert new != old
    assert admitted(server_url, old) == 401
    assert admitted(server_url, new) == 200


# -- what the Player reported ----------------------------------------------------------


def test_a_player_that_has_not_reported_says_so_in_words(ui, services, hall):
    services.access.issue(hall.id)
    open_players(ui)

    # Waiting for it, with what it waits on: not "Never reported", which reads as a fault on the evening it was added.
    # Two lines, the state and what it waits on: a pattern over the raw text, which a string would fold into one.
    expect(cell(ui, hall, "Status")).to_have_text(
        re.compile(
            "^"
            + re.escape("◌ Waiting for its first report")
            + r"\n"
            + re.escape("Once it is running with its token, it reports here within a minute or so.")
            + "$"
        ),
        use_inner_text=True,
    )
    expect(ui.page.locator(".page-facts")).to_have_text("1 Player · waiting for it to report", use_inner_text=True)
    expect(cell(ui, hall, "Screens")).to_have_text("Not reported yet.", use_inner_text=True)
    expect(cell(ui, hall, "Label panel")).to_have_text("Not known until it reports.", use_inner_text=True)


def test_a_report_is_listed_screen_by_screen_with_its_age(ui, services, settings, hall, the_wall):
    services.access.issue(hall.id)
    report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-2")
    open_players(ui)

    status = cell(ui, hall, "Status")
    expect(status).to_have_text(starting("● Reporting"), use_inner_text=True)
    expect(status).to_contain_text("It last reported ", use_inner_text=True)
    screens = cell(ui, hall, "Screens").locator("li")
    expect(screens).to_have_count(2)
    # A screen as a person names it (§ Vocabulary), never its port.
    expect(screens.nth(0)).to_have_text(starting("HDMI 1, 1920 × 1080 · ● detected"), use_inner_text=True)
    expect(screens.nth(0)).to_have_text(ending("No wall"), use_inner_text=True)
    expect(screens.nth(1)).to_have_text(starting("HDMI 2 · ○ none detected (off or unplugged)"), use_inner_text=True)
    expect(screens.nth(1)).to_have_text(ending(f"Shows {the_wall.name}"), use_inner_text=True)
    expect(cell(ui, hall, "Screens")).not_to_contain_text("hdmi-a", use_inner_text=True)
    # "connected" read as a cable fault when the usual cause is a television
    # switched off, which drops its hotplug line exactly as an unplugged one does.
    expect(cell(ui, hall, "Screens")).not_to_contain_text("connected", use_inner_text=True)
    wall = cell(ui, hall, "Screens").get_by_role("link", name=the_wall.name)
    expect(wall).to_have_attribute("href", f"#walls?wall={the_wall.id}")


@pytest.mark.at_a_fixed_instant(A_FIXED_NOON)
def test_a_report_older_than_three_heartbeats_says_nothing_about_now(ui, services, settings, hall, the_wall, shared_clock):
    """A Player that stopped leaves its last report saying "connected" for ever.

    So past the threshold Players says the screen is not known now, and Walls,
    reading the same threshold, never says "Shown by" for it: the two pages agree
    on one report, in the same words for its age.
    """
    services.access.issue(hall.id)
    old = shared_clock() - timedelta(days=5)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": old.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    status = cell(ui, hall, "Status")
    expect(status).to_have_text(starting("▲ Not heard from since "), use_inner_text=True)
    expect(status).to_have_text(ending("(5 days ago)"), use_inner_text=True)
    screens = cell(ui, hall, "Screens")
    expect(screens).to_contain_text("◌ not known now (was detected)", use_inner_text=True)
    expect(screens).not_to_contain_text("● detected", use_inner_text=True)
    expect(ui.page.locator(".page-facts")).to_have_text("1 Player · 0 reporting", use_inner_text=True)

    ui.open("#walls")
    # In the wall's Edit… dialog since ruling 4 of 2026-10-27, so opened first.
    ui.page.click("section.wall button.wall-edit")
    line = ui.page.locator("dialog.panel-dialog p.wall-client")
    expect(line).to_have_text(
        "Assigned to Hall Pi. Hall Pi last reported 5 days ago, so whether a screen is there now is not known.",
        use_inner_text=True,
    )
    expect(line).not_to_contain_text("Shown by", use_inner_text=True)


@pytest.mark.at_a_fixed_instant(A_FIXED_NOON)
def test_a_report_just_inside_the_threshold_still_speaks_for_now(ui, services, settings, hall, the_wall, shared_clock):
    """The paired case: two minutes old is a report, not a stopped Player."""
    services.access.issue(hall.id)
    recent = shared_clock() - timedelta(minutes=2)
    report(settings, hall, TWO_OUTPUTS | {"reported_at": recent.isoformat(timespec="seconds")})
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    expect(cell(ui, hall, "Status")).to_have_text(starting("● Reporting"), use_inner_text=True)
    expect(cell(ui, hall, "Screens").locator("li").first).to_contain_text("● detected", use_inner_text=True)

    ui.open("#walls")
    # In the wall's Edit… dialog since ruling 4 of 2026-10-27, so opened first.
    ui.page.click("section.wall button.wall-edit")
    expect(ui.page.locator("dialog.panel-dialog p.wall-client")).to_have_text("Shown by Hall Pi", use_inner_text=True)


def test_a_report_that_cannot_be_read_is_said_to_be_one(ui, services, settings, hall):
    services.access.issue(hall.id)
    client_heartbeat_path_in(settings.art_root, hall.id).write_text("{not json", encoding="utf-8")
    open_players(ui)

    status = cell(ui, hall, "Status")
    expect(status).to_have_text(starting("▲ Report unreadable"), use_inner_text=True)
    expect(status).to_contain_text("Its last report could not be read: ", use_inner_text=True)
    expect(cell(ui, hall, "Screens")).to_have_text("Not known: its last report could not be read.", use_inner_text=True)
    expect(row(ui, hall)).not_to_contain_text("Not reported yet", use_inner_text=True)


def test_a_player_whose_reports_are_refused_says_so_with_the_servers_words(ui, services, hall):
    """Its first report refused: a trouble with what it was told, never "waiting for its first report"."""
    services.access.issue(hall.id)
    refused = {**TWO_OUTPUTS, "reported_at": datetime.now(UTC).isoformat(), "outputs": [{"name": "hdmi-a-1", "kind": "hdmi"}]}
    with pytest.raises(ServiceError):
        services.clients.record_heartbeat(hall.id, refused)
    open_players(ui)

    status = cell(ui, hall, "Status")
    expect(status).to_have_text(starting("▲ Report unreadable"), use_inner_text=True)
    expect(status).to_contain_text(
        "Its last report could not be read: output 0: 'kind' is one of frame, framebuffer.", use_inner_text=True
    )
    expect(cell(ui, hall, "Screens")).to_have_text("Not known: its last report could not be read.", use_inner_text=True)
    expect(row(ui, hall)).not_to_contain_text("Once it is running with its token", use_inner_text=True)


def test_a_report_of_no_outputs_says_so_and_lists_none(ui, services, settings, hall):
    services.access.issue(hall.id)
    report(settings, hall, {"outputs": []})
    open_players(ui)

    expect(cell(ui, hall, "Screens")).to_have_text("It reported no screen.", use_inner_text=True)
    expect(cell(ui, hall, "Label panel")).to_have_text("None reported.", use_inner_text=True)
    expect(cell(ui, hall, "Screens").locator("li")).to_have_count(0)
    expect(row(ui, hall)).not_to_contain_text("Not reported yet", use_inner_text=True)
    expect(row(ui, hall)).not_to_contain_text("could not be read", use_inner_text=True)


def test_a_wall_set_on_a_screen_the_report_does_not_list_is_still_said(ui, services, settings, hall, the_wall):
    """A wall placed on a port before the Player reported it shows nothing there, and the row says where it is."""
    services.access.issue(hall.id)
    report(settings, hall)
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-3")
    open_players(ui)

    screens = cell(ui, hall, "Screens").locator("li")
    expect(screens).to_have_count(3)
    expect(screens.nth(2)).to_have_text(starting("HDMI 3 · ◌ not in its last report"), use_inner_text=True)
    expect(screens.nth(2)).to_have_text(ending(f"Shows {the_wall.name}"), use_inner_text=True)


def test_a_label_panel_is_listed_with_its_state_and_the_wall_it_captions(ui, services, settings, hall, the_wall):
    services.access.issue(hall.id)
    report(settings, hall, WITH_A_PANEL)
    open_players(ui)
    # One panel: its port is not named (§ Vocabulary names a panel by its Player).
    # The state and the wall, two parts: split by a line break or a tab, and nothing else in the cell.
    expect(cell(ui, hall, "Label panel")).to_have_text(
        re.compile("^" + re.escape("● answering, 800 × 480") + r"[\n\t]No wall$"), use_inner_text=True
    )

    services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    open_players(ui)
    panel = cell(ui, hall, "Label panel")
    expect(panel).to_have_text(ending(f"Captions {the_wall.name}"), use_inner_text=True)
    expect(panel).not_to_contain_text("epd-0", use_inner_text=True)
    expect(panel.get_by_role("link", name=the_wall.name)).to_have_attribute("href", f"#walls?wall={the_wall.id}")


#: Two label panels and no screen: the shape the owner's ruling 8 of 2026-11-19 keeps open.
TWO_PANELS = {
    "outputs": [],
    "label_outputs": [
        {"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]},
        {"name": "epd-1", "kind": "epaper", "connected": False, "size": None},
    ],
}


def test_a_player_with_only_label_panels_reads_panel_by_panel(ui, services, settings, hall):
    """Several panels and no screen read sensibly, each with its own state; one not connected is said, and is no trouble.

    Each panel's state is the server's (`state.outputs`, one per output). The
    one not connected is drawn as nothing there (○), never as a fault (▲), and
    Status, which lists the same Player, names it in no trouble.
    """
    services.access.issue(hall.id)
    report(settings, hall, TWO_PANELS)
    open_players(ui)

    expect(cell(ui, hall, "Status")).to_have_text(starting("● Reporting"), use_inner_text=True)
    expect(cell(ui, hall, "Screens")).to_have_text("It reported no screen.", use_inner_text=True)
    panels = cell(ui, hall, "Label panel").locator("li")
    # Two panels: each named by its port, since then it is what tells them apart.
    expect(panels).to_have_count(2)
    expect(panels.nth(0)).to_have_text(starting("epd-0 · ● answering, 800 × 480"), use_inner_text=True)
    expect(panels.nth(1)).to_have_text(starting("epd-1 · ○ not connected"), use_inner_text=True)
    expect(cell(ui, hall, "Label panel")).not_to_contain_text("▲", use_inner_text=True)

    ui.open("#health")
    outputs = ui.page.locator(f".players-reading li[data-player='{hall.id}'] li[data-kind='label']")
    expect(outputs).to_have_text(["Label panel epd-0 · ● answering", "Label panel epd-1 · ○ not connected"], use_inner_text=True)
    expect(ui.page.locator("#view .troubles")).not_to_contain_text("epd-1", use_inner_text=True)
    expect(ui.page.locator("#view .troubles")).not_to_contain_text(hall.name, use_inner_text=True)


def test_a_player_whose_report_names_its_settings_page_links_to_it_and_one_without_does_not(ui, services, settings, hall):
    """The address is the server's (`settings_url`, served only when it passes the contract's check), set as given.

    A link with no reference back to this page (`rel`), and its words this page's.
    A report with no address has no link at all: the page assembles none.
    """
    services.access.issue(hall.id)
    report(settings, hall, TWO_OUTPUTS)
    open_players(ui)
    expect(cell(ui, hall, "Status")).to_have_text(starting("● Reporting"), use_inner_text=True)
    expect(cell(ui, hall, "Player").locator("a")).to_have_count(0)

    address = "http://192.0.2.10:8771/"
    report(settings, hall, TWO_OUTPUTS | {"settings_url": address})
    open_players(ui)
    link = cell(ui, hall, "Player").get_by_role("link", name=f"{hall.name}'s settings page")
    expect(link).to_have_attribute("href", address)
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    expect(link).to_have_text("Its settings page", use_inner_text=True)


def test_a_script_in_a_players_settings_address_never_reaches_a_link(ui, services, settings, hall):
    """`javascript:` fails the contract's check: the server serves null, and the row carries no link (its report kept)."""
    services.access.issue(hall.id)
    report(settings, hall, TWO_OUTPUTS | {"settings_url": "javascript:alert(1)"})
    open_players(ui)

    # The report is kept, so the row is anchored on what it says first.
    expect(cell(ui, hall, "Status")).to_have_text(starting("● Reporting"), use_inner_text=True)
    expect(cell(ui, hall, "Player").locator("a")).to_have_count(0)
    expect(ui.page.locator("#view a[href^='javascript']")).to_have_count(0)


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
    expect(cell(ui, hall, "Player")).to_have_text("Study Pi", use_inner_text=True)
    expect(cell(ui, hall, "Screens")).to_contain_text(the_wall.name, use_inner_text=True)
    expect(ui.page.locator("#view [data-said]")).to_have_text(
        "Hall Pi is now called Study Pi. Its token and its walls are unchanged.", use_inner_text=True
    )


def test_a_refused_rename_is_said_in_the_dialog_and_changes_nothing(ui, services, hall):
    other = services.clients.add_client(name="Study Mac")
    open_players(ui)

    dialog = edit(ui, hall)
    dialog.get_by_label("Name", exact=True).fill("   ")
    rename = dialog.get_by_role("button", name="Rename Hall Pi")
    rename.click()
    assert "Couldn't rename Hall Pi" in ui.said_beside(rename)
    expect(dialog).to_be_visible()
    assert {view.client.name for view in services.clients.list_clients()} == {"Hall Pi", other.name}


def test_forgetting_asks_first_and_names_the_walls_left_without_a_player(ui, services, hall, the_wall, study, server_url):
    token = services.access.issue(hall.id).token
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.assign_wall(study.id, client_id=hall.id, output="hdmi-a-2")
    services.display.add_wall(name="Landing")
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Forget Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    expect(ui.page.locator("dialog.confirm .confirm-title")).to_have_text("Forget Hall Pi?", use_inner_text=True)
    expect(ui.page.locator("dialog.panel-dialog")).to_have_count(0)
    consequence = ui.page.locator("dialog.confirm .confirm-consequence")
    # In the order the server lists the Player's walls.
    first, second = (shown.wall.name for shown in services.clients.get_client_view(hall.id).walls)
    both = f"{first} and {second}"
    expect(consequence).to_contain_text(f"{both} will be left without a Player", use_inner_text=True)
    expect(consequence).to_have_text(starting("Its token stops working at once, and "), use_inner_text=True)
    expect(consequence).not_to_contain_text("Landing", use_inner_text=True)
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Forget Hall Pi')")
    ui.page.wait_for_selector("#view [data-said]")

    expect(ui.page.locator("#view [data-said]")).to_have_text(
        f"Hall Pi is forgotten. 2 walls now have no Player: {both}.", use_inner_text=True
    )
    assert services.clients.list_clients() == []
    assert services.clients.placement_of(study.id).client is None
    assert admitted(server_url, token) == 401


@pytest.mark.parametrize("leave", ["Cancel", "Escape"])
def test_declining_to_forget_keeps_the_player_and_its_walls(ui, services, hall, the_wall, leave):
    services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Forget Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    decline(ui, leave)

    assert [view.client.id for view in services.clients.list_clients()] == [hall.id]
    assert services.clients.placement_of(the_wall.id).client.id == hall.id
    expect(row(ui, hall)).to_be_visible()


def test_forgetting_a_player_that_shows_nothing_says_no_wall_is_affected(ui, hall):
    open_players(ui)

    edit(ui, hall).get_by_role("button", name="Forget Hall Pi…").click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    consequence = ui.page.locator("dialog.confirm .confirm-consequence")
    expect(consequence).to_contain_text("It shows no wall, so no wall is affected.", use_inner_text=True)
    expect(consequence).not_to_contain_text("left without a Player", use_inner_text=True)
    # Never issued one, so no token is said to stop.
    expect(consequence).to_have_text(starting("It has no token."), use_inner_text=True)
    expect(consequence).not_to_contain_text("token stops working", use_inner_text=True)


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
    # Left, not submitted: a request sent anyway would be in flight by now.
    ui.page.wait_for_load_state("networkidle")

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
    # Left, not submitted: a request sent anyway would be in flight by now.
    ui.page.wait_for_load_state("networkidle")

    assert services.clients.get_client(hall.id).name == "Hall Pi"
    assert services.clients.get_client(hall.id).token_issued_at == token.issued_at
    expect(cell(ui, hall, "Player")).to_have_text("Hall Pi", use_inner_text=True)
