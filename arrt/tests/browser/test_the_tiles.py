"""A work's tile is the work on a mat with its label beneath, and every row of
tiles is the same height.

Uniform rows are `design-direction.md` § Component Patterns, Tiles: a grid of
art that reflows as its text varies is the opposite of the identity. One long
title must not make its row taller than a row of short ones, so the fixture
puts a three-line title in one row and one-line titles in the next.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_catalogue_work, a_listing

LONG = "Lozenge Composition with Yellow, Black, Blue, Red, and Gray, and a Title Long Enough to Run On"


def _works():
    titles = [LONG] + ["Sunset"] * 7
    return [a_catalogue_work(artwork_id=f"w{index}", title=title) for index, title in enumerate(titles)]


def test_every_row_of_tiles_is_the_same_height(ui):
    ui.page.set_viewport_size({"width": 1280, "height": 900})
    ui.serve("**/api/works?*", a_listing(_works()))
    ui.open("#collection?density=catalogue")
    ui.page.wait_for_selector("#view li.card[data-artwork='w7']")
    rows = ui.page.evaluate("""() => {
          const byTop = new Map();
          for (const tile of document.querySelectorAll('#view li.card[data-artwork]')) {
            const box = tile.getBoundingClientRect();
            byTop.set(Math.round(box.top), Math.round(box.height));
          }
          return [...byTop.values()];
        }""")
    assert len(rows) >= 2, "the fixture must fill more than one row, or this proves nothing"
    assert len(set(rows)) == 1, f"row heights differ: {rows}"


def test_a_long_title_is_clamped_to_two_lines(ui):
    ui.serve("**/api/works?*", a_listing(_works()))
    ui.open("#collection?density=catalogue")
    title = ui.page.locator("#view li.card[data-artwork='w0'] .card-title")
    title.wait_for()
    lines = title.evaluate(
        "(node) => Math.round(node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight))"
    )
    assert lines == 2


def test_a_tile_is_not_boxed_and_its_picture_sits_on_the_mat(ui):
    ui.serve("**/api/works?*", a_listing(_works()))
    ui.open("#collection?density=catalogue")
    tile = ui.page.locator("#view li.card[data-artwork='w0']")
    tile.wait_for()
    look = tile.evaluate("""(node) => {
          const probe = document.createElement('span');
          probe.style.backgroundColor = 'var(--surface-2)';
          document.body.append(probe);
          const mat = getComputedStyle(probe).backgroundColor;
          probe.remove();
          const s = getComputedStyle(node);
          return {
            border: s.borderTopStyle,
            shadow: s.boxShadow,
            background: s.backgroundColor,
            picture: getComputedStyle(node.querySelector('.card-image')).backgroundColor,
            mat,
          };
        }""")
    assert look["border"] == "none"
    assert look["shadow"] == "none"
    assert look["background"] == "rgba(0, 0, 0, 0)"
    assert look["picture"] == look["mat"]
