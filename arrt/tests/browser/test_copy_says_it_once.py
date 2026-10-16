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

from arrt.persistence.records import EventKind

QID = re.compile(r"\bQ\d+\b")


# -- Status ----------------------------------------------------------------------------


def test_status_has_one_name_and_the_masthead_says_a_state(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    ui.page.wait_for_selector(".wall-reading")

    heading = ui.page.locator("#view h1").inner_text()
    page_link = ui.page.locator("#sidebar a[href='#health']").last.inner_text().strip()
    assert heading == "Status"
    assert page_link == "Status"
    assert ui.page.locator("#status").get_attribute("data-state") in {"well", "unwell"}
    assert "Status" not in ui.page.locator("#status").inner_text()


def test_status_says_when_a_wall_was_last_heard_from_once(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.open("#health")
    panel = ui.page.locator(".wall-reading").first
    panel.wait_for()

    text = ui.page.locator("#view").inner_text()
    assert panel.locator(".reading-sentence").inner_text().startswith("Last heard from ")
    assert "display plane" not in text
    assert "Every wall has reported." not in text, "with one wall the summary is its panel said twice"
    assert "Last reported" not in text


def test_status_keeps_the_summary_over_more_than_one_wall(ui, a_health_reading, a_wall_reading):
    reading = a_health_reading(walls=[a_wall_reading(), a_wall_reading(wall_id="wall-2", name="The study")])
    ui.serve("**/api/health", reading)
    ui.open("#health")
    ui.page.wait_for_selector(".wall-reading")
    assert "Every wall has reported." in ui.page.locator("#view").inner_text()


# -- Topic and Artist ------------------------------------------------------------------


def test_no_topic_title_or_heading_carries_a_bare_item(ui):
    ui.open("#topic/Q99999999")
    ui.page.wait_for_selector("#view h1")
    ui.page.wait_for_load_state("networkidle")
    heading = ui.page.locator("#view h1").inner_text()
    assert not QID.search(heading), heading
    assert not QID.search(ui.page.title()), ui.page.title()


def test_an_unmatched_artist_is_told_so_once(ui, service):
    painter = service.add_artist(name="Unmatched Painter")
    service.add_artwork(title="Something", artist_id=painter.id)
    ui.open(f"#artist/{painter.id}")
    ui.page.wait_for_selector("section[aria-labelledby='their-work'] p.note")

    text = ui.page.locator("#view").inner_text()
    assert len(re.findall(r"not matched", text)) == 1, text


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
    assert rows.count() == 2
    run = ui.page.locator("ol.history-events > li.verdict-run")
    assert "Turned down 5 works from its Get" in run.inner_text()
    links = run.locator("a", has_text="its Get")
    assert links.count() == 1, "the Get is the line's, not each work's"
    assert links.get_attribute("href").startswith(f"#get/{run_id}")
    run.locator("summary").click()
    assert run.locator(".verdict-run-works li").count() == 5


def test_two_verdicts_read_one_by_one(ui, service):
    run_id = "a-get-of-two"
    for title in ("One", "Two"):
        work = service.add_artwork(title=title)
        service.record_event(EventKind.REJECTED, work_id=work.id, run_id=run_id, detail={"title": title})
    ui.open("#history")
    ui.page.wait_for_selector("ol.history-events > li")
    assert ui.page.locator("ol.history-events > li").count() == 2
    assert ui.page.locator("li.verdict-run").count() == 0


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
    assert "Accepted 3 works from its Get" in run.inner_text()
    run.locator("summary").click()
    hrefs = run.locator(".verdict-run-works a").evaluate_all("(links) => links.map((a) => a.getAttribute('href'))")
    assert sorted(href.split("?")[0] for href in hrefs) == sorted(f"#work/{work.id}" for work in accepted)


def test_a_run_is_broken_by_another_verdict_or_another_get(ui, service):
    """Newest first: three from one Get, one accepted between, three from another Get."""
    _verdicts(service, "get-one", EventKind.REJECTED, ["A1", "A2", "A3"])
    _verdicts(service, "get-one", EventKind.ACCEPTED, ["B1"])
    _verdicts(service, "get-two", EventKind.REJECTED, ["C1", "C2", "C3"])
    ui.open("#history")
    ui.page.wait_for_selector("ol.history-events > li")
    rows = ui.page.locator("ol.history-events > li")
    assert rows.count() == 3
    assert ui.page.locator("li.verdict-run").count() == 2
    hrefs = ui.page.locator("li.verdict-run > span > a").evaluate_all("(links) => links.map((a) => a.getAttribute('href'))")
    assert sorted(href.split("?")[0] for href in hrefs) == ["#get/get-one", "#get/get-two"]
