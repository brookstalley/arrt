"""The panel (`core/editing.js`) leaves the page the moment it is closed.

The platform queues a `<dialog>`'s `close` event as a task, so a panel removed
only from that event stays in the document, closed, until the task runs. Every
caller that closes a panel and asks a question in the same click (*Hang…*'s wall
choice, *Get…*, *Add to theme…*) then has two `.confirm-title` headings on the
page for that moment, the stale one first. On a slow machine a reader found it.

Driven by importing the module in the page, as `test_the_confirmation.py` does,
so the check is synchronous with the close and does not depend on timing.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

_OPEN_AND_CLOSE = """
async () => {
  const { openPanel } = await import("/static/core/editing.js");
  let closed = 0;
  const panel = openPanel({ title: "Hang Automat on…", onClose: () => { closed += 1; } });
  panel.close();
  const right_after = {
    inDocument: document.contains(panel.dialog),
    titles: document.querySelectorAll(".confirm-title").length,
    closed,
  };
  // Let the queued `close` event run, so a second settlement would show.
  await new Promise((resolve) => setTimeout(resolve, 50));
  return { right_after, closed_later: closed };
}
"""


def test_a_closed_panel_is_gone_before_the_next_question_opens(ui):
    ui.open()
    result = ui.page.evaluate(_OPEN_AND_CLOSE)

    assert result["right_after"] == {"inDocument": False, "titles": 0, "closed": 1}
    assert result["closed_later"] == 1


def test_escape_still_removes_the_panel_and_settles_once(ui):
    ui.open()
    ui.page.evaluate("""async () => {
        const { openPanel } = await import("/static/core/editing.js");
        window.__closed = 0;
        openPanel({ title: "A panel", onClose: () => { window.__closed += 1; } });
    }""")
    ui.page.wait_for_selector("dialog.panel-dialog[open]")
    ui.page.keyboard.press("Escape")
    ui.page.wait_for_selector("dialog.panel-dialog", state="detached")

    assert ui.page.evaluate("() => window.__closed") == 1
