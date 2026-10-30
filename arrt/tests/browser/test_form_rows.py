"""A labelled field and its button, side by side, line up at the bottom.

The owner's review of 2026-10-02 found "Create" on the Themes screen, and
"Rename", "Make default" and "Delete" beside a theme's name, sitting lower than
the box they act on. One rule caused it (a field's bottom margin inside a row),
so one test holds it, measured rather than eyed. It measured the Themes index's
*Create* until ruling 9 of 2026-10-27 moved creating into *New theme…*, which
left the index no such row; it now measures the same shape in a wall's *Edit…*,
*Name* beside *Rename*, the row the rule's other sites share.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


def test_a_field_and_its_button_share_a_bottom_edge(ui, services):
    wall = services.display.survey_walls()[0].wall
    ui.open("#walls")
    ui.page.get_by_role("button", name=f"Edit {wall.name}…").click()
    rename = ui.page.locator("dialog.panel-dialog").get_by_role("button", name=f"Rename {wall.name}")
    rename.wait_for()

    edges = rename.evaluate("""(button) => {
          const row = button.closest('.row');
          const input = row.querySelector('.field input');
          return [input.getBoundingClientRect().bottom, button.getBoundingClientRect().bottom];
        }""")

    assert abs(edges[0] - edges[1]) <= 1, f"the input ends at {edges[0]} px and its button at {edges[1]} px"
