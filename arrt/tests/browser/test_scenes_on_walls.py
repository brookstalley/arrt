"""The Scene on Walls, in a real browser, against a real server.

The owner's first use (2026-10-26): two walls switching together to works picked
by hand. Picked here, a work per wall, then applied, released, and refused; what
each act does to the feeds is `tests/unit/test_scenes.py`'s, and here it is the
screen: that each control names its wall, that Apply asks first naming each wall
and its work, and that the section says what the walls did.
"""

import re
from datetime import UTC, datetime

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def two_walls(services, ready_work, wall_id):
    """The wall and the study, each hanging a theme of its own, and two works to pick that neither holds."""
    display = services.display
    study = display.add_wall(name="Study").id
    for wall, title in ((wall_id, "Automat"), (study, "Chop Suey")):
        theme = display.add_theme(name=f"{title}'s theme")
        display.add_to_theme(theme_id=theme.id, artwork_id=ready_work(title).id)
        display.activate_theme(theme.id, wall_id=wall)
    return {"The wall": wall_id, "Study": study}, ready_work("Persistence"), ready_work("Golconda")


def _pick(ui, wall_name, words, title):
    row = ui.page.locator(f"section.scene .scene-wall:has(.scene-wall-name:text-is('{wall_name}'))")
    row.get_by_role("searchbox", name=f"Find a work for {wall_name}").fill(words)
    row.get_by_role("button", name=f"Search the library for {wall_name}").click()
    row.get_by_role("button", name=f"Pick {title} for {wall_name}").click()
    ui.page.locator(
        f"section.scene .scene-wall:has(.scene-wall-name:text-is('{wall_name}')) .scene-pick:has-text('{title}')"
    ).wait_for()


def test_two_walls_are_picked_applied_together_and_released(ui, two_walls, services):
    walls, persistence, golconda = two_walls
    ui.open("#walls")
    ui.page.wait_for_selector("section.scene")

    _pick(ui, "The wall", "Persistence", "Persistence")
    _pick(ui, "Study", "Golconda", "Golconda")
    assert "Preparing the walls" in ui.page.locator("section.scene").inner_text()

    ui.page.get_by_role("button", name="Apply the scene").click()
    dialog = ui.page.locator("dialog.confirm[open]")
    dialog.wait_for()
    assert "Persistence on The wall" in dialog.inner_text()
    assert "Golconda on Study" in dialog.inner_text()
    assert "for 20 minutes" in dialog.inner_text()
    dialog.get_by_role("button", name="Apply").click()

    ui.page.locator("section.scene .scene-span").wait_for()
    section = ui.page.locator("section.scene").inner_text()
    assert "Scene until " in section
    assert "Persistence on The wall" in section
    assert "Golconda on Study" in section
    assert "The wall has not shown it yet" in section
    live = services.display.live_scene()
    assert {pin.wall_id: pin.work_id for pin in live.pins} == {walls["The wall"]: persistence.id, walls["Study"]: golconda.id}
    # Each wall's card says the scene is up there, beside Skip.
    card = ui.page.locator(f"section.wall[data-wall='{walls['Study']}'] .wall-scene")
    assert "A scene shows Golconda here until " in card.inner_text()

    release = ui.page.get_by_role("button", name=re.compile(r"^Release the scene on "))
    # Both walls, in the order their cards are in.
    assert release.get_attribute("aria-label") == "Release the scene on Study and The wall"
    release.click()
    ui.page.locator("section.scene .scene-span").wait_for(state="detached")
    assert services.display.live_scene() is None
    assert ui.page.locator("section.scene .scene-pick").all_inner_texts() == ["Nothing picked.", "Nothing picked."]
    assert ui.page.locator(".wall-scene").count() == 0


def test_hold_asks_naming_each_wall_and_has_no_end(ui, two_walls, services):
    ui.open("#walls")
    ui.page.wait_for_selector("section.scene")
    _pick(ui, "Study", "Golconda", "Golconda")

    ui.page.get_by_role("button", name="Hold the scene until released").click()
    dialog = ui.page.locator("dialog.confirm[open]")
    dialog.wait_for()
    assert "Golconda on Study, until you release it." in dialog.inner_text()
    dialog.get_by_role("button", name="Hold").click()

    ui.page.locator("section.scene .scene-span").wait_for()
    assert ui.page.locator("section.scene .scene-span").inner_text() == "Scene, held until released"
    assert services.display.live_scene().scene.until is None


def test_a_refused_pick_says_why_beside_that_wall_and_keeps_the_other(ui, two_walls, ready_work, services):
    walls, _, golconda = two_walls
    ready_work("Unprepared", master=False)
    ui.open("#walls")
    ui.page.wait_for_selector("section.scene")
    _pick(ui, "Study", "Golconda", "Golconda")

    row = ui.page.locator("section.scene .scene-wall:has(.scene-wall-name:text-is('The wall'))")
    row.get_by_role("searchbox", name="Find a work for The wall").fill("Unprepared")
    row.get_by_role("button", name="Search the library for The wall").click()
    row.get_by_role("button", name="Pick Unprepared for The wall").click()

    failure = row.locator(".act-failure")
    failure.wait_for()
    assert "cannot be shown on the wall" in failure.inner_text()
    assert {pin.wall_id: pin.work_id for pin in services.display.scene_draft().pins} == {walls["Study"]: golconda.id}
    assert (
        "Golconda" in ui.page.locator("section.scene .scene-wall:has(.scene-wall-name:text-is('Study')) .scene-pick").inner_text()
    )


def test_a_wall_somebody_is_watching_television_on_says_it_is_waiting(ui, two_walls, services):
    walls, persistence, _ = two_walls
    display = services.display
    # On a client's output, as a real wall is: a wall on no screen is unassigned, not in use.
    client = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(walls["The wall"], client_id=client.id, output="hdmi-a-1")
    draft = display.draft_scene().scene
    display.pin_scene(draft.id, walls["The wall"], persistence.id)
    display.apply_scene(draft.id, lifetime="hold")
    now = datetime.now(UTC).isoformat()
    display.record_heartbeat(
        walls["The wall"],
        {
            "schema": {"major": 1, "minor": 3},
            "reported_at": now,
            "current_work_id": None,
            "scene_id": None,
            "display_state": {"state": "in_use", "work_id": None, "since": now},
        },
    )

    ui.open("#walls")
    ui.page.locator("section.scene .scene-span").wait_for()

    assert "The wall is waiting for the television to be free." in ui.page.locator("section.scene").inner_text()


def test_discard_forgets_the_picks(ui, two_walls, services):
    ui.open("#walls")
    ui.page.wait_for_selector("section.scene")
    _pick(ui, "Study", "Golconda", "Golconda")

    ui.page.get_by_role("button", name="Discard the scene being assembled").click()
    ui.page.locator("section.scene .scene-pick:has-text('Golconda')").wait_for(state="detached")

    assert services.display.scene_draft() is None
    # The button that had focus is gone; focus is on the section's heading, not lost to the page.
    assert ui.page.evaluate("document.activeElement && document.activeElement.id") == "scene-title"


def test_a_wall_whose_work_was_kept_off_says_it_cannot_show_it(ui, two_walls, services):
    walls, persistence, golconda = two_walls
    display = services.display
    draft = display.draft_scene().scene
    display.pin_scene(draft.id, walls["The wall"], persistence.id)
    display.pin_scene(draft.id, walls["Study"], golconda.id)
    display.apply_scene(draft.id, lifetime="hold")
    display.exclude_work(persistence.id)

    ui.open("#walls")
    ui.page.locator("section.scene .scene-span").wait_for()

    line = ui.page.locator(f"section.scene li[data-wall='{walls['The wall']}']").inner_text()
    assert "The wall cannot show it, so it shows its schedule. It is kept off every wall." in line
    # Its card has no scene to speak of; the study's still does.
    assert ui.page.locator(f"section.wall[data-wall='{walls['The wall']}'] .wall-scene").count() == 0
    assert ui.page.locator(f"section.wall[data-wall='{walls['Study']}'] .wall-scene").count() == 1
