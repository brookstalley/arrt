"""The health panel with more than one wall, in a real browser.

**The panel is where "which wall is silent" is actually answered**, and neither
Python suite runs a line of the client that answers it. The JSON tests assert
that `GET /api/health` carries one reading per wall; whether the page puts the
room's *name* in front of a reader, or renders two indistinguishable blocks of
label/value pairs, is not expressible as JSON.

That distinction is the whole reason the heartbeat became one file per wall. One
shared file would have had the second display overwrite the first's report every
minute, so a wall that had gone dark read exactly like a wall that was fine — and
a panel that shows two readings without naming them reintroduces that at the last
step, on the surface built to prevent it.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect


@pytest.fixture
def two_walls(services):
    """The wall a fresh catalogue holds, and a study the curator recorded."""
    living_room = services.display.survey_walls()[0].wall
    return living_room, services.display.add_wall(name="Study")


def _reported(settings, wall, *, ago_seconds: float = 0.0) -> None:
    """Put a heartbeat where the display serving that wall would have put one."""
    settings.heartbeat_path(wall.id).write_text(
        json.dumps({"reported_at": (datetime.now(UTC) - timedelta(seconds=ago_seconds)).isoformat()}),
        encoding="utf-8",
    )


def test_the_panel_names_every_wall_it_is_reporting_on(ui, settings, two_walls):
    """Two rooms, two named readings — not two anonymous blocks of facts.

    The name is what makes a reading actionable: "the study has not reported"
    sends somebody into a room, and an age with no room attached does not.
    """
    living_room, study = two_walls
    _reported(settings, living_room)

    ui.open("#health")
    ui.page.wait_for_selector("h1:has-text('Status')")

    # `.wall-reading h2` since the client was split into modules: each wall's
    # reading became a panel of its own with its name as the heading, where it had
    # been an `h3` inside a shared "The walls" panel.
    #
    # **Set equality, not a subset.** This assertion was briefly relaxed to `<=`
    # while moving it to `.panel h2` — which selects the backup and geometry
    # panels too, so exactness was impossible there and the `==` half went with
    # it. That half is the one that catches a wall panel which should not exist:
    # a subset check passes against a screen naming a room that is not in the
    # catalogue. The selector, not the assertion, was what needed to change.
    #
    # Retried as: exactly two wall headings, and each of the two names is one of
    # them, whole, which is that set and no other.
    expect(ui.page.locator(".wall-reading h2")).to_have_count(2)
    for name in (living_room.name, study.name):
        expect(ui.page.locator(".wall-reading h2").filter(has_text=re.compile(rf"^\s*{re.escape(name)}\s*$"))).to_have_count(1)


def _on_a_player(services, *walls) -> None:
    """Put each wall on one of a reporting Player's screens, as Walls › Edit… does: only then is a report expected of it.

    The Player has reported (Chunk 62): one that has not, or has no token, is
    still being set up, and a wall it shows that has never reported waits for
    it rather than being called quiet (`test_a_wall_waiting_for_its_player_…`).
    """
    player = services.clients.add_client(name="The Pi in the hall")
    services.access.issue(player.id)
    for index, wall in enumerate(walls, start=1):
        services.clients.assign_wall(wall.id, client_id=player.id, output=f"hdmi-a-{index}")
    outputs = [
        {"name": f"hdmi-a-{index}", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]}
        for index in range(1, len(walls) + 1)
    ]
    services.clients.record_heartbeat(player.id, {"reported_at": datetime.now(UTC).isoformat(), "outputs": outputs})


def test_the_summary_names_the_wall_that_has_gone_quiet(ui, settings, services, two_walls):
    """The sentence a reader takes away, with the room in it.

    Before the split this could only ever have said that *a* display plane had
    not reported, which on a two-room installation is a fact nobody can act on.
    Both walls are on a Player: one with none is a step of setting up, and is
    never named as quiet (below).
    """
    living_room, study = two_walls
    _on_a_player(services, living_room, study)
    _reported(settings, living_room)

    ui.open("#health")
    ui.page.wait_for_selector(f".panel h2:has-text('{study.name}')")

    expect(ui.view).to_contain_text(f"{study.name!r} has not reported", use_inner_text=True)


def test_the_summary_never_names_a_wall_no_player_shows_as_quiet(ui, settings, two_walls):
    """A wall with no Player yet is `unassigned` (`vocabulary.json`), so the summary does not call it quiet."""
    living_room, study = two_walls
    _reported(settings, living_room)

    ui.open("#health")
    ui.page.wait_for_selector(f".panel h2:has-text('{study.name}')")

    expect(ui.view).to_contain_text("No Player shows a wall yet, so there is no report to read.", use_inner_text=True)
    expect(ui.view).not_to_contain_text(f"{study.name!r} has not reported", use_inner_text=True)
    # Its own panel says the step, in the contract's word, and the top bar says it as a step to take
    # (the server's `setup_steps`, chunk 41), never as a wall gone quiet. It named nothing of the
    # wall until then, and asserted the study's name was absent from it.
    panel = ui.page.locator(".wall-reading", has=ui.page.locator(f"h2:has-text('{study.name}')"))
    expect(panel.locator(".wall-state")).to_have_text(re.compile(r"No Player yet$"), use_inner_text=True)
    # Anchored on what the top bar does say of this deployment (no backup has run).
    expect(ui.page.locator("#status")).to_contain_text("The Library has never been backed up", use_inner_text=True)
    expect(ui.page.locator("#status .status-setup")).to_have_text(
        re.compile(rf"{study.name} has no Player yet"), use_inner_text=True
    )
    expect(ui.page.locator("#status .status-words")).not_to_contain_text(study.name, use_inner_text=True)
    expect(ui.page.locator("#status")).not_to_contain_text("has not reported", use_inner_text=True)


def test_a_wall_that_has_never_reported_says_so_without_a_verdict(ui, settings, services, two_walls):
    """Absent is a true reading, and never a fault or a colour.

    A wall no display has been pointed at yet is the state of every second room
    between recording it and configuring the device, and it must read as that
    rather than as something broken: `unassigned`, worded "No Player yet"
    (`vocabulary.json`), a setup step. The living room is on a Player, since only
    a Player reports, and its report is four days old.
    """
    living_room, study = two_walls
    _on_a_player(services, living_room)
    _reported(settings, living_room, ago_seconds=4 * 24 * 60 * 60)

    ui.open("#health")
    # Wait on the wall that never reported: it is the one this test is about, and
    # waiting on the other would let the assertions run before its panel painted.
    ui.page.wait_for_selector(f".panel h2:has-text('{study.name}')")

    # In the household's words (audit 2026-11-19, F5): a Player reports for a
    # wall; "heartbeat" and "display" for the Player are retired. It read "No
    # Player has ever reported for this wall." until audit wave 2b (chunk 31):
    # that is still said of a wall a Player shows that has never reported
    # (`test_the_sidebar.py`), and a wall no Player shows has its own state.
    panel = ui.page.locator(".wall-reading", has=ui.page.locator(f"h2:has-text('{study.name}')"))
    expect(panel.locator(".wall-state")).to_have_text(re.compile(r"^○\s*No Player yet$"), use_inner_text=True)
    expect(panel.locator(".wall-state")).to_have_class(re.compile(r"\bsetup\b"))
    expect(panel).to_contain_text("No Player shows this wall yet, so there is no report to read.", use_inner_text=True)
    expect(panel).not_to_contain_text("has not reported", use_inner_text=True)
    # The age in the unit a person reads it in, on the wall that *did* report.
    expect(ui.view).to_contain_text("4 days ago", use_inner_text=True)
    # Never a green dot. The panel states what was found and how long ago; whether
    # four days is alarming depends on whether that television was switched off on
    # purpose, which this plane does not know.
    # As words: a whitespace-separated word that is one of them, which is what splitting the page found.
    expect(ui.view).not_to_contain_text(re.compile(r"(?<!\S)(?:healthy|degraded|OK)(?!\S)"), use_inner_text=True)


@pytest.mark.parametrize(
    ("player", "state"),
    [({"token_issued": False}, "no_token"), ({"absent": True}, "awaiting_report")],
    ids=["no_token", "awaiting_report"],
)
def test_a_player_being_set_up_that_shows_two_walls_reads_as_one_step_everywhere(
    ui, a_health_reading, a_wall_reading, player, state
):
    """Chunk 62's acceptance on the screens: one step naming both walls, each wall's panel waiting, and no problem anywhere.

    Before, this household read three steps on the top bar ("System: 3 steps
    to finish") and each wall's panel read "▲ Not reporting" beside "Nothing
    needs attention". Every word here is the server's (`a_health_reading`
    builds through its functions); the page decides nothing.
    """
    reading = a_health_reading(
        walls=[
            a_wall_reading(wall_id="wall-1", name="The hall", absent=True),
            a_wall_reading(wall_id="wall-2", name="The study", absent=True),
        ],
        player=player,
    )
    assert reading["troubles"] == []
    [step] = reading["setup_steps"]
    assert (step["about"], step["state"]) == ("player", state)
    assert "The hall and The study" in step["words"]
    waits = {wall["wall_name"]: wall["waiting_for"] for wall in reading["walls"]}
    ui.serve("**/api/health", reading)
    ui.open("#health")
    ui.page.wait_for_selector("#view .setup-steps li")

    # The top bar and the System link: setting up, one step, no problem.
    expect(ui.page.locator("#status")).to_have_attribute("data-state", "setup")
    expect(ui.page.locator("#status .status-words")).to_have_text(step["words"], use_inner_text=True)
    system = ui.page.locator("nav.sidebar a.section-link[data-view='health']")
    expect(system).to_have_attribute("aria-label", "System: 1 step to finish")
    expect(system.locator(".status-count")).to_have_count(0)
    # Status: the one step, linked to the Player; nothing needs attention.
    expect(ui.page.locator("#view .setup-steps li .step-words")).to_have_text([step["words"]], use_inner_text=True)
    expect(ui.page.locator("#view .setup-steps li a")).to_have_attribute("href", "#clients?client=player-1")
    expect(ui.page.locator("#view .troubles")).to_contain_text("Nothing needs attention.", use_inner_text=True)
    # Each wall's panel says it waits, with a step's mark, in the server's words, linking to its Player.
    for name in ("The hall", "The study"):
        panel = ui.page.locator(".wall-reading", has=ui.page.locator(f"h2:has-text('{name}')"))
        line = panel.locator(".wall-state")
        expect(line).to_have_text(re.compile(rf"^○\s*{re.escape(waits[name]['words'])}$"), use_inner_text=True)
        expect(line).to_have_class(re.compile(r"\bsetup\b"))
        expect(line).to_have_attribute("data-state", state)
        expect(line.locator("a")).to_have_attribute("href", "#clients?client=player-1")
        expect(panel).not_to_contain_text("Not reporting", use_inner_text=True)
        expect(panel).not_to_contain_text("No Player has ever reported", use_inner_text=True)
    # Nothing on the page is drawn as a problem, and its sentence says the walls wait.
    expect(ui.view, "a problem's mark somewhere on the page").not_to_contain_text("▲", use_inner_text=True)
    expect(ui.view).not_to_contain_text("has not reported", use_inner_text=True)
    expect(ui.view).to_contain_text(reading["description"], use_inner_text=True)


def test_the_panel_states_every_installed_source_plugin_in_words(ui, a_health_reading, a_source_reading):
    """Declined, failed and loaded each as its own row, the state a word and never only a colour.

    A row rather than a sentence since the owner's ruling of 2026-10-08 (#265):
    a box per source was too long. What the sentence carried is still on the
    row: the state in words, the reason a plugin is not working here, and the
    fault count (`test_the_status_sources_table.py` holds it at every width).
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            sources=[
                a_source_reading(name="commons", state="declined", reason="WIKIDATA_USER_AGENT is unset"),
                a_source_reading(name="artic", faults=3),
                a_source_reading(name="gallery", state="failed", reason="it could not be imported"),
            ]
        ),
    )
    ui.open("#health")
    ui.page.wait_for_selector(".source-table tbody tr")

    def cell(text):
        """A cell's words whole, trimmed as before; a line break in them is the claim, so a pattern holds it."""
        if "\n" not in text:
            return text
        return re.compile(r"^\s*" + r"\n".join(re.escape(line) for line in text.split("\n")) + r"\s*$")

    expected = [
        ["Wikimedia Commons\nWIKIDATA_USER_AGENT is unset", "Not configured here", "—"],
        ["Art Institute of Chicago", "Loaded", "3"],
        ["gallery\nit could not be imported", "Could not be loaded", "—"],
    ]
    rows = ui.page.locator(".source-table tbody tr")
    expect(rows).to_have_count(len(expected))
    for index, words in enumerate(expected):
        cells = rows.nth(index).locator("td.col-source, td.col-state, td.col-faults")
        expect(cells).to_have_text([cell(text) for text in words], use_inner_text=True)


def test_the_panel_says_when_no_source_plugin_is_installed(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading(sources=[]))
    ui.open("#health")
    ui.page.wait_for_selector("h2:has-text('Image sources')")

    expect(ui.view).to_contain_text("No source plugin is installed", use_inner_text=True)


def test_the_panel_states_how_much_the_picture_store_keeps(ui, services):
    """The store has no ceiling, so its growth is watched here: files, bytes, and the count's age.

    Against the real server: two pictures kept are four files (two sizes each),
    and the page shows the count the store's own walk produced, not a canned one.
    """
    from io import BytesIO

    from PIL import Image

    for name in ("one", "two"):
        buffer = BytesIO()
        Image.new("RGB", (900, 600), (90, 70, 140)).save(buffer, format="JPEG")
        services.pictures.put("artic", f"https://museum.example/{name}", buffer.getvalue())
    expected = services.pictures.size()

    ui.open("#health")
    ui.page.wait_for_selector(".pictures-reading")
    panel = ui.page.locator(".pictures-reading")

    assert expected.pictures_files == 4
    expect(panel).to_contain_text("Kept pictures", use_inner_text=True)
    expect(panel).to_contain_text("4 files", use_inner_text=True)
    expect(panel).to_contain_text(f"{expected.pictures_bytes:,}", use_inner_text=True)


def test_a_reading_without_the_store_count_says_so(ui, a_health_reading):
    """A payload missing the field is a fault in the reading, stated rather than thrown."""
    reading = a_health_reading()
    del reading["pictures"]
    ui.serve("**/api/health", reading)

    ui.open("#health")
    ui.page.wait_for_selector("h1:has-text('Status')")

    expect(ui.view).to_contain_text("carries no count of kept pictures", use_inner_text=True)


def test_a_store_the_disk_refused_shows_what_could_not_be_read(ui, a_health_reading):
    """An unreadable store must not read as an empty one: the entries refused are a fact of their own."""
    reading = a_health_reading()
    reading["pictures"].update(unreadable=3, description="The picture store could not be read in full.")
    ui.serve("**/api/health", reading)

    ui.open("#health")
    ui.page.wait_for_selector(".pictures-reading")
    panel = ui.page.locator(".pictures-reading")

    expect(panel).to_contain_text("could not be read in full", use_inner_text=True)
    expect(panel).to_contain_text("Could not be read", use_inner_text=True)
    expect(panel).to_contain_text("3 entries", use_inner_text=True)


def test_a_healthy_store_shows_no_could_not_be_read_fact(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())

    ui.open("#health")
    ui.page.wait_for_selector(".pictures-reading")

    panel = ui.page.locator(".pictures-reading")
    # The panel has its own words before its absence means anything.
    expect(panel).to_contain_text("Kept pictures", use_inner_text=True)
    expect(panel).not_to_contain_text("Could not be read", use_inner_text=True)
