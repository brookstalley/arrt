"""Search and the Artist page say each work's state once, in a real browser against a real server.

A registry row the library holds is folded into its held twin by the server, so
the page shows it once. A work a run found that nobody has judged reads *Waiting
for review*, links to that review, and offers no Get: a second Get would pay
for an image a verdict is already owed on (the server skips it too). The
registry is a fake installed where the entry point builds Wikidata's; the work
waiting is proposed through the real discovery store.
"""

import re
from dataclasses import replace

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from playwright.sync_api import expect

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistryPerson,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.persistence.discovery_records import ResolutionStatus
from arrt.persistence.records import AcquisitionMethod, FetchStatus, RightsStatus, SourceClass

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


def _begins(words):
    """A pattern for text that begins with `words`, in whatever whitespace the page lays them out in.

    A string is compared folded to single spaces, but `startswith` is a pattern, and a pattern
    is matched against the raw text (`docs/testing.md`, hazard 2): so each gap is any whitespace.
    """
    return re.compile("^" + r"\s+".join(re.escape(word) for word in words.split()))


def _review_address(run_id):
    """A link's address up to its query, which carries only where the page was opened from."""
    return re.compile("^" + re.escape(f"#review/{run_id}") + r"(\?|$)")


def _row(ui, scope, title):
    """The row whose title is `title`; a link's address is read up to its query,
    which carries only where the page was opened from."""
    return ui.page.locator(f"{scope}:has(.row-title:text-is('{title}'))")


# -- the results page ----------------------------------------------------------------


def test_a_held_work_appears_once_on_the_results_page(ui, hunters_held_by_title):
    _results(ui, "bruegel")

    rows = ui.page.locator("#view .results-list li:has(.row-title:text-is('The Hunters in the Snow'))")
    expect(rows, "the library's row and Wikidata's are one work").to_have_count(1)
    # Under *Held*, the group's heading is the only "Held", and this work, held
    # with no master yet, says so in its picture's place (audit 6, finding 14;
    # until 2026-11-19 the row ended "● Held" and said nothing of its picture).
    expect(rows).to_have_text(_begins("No picture The Hunters in the Snow"), use_inner_text=True)
    expect(rows).not_to_contain_text("Held", use_inner_text=True)
    # A held work is never offered a Get. Its tick, since #317, is the held
    # half's, to add to a theme or archive: ticked, it lights those and leaves
    # Get dark. (This line asserted no tick at all until then, which was the
    # gap #317 closed, not the contract.)
    expect(rows.locator("input[type='checkbox']")).to_have_count(1)
    ui.page.click("#view button.select-toggle")
    rows.locator("input[type='checkbox']").check()
    expect(ui.page.locator("#view .selection button.selection-archive")).to_be_enabled()
    expect(ui.page.locator("#view .selection button.get-open")).to_be_disabled()


def test_a_folded_held_row_asks_for_the_picture_of_the_work_that_has_one_and_no_other(
    ui, pictures_load, hunters_held_by_title, service
):
    """The row's picture is the server's `pictured_artwork_id`, never a guess.

    *The Hunters in the Snow* with no master asks for no thumbnail (one would be
    refused) and says *No picture*; given a master, the row asks for that work's
    thumbnail and says nothing of its absence.

    The master has no file, so the server refuses its thumbnail, and a picture
    that fails to load takes its frame with it (`workPicture` in
    `core/registry.js`): the `<img>` asserted below lived only until the refusal
    arrived, and the test passed only when it was read first. The thumbnail is
    answered with a real image (`pictures_load`) so the frame stays."""
    _results(ui, "bruegel")
    row = _row(ui, "#view .results-list li", "The Hunters in the Snow")
    expect(row.locator(".work-pic-absent")).to_have_count(1)
    assert not [url for url in ui.requests if url.endswith("/thumbnail")], "a work with no picture was asked for one"

    _give_a_master(service, hunters_held_by_title)
    _results(ui, "bruegel")
    expect(row.locator(".work-pic-held img")).to_have_attribute("src", f"/api/works/{hunters_held_by_title.id}/thumbnail")
    expect(row.locator(".work-pic-absent")).to_have_count(0)


def _give_a_master(service, work):
    """A work's master on record, as a finished fetch leaves it; no file, so its thumbnail is refused."""
    source = service.add_source(
        artwork_id=work.id,
        url=f"https://museum.example/{work.id}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash=f"hash-{work.id}",
        fetch_status=FetchStatus.OK,
    )


def test_a_work_in_review_says_so_links_to_the_review_and_offers_no_get(ui, harvesters_waiting):
    _results(ui, "bruegel")

    row = _row(ui, "#view .results-list li", "The Harvesters")
    mark = row.locator(".state-mark")
    expect(mark).to_have_text("◔ Waiting for review", use_inner_text=True)
    expect(mark).to_have_attribute("href", _review_address(harvesters_waiting.discovery_run_id))
    # Anchored by the mark above, which only a drawn row has.
    expect(row.locator("input[type='checkbox']"), "a work waiting for review offers no Get").to_have_count(0)
    # The row beside it, neither held nor waiting, is still got from here.
    corn = _row(ui, "#view .results-list li", "The Corn Harvest")
    expect(corn.locator("input[type='checkbox']")).to_have_count(1)
    expect(corn).not_to_contain_text("Waiting for review", use_inner_text=True)


def test_an_artist_a_run_proposed_a_work_of_reads_waiting_for_review(ui, harvesters_waiting):
    _results(ui, "bruegel")

    artist = ui.page.locator(f"section[aria-labelledby='results-not-held-artists'] li:has-text('{BRUEGEL_NAME}')")
    expect(artist.locator(".state-mark")).to_have_attribute("href", _review_address(harvesters_waiting.discovery_run_id))


def test_the_mark_opens_the_review(ui, harvesters_waiting):
    _results(ui, "bruegel")

    _row(ui, "#view .results-list li", "The Harvesters").locator(".state-mark").click()

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#review/{harvesters_waiting.discovery_run_id}')")


def test_a_suggestion_says_waiting_for_review_and_holds_no_control(ui, harvesters_waiting):
    ui.open("")
    ui.page.fill("#search", "bruegel")
    option = ui.page.locator("[role='option']:has-text('The Harvesters')")
    option.wait_for()

    expect(option).to_contain_text("Waiting for review", use_inner_text=True)
    expect(option.locator("a, button, input"), "a control inside an option is what ARIA forbids").to_have_count(0)


# -- the Artist page -----------------------------------------------------------------


def test_the_artist_page_shows_a_work_in_review_without_a_get(ui, harvesters_waiting, hunters_held_by_title):
    ui.open(f"#artist/{BRUEGEL}")
    # Ticks show in *Select* mode (`core/selecting.js`).
    ui.page.click("#view button.select-toggle")
    table = ui.page.locator("section table")
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").wait_for()

    harvesters = table.locator("tr:has-text('The Harvesters')")
    # The rows are drawn, with their ticks, as the wait above saw (the Corn Harvest's is there).
    expect(harvesters.locator("input[type='checkbox']")).to_have_count(0)
    mark = harvesters.locator(".state-mark")
    expect(mark).to_have_text("◔ Waiting for review", use_inner_text=True)
    expect(mark).to_have_attribute("href", _review_address(harvesters_waiting.discovery_run_id))
    expect(table.locator("tr:has-text('The Hunters in the Snow')"), "held, and listed once").to_have_count(1)
    expect(table.locator("tr:has-text('The Hunters in the Snow') input[type='checkbox']")).to_have_count(0)


def test_get_shows_it_is_free_before_it_is_pressed(ui):
    """A Get spends nothing by construction, and says so with the tier every spending control carries.

    In the dialog *Get…* opens, after *Add to*, where the Get it qualifies is
    pressed; the toolbar holds only the opener (ruling 1 of 2026-10-27)."""
    ui.open(f"#artist/{BRUEGEL}")
    ui.page.click("#view button.select-toggle")
    ui.page.locator("#view section table input[type='checkbox']").first.check()
    ui.page.click("#view button.get-open")
    get = ui.page.locator("dialog button.get-confirm")
    get.wait_for()

    expect(ui.page.locator("dialog .badge-tier")).to_have_text("Cost: Free", use_inner_text=True)
    expect(ui.page.locator("#view .get-control .badge-tier"), "the tier is said once, in the dialog").to_have_count(0)
    tier = ui.page.locator("dialog .badge-tier").bounding_box()  # one-shot: geometry, read once the dialog's tier is said
    field = ui.page.locator("dialog .get-into").bounding_box()  # one-shot: geometry, read once the dialog's tier is said
    assert tier is not None
    assert field is not None
    assert tier["x"] == field["x"], "the tier starts its line, under Add to, rather than centred"
