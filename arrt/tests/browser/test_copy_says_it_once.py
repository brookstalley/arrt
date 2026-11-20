"""Each screen says one thing once, in the curator's words.

The second UX walk (`ux-review-2026-10.md` findings 39 and 44, #359) found copy
that explains the system rather than the art:
- Status under three names, its first lines one fact three times.
- Topic pages titled "Wikidata Q7049".
- An unmatched artist told so three times, with a QID.
- A Get's cost in four rows.
- History's forty near-identical rows.
- The Artworks rail offering a heading over one dead option.
"""

import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

from arrt.persistence.records import EventKind

QID = re.compile(r"\bQ\d+\b")


# -- Status ----------------------------------------------------------------------------


def test_status_has_one_name_and_the_masthead_says_a_state(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    ui.page.wait_for_selector(".wall-reading")

    expect(ui.page.locator("#view h1")).to_have_text("Status", use_inner_text=True)
    expect(ui.page.locator("#sidebar a[href='#health']").last).to_have_text("Status", use_inner_text=True)
    expect(ui.page.locator("#status")).to_have_attribute("data-state", re.compile(r"^(well|unwell)$"))
    # After the masthead has said a state, which is what shows it is drawn.
    expect(ui.page.locator("#status")).not_to_contain_text("Status", use_inner_text=True)


def test_status_says_when_a_wall_was_last_heard_from_once(ui, a_health_reading):
    reading = a_health_reading()
    ui.serve("**/api/health", reading)
    ui.open("#health")
    panel = ui.page.locator(".wall-reading").first
    panel.wait_for()

    expect(panel.locator(".reading-sentence")).to_have_text(re.compile("^" + re.escape("Last heard from ")), use_inner_text=True)
    # After the panel's sentence, which is what shows the page is drawn.
    expect(ui.view).not_to_contain_text("display plane", use_inner_text=True)
    # The server's summary for these walls, whatever it says: the fixture's
    # hand-written "Every wall has reported." until audit wave 2b (chunk 31)
    # derived it through `HealthReading.describe`.
    expect(ui.view, "with one wall the summary is its panel said twice").not_to_contain_text(
        reading["description"], use_inner_text=True
    )
    expect(ui.view).not_to_contain_text("Last reported", use_inner_text=True)


def test_status_keeps_the_summary_over_more_than_one_wall(ui, a_health_reading, a_wall_reading):
    reading = a_health_reading(walls=[a_wall_reading(), a_wall_reading(wall_id="wall-2", name="The study")])
    assert reading["description"].startswith("Every wall has reported")
    ui.serve("**/api/health", reading)
    ui.open("#health")
    ui.page.wait_for_selector(".wall-reading")
    expect(ui.view).to_contain_text(reading["description"], use_inner_text=True)


# -- Topic and Artist ------------------------------------------------------------------


def test_no_topic_title_or_heading_carries_a_bare_item(ui):
    ui.open("#topic/Q99999999")
    ui.page.wait_for_selector("#view h1")
    ui.page.wait_for_load_state("networkidle")
    # The page is quiet, so what the heading and the title were going to become they have become.
    expect(ui.page.locator("#view h1")).not_to_have_text(QID, use_inner_text=True)
    expect(ui.page).not_to_have_title(QID)


def test_an_unmatched_artist_is_told_so_once(ui, service):
    painter = service.add_artist(name="Unmatched Painter")
    service.add_artwork(title="Something", artist_id=painter.id)
    ui.open(f"#artist/{painter.id}")
    ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

    # "Not matched" once: the view's words hold it exactly once.
    exactly_once = re.compile(r"^(?:(?!not matched).)*not matched(?:(?!not matched).)*$", re.DOTALL)
    expect(ui.view).to_have_text(exactly_once, use_inner_text=True)


# -- Artworks' rail ----------------------------------------------------------------------


def test_the_rail_shows_no_group_whose_every_option_is_zero(ui, service, services):
    """Nothing hangs, so *Not on any wall* selects every work and is left out; a
    theme that holds nothing in the collection is no group either."""
    service.add_artwork(title="Study")
    services.display.add_theme(name="Empty theme")
    ui.open("#collection")
    ui.page.wait_for_selector("ul.grid li.card")
    groups = ui.page.locator(".rail").evaluate_all(
        """(rails) => rails.map((rail) => [...rail.querySelectorAll('.facet-option')].map((o) => o.textContent))"""
    )
    for options in groups:
        assert not all(option.endswith("(0)") for option in options), groups


# -- History ----------------------------------------------------------------------------


def test_a_run_of_verdicts_from_one_get_is_one_row_with_its_works_a_click_away(ui, service):
    run_id = "a-get-of-five"
    titles = [f"Study {number}" for number in range(5)]
    for title in titles:
        work = service.add_artwork(title=title)
        service.record_event(EventKind.REJECTED, work_id=work.id, run_id=run_id, detail={"title": title})
    archived = service.add_artwork(title="Kept apart")
    service.archive_artwork(archived.id)

    ui.open("#history")
    ui.page.wait_for_selector("ol.history-events > li")

    rows = ui.page.locator("ol.history-events > li")
    expect(rows).to_have_count(2)
    run = ui.page.locator("ol.history-events > li.verdict-run")
    expect(run).to_contain_text("Turned down 5 works from its Get", use_inner_text=True)
    links = run.locator("a", has_text="its Get")
    expect(links, "the Get is the line's, not each work's").to_have_count(1)
    expect(links).to_have_attribute("href", re.compile("^" + re.escape(f"#get/{run_id}")))
    run.locator("summary").click()
    expect(run.locator(".verdict-run-works li")).to_have_count(5)


def test_two_verdicts_read_one_by_one(ui, service):
    run_id = "a-get-of-two"
    for title in ("One", "Two"):
        work = service.add_artwork(title=title)
        service.record_event(EventKind.REJECTED, work_id=work.id, run_id=run_id, detail={"title": title})
    ui.open("#history")
    ui.page.wait_for_selector("ol.history-events > li")
    expect(ui.page.locator("ol.history-events > li")).to_have_count(2)
    # After both rows are in, so a fold that was going to be drawn would be.
    expect(ui.page.locator("li.verdict-run")).to_have_count(0)


def _verdicts(service, run_id, kind, titles):
    works = []
    for title in titles:
        work = service.add_artwork(title=title)
        service.record_event(kind, work_id=work.id, run_id=run_id, detail={"title": title})
        works.append(work)
    return works


def test_exactly_three_verdicts_fold_and_accepted_works_are_links(ui, service):
    accepted = _verdicts(service, "a-get-of-three", EventKind.ACCEPTED, ["Alpha", "Beta", "Gamma"])
    ui.open("#history")
    run = ui.page.locator("ol.history-events > li.verdict-run")
    run.wait_for()
    expect(run).to_contain_text("Accepted 3 works from its Get", use_inner_text=True)
    run.locator("summary").click()
    # Three links, and each accepted work has exactly one, up to its query: the set the sorted lists compared.
    expect(run.locator(".verdict-run-works a")).to_have_count(len(accepted))
    for work in accepted:
        expect(
            run.locator(f".verdict-run-works a[href='#work/{work.id}'], .verdict-run-works a[href^='#work/{work.id}?']")
        ).to_have_count(1)


def test_a_run_is_broken_by_another_verdict_or_another_get(ui, service):
    """Newest first: three from one Get, one accepted between, three from another Get."""
    _verdicts(service, "get-one", EventKind.REJECTED, ["A1", "A2", "A3"])
    _verdicts(service, "get-one", EventKind.ACCEPTED, ["B1"])
    _verdicts(service, "get-two", EventKind.REJECTED, ["C1", "C2", "C3"])
    ui.open("#history")
    ui.page.wait_for_selector("ol.history-events > li")
    rows = ui.page.locator("ol.history-events > li")
    expect(rows).to_have_count(3)
    expect(ui.page.locator("li.verdict-run")).to_have_count(2)
    # Two links, one to each Get, up to its query: the set the sorted lists compared.
    expect(ui.page.locator("li.verdict-run > span > a")).to_have_count(2)
    for get in ("get-one", "get-two"):
        expect(
            ui.page.locator(f"li.verdict-run > span > a[href='#get/{get}'], li.verdict-run > span > a[href^='#get/{get}?']")
        ).to_have_count(1)
