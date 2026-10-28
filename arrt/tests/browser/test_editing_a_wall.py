"""A wall's Edit… dialog and Add wall…, in a real browser against a real server.

The owner's rulings of 2026-10-27 (`ia-proposal.md`, rulings 1 and 4) put a wall's
settings in one dialog opened from its card, and gave the page a way to add a
wall. Each part of the dialog is set by its own act; every test here reads the
result back from the server rather than from the page, with a value that is not
the default, so a control that changed only the page would fail.
"""

import json
from datetime import UTC, datetime

import pytest

from arrt.persistence.records import MatMethod, RenditionKind
from arrt.programming.client_heartbeat import client_heartbeat_path_in

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

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
    assert ui.page.locator("dialog.panel-dialog").count() == 0


def test_a_taken_name_is_refused_beside_the_field_and_nothing_changes(ui, services, the_wall):
    services.display.add_wall(name="Study")
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("Study")
    dialog.get_by_role("button", name=f"Rename {the_wall.name}").click()

    failure = dialog.locator(".act-failure")
    failure.wait_for()
    assert "Another wall is already called 'Study'." in failure.inner_text()
    assert services.display.get_wall(the_wall.id).name == the_wall.name


def test_where_it_shows_puts_the_wall_on_a_players_screen_and_none_takes_it_off(ui, services, the_wall, hall):
    dialog = open_edit(ui, the_wall.name)
    player = dialog.get_by_label(f"Player for {the_wall.name}", exact=True)
    assert player.input_value() == ""
    player.select_option(hall.id)
    screen = dialog.get_by_label("Screen", exact=True)
    assert screen.locator("option").all_inner_texts() == ["hdmi-a-1", "hdmi-a-2 · nothing connected"]
    # Not the first screen offered, so a picker that sent its default would fail.
    screen.select_option("hdmi-a-2")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    read = walls_read(ui)[the_wall.id]
    assert (read["client_id"], read["output"]) == (hall.id, "hdmi-a-2")
    # The card is repainted from that, and no longer says no Player shows it.
    card(ui, the_wall.name).locator(".wall-problem").wait_for(state="detached")

    dialog = open_edit(ui, the_wall.name)
    assert dialog.get_by_label(f"Player for {the_wall.name}", exact=True).input_value() == hall.id
    assert dialog.get_by_label("Screen", exact=True).input_value() == "hdmi-a-2"
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option("")
    dialog.get_by_role("button", name=f"Show {the_wall.name} there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert walls_read(ui)[the_wall.id]["client_id"] is None
    problem = card(ui, the_wall.name).locator(".wall-problem")
    problem.wait_for()
    assert problem.inner_text().startswith("No Player shows this wall.")


def test_a_label_panel_is_added_from_the_dialog_and_stopped_there(ui, services, settings, the_wall, hall):
    # A label panel the Player has, captioning nothing: added, then stopped, which
    # leaves it recorded (`remove_label`), as a Player that reported one would.
    labelled = services.clients.add_label(the_wall.id, client_id=hall.id, output="epd-0")
    services.clients.remove_label(the_wall.id, label_id=labelled.label.id)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label(f"Caption {the_wall.name} with", exact=True).select_option(label="epd-0 on Hall Pi")
    dialog.get_by_role("button", name=f"Caption {the_wall.name} with this label panel").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    [label] = walls_read(ui)[the_wall.id]["labels"]
    assert (label["output"], label["client_id"]) == ("epd-0", hall.id)

    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_role("button", name=f"Stop epd-0 captioning {the_wall.name}").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")
    assert walls_read(ui)[the_wall.id]["labels"] == []


def test_escape_closes_the_dialog_and_changes_nothing(ui, services, the_wall, hall):
    dialog = open_edit(ui, the_wall.name)
    dialog.get_by_label("Name", exact=True).fill("Not saved")
    dialog.get_by_label(f"Player for {the_wall.name}", exact=True).select_option(hall.id)
    ui.page.keyboard.press("Escape")
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    assert services.display.get_wall(the_wall.id).name == the_wall.name
    assert walls_read(ui)[the_wall.id]["client_id"] is None


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


def test_a_wall_added_here_can_be_put_on_a_screen_and_hung_and_its_feed_is_published(ui, services, hall, a_theme_to_hang):
    """Add wall…, then its Edit… and its Hanging picker: the new wall ends with a published feed."""
    ui.open("#walls")
    ui.page.get_by_role("button", name="Add wall…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.get_by_label("Name", exact=True).fill("Study")
    dialog.get_by_role("button", name="Add wall").click()
    card(ui, "Study").wait_for()
    study = next(view.wall for view in services.display.survey_walls() if view.wall.name == "Study")

    dialog = open_edit(ui, "Study")
    dialog.get_by_label("Player for Study", exact=True).select_option(hall.id)
    dialog.get_by_label("Screen", exact=True).select_option("hdmi-a-1")
    dialog.get_by_role("button", name="Show Study there").click()
    ui.page.locator("dialog.panel-dialog").wait_for(state="detached")

    ui.page.select_option(f"select#hang-{study.id}", a_theme_to_hang.id)
    ui.page.locator("dialog.confirm[open]").get_by_role("button", name="Hang").click()
    card(ui, "Study").locator(".wall-hanging dt:text-is('Changes')").wait_for()

    assert walls_read(ui)[study.id]["client_id"] == hall.id
    assert services.display.hanging_on(study.id).id == a_theme_to_hang.id
    assert services.display.published_manifest_v2(study.id) is not None


def test_adding_a_wall_with_a_taken_name_is_refused_in_the_dialog(ui, services, the_wall):
    ui.open("#walls")
    ui.page.get_by_role("button", name="Add wall…").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.get_by_label("Name", exact=True).fill(the_wall.name)
    dialog.get_by_role("button", name="Add wall").click()

    failure = dialog.locator(".act-failure")
    failure.wait_for()
    assert f"Another wall is already called '{the_wall.name}'." in failure.inner_text()
    assert len(services.display.survey_walls()) == 1
