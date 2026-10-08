"""Search and the Artist page say each work's state once, in a real browser against a real server.

A registry row the library holds is folded into its held twin by the server, so
the page shows it once. A work a run found that nobody has judged reads *Waiting
for review*, links to that review, and offers no Get: a second Get would pay
for an image a verdict is already owed on (the server skips it too). The
registry is a fake installed where the entry point builds Wikidata's; the work
waiting is proposed through the real discovery store.
"""

from dataclasses import replace

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistryPerson,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.persistence.discovery_records import ResolutionStatus

BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
CORN = "Q1170285"
BRUEGEL_NAME = "Pieter Brueghel the Elder"
BY = RegistryCreator(qid=BRUEGEL, name=BRUEGEL_NAME)


@pytest.fixture
def registry():
    return FakeRegistry(
        people={"bruegel": [RegistryPerson(qid=BRUEGEL, label=BRUEGEL_NAME, born=1525, died=1569)]},
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name=BRUEGEL_NAME,
                works=(
                    RegistryWorkEntry(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39),
                    RegistryWorkEntry(qid=HARVESTERS, title="The Harvesters", sitelinks=25),
                    RegistryWorkEntry(qid=CORN, title="The Corn Harvest", sitelinks=12),
                ),
                works_total=3,
            ),
        },
        matches={
            "bruegel": [
                RegistryWorkMatch(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, creator=BY),
                RegistryWorkMatch(qid=HARVESTERS, title="The Harvesters", sitelinks=25, creator=BY),
                RegistryWorkMatch(qid=CORN, title="The Corn Harvest", sitelinks=12, creator=BY),
            ]
        },
    )


@pytest.fixture
def harvesters_waiting(discovery_store, propose):
    """*The Harvesters*, proposed by name as an Ask proposes and found, with no verdict yet."""
    work = propose("The Harvesters", proposed_artist=BRUEGEL_NAME)
    discovery_store.update_candidate_work(replace(work, resolution_status=ResolutionStatus.RESOLVED))
    return work


@pytest.fixture
def hunters_held_by_title(service):
    """*The Hunters in the Snow* in the library with no Wikidata item: folded by title and artist."""
    bruegel = service.add_artist(name=BRUEGEL_NAME, born=1525, died=1569)
    return service.add_artwork(title="The Hunters in the Snow", artist_id=bruegel.id)


def _results(ui, query):
    ui.open(f"#search?q={query}")
    ui.page.wait_for_function(
        "() => { const note = document.querySelector(\"section[aria-labelledby='results-not-held'] p[aria-live]\");"
        " return note !== null && !note.textContent.startsWith('Asking'); }"
    )


def _row(ui, scope, title):
    """The row whose title is `title`; a link's address is read up to its query,
    which carries only where the page was opened from."""
    return ui.page.locator(f"{scope}:has(.row-title:text-is('{title}'))")


# -- the results page ----------------------------------------------------------------


def test_a_held_work_appears_once_on_the_results_page(ui, hunters_held_by_title):
    _results(ui, "bruegel")

    rows = ui.page.locator("#view .results-list li:has(.row-title:text-is('The Hunters in the Snow'))")
    assert rows.count() == 1, "the library's row and Wikidata's are one work"
    assert " ".join(rows.inner_text().split()).endswith("● Held")
    assert rows.locator("input[type='checkbox']").count() == 0


def test_a_work_in_review_says_so_links_to_the_review_and_offers_no_get(ui, harvesters_waiting):
    _results(ui, "bruegel")

    row = _row(ui, "#view .results-list li", "The Harvesters")
    mark = row.locator(".state-mark")
    assert " ".join(mark.inner_text().split()) == "◔ Waiting for review"
    assert mark.get_attribute("href").split("?")[0] == f"#review/{harvesters_waiting.discovery_run_id}"
    assert row.locator("input[type='checkbox']").count() == 0, "a work waiting for review offers no Get"
    # The row beside it, neither held nor waiting, is still got from here.
    assert _row(ui, "#view .results-list li", "The Corn Harvest").locator("input[type='checkbox']").count() == 1
    assert "Waiting for review" not in _row(ui, "#view .results-list li", "The Corn Harvest").inner_text()


def test_an_artist_a_run_proposed_a_work_of_reads_waiting_for_review(ui, harvesters_waiting):
    _results(ui, "bruegel")

    artist = ui.page.locator(f"section[aria-labelledby='results-not-held-artists'] li:has-text('{BRUEGEL_NAME}')")
    assert artist.locator(".state-mark").get_attribute("href").split("?")[0] == f"#review/{harvesters_waiting.discovery_run_id}"


def test_the_mark_opens_the_review(ui, harvesters_waiting):
    _results(ui, "bruegel")

    _row(ui, "#view .results-list li", "The Harvesters").locator(".state-mark").click()

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#review/{harvesters_waiting.discovery_run_id}')")


def test_a_suggestion_says_waiting_for_review_and_holds_no_control(ui, harvesters_waiting):
    ui.open("")
    ui.page.fill("#search", "bruegel")
    option = ui.page.locator("[role='option']:has-text('The Harvesters')")
    option.wait_for()

    assert "Waiting for review" in option.inner_text()
    assert option.locator("a, button, input").count() == 0, "a control inside an option is what ARIA forbids"


# -- the Artist page -----------------------------------------------------------------


def test_the_artist_page_shows_a_work_in_review_without_a_get(ui, harvesters_waiting, hunters_held_by_title):
    ui.open(f"#artist/{BRUEGEL}")
    table = ui.page.locator("section table")
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").wait_for()

    harvesters = table.locator("tr:has-text('The Harvesters')")
    assert harvesters.locator("input[type='checkbox']").count() == 0
    mark = harvesters.locator(".state-mark")
    assert " ".join(mark.inner_text().split()) == "◔ Waiting for review"
    assert mark.get_attribute("href").split("?")[0] == f"#review/{harvesters_waiting.discovery_run_id}"
    assert table.locator("tr:has-text('The Hunters in the Snow')").count() == 1, "held, and listed once"
    assert table.locator("tr:has-text('The Hunters in the Snow') input[type='checkbox']").count() == 0


def test_get_shows_it_is_free_before_it_is_pressed(ui):
    """A Get spends nothing by construction, and says so with the tier every spending control carries."""
    ui.open(f"#artist/{BRUEGEL}")
    get = ui.page.locator("#view .get-control button.action")
    get.wait_for()

    assert " ".join(get.locator("xpath=following-sibling::*[1]").inner_text().split()) == "Cost: Free"
