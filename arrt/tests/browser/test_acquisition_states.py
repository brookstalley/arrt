"""Where an accepted work's image stands, in a real browser.

The acquisition queue fetches and prepares every accepted work that holds no
image, one at a time (`build-plan-after-review.md` Chunks 01-02). Three screens
say where a work stands in it, in the same words (`core/acquiring.js`): the Work
page, a Review card for an accepted work, and Activity › Queue. Each state is
said as glyph and word; a work the queue owes nothing says none of them.

The suite's application runs no queue worker, so a work with no image stays
*queued* and the states below are written to the queue's own table, which is
what the worker would have left.
"""

from datetime import UTC, datetime, timedelta

import pytest
from payloads import a_candidate, a_candidate_page, a_card

from arrt.library.acquisition.queue import QueuePause
from arrt.persistence.records import AcquisitionMethod, QueuedAcquisition, RightsStatus, SourceClass

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)


@pytest.fixture
def accepted(services):
    """An accepted work with a source and no image: what acceptance leaves."""

    def _accepted(title="Hunters in the Snow"):
        work = services.catalogue.add_artwork(title=title)
        services.catalogue.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}.jpg",
            provider="gallery_site",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
            is_primary=True,
        )
        return work

    return _accepted


def open_work(ui, work):
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector("#view h3:has-text('The master image')")


# -- the Work page ------------------------------------------------------------


def test_a_work_with_no_image_says_it_is_queued_and_offers_no_retry(ui, accepted):
    work = accepted()

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "queued" in line
    assert "Waiting its turn to be fetched" in line
    assert ui.page.locator(".acquisition-line button").count() == 0, "nothing has failed, so there is nothing to retry"
    panel = ui.page.locator(".panel:has(h3:has-text('The master image'))").inner_text()
    assert "No master image has been acquired" not in panel, "the queue's line replaces the bare sentence"


def test_a_work_the_queue_gave_up_on_says_why_and_retry_puts_it_back(ui, accepted, store):
    work = accepted()
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=work.id, failures=4, detail="the museum answered 404."))

    open_work(ui, work)
    line = ui.page.inner_text(".acquisition-line")
    assert "gave up" in line
    assert "Gave up after 4 tries: the museum answered 404." in line

    ui.page.click(".acquisition-line button:has-text('Retry')")
    ui.page.wait_for_selector(".acquisition-line:has-text('queued')")

    assert "gave up" not in ui.page.inner_text(".acquisition-line")
    assert store.get_queued_acquisition(work.id).failures == 0


def test_a_failed_work_says_which_try_failed_and_when_the_next_is(ui, accepted, store):
    work = accepted()
    next_try = datetime.now(UTC) + timedelta(hours=1)
    store.set_queued_acquisition(
        QueuedAcquisition(artwork_id=work.id, failures=1, next_try_at=next_try, detail="the connection was reset.")
    )

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "failed" in line
    assert "Try 1 of 4 failed: the connection was reset." in line
    assert "It tries again at" in line
    assert ui.page.locator(".acquisition-line button:has-text('Retry now')").count() == 1


def test_a_work_being_fetched_says_since_when_and_that_it_takes_a_while(ui, accepted, services):
    work = accepted()
    # What the worker sets while it holds this work; the suite runs no worker.
    services.acquisition_queue._fetching = (work.id, datetime.now(UTC))

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "fetching" in line
    assert "Being fetched since" in line and "up to half an hour" in line
    assert ui.page.locator(".acquisition-line button").count() == 0, "a fetch in hand is not retried"


def test_a_paused_queue_says_why_and_what_ends_it_on_the_work_page(ui, accepted, services):
    work = accepted()
    services.acquisition_queue._enter_pause(
        QueuePause(condition="NotEnoughSpace", detail="only 1.2 GB free; 2.0 GB required.", since=datetime.now(UTC))
    )

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "paused" in line
    assert "Every fetch is paused: only 1.2 GB free; 2.0 GB required." in line
    assert "MIN_FREE_BYTES" in line


def test_a_pause_nothing_anticipated_points_at_the_journal_rather_than_a_remedy(ui, accepted, services):
    work = accepted()
    services.acquisition_queue.note_error(OSError("database disk image is malformed"))

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "Every fetch is paused: database disk image is malformed" in line
    assert "acquisition.queue_error" in line


def test_a_work_holding_its_image_says_nothing_about_the_queue(ui, ready_work):
    work = ready_work()

    open_work(ui, work)

    assert ui.page.locator(".acquisition-line").count() == 0
    assert "Pixels" in ui.text()


# -- Activity › Queue ---------------------------------------------------------


def test_the_queue_lists_every_work_owed_its_image_in_the_order_it_will_try_them(ui, accepted, store):
    accepted("Accepted first")
    failed = accepted("Failed once")
    store.set_queued_acquisition(
        QueuedAcquisition(artwork_id=failed.id, failures=1, next_try_at=datetime.now(UTC) + timedelta(hours=1), detail="refused.")
    )

    ui.open("#queue")
    ui.page.wait_for_selector("h3:has-text('Fetching images')")

    rows = ui.page.locator(".acquisitions tbody tr").all_inner_texts()
    titles = [row.split("\t")[0] for row in rows]
    assert titles.index("Accepted first") < titles.index("Failed once")
    failed_row = next(row for row in rows if row.startswith("Failed once"))
    assert "failed" in failed_row and "Retry now" in failed_row
    first_row = next(row for row in rows if row.startswith("Accepted first"))
    assert "queued" in first_row and "Retry" not in first_row


def test_a_paused_queue_says_why_and_what_ends_it_above_the_works(ui):
    remedy = "Free space on the art tree's disk, or lower MIN_FREE_BYTES if this deployment means to run closer to full."
    ui.serve(
        "**/api/acquisitions",
        {
            "pause": {
                "condition": "NotEnoughSpace",
                "detail": "only 1.2 GB free; 2.0 GB required.",
                "since": "2026-10-02T12:00:00+00:00",
                "remedy": remedy,
            },
            "works": [
                {
                    "title": "Hunters in the Snow",
                    "acquisition": {
                        "artwork_id": "w-1",
                        "phase": "paused",
                        "failures": 0,
                        "detail": "only 1.2 GB free; 2.0 GB required.",
                        "next_try_at": None,
                        "since": None,
                        "condition": "NotEnoughSpace",
                        "remedy": remedy,
                    },
                }
            ],
        },
    )

    ui.open("#queue")
    ui.page.wait_for_selector(".acquisition-pause")

    pause = ui.page.inner_text(".acquisition-pause")
    assert "Every fetch is paused: only 1.2 GB free" in pause
    assert "MIN_FREE_BYTES" in pause
    panel = ui.page.inner_text(".acquisitions")
    assert panel.index("Every fetch is paused") < panel.index("Hunters in the Snow"), "the pause holds every row beneath it"


def test_a_queue_owing_nothing_says_so(ui):
    ui.serve("**/api/acquisitions", {"pause": None, "works": []})

    ui.open("#queue")
    ui.page.wait_for_selector("h3:has-text('Fetching images (0)')")

    assert "Every accepted work holds its image." in ui.text()
    assert ui.page.locator(".acquisition-pause").count() == 0


# -- a Review card for an accepted work -----------------------------------------


def test_an_accepted_card_says_its_image_is_queued_and_a_pending_one_says_nothing(ui, accepted):
    work = accepted()
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    pending = a_card(a_candidate(work_id="pending", title="Still to judge"))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken, pending]))

    ui.open("#review/run-1")
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-line")

    line = ui.page.inner_text("li.card[data-work='taken'] .acquisition-line")
    assert "queued" in line and "Waiting its turn" in line
    assert ui.page.locator("li.card[data-work='pending'] .acquisition-slot").count() == 0


def test_an_accepted_card_whose_image_is_held_says_so(ui, ready_work):
    work = ready_work()
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken]))

    ui.open("#review/run-1")
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-slot p")

    assert ui.page.inner_text("li.card[data-work='taken'] .acquisition-slot") == "Its image is held and prepared for the wall."


def test_an_accepted_card_the_queue_owes_nothing_and_holds_no_image_says_none_is_coming(ui, accepted, services):
    work = accepted()
    services.catalogue.archive_artwork(work.id)
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken]))

    ui.open("#review/run-1")
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-slot p")

    assert ui.page.inner_text("li.card[data-work='taken'] .acquisition-slot") == "No image is being fetched for it."
