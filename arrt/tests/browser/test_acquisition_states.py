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

import re
from datetime import UTC, datetime, timedelta

import pytest
from payloads import a_candidate, a_candidate_page, a_card

from arrt.library.acquisition.queue import QueuePause
from arrt.library.acquisition.service import remedy_for
from arrt.persistence.records import AcquisitionMethod, FetchOutcome, QueuedAcquisition, RightsStatus, SourceClass

expect = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
).expect


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
    ui.page.wait_for_selector("#view h2:text-is('Picture')")


# -- the Work page ------------------------------------------------------------


def test_a_work_with_no_image_says_it_is_queued_and_offers_no_retry(ui, accepted):
    work = accepted()

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("queued", use_inner_text=True)
    expect(line).to_contain_text("Waiting its turn to be fetched", use_inner_text=True)
    expect(ui.page.locator(".acquisition-line button"), "nothing has failed, so there is nothing to retry").to_have_count(0)
    # The queue's line replaces the bare "no picture yet" sentence: the Picture
    # panel holds its heading and that line and nothing else. Keyed on what the
    # panel holds rather than on the sentence's wording, which a rewording would
    # leave this passing without checking anything (until 2026-11-19 it asserted
    # one wording's absence).
    panel = ui.page.locator(".work-record > .panel:has(h2:text-is('Picture'))")
    expect(panel).to_have_count(1)
    expect(panel.locator(".acquisition-line")).to_have_count(1)
    expect(panel.locator(":scope > :not(h2, .acquisition-line)")).to_have_count(0)


def test_a_work_the_queue_gave_up_on_says_why_and_retry_puts_it_back(ui, accepted, store):
    work = accepted()
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=work.id, failures=4, detail="the museum answered 404."))

    open_work(ui, work)
    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("gave up", use_inner_text=True)
    expect(line).to_contain_text("Gave up after 4 tries: the museum answered 404.", use_inner_text=True)

    ui.page.click(".acquisition-line button:has-text('Retry')")
    ui.page.wait_for_selector(".acquisition-line:has-text('queued')")

    expect(line).not_to_contain_text("gave up", use_inner_text=True)
    assert store.get_queued_acquisition(work.id).failures == 0


def test_a_failed_work_says_which_try_failed_and_when_the_next_is(ui, accepted, store):
    work = accepted()
    next_try = datetime.now(UTC) + timedelta(hours=1)
    store.set_queued_acquisition(
        QueuedAcquisition(artwork_id=work.id, failures=1, next_try_at=next_try, detail="the connection was reset.")
    )

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("failed", use_inner_text=True)
    expect(line).to_contain_text("Try 1 of 4 failed: the connection was reset.", use_inner_text=True)
    expect(line).to_contain_text("It tries again at", use_inner_text=True)
    expect(ui.page.locator(".acquisition-line button:has-text('Retry now')")).to_have_count(1)


def test_a_work_being_fetched_says_since_when_and_that_it_takes_a_while(ui, accepted, services):
    work = accepted()
    # What the worker sets while it holds this work; the suite runs no worker.
    services.acquisition_queue._fetching = (work.id, datetime.now(UTC))

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("fetching", use_inner_text=True)
    expect(line).to_contain_text("Being fetched since", use_inner_text=True)
    expect(line).to_contain_text("up to half an hour", use_inner_text=True)
    expect(ui.page.locator(".acquisition-line button"), "a fetch in hand is not retried").to_have_count(0)


def test_a_paused_queue_says_why_and_what_ends_it_on_the_work_page(ui, accepted, services):
    work = accepted()
    services.acquisition_queue._enter_pause(
        QueuePause(condition="NotEnoughSpace", detail="only 1.2 GB free; 2.0 GB required.", since=datetime.now(UTC))
    )

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("paused", use_inner_text=True)
    expect(line).to_contain_text("Every fetch is paused: only 1.2 GB free; 2.0 GB required.", use_inner_text=True)
    expect(line).to_contain_text("Free some space on it", use_inner_text=True)
    expect(line, "the Work page is a household page, which names no setting").not_to_contain_text(
        "MIN_FREE_BYTES", use_inner_text=True
    )


def test_a_pause_nothing_anticipated_points_at_the_journal_rather_than_a_remedy(ui, accepted, services):
    work = accepted()
    services.acquisition_queue.note_error(OSError("database disk image is malformed"))

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text("Every fetch is paused: database disk image is malformed", use_inner_text=True)
    expect(line).to_contain_text("acquisition.queue_error", use_inner_text=True)


def test_a_work_holding_its_image_says_nothing_about_the_queue(ui, ready_work):
    work = ready_work()

    open_work(ui, work)

    # What a held work's page says, so the page is drawn when the line is found absent.
    expect(ui.view).to_contain_text("Pixels", use_inner_text=True)
    expect(ui.page.locator(".acquisition-line")).to_have_count(0)


# -- Activity › Queue ---------------------------------------------------------


def test_the_queue_lists_the_works_in_line_in_the_order_it_will_try_them(ui, accepted, services):
    accepted("Accepted first")
    retried = accepted("Retried")
    # A Retry goes to the front of the line.
    services.acquisition_queue.retry(retried.id)

    ui.open("#queue")
    ui.page.wait_for_selector(".acquisitions .in-line tbody tr")

    # The retried work comes ahead of the one accepted first: the first
    # "Retried" has no "Accepted first" before it, and one follows.
    rows = ui.page.locator(".acquisitions .in-line tbody tr")
    expect(ui.page.locator(".acquisitions .in-line tbody")).to_have_text(
        re.compile(r"^(?:(?!Accepted first)[\s\S])*?Retried[\s\S]*Accepted first"), use_inner_text=True
    )
    first_row = rows.filter(has_text="Accepted first")
    expect(first_row).to_contain_text("queued", use_inner_text=True)
    expect(first_row).not_to_contain_text("Retry", use_inner_text=True)


def _failed(store, work, detail, *, failures=1):
    store.set_queued_acquisition(
        QueuedAcquisition(
            artwork_id=work.id,
            failures=failures,
            next_try_at=None if failures >= 4 else datetime.now(UTC) + timedelta(hours=1),
            detail=detail,
        )
    )


def test_a_failed_work_is_under_its_cause_and_opens_into_its_title_with_no_retry_on_its_row(ui, accepted, store):
    accepted("Waiting")
    failed = accepted("Failed once")
    _failed(store, failed, "refused.")

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    # The work that waits is in line, so the line has drawn when the failed one is found not to be.
    expect(ui.page.locator(".in-line tbody tr:has-text('Waiting')").first).to_be_attached()
    expect(ui.page.locator(".in-line tbody tr:has-text('Failed once')"), "a failed work was also in line").to_have_count(0)
    head = ui.page.locator(".failure-cause")
    expect(head).to_contain_text("refused.", use_inner_text=True)
    expect(head).to_contain_text("1 work", use_inner_text=True)
    # A group of one says "Retry": "Retry all" over one work promised more than it did.
    expect(ui.page.locator(".failure-cause button")).to_have_text(["Retry"])

    ui.page.click(".failure-cause a:has-text('Show the works')")
    ui.page.wait_for_selector(".failure-cause-works tbody tr")

    row = ui.page.locator(".failure-cause-works tbody tr")
    expect(row).to_have_text(re.compile(r"^Failed once"), use_inner_text=True)
    expect(row, "the cause is the group's heading, not repeated per work").to_contain_text(
        "Try 1 of 4 failed. It tries again at", use_inner_text=True
    )
    expect(ui.page.locator(".failure-cause-works a:has-text('Failed once')")).to_have_attribute(
        "href", re.compile("^" + re.escape(f"#work/{failed.id}"))
    )
    # One Retry for the group; a row has none (design direction: never one button
    # per row, audit-6 finding 11). A single work is retried on its own page.
    expect(ui.page.locator(".failure-cause-works button")).to_have_count(0)
    expect(ui.page, "opening a group is an address").to_have_url(re.compile(re.escape("cause=refused.")))


def test_two_thousand_failures_of_one_cause_are_one_row_and_its_works_page(ui, seed_the_served_catalogue, catalogue_file, store):
    """`ux-review-2026-10.md` finding 18: Queue at 2,000 failures was one 209,000-px table naming each work by id."""
    works = seed_the_served_catalogue(size=2000)
    with catalogue_file.transaction():
        for work in works:
            # What the acquirer's refusal records for a work with no source: its id inside.
            _failed(store, work, f"Artwork {work.id!r} has no source to acquire from.")

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    head = ui.page.locator(".failure-cause")
    expect(head).to_have_count(1)
    expect(head).to_contain_text("The work has no source to acquire from.", use_inner_text=True)
    expect(head).to_contain_text("2,000 works", use_inner_text=True)
    # At most 25 rows: there is no 26th.
    expect(
        ui.page.locator(".acquisitions tbody tr").nth(25), "a failure was drawn as a row before its group opened"
    ).to_have_count(0)
    height = ui.page.evaluate("() => document.documentElement.scrollHeight")
    assert height < 3000, f"Queue is {height}px tall with one cause"

    ui.page.click(".failure-cause a:has-text('Show the works')")
    ui.page.wait_for_selector(".failure-cause-works tbody tr")

    rows = ui.page.locator(".failure-cause-works tbody tr")
    expect(rows).to_have_count(25)
    expect(ui.page.locator(".acquisitions")).to_contain_text("1–25 of 2,000", use_inner_text=True)
    # No pattern of two thousand ids is written for `not_to_contain_text`: the
    # panel's words are read once, after the expects above have drawn it whole.
    shown = ui.page.inner_text(
        ".acquisitions"
    )  # one-shot: membership of 2,000 ids in the settled panel, which has no retrying form
    assert not any(work.id in shown for work in works), "a work was named by its id"
    ui.page.click(".failure-cause-works a:has-text('Next')")
    ui.page.wait_for_selector(".failure-cause-works :text('26–50 of 2,000')")
    expect(rows).to_have_count(25)

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

    # The button says how many it retries: the whole group, four works.
    expect(ui.page.locator(".failure-cause button")).to_have_text(["Retry 4"])
    ui.page.click(".failure-cause button:text-is('Retry 4')")

    expect(ui.page.locator(".retry-all-said")).to_have_text(
        "3 works put back in line. 1 work not: The work has no source to acquire from.", use_inner_text=True
    )
    assert len(ui.requests_matching("/api/acquisitions/causes/retry")) == 1
    assert ui.requests_matching("/acquisition/retry") == [], "a group's Retry asked once per work"
    assert {store.get_queued_acquisition(work.id).failures for work in retried} == {0}
    # The one refused stays under its cause; the three are back in line.
    expect(ui.page.locator(".failure-cause")).to_have_count(1)
    expect(ui.page.locator(".failure-cause")).to_contain_text("1 work", use_inner_text=True)
    for number in range(3):
        expect(ui.page.locator(".in-line")).to_contain_text(f"Given up {number}", use_inner_text=True)


def test_the_works_in_line_page_from_the_server(ui, accepted):
    for number in range(30):
        accepted(f"Waiting {number:02}")

    ui.open("#queue")
    ui.page.wait_for_selector(".in-line tbody tr")

    expect(ui.page.locator(".in-line tbody tr")).to_have_count(25)
    ui.page.click(".in-line a:has-text('Next')")
    ui.page.wait_for_selector(".in-line .queue-paging :text('26–')")
    expect(ui.page).to_have_url(re.compile(re.escape("offset=25")))
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
    remedy = remedy_for("NotEnoughSpace")
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

    pause = ui.page.locator(".acquisition-pause")
    expect(pause).to_contain_text("Every fetch is paused: only 1.2 GB free", use_inner_text=True)
    expect(pause).to_contain_text("Free some space on it", use_inner_text=True)
    # The first "Every fetch is paused" has no title before it, and the title follows.
    expect(ui.page.locator(".acquisitions"), "the pause holds every row beneath it").to_have_text(
        re.compile(r"^(?:(?!Hunters in the Snow)[\s\S])*?Every fetch is paused[\s\S]*Hunters in the Snow"),
        use_inner_text=True,
    )


def test_a_queue_owing_nothing_says_so(ui):
    ui.serve("**/api/acquisitions", _listing())

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('Fetching images (0)')")

    expect(ui.view).to_contain_text("Every accepted work holds its image.", use_inner_text=True)
    expect(ui.page.locator(".acquisition-pause")).to_have_count(0)


# -- a Review card for an accepted work -----------------------------------------


def test_an_accepted_card_says_its_image_is_queued_and_a_pending_one_says_nothing(ui, accepted):
    work = accepted()
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    pending = a_card(a_candidate(work_id="pending", title="Still to judge"))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken, pending]))

    ui.open("#review/run-1")
    ui.open_folds()
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-line")

    line = ui.page.locator("li.card[data-work='taken'] .acquisition-line")
    expect(line).to_contain_text("queued", use_inner_text=True)
    expect(line).to_contain_text("Waiting its turn", use_inner_text=True)
    expect(ui.page.locator("li.card[data-work='pending'] .acquisition-slot")).to_have_count(0)


def test_an_accepted_card_whose_image_is_held_says_so(ui, ready_work):
    work = ready_work()
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken]))

    ui.open("#review/run-1")
    ui.open_folds()
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-slot p")

    expect(ui.page.locator("li.card[data-work='taken'] .acquisition-slot")).to_have_text(
        "Its image is held and prepared for the wall.", use_inner_text=True
    )


def test_an_accepted_card_the_queue_owes_nothing_and_holds_no_image_says_none_is_coming(ui, accepted, services):
    work = accepted()
    services.catalogue.archive_artwork(work.id)
    taken = a_card(a_candidate(work_id="taken", verdict="accepted", artwork_id=work.id))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve("**/api/runs/run-1/candidates*", a_candidate_page([taken]))

    ui.open("#review/run-1")
    ui.open_folds()
    ui.page.wait_for_selector("li.card[data-work='taken'] .acquisition-slot p")

    expect(ui.page.locator("li.card[data-work='taken'] .acquisition-slot")).to_have_text(
        "No image is being fetched for it.", use_inner_text=True
    )


def test_a_failed_work_keeps_the_wall_label_layout_with_its_failure_in_the_record(ui, accepted, store):
    """The page a curator meets most while the library fills: no picture, a
    failed try, a source. The label still sits beside where the picture would
    be, and the failure is in the Picture section, ruled like the rest."""
    work = accepted()
    _failed(store, work, "the connection was reset.")
    ui.page.set_viewport_size({"width": 1280, "height": 900})

    open_work(ui, work)

    layout = ui.page.evaluate("""() => {
          const hero = document.querySelector('.work-head > .work-hero').getBoundingClientRect();
          const label = document.querySelector('.work-head > .work-label').getBoundingClientRect();
          const master = [...document.querySelectorAll('.work-record > .panel')]
            .find((panel) => panel.querySelector('h2')?.textContent === 'Picture');
          return {
            side_by_side: label.left >= hero.right,
            failure_in_master: Boolean(master && master.querySelector('.acquisition-line')),
            ruled: master && getComputedStyle(master).borderTopStyle === 'solid',
          };
        }""")
    assert layout == {"side_by_side": True, "failure_in_master": True, "ruled": True}


def test_the_fetches_section_says_what_it_holds_before_its_parts(ui):
    """Under its name and above its first part, so two headings never stand one on the other."""
    work = {
        "title": "Hunters in the Snow",
        "acquisition": {
            "artwork_id": "w-1",
            "phase": "queued",
            "failures": 0,
            "detail": None,
            "next_try_at": None,
            "since": None,
            "condition": None,
            "remedy": None,
        },
    }
    ui.serve("**/api/acquisitions", _listing(works=[work]))

    ui.open("#queue")
    summary = ui.page.locator(".acquisitions > .acquisition-summary")
    summary.wait_for()

    expect(summary).to_have_text("1 work in line", use_inner_text=True)
    order = ui.page.locator(".acquisitions").evaluate(
        "(panel) => [...panel.querySelectorAll('h2, .acquisition-summary, h3')]"
        ".map((n) => n.tagName === 'P' ? 'summary' : n.tagName)"
    )
    assert order[:3] == ["H2", "summary", "H3"]


# -- what the fetch said ----------------------------------------------------------------


def _said(store, work, outcome, detail, *, failures=1, plugin="artic"):
    """A failure as the queue records one whose fetch said `outcome`: no next try unless the schedule sets one."""
    store.set_queued_acquisition(
        QueuedAcquisition(
            artwork_id=work.id,
            failures=failures,
            detail=detail,
            outcome=outcome,
            plugin=plugin,
            failed_at=datetime.now(UTC),
        )
    )


def test_works_that_could_not_be_asked_at_one_museum_are_one_group_labelled_by_it(ui, accepted, store):
    """#318: two wordings of one cause were two groups. The group says what the fetches said, and where."""
    for title, said in (("First", "Art Institute answered 503"), ("Second", "Art Institute took 240 s")):
        _said(store, accepted(title), FetchOutcome.UNASKED, f"the plugin could not read this source: {said}")

    ui.open("#queue")
    ui.page.wait_for_selector(".failure-cause")

    group = ui.page.locator(".failure-cause:has-text('Art Institute of Chicago')")
    expect(group).to_have_count(1)
    expect(group.locator(".failure-cause-count")).to_have_text(
        "Could not be asked · Art Institute of Chicago · 2 works", use_inner_text=True
    )
    expect(group.locator("button")).to_have_text(["Retry 2"])

    group.locator("a:has-text('Show the works')").click()
    row = ui.page.locator(".failure-cause-works tbody tr:has-text('First')")
    expect(row, "a work waiting for the next pass has no moment and no count of four").to_contain_text(
        "Try 1 failed. It is asked again on the queue's next pass.", use_inner_text=True
    )


@pytest.mark.parametrize(
    ("outcome", "said"),
    [
        (
            FetchOutcome.FAULTED,
            "Try 1 failed: the plugin faulted. It is asked again once Arrt next starts and loads its plugins.",
        ),
        (FetchOutcome.UNASKED, "Try 1 failed: the plugin faulted. It is asked again on the queue's next pass."),
    ],
)
def test_a_work_waiting_for_a_pass_or_a_start_says_which_on_its_page(ui, accepted, store, outcome, said):
    work = accepted()
    _said(store, work, outcome, "the plugin faulted")

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text(said, use_inner_text=True)
    expect(line, "no next try was set, so none is promised").not_to_contain_text("tries again at", use_inner_text=True)


def test_a_settled_work_says_what_brings_it_back(ui, accepted, store):
    work = accepted()
    _said(store, work, FetchOutcome.LINK_GONE, "the page answered 410")

    open_work(ui, work)

    line = ui.page.locator(".acquisition-line")
    expect(line).to_contain_text(
        "Settled after 1 try: the page answered 410. Nothing tries again until you retry, or until its Wikidata item changes.",
        use_inner_text=True,
    )
    expect(ui.page.locator(".acquisition-line button:has-text('Retry')")).to_have_count(1)
