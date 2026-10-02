"""Get in the client, in a real browser against a real server.

Ruling 3: Get is an action on a selection of works the library does not hold, on
the Artist page's *Their work* and the results page, and on a work's own page.
The page stays where it is and says what started, with a link to the run.

The registry is a fake installed where the entry point builds Wikidata's. `POST
/api/gets` is answered by the test, which records what the client sent: what is
under test here is which items the client asks for and what it says afterwards.
The server side of a Get is `tests/integration/test_get_surface.py`'s.
"""

import json

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry  # noqa: E402  (after the skip guard)
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view  # noqa: E402

from arrt.library.registry import (  # noqa: E402
    RegistryArtist,
    RegistryCreator,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.persistence.discovery_records import ResolutionStatus, RunStatus, WorkProvenance  # noqa: E402

BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
CORN = "Q1170285"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
BY = RegistryCreator(qid=BRUEGEL, name="Pieter Brueghel the Elder")
GET_ID = "get-1"


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: RegistryWork(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, image=COMMONS, creators=(BY,)),
        },
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name="Pieter Brueghel the Elder",
                works=(
                    RegistryWorkEntry(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, image=COMMONS),
                    RegistryWorkEntry(qid=HARVESTERS, title="The Harvesters", sitelinks=25),
                    RegistryWorkEntry(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS),
                ),
                works_total=3,
            ),
        },
        matches={
            "harvest": [
                RegistryWorkMatch(qid=HARVESTERS, title="The Harvesters", sitelinks=25, creator=BY),
                RegistryWorkMatch(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS, creator=BY),
            ]
        },
    )


@pytest.fixture
def hunters_held(services, service):
    """The Hunters in the Snow in the library, matched to its item."""
    work = service.add_artwork(title="The Hunters in the Snow")
    services.identity.set_work_identity(work.id, HUNTERS)
    return work


def a_get(skipped=(), *, started=True) -> dict:
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value)
    return {"run": run.model_dump(mode="json") if started else None, "skipped": list(skipped)}


def answer_gets(ui, answer) -> list[list[str]]:
    """Answer every Get with `answer`, and return what each one asked for."""
    sent: list[list[str]] = []

    def handler(route):
        sent.append(json.loads(route.request.post_data)["qids"])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))

    ui.page.route("**/api/gets", handler)
    return sent


def status_text(ui) -> str:
    return " ".join(ui.page.locator("#view .get-status").inner_text().split())


# -- the Artist page ---------------------------------------------------------------


def test_their_work_gets_exactly_the_ticked_works_the_library_does_not_hold(ui, hunters_held):
    sent = answer_gets(ui, a_get())
    ui.open(f"#artist/{BRUEGEL}")
    table = ui.page.locator("section table")
    table.wait_for()

    assert table.locator("tr:has-text('The Hunters in the Snow') input[type='checkbox']").count() == 0, "a held row has no box"
    button = ui.page.locator("#view .get-control button.action")
    assert (button.inner_text(), button.is_disabled()) == ("Get", True)
    table.locator("tr:has-text('The Harvesters') input[type='checkbox']").check()
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").check()
    assert button.inner_text() == "Get 2 works"
    button.click()

    ui.page.wait_for_selector("#view .get-status button:text-is('Open the Get')")
    assert sent == [[HARVESTERS, CORN]]
    assert status_text(ui) == "Getting 2 works. Open the Get"
    assert table.locator("input[type='checkbox']:checked").count() == 0, "the ticks are cleared once got"
    assert button.is_disabled()


def test_unticking_the_last_work_disables_get_again(ui):
    ui.open(f"#artist/{BRUEGEL}")
    box = ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']")
    box.wait_for()
    button = ui.page.locator("#view .get-control button.action")

    box.check()
    box.uncheck()

    assert (button.inner_text(), button.is_disabled()) == ("Get", True)


def test_the_announcement_opens_the_run(ui):
    answer_gets(ui, a_get())
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.open(f"#artist/{BRUEGEL}")
    ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']").check()
    ui.page.click("#view .get-control button.action")

    ui.page.click("#view .get-status button:text-is('Open the Get')")

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#run/{GET_ID}')")


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        pytest.param(
            a_get([{"qid": CORN, "reason": "being_got"}]),
            "Getting 1 work. Left out: 1 is already being got. Open the Get",
            id="one left out",
        ),
        pytest.param(
            a_get([{"qid": HARVESTERS, "reason": "not_found"}, {"qid": CORN, "reason": "not_found"}], started=False),
            "Nothing was started. Left out: 2 are not works Wikidata has.",
            id="everything left out",
        ),
    ],
)
def test_what_a_get_left_out_is_said(ui, answer, said):
    answer_gets(ui, answer)
    ui.open(f"#artist/{BRUEGEL}")
    table = ui.page.locator("section table")
    table.locator("tr:has-text('The Harvesters') input[type='checkbox']").check()
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").check()

    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_function("() => document.querySelector('#view .get-status').textContent.length > 0")
    assert status_text(ui) == said


def test_a_refused_get_is_shown_as_an_error_and_keeps_the_ticks(ui):
    ui.serve(
        "**/api/gets", (400, {"error": "A Get names its works by their Wikidata items, and this deployment has no registry."})
    )
    ui.open(f"#artist/{BRUEGEL}")
    box = ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']")
    box.check()

    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("text=has no registry")
    assert box.is_checked()
    assert not ui.page.locator("#view .get-control button.action").is_disabled()


# -- the results page ----------------------------------------------------------------


def test_the_results_page_gets_the_ticked_wikidata_works(ui):
    sent = answer_gets(ui, a_get())
    ui.open("#search?q=harvest")
    box = ui.page.locator("#view .results-list li:has-text('The Corn Harvest') input[type='checkbox']")
    box.wait_for()

    box.check()
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status button:text-is('Open the Get')")
    assert sent == [[CORN]]


# -- one work's page -----------------------------------------------------------------


def test_a_work_not_held_is_got_from_its_own_page(ui):
    sent = answer_gets(ui, a_get())
    ui.open(f"#work/{HUNTERS}")
    button = ui.page.locator("#view button:text-is('Get this work')")

    button.click()

    ui.page.wait_for_selector("#view .get-status button:text-is('Open the Get')")
    assert sent == [[HUNTERS]]
    assert status_text(ui) == "Getting 1 work. Open the Get"
    assert button.is_disabled(), "got once, a second press would only be left out"
    assert ui.page.locator("#view button:has-text('Search museums'), #view button:has-text('Ask about')").count() == 0


# -- the run, in Queue and on its own screen ------------------------------------------


def test_queue_lists_a_get_as_one(ui):
    ui.serve(
        "**/api/runs",
        {
            "runs": [a_run(run_id=GET_ID, kind="get", intent=None).model_dump(mode="json")],
            "count": 1,
            "total": 1,
            "truncated": False,
        },
    )
    ui.open("#queue")
    ui.page.wait_for_selector("#view table")

    row = " ".join(ui.page.locator("#view tbody tr").first.inner_text().split())
    assert row.startswith("Works you chose Get "), row


@pytest.mark.parametrize(
    ("status", "said"),
    [
        pytest.param(RunStatus.RESOLVING_IMAGES.value, "Looking for images of the 2 works you chose.", id="running"),
        pytest.param(RunStatus.COMPLETED.value, "This Get finished: 1 of the 2 works you chose has an image.", id="finished"),
    ],
)
def test_the_run_screen_words_a_get_as_one(ui, status, said):
    works = [
        a_candidate(work_id="w1", provenance=WorkProvenance.CHOSEN.value, wikidata_qid=HARVESTERS),
        a_candidate(
            work_id="w2",
            provenance=WorkProvenance.CHOSEN.value,
            wikidata_qid=CORN,
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason="not_held",
        ),
    ]
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(a_run(run_id=GET_ID, kind="get", intent=None, status=status), works))
    ui.serve(f"**/api/runs/{GET_ID}/spend*", {"scope": "run", "cost_usd": "0", "run_id": GET_ID, "year": None, "month": None})
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("#view h2:text-is('Get')")

    text = " ".join(ui.text().split())
    assert said in text
    assert "2 works you chose." in text
    assert "asked for" not in text


def test_a_chosen_work_in_review_links_the_item_it_was_got_by(ui):
    card = a_card(work=a_candidate(provenance=WorkProvenance.CHOSEN.value, wikidata_qid=HUNTERS))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.open(f"#review/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("#view h2").first.inner_text() == "Get"
    assert ui.page.locator("#view button:text-is('← The Get')").count() == 1
    ui.page.click(f"li.card .card-meta button:text-is('{HUNTERS}')")

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#work/{HUNTERS}')")


def test_an_artist_with_no_description_shows_nothing_in_its_place(ui):
    """An absent description was passed to the page as `null` and printed as the word."""
    ui.open(f"#artist/{BRUEGEL}")
    ui.page.locator("section table").wait_for()

    assert "null" not in ui.text()
