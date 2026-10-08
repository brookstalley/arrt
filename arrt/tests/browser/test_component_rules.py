"""The shared component rules: one heading scale, one empty page, a disabled
act that looks disabled, and a hover that leaves a full-card link whole.

`design-direction.md` § Component Patterns names each rule. The October review
(`ux-review-2026-10.md` finding 27) found five heading treatments and four
empty-page patterns across the screens, and disabled acts drawn as if they
were ready. These checks run on every page the sidebar reaches, read from the
route table, so a page added later is held to the same rules.
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
from payloads import a_listing

ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))
PAGES = {key: route for key, route in ROUTES.items() if route.page}

#: The sidebar pages that open on their empty state in the suite's library,
#: which holds three works by two artists and nothing else. The others say
#: something else first: Artworks and Artists list what is held, Ask opens on
#: its intent box, Walls on its wall, Sources on the built-in plugins, Status
#: on its readings. Their empty pages are checked below with the listing
#: stubbed empty, because the suite's server always holds its three works.
EMPTY_WHEN_NOTHING_IS_HELD = {
    "theme",
    "topics",
    "to_review",
    "queue",
    "history",
    "wanted",
    "taste",
    "clients",
}


def test_the_empty_pages_named_here_are_sidebar_pages():
    # A renamed route would otherwise leave its key here, unchecked.
    assert PAGES.keys() >= EMPTY_WHEN_NOTHING_IS_HELD


@pytest.mark.parametrize("key", sorted(PAGES))
def test_every_page_heading_has_the_one_h1_treatment(ui, key):
    """Every page names itself at the same size: Walls included, which once had
    a heading twice the others' as "the product's home"."""
    ui.open(f"#{key}")
    ui.page.wait_for_selector("#view h1")
    size, expected = ui.page.evaluate("""() => {
          const probe = document.createElement('span');
          probe.style.fontSize = 'var(--text-lg)';
          document.body.append(probe);
          const expected = getComputedStyle(probe).fontSize;
          probe.remove();
          return [getComputedStyle(document.querySelector('#view h1')).fontSize, expected];
        }""")
    assert size == expected


@pytest.mark.parametrize("key", sorted(PAGES))
def test_an_empty_page_uses_the_one_empty_state(ui, key):
    """An empty page leads with a sentence, not a heading, in the shared shape;
    and a page that is not empty does not show one."""
    ui.open(f"#{key}")
    ui.page.wait_for_selector("#view h1")
    if key in EMPTY_WHEN_NOTHING_IS_HELD:
        lead = ui.page.locator("#view .empty > p.empty-lead")
        lead.first.wait_for()
        assert lead.count() == 1
        assert lead.inner_text().strip()
        # The page's name outranks what the page says about itself.
        sizes = ui.page.evaluate(
            "() => ['#view h1', '#view .empty-lead'].map((s) => parseFloat(getComputedStyle(document.querySelector(s)).fontSize))"
        )
        assert sizes[1] < sizes[0]
    else:
        ui.page.wait_for_load_state("networkidle")
        assert ui.page.locator("#view .empty").count() == 0
    # The shapes the shared one replaced.
    assert ui.page.locator("#view .empty :is(h2, h3), #view .panel.empty, #view .stack.empty").count() == 0


@pytest.mark.parametrize(
    ("key", "listing", "lead"),
    [
        pytest.param("collection", "**/api/works?*", "Nothing is held yet.", id="collection"),
        pytest.param("artist", "**/api/artists", "No artists yet.", id="artist"),
    ],
)
def test_the_lists_of_what_is_held_use_the_one_empty_state_when_empty(ui, key, listing, lead):
    ui.serve(listing, a_listing([]) if key == "collection" else {"artists": []})
    ui.open(f"#{key}")
    shown = ui.page.locator("#view .empty > p.empty-lead")
    shown.wait_for()
    assert shown.inner_text() == lead


def _probe(ui, markup: str):
    ui.open("#collection")
    ui.page.wait_for_selector("#view h1")
    # Into the body, not the view: the view is repainted when the page's works
    # arrive, which would take a probe placed in it away mid-test.
    ui.page.evaluate("(markup) => document.body.insertAdjacentHTML('beforeend', markup)", markup)


def _look(ui, selector: str) -> dict:
    return ui.page.eval_on_selector(
        selector,
        """(node) => {
          const s = getComputedStyle(node);
          return { background: s.backgroundColor, color: s.color, cursor: s.cursor, shadow: s.boxShadow };
        }""",
    )


@pytest.mark.parametrize("variant", ["action", "action quiet"])
def test_a_disabled_act_does_not_look_ready(ui, variant):
    _probe(
        ui,
        f'<button id="ready" class="{variant}">Go</button><button id="off" class="{variant}" disabled>Go</button>',
    )
    ready, off = _look(ui, "#ready"), _look(ui, "#off")
    assert off["background"] != ready["background"]
    assert off["color"] != ready["color"]
    assert off["cursor"] == "not-allowed"
    ui.page.hover("#off", force=True)
    assert _look(ui, "#off")["shadow"] == "none", "a disabled act answers the pointer as if it would act"


def test_hovering_an_act_leaves_a_full_card_link_covering_the_card(ui):
    """A link drawn as an act may cover its whole card. Hovering it must not
    shrink that cover to the link: a press on the card would then miss.

    A `filter` on hover did exactly that, because a filter makes the element the
    box its absolutely positioned children are placed in.
    """
    _probe(
        ui,
        '<div id="card" style="position: relative; width: 400px; height: 300px">'
        '<a id="act" class="action" href="#collection" style="position: static">Open'
        '<span id="cover" style="position: absolute; inset: 0"></span></a></div>',
    )
    ui.page.hover("#act")
    card = ui.page.locator("#card").bounding_box()
    cover = ui.page.locator("#cover").bounding_box()
    assert (cover["width"], cover["height"]) == (card["width"], card["height"])
