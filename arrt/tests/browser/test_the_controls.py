"""Controls are one size, rows of them are spaced alike, and a cost is words.

`design-direction.md` § Component Patterns, Controls. The owner walked the
redesign and found buttons "spaced erratically", "a jumble of button sizes",
and a boxed "$" that read as a button. Each check runs on every page the
sidebar reaches, read from the route table, so a page added later is held to
the same rules.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above
from conftest import Ui

ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))
PAGES = sorted(key for key, route in ROUTES.items() if route.page)

#: The pages whose suite library draws a row of acts after something, so the
#: spacing check has a row to measure there.
PAGES_WITH_ROWS = {"discover", "walls"}

MEASURE = """(probeValue) => {
  const probe = document.createElement('div');
  probe.style.height = probeValue;
  document.body.append(probe);
  const px = probe.getBoundingClientRect().height;
  probe.remove();
  return px;
}"""


def _settled(ui, key):
    ui.open(f"#{key}")
    ui.page.wait_for_selector("#view h1")
    ui.page.wait_for_load_state("networkidle")


def test_the_pages_named_with_rows_are_sidebar_pages():
    assert set(PAGES) >= PAGES_WITH_ROWS


ROW_GAPS = """() => {
          const flexColumn = (node) => {
            const s = getComputedStyle(node);
            return (s.display === 'flex' || s.display === 'grid') && s.rowGap !== 'normal' && s.rowGap !== '0px';
          };
          const out = [];
          for (const row of document.querySelectorAll('#view :is(.row, .identity)')) {
            const before = row.previousElementSibling;
            if (!before || row.offsetParent === null || before.offsetParent === null) continue;
            if (flexColumn(row.parentElement)) continue;
            const gap = row.getBoundingClientRect().top - before.getBoundingClientRect().bottom;
            out.push([row.textContent.trim().slice(0, 40), gap]);
          }
          return out;
        }"""


def _flush_rows(ui):
    """Each row of acts that sits closer than one step to what precedes it."""
    step = ui.page.evaluate(MEASURE, "var(--space-4)")
    gaps = ui.page.evaluate(ROW_GAPS)
    return gaps, [(text, round(gap, 1)) for text, gap in gaps if gap < step - 0.5]


@pytest.mark.parametrize("key", PAGES)
def test_a_row_of_acts_sits_a_step_below_what_precedes_it(ui, key):
    _settled(ui, key)
    gaps, flush = _flush_rows(ui)
    if key in PAGES_WITH_ROWS:
        assert gaps, f"{key} drew no row of acts after anything"
    assert not flush, f"rows closer than one step to what precedes them: {flush}"


def test_an_artist_page_spaces_its_wikidata_line_and_reactions_alike(ui, service):
    """The page the owner walked: the Wikidata line, More like this / Not this,
    each a step below what precedes it rather than flush."""
    artist = service.add_artist(name="Charles Demuth", born=1883, died=1935)
    service.add_artwork(title="Eggplant and Plums", artist_id=artist.id, date_created="1927")
    ui.open(f"#artist/{artist.id}")
    ui.page.wait_for_selector("#view button:text-is('More like this')")
    ui.page.wait_for_load_state("networkidle")
    gaps, flush = _flush_rows(ui)
    assert len(gaps) >= 2, f"expected the identity line and the reactions, measured {gaps}"
    assert not flush, flush


@pytest.mark.parametrize("key", PAGES)
def test_every_act_is_at_least_the_control_height(ui, key):
    _settled(ui, key)
    height = ui.page.evaluate(MEASURE, "var(--control-h)")
    short = ui.page.evaluate(
        """(height) => [...document.querySelectorAll(':is(button, a).action')]
          .filter((node) => node.offsetParent !== null)
          .map((node) => [node.textContent.trim().slice(0, 30), node.getBoundingClientRect().height])
          .filter(([, h]) => h < height - 0.5)""",
        height,
    )
    assert not short, f"acts shorter than {height}px: {short}"


@pytest.mark.parametrize("key", ["discover", "collection", "artist", "health"])
def test_a_touch_screen_gets_44px_controls(browser, server_url, key):
    """`pointer: coarse` raises every control to 2.75rem, whatever the
    viewport, because a finger is what matters, not the window's width. Every
    visible control is measured, the top bar's included, on a page of each
    kind: a form, a list with its filter rail, an index, and a report."""
    context = browser.new_context(has_touch=True, is_mobile=True, viewport={"width": 1024, "height": 800})
    try:
        ui = Ui(context.new_page(), server_url)
        _settled(ui, key)
        small = ui.page.evaluate("""() => [...document.querySelectorAll(
              'button, input[type="text"], input[type="search"], textarea, select, nav.sidebar a')]
              .filter((node) => node.offsetParent !== null && !node.closest('.visually-hidden'))
              .map((node) => [node.textContent.trim().slice(0, 30) || node.getAttribute('aria-label')
                || node.getAttribute('placeholder') || node.tagName, node.getBoundingClientRect().height])
              .filter(([, h]) => h < 44 - 0.5)""")
        assert not small, f"controls under 44px on a touch screen: {small}"
    finally:
        context.close()


def test_a_cost_is_words_beside_its_act_not_a_box(ui):
    _settled(ui, "discover")
    mark = ui.page.locator("#view button:text-is('Get') + .badge-tier")
    look = mark.evaluate("""(node) => {
          const s = getComputedStyle(node);
          return {border: s.borderTopStyle, background: s.backgroundColor, wrap: s.whiteSpace,
                  label: node.textContent.replace(/\\s+/g, ' ').trim()};
        }""")
    assert look["border"] == "none"
    assert look["background"] == "rgba(0, 0, 0, 0)"
    assert look["label"].startswith("Cost: ")
    # Kept whole: "Cost:" never wraps away from its tier in a narrow row.
    assert look["wrap"] == "nowrap"
