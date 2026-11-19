"""Setting up a wall and its Player, in the order the screens give it.

Audit 2026-11-19, finding 2: Settings › Players › *Add Player…*, copy the token,
then Walls › *Edit…* › *Where it shows* › *Show it there* answered "output
cannot be empty", because the Player had not reported a screen yet and nothing
said so. This file walks that sequence and the states it passes through, each
reached for real: a Player added through the page, its token copied off the
page, its report written where a running Player leaves one.

**What each step must say is what it is waiting for.** An act that cannot work
yet is disabled with its reason in words beside it; the Players row and its
lead line say they wait for a report; the wall's card says which Player has not
reported. And the vocabulary half (F5, finding 8): no screen of the four says
*plane*, *heartbeat* or *display* for the Player, in any state seeded here.
"""

import json
import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

from arrt.programming.client_heartbeat import client_heartbeat_path_in

#: A running Player's report: two screens, the first with a television on it.
TWO_SCREENS = {
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}

#: Long enough for the dialog's ask-again (every 3 s) to see a report written
#: after it opened, with room for a loaded machine.
REPORT_ARRIVES_MS = 15_000


def report(settings, client, document=TWO_SCREENS):
    """What a running Player's report leaves under the art root, stamped now."""
    stamped = {"reported_at": datetime.now(UTC).isoformat(timespec="seconds")} | document
    client_heartbeat_path_in(settings.art_root, client.id).write_text(json.dumps(stamped), encoding="utf-8")


@pytest.fixture
def the_wall(services):
    return services.display.survey_walls()[0].wall


def card(ui, wall):
    return ui.page.locator(f"section.wall[data-wall='{wall.id}']")


def open_where(ui, wall):
    """Walls › the wall's *Edit…*, and its *Where it shows* parts."""
    ui.open("#walls")
    card(ui, wall).get_by_role("button", name=f"Edit {wall.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    expect(dialog).to_be_visible()
    return (
        dialog,
        dialog.get_by_label(f"Player for {wall.name}", exact=True),
        dialog.get_by_role("button", name=f"Show {wall.name} there"),
    )


def add_player(ui, name):
    ui.open("#clients")
    ui.page.get_by_role("button", name="Add Player…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label("Name", exact=True).fill(name)
    dialog.get_by_role("button", name="Add Player", exact=True).click()
    field = ui.page.get_by_label(f"Token for {name}", exact=True)
    expect(field).to_be_visible()
    return field


# -- the sequence, end to end ----------------------------------------------------


def test_a_wall_is_set_up_in_the_order_the_screens_give_it(ui, services, settings, server_url, the_wall):
    """Add the Player, copy its token, wait for its report, then put the wall on its screen.

    Each step says what comes next; the one that cannot work until the Player
    reports is disabled with that reason, and comes alive in the open dialog
    when the report arrives, without the household closing and reopening it.
    """
    ui.page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=server_url)
    field = add_player(ui, "Hall Pi")
    token = field.input_value()

    # Behind the dialog, already: the list holds the Player, waiting (finding 15).
    expect(ui.page.locator("#view .page-facts")).to_have_text("1 Player · waiting for it to report")
    [hall] = [view.client for view in services.clients.list_clients()]
    expect(ui.page.locator(f"#view tr[data-player='{hall.id}'] td[data-label='Status']")).to_contain_text(
        "Waiting for it to report"
    )

    ui.page.get_by_role("button", name="Copy Hall Pi's token").click()
    expect(ui.page.locator(".token-copied")).to_have_text("Copied.")
    assert ui.page.evaluate("() => navigator.clipboard.readText()") == token
    ui.page.get_by_role("button", name="Done").click()

    # The wall's card names the Player it waits on.
    ui.open("#walls")
    expect(card(ui, the_wall).locator("p.wall-waiting")).to_have_text(
        "Hall Pi has not reported yet. Its screens can be chosen here once it is running with its token and reports."
    )

    card(ui, the_wall).get_by_role("button", name=f"Choose the Player for {the_wall.name}…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option(hall.id)
    show = dialog.get_by_role("button", name=f"Show {the_wall.name} there")
    why = dialog.locator("p.wall-not-yet")
    expect(show).to_be_disabled()
    expect(why).to_have_text(
        "Hall Pi has not reported yet. It must be running with its token, from its own settings page; "
        "its screens appear here once it reports, usually within a minute of starting."
    )
    expect(show).to_have_attribute("aria-describedby", why.get_attribute("id"))

    # The Player starts and reports: the open dialog sees it.
    report(settings, hall)
    expect(show).to_be_enabled(timeout=REPORT_ARRIVES_MS)
    expect(why).to_be_hidden()
    screen = dialog.get_by_label("Screen", exact=True)
    expect(screen.locator("option")).to_have_text(["HDMI 1", "HDMI 2 · nothing connected"])

    show.click()
    expect(dialog).to_have_count(0)
    read = {each["wall_id"]: each for each in ui.page.evaluate("() => fetch('/api/walls').then((r) => r.json())")["walls"]}
    assert (read[the_wall.id]["client_id"], read[the_wall.id]["output"]) == (hall.id, "hdmi-a-1")
    expect(card(ui, the_wall).locator(".wall-problem")).to_have_count(0)


# -- Show it there, by what the chosen Player has said -------------------------


@pytest.mark.parametrize(
    ("given", "says"),
    [
        ("no token", "Hall Pi has no token yet, so it cannot report."),
        ("no report", "Hall Pi has not reported yet. It must be running with its token"),
        ("no screen", "Hall Pi reported no screen."),
        ("unreadable", "Hall Pi's last report could not be read, so its screens are not known."),
    ],
)
def test_show_it_there_is_disabled_with_its_reason_until_the_player_has_a_screen(ui, services, settings, the_wall, given, says):
    """Each way a Player can have no screen to offer, said in its own words, and the act refused before it is pressed."""
    hall = services.clients.add_client(name="Hall Pi")
    if given != "no token":
        services.access.issue(hall.id)
    if given == "no screen":
        report(settings, hall, {"outputs": []})
    if given == "unreadable":
        client_heartbeat_path_in(settings.art_root, hall.id).write_text("not json", encoding="utf-8")

    dialog, player, show = open_where(ui, the_wall)
    player.select_option(hall.id)

    expect(show).to_be_disabled()
    expect(dialog.locator("p.wall-not-yet")).to_contain_text(says)


def test_show_it_there_is_enabled_and_says_nothing_once_the_player_has_reported_a_screen(ui, services, settings, the_wall):
    """The paired case: a Player with a screen is offered, and no reason is drawn."""
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    report(settings, hall)

    dialog, player, show = open_where(ui, the_wall)
    player.select_option(hall.id)

    expect(show).to_be_enabled()
    expect(dialog.locator("p.wall-not-yet")).to_be_hidden()
    expect(show).not_to_have_attribute("aria-describedby", re.compile(".+"))
    # And None, which takes the wall off its Player, is never held back.
    player.select_option("")
    expect(show).to_be_enabled()


def test_the_card_says_nothing_of_waiting_once_the_player_has_reported(ui, services, settings, the_wall):
    """The card's waiting line is for a Player that has not reported; one that has is offered in Edit… without it."""
    hall = services.clients.add_client(name="Hall Pi")
    services.access.issue(hall.id)
    report(settings, hall)
    ui.open("#walls")

    expect(card(ui, the_wall).locator("p.wall-problem")).to_be_visible()
    expect(card(ui, the_wall).locator("p.wall-waiting")).to_have_count(0)


# -- the token ------------------------------------------------------------------


def test_copy_works_where_the_clipboard_api_is_absent(ui, services):
    """A household server is often reached over plain http, where `navigator.clipboard` does not exist.

    Taken away here as such a page would have it, and `execCommand('copy')`
    recorded: Copy must select the token and copy it the older way, not fail.
    """
    ui.page.add_init_script("""
        Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined, configurable: true });
        window.__copied = [];
        document.execCommand = (command) => {
          const field = document.activeElement;
          if (command === "copy" && field) window.__copied.push(field.value.slice(field.selectionStart, field.selectionEnd));
          return command === "copy";
        };
        """)
    field = add_player(ui, "Hall Pi")
    assert ui.page.evaluate("() => navigator.clipboard") is None

    ui.page.get_by_role("button", name="Copy Hall Pi's token").click()
    expect(ui.page.locator(".token-copied")).to_have_text("Copied.")
    assert ui.page.evaluate("() => window.__copied") == [field.input_value()]


def test_a_browser_that_will_not_copy_says_so_and_leaves_the_token_selected(ui, services):
    """The fallback's own failure is said, in words, with what to do instead."""
    ui.page.add_init_script("""
        Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined, configurable: true });
        document.execCommand = () => false;
        """)
    add_player(ui, "Hall Pi")

    ui.page.get_by_role("button", name="Copy Hall Pi's token").click()
    expect(ui.page.locator(".token-copied")).to_have_text(
        "This browser would not copy it. The token is selected: copy it with the keyboard."
    )
    assert ui.page.evaluate("() => document.activeElement.id") == "player-token"


# -- the words ------------------------------------------------------------------

#: The words a person never reads on Walls, Players, Status or the top bar
#: (`information-architecture.md` § Vocabulary; audit 2026-11-19, F5 and
#: finding 8): the retired architecture, the wire's word for a report, and a
#: Player called a display. Bare "display" is not refused, since a work is
#: displayable; "a display", "its display" and the like are what called the
#: Player one.
RETIRED = (
    re.compile(r"\bplanes?\b", re.IGNORECASE),
    re.compile(r"\bheartbeats?\b", re.IGNORECASE),
    re.compile(r"\b(?:a|its|no|the|any) display\b", re.IGNORECASE),
)


def _a_hung_wall(seed):
    """A theme holding one work hung on the wall: its feed is written, and nothing yet shows it."""
    theme = seed.services.display.add_theme(name="Winter")
    work = seed.service.add_artwork(title="Nighthawks")
    seed.services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    seed.services.display.activate_theme(theme.id, wall_id=seed.wall.id)


def _a_waiting_player(seed, *, assign=False):
    hall = seed.services.clients.add_client(name="Hall Pi")
    seed.services.access.issue(hall.id)
    if assign:
        seed.services.clients.assign_wall(seed.wall.id, client_id=hall.id, output="hdmi-a-1")
    return hall


def _state_nothing_set_up(seed):
    pass


def _state_no_player_hung(seed):
    _a_hung_wall(seed)


def _state_a_player_waiting(seed):
    _a_hung_wall(seed)
    _a_waiting_player(seed)


def _state_a_player_silent_on_the_wall(seed):
    _a_hung_wall(seed)
    _a_waiting_player(seed, assign=True)


def _state_a_report_unreadable(seed):
    _a_hung_wall(seed)
    hall = _a_waiting_player(seed, assign=True)
    client_heartbeat_path_in(seed.settings.art_root, hall.id).write_text("not json", encoding="utf-8")
    seed.ui.serve(
        "**/api/health",
        seed.a_health_reading(
            walls=[seed.a_wall_reading(wall_id=seed.wall.id, name=seed.wall.name, problem="the file is not JSON")]
        ),
    )


def _state_the_reading_names_no_wall(seed):
    _a_hung_wall(seed)
    _a_waiting_player(seed, assign=True)
    seed.ui.serve("**/api/health", seed.a_health_reading(walls=[]))


def _state_the_reading_fails(seed):
    _a_hung_wall(seed)
    seed.ui.serve("**/api/health", (500, {"error": "the reading could not be taken"}))


def _state_the_feed_is_refused(seed):
    _a_hung_wall(seed)
    seed.ui.serve("**/api/manifest*", (500, {"error": "the theme could not be evaluated"}))


def _state_a_player_reporting(seed):
    _a_hung_wall(seed)
    hall = _a_waiting_player(seed, assign=True)
    report(seed.settings, hall)


STATES = {
    "nothing set up": _state_nothing_set_up,
    "no Player, a theme hung": _state_no_player_hung,
    "a Player waiting for its report": _state_a_player_waiting,
    "a Player on the wall, silent": _state_a_player_silent_on_the_wall,
    "a report that cannot be read": _state_a_report_unreadable,
    "a reading that names no wall": _state_the_reading_names_no_wall,
    "the reading not arriving": _state_the_reading_fails,
    "the feed refused": _state_the_feed_is_refused,
    "a Player reporting": _state_a_player_reporting,
}

#: Each page the words are read on, and the one it waits for. The wall's
#: *Edit…* is opened on Walls, since its *Where it shows* says what the Player
#: reported.
PAGES = {
    "walls": ("#walls", "#view h1:text-is('Walls')"),
    "edit": ("#walls", "#view h1:text-is('Walls')"),
    "players": ("#clients", "#view h1:text-is('Players')"),
    # A reading that does not arrive is the page's banner, not its name.
    "status": ("#health", "#view h1:text-is('Status'), main [role='alert']:not(:empty)"),
}


@pytest.mark.parametrize("screen", list(PAGES))
@pytest.mark.parametrize("state", list(STATES))
def test_no_retired_word_is_read_on_these_screens(
    ui, services, service, settings, the_wall, a_health_reading, a_wall_reading, state, screen
):
    """Every string the page and the top bar render, in each seeded state, scanned for the retired words."""
    seed = SimpleNamespace(
        ui=ui,
        services=services,
        service=service,
        settings=settings,
        wall=the_wall,
        a_health_reading=a_health_reading,
        a_wall_reading=a_wall_reading,
    )
    STATES[state](seed)
    fragment, painted = PAGES[screen]
    ui.open(fragment)
    expect(ui.page.locator(painted).first).to_be_visible()
    if fragment == "#walls":
        expect(ui.page.locator("section.wall .wall-controls, #view button:text-is('Ask again')").first).to_be_visible()
    if screen == "edit":
        card(ui, the_wall).get_by_role("button", name=f"Edit {the_wall.name}…").click()
        expect(ui.page.locator("dialog.panel-dialog[open]")).to_be_visible()
    expect(ui.page.locator("#status .status-words")).not_to_be_empty()

    text = ui.page.evaluate("() => document.body.innerText")
    found = [match.group(0) for pattern in RETIRED for match in pattern.finditer(text)]
    assert not found, f"{screen} with {state} says {found}"


def test_the_backup_records_file_is_named_only_with_debug(ui, a_health_reading):
    """Finding 8: Status printed the backup record's path, a file under a temporary directory, to a household.

    With no backup, and with a record that cannot be read, the server's sentence
    names the file; it is debug's then, and the page says it in words.
    """
    for backup in ({"absent": True}, {"absent": False, "problem": "the record is not JSON"}):
        reading = a_health_reading()
        reading["backup"].update(
            absent=backup["absent"],
            problem=backup.get("problem"),
            completed_at=None,
            age_seconds=None,
            reported=None,
            description="No backup has been recorded at /srv/arrt-scratch-9f2/backup-receipt.json; nothing has written one yet.",
        )
        ui.serve("**/api/health", reading)
        ui.open("#health")
        expect(ui.page.locator("#view h2:text-is('Backup')")).to_be_visible()
        assert "/srv/arrt-scratch-9f2/backup-receipt.json" not in ui.page.locator("#view").inner_text()

        ui.open("?debug#health")
        expect(ui.page.locator("#view h2:text-is('Backup')")).to_be_visible()
        assert "/srv/arrt-scratch-9f2/backup-receipt.json" in ui.page.locator("#view").inner_text()


def test_status_says_the_picture_counts_age_once(ui, a_health_reading):
    """Finding 20: "counted 226 seconds ago" and "Counted 4 minutes ago" on one panel."""
    reading = a_health_reading()
    reading["pictures"].update(age_seconds=226.0, description="The picture store keeps 2 files, counted 226 seconds ago.")
    ui.serve("**/api/health", reading)
    ui.open("#health")

    panel = ui.page.locator(".pictures-reading")
    expect(panel).to_contain_text("counted 226 seconds ago")
    assert len(re.findall(r"\bcounted\b", panel.inner_text(), flags=re.IGNORECASE)) == 1


# -- hanging, before and after a Player shows the wall ------------------------------


@pytest.mark.parametrize("shown", [False, True], ids=["no Player", "a Player"])
def test_hanging_a_work_promises_the_house_sees_it_only_where_a_player_shows_the_wall(
    ui, services, work_with_an_image, the_wall, shown
):
    """Finding 19 of audit 2026-11-19, the client half, through the Work page's *Hang…* (`core/selection.js`).

    "Everyone in the house sees {wall} change" is true of a wall a Player shows,
    and of nothing else: with no Player, the question says nothing shows it yet.
    """
    work = work_with_an_image("Automat")
    if shown:
        hall = services.clients.add_client(name="Hall Pi")
        services.clients.assign_wall(the_wall.id, client_id=hall.id, output="hdmi-a-1")
    ui.open(f"#work/{work.id}")
    ui.page.locator(".page-toolbar button:text-is('Hang…')").click()

    consequence = ui.page.locator("dialog.confirm[open] .confirm-consequence")
    if shown:
        expect(consequence).to_contain_text(f"Everyone in the house sees {the_wall.name} change.")
        expect(consequence).not_to_contain_text("No Player shows")
    else:
        expect(consequence).to_contain_text(f"No Player shows {the_wall.name} yet, so nothing shows it until one does.")
        expect(consequence).not_to_contain_text("Everyone in the house")
