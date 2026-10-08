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
    ui.page.wait_for_selector("#view h2:has-text('Master image')")


# -- the Work page ------------------------------------------------------------


def test_a_work_with_no_image_says_it_is_queued_and_offers_no_retry(ui, accepted):
    work = accepted()

    open_work(ui, work)

    line = ui.page.inner_text(".acquisition-line")
    assert "queued" in line
    assert "Waiting its turn to be fetched" in line
    assert ui.page.locator(".acquisition-line button").count() == 0, "nothing has failed, so there is nothing to retry"
    panel = ui.page.locator(".panel:has(h2:has-text('Master image'))").inner_text()
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
    assert "Being fetched since" in line
    assert "up to half an hour" in line
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


def test_the_queue_lists_the_works_in_line_in_the_order_it_will_try_them(ui, accepted, services):
    accepted("Accepted first")
    retried = accepted("Retried")
    # A Retry goes to the front of the line.
    services.acquisition_queue.retry(retried.id)

    ui.open("#queue")
    ui.page.wait_for_selector(".acquisitions .in-line tbody tr")

    rows = ui.page.locator(".acquisitions .in-line tbody tr").all_inner_texts()
    titles = [row.split("\t")[0] for row in rows]
    assert titles.index("Retried") < titles.index("Accepted first")
    first_row = next(row for row in rows if row.startswith("Accepted first"))
    assert "queued" in first_row
    assert "Retry" not in first_row


def _failed(store, work, detail, *, failures=1):
    store.set_queued_acquisition(
        QueuedAcquisition(
            artwork_id=work.id,
            failures=failures,
            next_try_at=None if failures >= 4 else datetime.now(UTC) + timedelta(hours=1),
            detail=detail,
        )
    )


def test_a_failed_work_is_under_its_cause_and_opens_into_its_title_with_its_own_retry(ui, accepted, store):
    accepted("Waiting")
    failed = accepted("Failed once")
    _failed(store, failed, "refused.")

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    assert ui.page.locator(".in-line tbody tr:has-text('Failed once')").count() == 0, "a failed work was also in line"
    head = ui.page.inner_text(".failure-cause")
    assert "refused." in head
    assert "1 work" in head
    assert ui.page.locator(".failure-cause button:has-text('Retry all')").count() == 1

    ui.page.click(".failure-cause a:has-text('Show the works')")
    ui.page.wait_for_selector(".failure-cause-works tbody tr")

    row = ui.page.locator(".failure-cause-works tbody tr").inner_text()
    assert row.startswith("Failed once")
    assert "Try 1 of 4 failed. It tries again at" in row, "the cause is the group's heading, not repeated per work"
    href = ui.page.locator(".failure-cause-works a:has-text('Failed once')").get_attribute("href")
    assert href.startswith(f"#work/{failed.id}")
    assert ui.page.locator(".failure-cause-works button:has-text('Retry now')").count() == 1
    assert "cause=refused." in ui.page.url, "opening a group is an address"


def test_two_thousand_failures_of_one_cause_are_one_row_and_its_works_page(ui, seed_the_served_catalogue, catalogue_file, store):
    """`ux-review-2026-10.md` finding 18: Queue at 2,000 failures was one 209,000-px table naming each work by id."""
    works = seed_the_served_catalogue(size=2000)
    with catalogue_file.transaction():
        for work in works:
            # What the acquirer's refusal records for a work with no source: its id inside.
            _failed(store, work, f"Artwork {work.id!r} has no source to acquire from.")

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    assert ui.page.locator(".failure-cause").count() == 1
    head = ui.page.inner_text(".failure-cause")
    assert "The work has no source to acquire from." in head
    assert "2000 works" in head
    assert ui.page.locator(".acquisitions tbody tr").count() <= 25, "a failure was drawn as a row before its group opened"
    height = ui.page.evaluate("() => document.documentElement.scrollHeight")
    assert height < 3000, f"Queue is {height}px tall with one cause"

    ui.page.click(".failure-cause a:has-text('Show the works')")
    ui.page.wait_for_selector(".failure-cause-works tbody tr")

    rows = ui.page.locator(".failure-cause-works tbody tr")
    assert rows.count() == 25
    shown = ui.page.inner_text(".acquisitions")
    assert not any(work.id in shown for work in works), "a work was named by its id"
    assert "1–25 of 2000" in shown
    ui.page.click(".failure-cause-works a:has-text('Next')")
    ui.page.wait_for_selector(".failure-cause-works :text('26–50 of 2000')")
    assert rows.count() == 25

    # On a phone the group and its opened works fit across: no sideways scroll.
    ui.page.set_viewport_size({"width": 390, "height": 844})
    overflow = ui.page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, f"Queue scrolls {overflow}px sideways on a phone"


def test_retry_all_retries_the_group_in_one_request_and_says_what_it_did(ui, accepted, store, services):
    retried = [accepted(f"Given up {number}") for number in range(3)]
    sourceless = services.catalogue.add_artwork(title="Sourceless")
    for work in (*retried, sourceless):
        _failed(store, work, "the museum answered 404.", failures=4)

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    ui.page.click(".failure-cause button:has-text('Retry all')")
    said = ui.page.wait_for_selector(".retry-all-said")

    assert said.inner_text() == "3 works put back in line. 1 work not: The work has no source to acquire from."
    assert len(ui.requests_matching("/api/acquisitions/causes/retry")) == 1
    assert ui.requests_matching("/acquisition/retry") == [], "Retry all asked once per work"
    assert {store.get_queued_acquisition(work.id).failures for work in retried} == {0}
    # The one refused stays under its cause; the three are back in line.
    assert ui.page.locator(".failure-cause").count() == 1
    assert "1 work" in ui.page.inner_text(".failure-cause")
    in_line = ui.page.inner_text(".in-line")
    assert all(f"Given up {number}" in in_line for number in range(3))


def test_the_works_in_line_page_from_the_server(ui, accepted):
    for number in range(30):
        accepted(f"Waiting {number:02}")

    ui.open("#queue")
    ui.page.wait_for_selector(".in-line tbody tr")

    assert ui.page.locator(".in-line tbody tr").count() == 25
    ui.page.click(".in-line a:has-text('Next')")
    ui.page.wait_for_selector(".in-line .queue-paging :text('26–')")
    assert "offset=25" in ui.page.url
    assert ui.requests_matching("/api/acquisitions?offset=25")


def _listing(pause=None, works=(), failing=0, causes=0):
    """`GET /api/acquisitions` as the server answers it: one page of the works in line."""
    return {
        "pause": pause,
        "works": list(works),
        "total": len(works),
        "limit": 25,
        "offset": 0,
        "failing": failing,
        "causes": causes,
    }


def test_a_paused_queue_says_why_and_what_ends_it_above_the_works(ui):
    remedy = "Free space on the art tree's disk, or lower MIN_FREE_BYTES if this deployment means to run closer to full."
    ui.serve(
        "**/api/acquisitions",
        _listing(
            pause={
                "condition": "NotEnoughSpace",
                "detail": "only 1.2 GB free; 2.0 GB required.",
                "since": "2026-10-02T12:00:00+00:00",
                "remedy": remedy,
            },
            works=[
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
        ),
    )

    ui.open("#queue")
    ui.page.wait_for_selector(".acquisition-pause")

    pause = ui.page.inner_text(".acquisition-pause")
    assert "Every fetch is paused: only 1.2 GB free" in pause
    assert "MIN_FREE_BYTES" in pause
    panel = ui.page.inner_text(".acquisitions")
    assert panel.index("Every fetch is paused") < panel.index("Hunters in the Snow"), "the pause holds every row beneath it"


def test_a_queue_owing_nothing_says_so(ui):
    ui.serve("**/api/acquisitions", _listing())

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('Fetching images (0)')")

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
    assert "queued" in line
    assert "Waiting its turn" in line
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


def test_a_failed_work_keeps_the_wall_label_layout_with_its_failure_in_the_record(ui, accepted, store):
    """The page a curator meets most while the library fills: no picture, a
    failed try, a source. The label still sits beside where the picture would
    be, and the failure is in the Master image section, ruled like the rest."""
    work = accepted()
    _failed(store, work, "the connection was reset.")
    ui.page.set_viewport_size({"width": 1280, "height": 900})

    open_work(ui, work)

    layout = ui.page.evaluate("""() => {
          const hero = document.querySelector('.work-head > .work-hero').getBoundingClientRect();
          const label = document.querySelector('.work-head > .work-label').getBoundingClientRect();
          const master = [...document.querySelectorAll('.work-record > .panel')]
            .find((panel) => panel.querySelector('h2')?.textContent === 'Master image');
          return {
            side_by_side: label.left >= hero.right,
            failure_in_master: Boolean(master && master.querySelector('.acquisition-line')),
            ruled: master && getComputedStyle(master).borderTopStyle === 'solid',
          };
        }""")
    assert layout == {"side_by_side": True, "failure_in_master": True, "ruled": True}
