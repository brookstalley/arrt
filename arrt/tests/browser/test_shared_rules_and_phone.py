"""The shared rules a page is laid out by, and the pages at a phone's width.

The second UX walk (`ux-review-2026-10.md` findings 36 and 40, 41 and 45; #360
and #357) found rows, gaps and type drifting in a few shared rules, not page by
page: a row aligning text to its button's bottom edge, a tile's title taking a
heading's margin inside a panel, its badge floating to the next row's picture,
three gaps under a page's name, every quiet act gilt in dark, prose running the
full width, numbers left-aligned. At 390 px the top bar cut its status to "● W…",
the open drawer covered its own Menu button, Artworks put its toolbar before
any picture, and Clients' tables overflowed and wrapped identifiers mid-word.

Measured, not looked at: each test reads the geometry or the computed style the
finding was about.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

from arrt.programming.client_heartbeat import client_heartbeat_path_in

ROUTES = ux_walk.declared_routes(ux_walk.APP_JS.read_text(encoding="utf-8"))
PAGES = [route for route in ROUTES.values() if route.page]

PHONE = {"width": 390, "height": 844}

#: Where the first thing under the page's name starts, measured from the bottom
#: of the name: a rule if the block draws one, else the first words, picture or
#: control drawn inside it. The words' top is their line box's, so a line's
#: half-leading sits inside the gap (`HALF_LEADING`).
GAP_UNDER_THE_NAME = """() => {
  const h1 = document.querySelector('#view h1');
  let next = h1.nextElementSibling;
  // Passed over: anything not drawn, and a live region hidden to the eye (1px).
  while (next && (next.hidden || next.getBoundingClientRect().height <= 1)) next = next.nextElementSibling;
  if (!next) return null;
  const below = h1.getBoundingClientRect().bottom;
  if (parseFloat(getComputedStyle(next).borderTopWidth) > 0) return Math.round(next.getBoundingClientRect().top - below);
  const tops = [];
  const walker = document.createTreeWalker(next, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let node = walker.currentNode; node; node = walker.nextNode()) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!node.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rect = range.getClientRects()[0];
      if (rect && rect.height > 1) tops.push(rect.top);
    } else if (node.matches('img, input, textarea, select, button, a.action, hr')) {
      const rect = node.getBoundingClientRect();
      if (rect.height > 1) tops.push(rect.top);
    } else if (parseFloat(getComputedStyle(node).borderTopWidth) > 0 && node.getBoundingClientRect().height > 1) {
      tops.push(node.getBoundingClientRect().top);
    }
  }
  return tops.length ? Math.round(Math.min(...tops) - below) : null;
}"""

#: A line box's half-leading above its words, at most: the gap may grow by this
#: much from a line's own spacing without a second gap having been added.
HALF_LEADING = 8


# -- the gap under a page's name ---------------------------------------------------------


@pytest.mark.parametrize("route", PAGES, ids=[route.key for route in PAGES])
def test_a_pages_name_has_one_gap_to_what_follows_it(ui, route):
    ui.open(f"#{route.key}")
    ui.page.wait_for_selector("#view h1")
    ui.page.wait_for_load_state("networkidle")
    expected = ui.page.locator("#view h1").evaluate("(h1) => Math.round(parseFloat(getComputedStyle(h1).marginBottom))")
    gap = ui.page.evaluate(GAP_UNDER_THE_NAME)
    assert expected <= gap <= expected + HALF_LEADING, f"{gap}px under the page's name"


# -- a row of acts ---------------------------------------------------------------------------


def test_a_row_sets_its_text_and_its_acts_on_one_line(ui):
    """A captioned act beside a bare act beside a sentence: their words share a baseline.

    Built from the app's own markup classes on its own stylesheet, so this is
    the shared rule under test and not one screen's arrangement of it.
    """
    ui.open("#collection")
    tops = ui.page.evaluate("""() => {
          const row = document.createElement('div');
          row.className = 'row';
          row.innerHTML =
            '<div class="captioned"><button class="action" type="button"><span class="w">Ask</span></button>' +
            '<span class="act-caption">Costs under a cent</span></div>' +
            '<button class="action quiet" type="button"><span class="w">Start over</span></button>' +
            '<span class="w">Wikidata: not matched yet</span>';
          document.querySelector('#view').append(row);
          return [...row.querySelectorAll('.w')].map((node) => {
            const r = document.createRange();
            r.selectNodeContents(node);
            return Math.round(r.getBoundingClientRect().bottom);
          });
        }""")
    assert max(tops) - min(tops) <= 2, f"word bottoms {tops}"


def test_a_row_of_fields_still_sets_its_act_level_with_the_boxes(ui):
    """A labelled field beside its button keeps the button on the box's edge, not the label's."""
    ui.open("#theme")
    edges = ui.page.evaluate("""() => {
          const row = document.createElement('div');
          row.className = 'row';
          row.innerHTML =
            '<div class="field"><label for="x">Name</label><input id="x"></div>' +
            '<button class="action" type="button">Create</button>';
          document.querySelector('#view').append(row);
          const boxes = [row.querySelector('input'), row.querySelector('button')];
          return boxes.map((n) => Math.round(n.getBoundingClientRect().bottom));
        }""")
    assert abs(edges[0] - edges[1]) <= 2, f"input and button bottoms {edges}"


# -- tiles -------------------------------------------------------------------------------------


@pytest.fixture
def an_artist_with_a_work(service):
    artist = service.add_artist(name="Aleksandra Ekster", nationality="Ukrainian", born=1882, died=1949)
    work = service.add_artwork(title="City at Night", artist_id=artist.id, date_created="1915")
    return artist, work


def test_a_tiles_title_has_no_heading_margin_inside_a_panel(ui, an_artist_with_a_work):
    artist, work = an_artist_with_a_work
    ui.open(f"#artist/{artist.id}")
    title = ui.page.locator(f".panel li.card[data-artwork='{work.id}'] .card-title")
    title.wait_for()
    margins = title.evaluate("(n) => { const s = getComputedStyle(n); return [s.marginTop, s.marginBottom, s.fontWeight]; }")
    assert margins == ["0px", "0px", "400"]


def test_a_tiles_badge_sits_under_its_own_label(ui, service):
    """A tile with an unusual value: its badge follows the label's last line, not the floor of the block."""
    work = service.add_artwork(title="Crak!")
    ui.open("#collection")
    card = ui.page.locator(f"li.card[data-artwork='{work.id}']")
    card.locator(".card-footer .badge").first.wait_for()
    gap = card.evaluate("""(card) => {
          const lines = [...card.querySelectorAll('.card-body > :not(.card-footer)')]
            .filter((n) => n.getBoundingClientRect().height);
          const last = Math.max(...lines.map((n) => n.getBoundingClientRect().bottom));
          return card.querySelector('.card-footer .badge').getBoundingClientRect().top - last;
        }""")
    assert 0 <= gap <= 16, f"{gap}px between the label's last line and its badge"


# -- type and colour ---------------------------------------------------------------------------


def test_a_badge_beside_a_heading_is_set_in_the_ui_face(ui):
    ui.open("#collection")
    faces = ui.page.evaluate("""() => {
          const h1 = document.querySelector('#view h1');
          const badge = document.createElement('span');
          badge.className = 'badge';
          badge.textContent = 'default';
          h1.append(badge);
          const tool = document.createElement('button');
          tool.className = 'action';
          document.body.append(tool);
          return [getComputedStyle(badge).fontFamily, getComputedStyle(tool).fontFamily, getComputedStyle(badge).fontWeight];
        }""")
    assert faces[0] == faces[1], "a badge in a heading takes the heading's serif"
    assert faces[2] == "400"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_quiet_act_is_set_in_the_texts_colour_not_the_accent(ui, scheme):
    """The one filled act carries the accent; quiet ones are ink, in both schemes."""
    ui.page.emulate_media(color_scheme=scheme)
    ui.open("#collection")
    colours = ui.page.evaluate("""() => {
          const quiet = document.createElement('button');
          quiet.className = 'action quiet';
          quiet.textContent = 'Sort';
          document.querySelector('#view').append(quiet);
          const probe = document.createElement('p');
          probe.textContent = 'text';
          document.querySelector('#view').append(probe);
          return [getComputedStyle(quiet).color, getComputedStyle(probe).color];
        }""")
    assert colours[0] == colours[1]


def test_prose_is_held_to_a_readable_measure(ui):
    """A long paragraph in the view, on a wide window, stops at a readable measure."""
    ui.page.set_viewport_size({"width": 1800, "height": 1000})
    ui.open("#clients")
    chs = ui.page.evaluate("""() => {
          const p = document.createElement('p');
          p.textContent = 'A sentence long enough to run the width of the page. '.repeat(8);
          document.querySelector('#view').append(p);
          const zero = document.createElement('span');
          zero.textContent = '0'.repeat(100);
          p.append(zero);
          const ch = zero.getBoundingClientRect().width / 100;
          zero.remove();
          return p.getBoundingClientRect().width / ch;
        }""")
    assert chs <= 70.5, f"a paragraph {chs} characters wide"


def test_numbers_in_a_table_are_right_aligned_and_its_first_column_is_on_the_pages_edge(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    table = ui.page.locator("#view table").filter(has=ui.page.locator("th", has_text="Offered")).first
    table.wait_for()
    report = table.evaluate("""(table) => {
          const heads = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim());
          const at = heads.indexOf('Offered');
          const row = table.querySelector('tbody tr');
          const cell = row.children[at];
          const first = row.children[0];
          const h2 = table.closest('.panel').querySelector('h2, h3');
          return {
            align: getComputedStyle(cell).textAlign,
            headAlign: getComputedStyle(table.querySelectorAll('thead th')[at]).textAlign,
            firstText: Math.round(first.getBoundingClientRect().left + parseFloat(getComputedStyle(first).paddingLeft)),
            edge: Math.round(h2.getBoundingClientRect().left),
            numerals: getComputedStyle(cell).fontVariantNumeric,
          };
        }""")
    assert report["align"] == "right"
    assert report["headAlign"] == "right"
    assert "tabular-nums" in report["numerals"]
    assert report["firstText"] == report["edge"]


# -- at a phone's width ------------------------------------------------------------------------


@pytest.mark.parametrize("route", PAGES, ids=[route.key for route in PAGES])
def test_on_a_phone_the_status_is_a_whole_word(ui, route):
    ui.page.set_viewport_size(PHONE)
    ui.open(f"#{route.key}")
    ui.page.wait_for_selector("#status[data-state]")
    shown = ui.page.evaluate("""() => [...document.querySelectorAll('#status > span')]
             .filter((n) => n.getBoundingClientRect().width > 1 && !n.classList.contains('glyph'))
             .map((n) => ({ text: n.textContent, cut: n.scrollWidth > n.clientWidth + 1 }))""")
    assert len(shown) == 1, shown
    assert not shown[0]["cut"], shown
    assert shown[0]["text"].strip()
    assert "…" not in shown[0]["text"]


def test_on_a_phone_the_whole_trouble_is_still_read_out(ui, a_health_reading, a_wall_reading):
    """The short word is what is shown; the sentence naming what is wrong stays for a screen reader."""
    ui.serve("**/api/health", a_health_reading(walls=[a_wall_reading(name="The hall", absent=True)]))
    ui.page.set_viewport_size(PHONE)
    ui.open("#collection")
    ui.page.wait_for_selector("#status[data-state='unwell']")
    assert "The hall has not reported" in ui.page.locator("#status").evaluate("(n) => n.textContent")


def test_on_a_phone_the_open_drawer_leaves_menu_to_close_it(ui):
    ui.page.set_viewport_size(PHONE)
    ui.open("#collection")
    menu = ui.page.locator(".menu-button")
    menu.click()
    ui.page.wait_for_selector("nav.sidebar[data-open]")
    assert menu.is_visible()
    box = menu.bounding_box()
    on_top = ui.page.evaluate(
        "([x, y]) => document.elementFromPoint(x, y).closest('.menu-button') !== null",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
    )
    assert on_top, "the drawer covers the button that opened it"
    menu.click()
    ui.page.wait_for_selector("nav.sidebar:not([data-open])", state="attached")


def test_on_a_phone_artworks_shows_a_picture_in_the_first_screen(ui, service, services):
    """With the toolbar and a rail of facets above the grid, as a real library has them."""
    theme = services.display.add_theme(name="End-to-end validation 2026-08-04")
    for number, movement in enumerate(["Cubism", "Suprematism", "Futurism", "Fauvism", "Dada", "Surrealism"] * 2):
        work = service.add_artwork(title=f"Study {number}")
        service.record_facet(artwork_id=work.id, kind="movement", value=movement, derivation="inferred")
        services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    ui.page.set_viewport_size(PHONE)
    ui.open("#collection")
    ui.page.wait_for_selector(".rails .facet-option")
    first = ui.page.locator("ul.grid li.card .card-image").first
    first.wait_for()
    assert first.bounding_box()["y"] < PHONE["height"] - 200, "the first picture starts below the fold"


def test_on_a_phone_the_filter_rail_shows_that_it_scrolls(ui, service):
    for number, movement in enumerate(["Cubism", "Suprematism", "Futurism", "Fauvism", "Dada", "Surrealism"]):
        work = service.add_artwork(title=f"Study {number}")
        service.record_facet(artwork_id=work.id, kind="movement", value=movement, derivation="inferred")
        service.record_facet(artwork_id=work.id, kind="medium", value=f"Medium {number}", derivation="inferred")
    ui.page.set_viewport_size(PHONE)
    ui.open("#collection")
    rails = ui.page.locator(".rails")
    rails.wait_for()
    ui.page.wait_for_selector(".rails .facet-option")
    overflows, cue = rails.evaluate(
        "(n) => [n.scrollWidth > n.clientWidth, getComputedStyle(n).maskImage || getComputedStyle(n).webkitMaskImage]"
    )
    assert overflows, "the rail fits, so this test shows nothing"
    assert cue, "a rail cut at the edge with no sign it scrolls"
    assert cue != "none", "a rail cut at the edge with no sign it scrolls"


def test_on_a_phone_the_players_table_fits_and_keeps_its_names_whole(ui, services, settings):
    """Each row is a card on a phone (`table.stacked`), and a screen's name and
    size never break across lines: *HDMI 1* split from its number reads as two
    things. The ports themselves are no longer shown (§ Vocabulary)."""
    hall = services.clients.add_client(name="Hall Pi")
    reported = {
        "reported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "outputs": [
            {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
            {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
        ],
        "label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}],
    }
    client_heartbeat_path_in(settings.art_root, hall.id).write_text(json.dumps(reported), encoding="utf-8")
    wall = services.display.survey_walls()[0].wall
    services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
    services.clients.add_label(wall.id, client_id=hall.id, output="epd-0")
    ui.page.set_viewport_size(PHONE)
    ui.open("#clients")
    ui.page.wait_for_selector(f"#view tr[data-player='{hall.id}'] td[data-label='Screens'] li")
    report = ui.page.evaluate("""() => ({
          overflowing: [...document.querySelectorAll('#view .table-scroll')]
            .filter((n) => n.scrollWidth > n.clientWidth + 1).length,
          checked: [...document.querySelectorAll('#view td')].filter((td) => /HDMI \\d+|\\d+ × \\d+/.test(td.textContent)).length,
          broken: [...document.querySelectorAll('#view td')]
            .filter((td) => /HDMI \\d+|\\d+ × \\d+/.test(td.textContent))
            .filter((td) => {
            const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);
            for (let text = walker.nextNode(); text; text = walker.nextNode()) {
              const at = text.textContent.search(/HDMI \\d+|\\d+ × \\d+/);
              if (at < 0) continue;
              const word = text.textContent.slice(at).match(/^(HDMI \\d+|\\d+ × \\d+)/)[0];
              const range = document.createRange();
              range.setStart(text, at);
              range.setEnd(text, at + word.length);
              const tops = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
              if (tops.size > 1) return true;
            }
            return false;
          }).length,
        })""")
    # The screens and the label panel's size: a guard with nothing to read passes.
    assert report.pop("checked") >= 2
    assert report == {"overflowing": 0, "broken": 0}


def test_on_a_phone_artists_rows_leave_no_dead_ground(ui, service):
    for number in range(4):
        service.add_artist(name=f"Painter {number}", born=1900, died=1980)
    ui.page.set_viewport_size(PHONE)
    ui.open("#artist")
    cards = ui.page.locator("#view li.card[data-artist]")
    cards.first.wait_for()
    slack, reserve = cards.first.evaluate("""(card) => {
          const body = card.querySelector('.card-body');
          const shown = [...body.children].filter((n) => n.getBoundingClientRect().height);
          const used = Math.max(...shown.map((n) => n.getBoundingClientRect().bottom));
          // What a poster keeps in hand for uniform rows: a second line of name
          // and the badge row with its padding (§ Component Patterns, Tiles), and nothing more.
          const probe = document.createElement('div');
          probe.style.height = 'calc(1.25 * var(--text-lg) + var(--space-3) + 1.75rem)';
          card.append(probe);
          const kept = probe.getBoundingClientRect().height;
          probe.remove();
          return [body.getBoundingClientRect().bottom - used, kept];
        }""")
    assert slack <= reserve + 2, f"{slack}px of empty ground under an artist's poster, {reserve}px kept for its longest shape"


def test_an_act_in_a_line_of_words_is_never_flush_against_them(ui):
    ui.open("#collection")
    gaps = ui.page.evaluate("""() => {
          const view = document.querySelector('#view');
          const measure = (html) => {
            const holder = document.createElement('div');
            holder.innerHTML = html;
            view.append(holder);
            const words = holder.querySelector('.w');
            const range = document.createRange();
            range.selectNodeContents(words);
            return Math.round(holder.querySelector('button').getBoundingClientRect().left - range.getBoundingClientRect().right);
          };
          return [
            measure(
              '<ul><li><span class="w">epd-0 captions The wall</span>' +
                '<button class="action quiet">Stop captioning</button></li></ul>'
            ),
            measure('<p><span class="w">their years agree</span> <button class="action quiet">This is them</button></p>'),
          ];
        }""")
    assert min(gaps) >= 8, f"gaps {gaps}"


def test_what_follows_a_row_of_acts_sits_a_step_below_it(ui):
    ui.open("#collection")
    gap = ui.page.evaluate("""() => {
          const holder = document.createElement('div');
          holder.innerHTML = '<div class="row"><button class="action">Add</button></div><p class="note">Shown in order.</p>';
          document.querySelector('#view').append(holder);
          const below = holder.querySelector('p').getBoundingClientRect().top;
          return Math.round(below - holder.querySelector('.row').getBoundingClientRect().bottom);
        }""")
    assert gap >= 16


def test_a_sub_heading_after_a_list_stands_clear_of_it(ui):
    """Topics: a kind with one topic held, then "Other centuries" under it."""
    ui.open("#collection")
    gap = ui.page.evaluate("""() => {
          const panel = document.createElement('section');
          panel.className = 'panel';
          panel.innerHTML =
            '<h2>Centuries</h2><ul class="results-list"><li><a class="row-title">20th century</a></li></ul>' +
            '<h3>Other centuries</h3>';
          document.querySelector('#view').append(panel);
          const below = panel.querySelector('h3').getBoundingClientRect().top;
          return Math.round(below - panel.querySelector('ul').getBoundingClientRect().bottom);
        }""")
    assert gap >= 16


def test_ask_offers_start_over_only_once_something_has_been_said(ui):
    ui.open("#discover")
    ui.page.wait_for_selector("#ask-words")
    assert ui.page.locator("#view button:text-is('Start over')").is_hidden()


def test_the_sidebars_budget_line_starts_on_the_navs_glyph_line(ui):
    ui.page.set_viewport_size({"width": 1280, "height": 800})
    ui.open("#collection")
    ui.page.wait_for_selector(".sidebar .budget p")
    lefts = ui.page.evaluate("""() => {
          const range = document.createRange();
          range.selectNodeContents(document.querySelector('.sidebar .budget p'));
          return [range.getBoundingClientRect().left, document.querySelector('nav.sidebar .glyph').getBoundingClientRect().left];
        }""")
    assert abs(lefts[0] - lefts[1]) <= 2, f"budget at {lefts[0]}, glyphs at {lefts[1]}"


def test_the_shared_table_marks_a_column_of_figures_and_no_other(ui):
    """`table()` decides from the values which columns are figures (`core/badges.js`).

    Through the shipped module rather than one screen's table, so every caller's
    columns are covered: figures with units, a figure column holding a dash for
    "none", a column of words, a column of dashes alone, a column with a link
    in it, and a column of titles that are years only in part.
    """
    ui.open("#collection")
    marks = ui.page.evaluate("""async () => {
          const { table } = await import('/static/core/badges.js');
          const link = document.createElement('a');
          link.textContent = '12';
          const node = table('A test table.', ['Title', 'Works', 'Size', 'Faults', 'Gone', 'Linked', 'Years'], [
            ['Winter', '12', '1,110 px', '3', '—', link, '1915'],
            ['Spring', '7', '7.5 MB', '—', '—', '4', 'Composition'],
          ]);
          document.querySelector('#view').append(node);
          const heads = [...node.querySelectorAll('thead th')];
          const cells = [...node.querySelectorAll('tbody tr:first-child td')];
          return heads.map((th, at) => ({
            column: th.textContent,
            head: th.classList.contains('num'),
            cell: cells[at].classList.contains('num'),
            align: getComputedStyle(cells[at]).textAlign,
            numerals: getComputedStyle(cells[at]).fontVariantNumeric,
          }));
        }""")
    figures = {mark["column"] for mark in marks if mark["head"] and mark["cell"]}
    assert figures == {"Works", "Size", "Faults"}
    for mark in marks:
        assert mark["head"] == mark["cell"], mark
        if mark["column"] in figures:
            assert mark["align"] == "right"
            assert "tabular-nums" in mark["numerals"]
        else:
            assert mark["align"] == "left"
