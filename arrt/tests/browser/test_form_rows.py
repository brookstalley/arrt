"""A labelled field and its button, side by side, line up at the bottom.

The owner's review of 2026-10-02 found "Create" on the Themes screen, and
"Rename", "Make default" and "Delete" beside a theme's name, sitting lower than
the box they act on. One rule caused it (a field's bottom margin inside a row),
so one test on the Themes screen's form holds it, measured rather than eyed.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


def test_a_field_and_its_button_share_a_bottom_edge(ui):
    ui.open("#theme")
    ui.page.wait_for_selector("button:text-is('Create')")

    edges = ui.page.evaluate("""() => {
          const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Create');
          const row = button.closest('.row');
          const input = row.querySelector('.field input');
          return [input.getBoundingClientRect().bottom, button.getBoundingClientRect().bottom];
        }""")

    assert abs(edges[0] - edges[1]) <= 1, f"the input ends at {edges[0]} px and its button at {edges[1]} px"
