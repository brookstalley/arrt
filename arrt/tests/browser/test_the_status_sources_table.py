"""Status's image sources as one table, one row per source, in a real browser.

The owner's ruling of 2026-10-08 (#265): a box per source, with its sentence and
its "faults: 0" line, was too long, and there will be more sources. So one row
each, with what each source has given the library beside its state. As the panel
narrows the columns leave in a fixed order, and the one fact that may never leave
the screen is a fault: when the Faults column goes, its count moves into State.

Which columns show at a width is decided by the stylesheet, so only a browser
can say it; and whether a narrowing table still fits depends on the fonts, so the
sweep runs twice, once with every glyph spaced wider, because CI's fonts are
wider than a Mac's.
"""

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from payloads import a_searched_source
from playwright.sync_api import expect

#: Every column, left to right, by the class the client gives it.
COLUMNS = [
    "source",
    "state",
    "offered",
    "chosen",
    "only-here",
    "searches",
    "hit-rate",
    "latency",
    "median",
    "faults",
    "last-fault",
]
#: Never dropped.
KEPT = {"source", "state", "offered", "chosen"}
#: The order they leave in as the width narrows: the owner's for median,
#: last-fault, only-here and faults (2026-10-08), with the search record's three
#: placed among them, Hit rate kept longest.
DROP_ORDER = ["median", "searches", "last-fault", "latency", "only-here", "hit-rate", "faults"]


def _yields(*rows):
    return {
        "sources": [dict(zip(("name", "offered", "chosen", "only_here", "median_long_edge"), row, strict=True)) for row in rows]
    }


@pytest.fixture
def three_sources(ui, a_health_reading, a_source_reading):
    """A source that faulted, one with the longest built-in museum name, and one declined with a setting's name.

    The first two searched: the Art Institute answered 80 of its last 100 works,
    60 with an image, at a median of 2.35 s; the National Gallery 3 of 4, 2 with
    an image, and late, at a median of 95 s. The declined one was never searched.
    """
    ui.serve(
        "**/api/health",
        a_health_reading(
            sources=[
                a_searched_source("artic", searched=100, answered=80, with_images=60, median_latency_seconds=2.35, faults=2),
                a_searched_source("nga", searched=4, answered=3, with_images=2, median_latency_seconds=95.0),
                a_source_reading(name="commons", state="declined", reason="WIKIDATA_USER_AGENT is unset"),
            ]
        ),
    )
    ui.serve("**/api/sources/yields", _yields(("artic", 1240, 31, 7, 4096), ("nga", 15, 2, 0, 3001), ("commons", 0, 0, 0, None)))


def _rows(ui):
    """Each body row as {column: its visible text}, the columns the stylesheet hides left out."""
    return ui.page.evaluate("""() => [...document.querySelectorAll('.source-table tbody tr')].map((row) =>
             Object.fromEntries([...row.cells]
               .filter((cell) => getComputedStyle(cell).display !== 'none')
               .map((cell) => [[...cell.classList].find((name) => name.startsWith('col-')).slice(4), cell.innerText.trim()])))""")


def test_each_source_is_one_row_with_its_state_in_words_and_what_it_has_given(ui, three_sources):
    ui.page.set_viewport_size({"width": 1600, "height": 900})
    ui.open("#health")
    ui.page.wait_for_selector(".source-table tbody tr")

    rows = _rows(ui)
    assert [row["source"].split("\n")[0] for row in rows] == [
        "Art Institute of Chicago",
        "National Gallery of Art, Washington",
        "Wikimedia Commons",
    ]
    # Every column at this width, and the State a word.
    assert all(list(row) == COLUMNS for row in rows)
    assert [row["state"] for row in rows] == ["Loaded", "Loaded", "Not configured here"]
    # The declined source says which setting would change it.
    assert "WIKIDATA_USER_AGENT is unset" in rows[2]["source"]
    assert [(row["offered"], row["chosen"], row["only-here"]) for row in rows] == [
        ("1,240", "31", "7"),
        ("15", "2", "0"),
        ("0", "0", "0"),
    ]
    assert [row["median"] for row in rows] == ["4,096 px", "3,001 px", "—"]
    # The search record's three: a rate over what it answered, a median in the
    # unit a person reads, and "—" for a source that answered nothing.
    assert [(row["searches"], row["hit-rate"], row["latency"]) for row in rows] == [
        ("100", "75%", "2.4 s"),
        ("4", "67%", "2 minutes"),
        ("0", "—", "—"),
    ]
    # "75%" beside "Searches 100" is not 75 of 100: the column is headed as a rate of what was
    # answered, and the figure says which numbers it is of (60 of the 80 answered, 20 not).
    expect(ui.page.locator(".source-table thead th.col-hit-rate")).to_have_text("Hit rate of answered")
    titles = ui.page.evaluate(
        "() => [...document.querySelectorAll('.source-table tbody td.col-hit-rate span')].map((span) => span.title)"
    )
    assert titles == [
        "60 of the 80 searches it answered had an image; 20 of the 100 searches were not answered.",
        "2 of the 3 searches it answered had an image; 1 of the 4 searches were not answered.",
        "",
    ]
    assert [row["faults"] for row in rows] == ["2", "0", "—"]
    assert rows[0]["last-fault"] == "12 seconds ago: KeyError: 'x'"
    assert rows[1]["last-fault"] == "—"
    # One table, not a box per source: the old per-source sentences are gone.
    expect(ui.page.locator("ul.source-readings")).to_have_count(0)


@pytest.mark.parametrize("wide_fonts", [False, True], ids=["fonts-as-they-are", "fonts-spaced-wider"])
def test_columns_leave_in_the_owners_order_and_a_fault_never_leaves_the_screen(ui, three_sources, wide_fonts):
    ui.page.set_viewport_size({"width": 1600, "height": 900})
    ui.open("#health")
    ui.page.wait_for_selector(".source-table tbody tr")
    if wide_fonts:
        ui.page.add_style_tag(content="* { letter-spacing: 0.1em !important; }")

    seen = []
    # Every 10 px from a wide desktop to the narrowest phone, so a column that
    # still overflows just above its breakpoint has nowhere to fall between steps.
    for width in range(1600, 319, -10):
        ui.page.set_viewport_size({"width": width, "height": 900})
        reading = ui.page.evaluate("""() => {
                 const table = document.querySelector('.source-table');
                 const visible = (node) => node && getComputedStyle(node).display !== 'none' && node.getClientRects().length > 0;
                 // Read off a body row rather than the headings, which a phone's
                 // stacked cards move off screen while every cell stays.
                 const faulted = table.querySelector('tbody tr');
                 const column_of = (cell) => [...cell.classList].find((name) => name.startsWith('col-')).slice(4);
                 const shown = [...faulted.cells].filter(visible).map(column_of);
                 const column = faulted.querySelector('.col-faults');
                 const inState = faulted.querySelector('.state-faults');
                 const scroll = table.querySelector('.table-scroll');
                 return {
                   shown,
                   faultsColumn: visible(column) ? column.innerText.trim() : null,
                   faultsInState: visible(inState) ? inState.innerText.trim() : null,
                   overflow: scroll.scrollWidth - scroll.clientWidth,
                   page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                 };
               }""")
        dropped = [name for name in COLUMNS if name not in reading["shown"]]
        assert set(reading["shown"]) >= KEPT, (width, reading)
        # A prefix of the drop order: nothing leaves before what the owner ranked below it.
        assert set(dropped) == set(DROP_ORDER[: len(dropped)]), (width, dropped)
        # The fault count, exactly once: in its column, or in State once the column has gone.
        where = (reading["faultsColumn"], reading["faultsInState"])
        assert where == (("2", None) if "faults" in reading["shown"] else (None, "· 2 faults")), (width, reading)
        # Dropping columns is what keeps the table whole: no sideways scroll, no wider page.
        assert max(reading["overflow"], reading["page"]) <= 1, (width, reading)
        seen.append(len(dropped))

    # The sweep reached both ends: every column at its widest, only the four kept at its narrowest.
    assert (seen[0], seen[-1]) == (0, len(DROP_ORDER))
    # And each drop happened at some width, so no step was skipped.
    assert set(seen) == set(range(len(DROP_ORDER) + 1))


def test_counts_that_cannot_be_read_are_said_and_the_states_still_shown(ui, a_health_reading, a_source_reading):
    """The product's only alerting surface: a failed count read must not take the sources' states with it."""
    ui.serve("**/api/health", a_health_reading(sources=[a_source_reading(name="artic", faults=1)]))
    ui.serve("**/api/sources/yields", (500, {"detail": "the catalogue file is locked"}))
    ui.open("#health")
    ui.page.wait_for_selector(".source-table tbody tr")

    expect(ui.view).to_contain_text("The counts could not be read", use_inner_text=True)
    row = _rows(ui)[0]
    assert row["state"] == "Loaded"
    assert row["offered"] == row["chosen"] == "—"
    expect(ui.page.locator("#error:not([hidden])")).to_have_count(0)


def test_status_says_nothing_of_a_television_or_its_geometry(ui):
    """The geometry panel was one television's; the server no longer has one (#266)."""
    ui.open("#health")
    ui.page.wait_for_selector("#view h1:text-is('Status')")
    ui.page.wait_for_load_state("networkidle")

    expect(ui.view).not_to_contain_text("television", use_inner_text=True, ignore_case=True)
    expect(ui.view).not_to_contain_text("geometry", use_inner_text=True, ignore_case=True)
    expect(ui.view).not_to_contain_text("artwork box", use_inner_text=True, ignore_case=True)


@pytest.mark.parametrize(
    ("searched", "answered", "with_images", "median", "said"),
    [
        (5, 4, 3, 4.0, ("5", "75%", "4 s")),
        (1_240, 1_000, 0, 0.84, ("1,240", "0%", "0.8 s")),
        (3, 3, 3, 35.4, ("3", "100%", "35 s")),
        (2, 0, 0, None, ("2", "—", "—")),
    ],
    ids=["three-of-four", "answered-without-images", "every-answer-an-image", "answered-none"],
)
def test_the_three_search_columns_read_what_the_record_says(ui, a_health_reading, searched, answered, with_images, median, said):
    """Searches, Hit rate and Median latency, as `GET /api/health` carries them for each source.

    "0%" is a source that answered and never had an image; "—" is one that
    answered nothing, so has no rate to state.
    """
    source = a_searched_source(
        "artic",
        searched=searched,
        answered=answered,
        with_images=with_images,
        median_latency_seconds=median,
        owed=searched - answered,
    )
    ui.serve("**/api/health", a_health_reading(sources=[source]))
    ui.serve("**/api/sources/yields", _yields(("artic", 10, 1, 0, 4096)))
    ui.page.set_viewport_size({"width": 1600, "height": 900})
    ui.open("#health")
    ui.page.wait_for_selector(".source-table tbody tr")

    (row,) = _rows(ui)
    assert (row["searches"], row["hit-rate"], row["latency"]) == said
    # Each under its own heading, in words.
    for name, heading in (("searches", "Searches"), ("hit-rate", "Hit rate of answered"), ("latency", "Median latency")):
        expect(ui.page.locator(f".source-table thead th.col-{name}")).to_have_text(heading)
