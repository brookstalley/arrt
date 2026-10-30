"""Hanging a theme, in a real browser, against a real server.

The theme panel is where the single-wall assumption was most visible in the
client: one "Put on the wall" button, and a badge that said "on the wall" with no
room to say which. A theme's page now hangs it through *Hang…*, a dialog of
every wall by name (ruling 9 of 2026-10-27). Neither is expressible as JSON, so neither Python suite runs a
line of it — this does.

**These tests are here rather than in a screen chunk because the client changed
in this one.** Chunks 04, 05 and 09 rebuild these screens; until they do, this is
the only executed coverage the per-wall controls have.
"""

import json

import pytest

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def a_theme(services):
    """One theme, hanging nowhere. What a curator has just after creating one."""
    return services.display.add_theme(name="Late night")


def _open_hang(ui, theme):
    """A theme's *Hang…*: since ruling 9 of 2026-10-27 one dialog of every wall,
    ticked where the theme hangs, in place of a button per wall and *Take down*."""
    ui.open(f"#theme/{theme.id}")
    ui.page.locator("#view .page-toolbar button", has_text="Hang…").click()
    dialog = ui.page.locator("dialog.panel-dialog[open]")
    dialog.wait_for()
    return dialog


def _walls_offered(dialog):
    """Each wall the dialog offers, by its label, and whether it is ticked."""
    return {
        dialog.locator(f"label[for='{box.get_attribute('id')}']").inner_text(): box.is_checked()
        for box in dialog.locator("input[type='checkbox']").all()
    }


def test_the_control_names_the_wall_it_would_hang_on(ui, a_theme):
    """A wall by its name, never "the wall".

    A label that reads correctly today only because there is one possible target
    is a sentence that silently becomes wrong, and the label is the last place a
    curator can catch a mistake before the room changes.
    """
    dialog = _open_hang(ui, a_theme)

    assert _walls_offered(dialog) == {"The wall": False}


def test_a_second_wall_becomes_a_second_choice_rather_than_a_different_screen(ui, a_theme, services):
    """One wall is the degenerate case of many, and the layout does not switch.

    The single-wall rendering is the many-wall rendering with one entry in it, so
    a second display adds a tick rather than replacing a control.
    """
    services.display.add_wall(name="Study")

    dialog = _open_hang(ui, a_theme)

    assert _walls_offered(dialog) == {"Study": False, "The wall": False}


def test_hanging_reports_back_by_naming_the_wall_rather_than_a_colour(ui, a_theme, services):
    """The page says where it hangs by the wall's own name, a link, never by colour.

    Two claims in one, and both matter: colour is never the sole carrier of
    state, and "on the wall" is not a thing that can be said once there is more
    than one. Since ruling 9 of 2026-10-27 it is said in the page's facts, and
    *Hang…* shows the wall it hangs on ticked and the other free to tick.
    """
    services.display.add_wall(name="Study")
    dialog = _open_hang(ui, a_theme)
    dialog.locator("label:text-is('Study')").click()
    dialog.get_by_role("button", name="Hang", exact=True).click()
    # Through the confirmation: activation is the one act that changes what
    # other people in the house see, and flow 6 requires it be asked about. What
    # the question says is asserted in `test_the_theme_screen.py`; here it is the
    # gate between the click and the write.
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    facts = ui.page.locator("#view .theme-facts")
    ui.page.wait_for_selector("#view .theme-facts a:text-is('Study')")

    assert "Hanging on Study" in facts.inner_text()
    assert facts.get_by_role("link", name="Study").count() == 1
    assert "The wall" not in facts.inner_text()
    dialog = _open_hang(ui, a_theme)
    assert _walls_offered(dialog) == {"Study": True, "The wall": False}


def test_a_hung_theme_can_be_taken_down_from_the_wall_it_is_on(ui, a_theme, services):
    """The route out of the delete refusal, exercised where a curator meets it.

    A theme hanging anywhere is undeletable, and this is what makes that absolute
    rule survivable rather than a dead end: unticking the wall in *Hang…*, asked
    once, since ruling 9 of 2026-10-27 (*Take down from …* until then, unasked).
    """
    wall = services.display.survey_walls()[0].wall
    services.display.activate_theme(a_theme.id, wall_id=wall.id)

    dialog = _open_hang(ui, a_theme)
    dialog.locator(f"label:text-is('{wall.name}')").click()
    dialog.get_by_role("button", name="Hang", exact=True).click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert ui.page.inner_text("dialog.confirm .confirm-title") == f"Take Late night down from {wall.name}?"
    assert "goes on showing what it shows until something else is hung there" in ui.page.inner_text(
        "dialog.confirm .confirm-consequence"
    )
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Take down')")
    ui.page.wait_for_function("() => !document.querySelector('#view .theme-facts').textContent.includes('Hanging on')")

    assert services.display.hanging_on(wall.id) is None


def test_one_hang_puts_it_up_on_one_wall_and_takes_it_down_from_another(ui, a_theme, services):
    """Two changes, one question naming both walls, and only the changed walls sent."""
    the_wall = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="Study")
    landing = services.display.add_wall(name="Landing")
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)
    services.display.activate_theme(a_theme.id, wall_id=landing.id)

    dialog = _open_hang(ui, a_theme)
    sent = []

    def note(request):
        if request.url.endswith("/activate"):
            sent.append(("POST", "activate", json.loads(request.post_data)["wall_id"]))
        elif request.method == "DELETE" and request.url.endswith("/theme"):
            sent.append(("DELETE", request.url.split("/api/walls/")[1].split("/")[0], None))

    ui.page.on("request", note)
    dialog.locator("label:text-is('Study')").click()
    dialog.locator(f"label:text-is('{the_wall.name}')").click()
    dialog.get_by_role("button", name="Hang", exact=True).click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    assert (
        ui.page.inner_text("dialog.confirm .confirm-title") == f"Hang Late night on Study and take it down from {the_wall.name}?"
    )
    consequence = ui.page.inner_text("dialog.confirm .confirm-consequence")
    assert consequence.startswith("Study: ")
    assert f"Everyone in the house sees Study and {the_wall.name} change." in consequence
    assert "Landing" not in consequence
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")
    ui.page.wait_for_selector("#view .theme-facts a:text-is('Study')")

    hanging = {
        wall["name"]: wall["theme"] for wall in ui.page.evaluate("() => fetch('/api/walls').then((r) => r.json())")["walls"]
    }
    assert hanging["Study"]["theme_id"] == a_theme.id
    assert hanging["Landing"]["theme_id"] == a_theme.id
    assert hanging[the_wall.name] is None
    # Landing was ticked and left ticked, so nothing was sent for it: one hang,
    # for Study, and one take-down, for the wall.
    assert sent == [("POST", "activate", study.id), ("DELETE", the_wall.id, None)]


@pytest.mark.parametrize("leave", ["unchanged", "Cancel", "Escape"])
def test_leaving_hang_as_it_was_or_closing_it_sends_nothing(ui, a_theme, services, leave):
    wall = services.display.survey_walls()[0].wall
    dialog = _open_hang(ui, a_theme)
    if leave == "unchanged":
        dialog.get_by_role("button", name="Hang", exact=True).click()
    elif leave == "Escape":
        dialog.locator(f"label:text-is('{wall.name}')").click()
        ui.page.keyboard.press("Escape")
    else:
        dialog.locator(f"label:text-is('{wall.name}')").click()
        dialog.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="detached")
    ui.page.wait_for_timeout(300)

    assert ui.page.locator("dialog.confirm").count() == 0
    assert ui.requests_matching("/api/manifest") == []
    assert services.display.hanging_on(wall.id) is None


def test_a_wall_with_nothing_hanging_says_so_instead_of_showing_an_empty_manifest(ui, a_theme):
    """The wall view names the wall and the fix, rather than rendering nothing.

    An empty table under a heading reads as "the theme is empty"; this state is
    "no theme has been chosen", and the two lead to different actions.
    """
    ui.open("#walls")
    ui.page.wait_for_selector("h1")

    assert "Nothing is hanging on The wall" in ui.text()
    # And the fact the MCP surface states after an unhang, which the human
    # surface withheld: taking a theme down rewrites no manifest, so the set goes
    # on showing the picture. Without this line the empty wall reads as a failed
    # take-down, and the curator's next move is to do it again.
    assert "goes on showing what it was showing until a theme is hung" in ui.text()


def test_the_take_down_note_is_said_once_however_many_walls_are_empty(ui, services):
    """One fact about how taking down works, not a property of any wall.

    It reads as a caption under the list of empty rooms; repeated per room it
    reads as three separate warnings about three separate problems. Two empty
    walls is the smallest state that can tell the two renderings apart, and
    without this test the note could be moved back inside the loop with the
    suite still green — which is exactly where it started.
    """
    services.display.add_wall(name="Study")

    ui.open("#walls")
    ui.page.wait_for_selector("h1")

    assert ui.page.locator("p", has_text="goes on showing what it was showing").count() == 1
    # Both rooms are named, so the one note is standing for two walls rather
    # than one of them having gone missing.
    assert "Nothing is hanging on The wall" in ui.text()
    assert "Nothing is hanging on Study" in ui.text()


def test_each_walls_panels_nest_under_that_wall_rather_than_beside_it(ui, a_theme, services):
    """Two hung walls, and a reader navigating by heading can still tell the rooms apart.

    The wall view renders one section per wall, each with its own Not showing /
    How it rotates panels (a third, Showing, left the card when it began leading
    with the work on the wall). When every one of those was an `h2` the
    single-wall case read correctly by accident — with two walls hung it is six
    sibling headings in a row and no structural signal for which counts belong to
    which room. Asserted rather than left to the eye because nothing else
    executes this markup: `accessibility-spec.md` states no heading rule, so this
    test is the rule.
    """
    # Read before the study exists, because walls come back ordered by name and
    # "Study" would displace the migration's wall from position zero — after
    # which this index would hang the theme in the same room twice and the test
    # would assert nothing about nesting.
    the_wall = services.display.survey_walls()[0].wall
    study = services.display.add_wall(name="Study")
    services.display.activate_theme(a_theme.id, wall_id=the_wall.id)
    services.display.activate_theme(a_theme.id, wall_id=study.id)

    ui.open("#walls")
    ui.page.wait_for_selector("h2")

    # One h2 per wall, and every panel heading a rank below it. The theme is on
    # the line under the heading now, not in it. The Scene is no longer an h2 on
    # the page: assembling one is the Scene… dialog's (ruling 5 of 2026-10-27).
    assert sorted(ui.page.locator("h2").all_text_contents()) == ["Study", "The wall"]
    assert ui.page.locator("h2.wall-title").count() == 2
    assert ui.page.locator(".panel h2").count() == 0
    # The panels left the cards for each wall's Edit… dialog (ruling 4 of
    # 2026-10-27), so none sits beside another wall's on the page; opened, one
    # wall's dialog has its own title and its six panels a rank below it.
    assert ui.page.locator("#view .panel h3").count() == 0
    ui.page.locator(f"section.wall[data-wall='{the_wall.id}'] button.wall-edit").click()
    dialog = ui.page.locator("dialog.panel-dialog")
    dialog.wait_for()
    assert dialog.locator("h2").all_text_contents() == [f"Edit {the_wall.name}"]
    assert dialog.locator(".panel h3").count() == 6
    # And with nothing empty there is no take-down note: a caption with nothing
    # to caption. This is the other half of the guard the sibling test above
    # exercises, and without it the guard could be deleted with the suite green.
    assert ui.page.locator("p", has_text="goes on showing what it was showing").count() == 0
