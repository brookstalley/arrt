"""Review leads with the cards a curator can judge by their picture.

The owner walked Review (2026-10-08) and ruled: cards with a picture to judge
come first; the cards where the Get found no image fold into one line at the
end, which only opens, showing the same cards with their Want and Forget; and
cards already decided fold into one "N decided" line after that. Each test
holds one of those, on the review screen, where every part of it applies.
"""

import pytest
from payloads import a_candidate, a_candidate_page, a_card

from arrt.persistence.discovery_records import ResolutionStatus, UnresolvedReason, Verdict

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"


def _found_none(work_id, title):
    return a_card(
        work=a_candidate(
            work_id=work_id,
            title=title,
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason=UnresolvedReason.NOT_HELD.value,
        ),
        shown=None,
    )


def _open_review(ui, cards):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page(cards))
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("#view li.review-card", state="attached")


def _order(ui):
    """Every card's work id, in page order, and whether it is on screen."""
    return ui.page.evaluate("""() => [...document.querySelectorAll('#view li.review-card')]
              .map((li) => [li.dataset.work, li.checkVisibility()])""")


@pytest.fixture
def mixed(ui):
    # Server order, deliberately interleaved: a decided card and a found-none
    # card each sit before a card with a picture, so a page that kept the
    # server's order would fail every assertion below.
    cards = [
        a_card(work=a_candidate(work_id="taken", title="Already Accepted", verdict=Verdict.ACCEPTED.value)),
        _found_none("lost-1", "Nowhere To Be Found"),
        a_card(work=a_candidate(work_id="judge-1", title="The Persistence of Memory")),
        _found_none("lost-2", "Also Missing"),
        a_card(work=a_candidate(work_id="judge-2", title="Swans Reflecting Elephants")),
        a_card(work=a_candidate(work_id="gone", title="Already Rejected", verdict=Verdict.REJECTED.value)),
    ]
    _open_review(ui, cards)
    return ui


def test_cards_with_a_picture_to_judge_come_first_and_are_open(mixed):
    order = _order(mixed)
    assert order[:2] == [["judge-1", True], ["judge-2", True]]


def test_found_none_cards_fold_into_one_line_after_them(mixed):
    fold = mixed.page.locator("#view details.fold-found-none")
    assert fold.locator(":scope > summary").inner_text().strip() == "2 found no image"
    assert fold.get_attribute("open") is None
    ids = [li.get_attribute("data-work") for li in fold.locator("li.review-card").all()]
    assert ids == ["lost-1", "lost-2"]
    # Folded, not gone: nothing of them is on screen until the line is opened.
    assert ["lost-1", False] in _order(mixed)


def test_opening_the_found_none_line_shows_the_same_cards_with_want_and_forget(mixed):
    mixed.page.click("#view details.fold-found-none > summary")

    card = mixed.page.locator("#view li.review-card[data-work='lost-1']")
    assert card.is_visible()
    assert card.locator("button:text-is('Want')").is_visible()
    assert card.locator("button:text-is('Forget')").is_visible()
    # The line only opens: it carries no act of its own.
    assert mixed.page.locator("#view details.fold-found-none > summary button").count() == 0


def test_decided_cards_fold_into_the_last_line(mixed):
    folds = mixed.page.locator("#view details.fold").all()
    assert [f.get_attribute("class").split()[-1] for f in folds] == ["fold-found-none", "fold-decided"]
    decided = mixed.page.locator("#view details.fold-decided")
    assert decided.locator(":scope > summary").inner_text().strip() == "2 decided"
    ids = [li.get_attribute("data-work") for li in decided.locator("li.review-card").all()]
    assert ids == ["taken", "gone"]


def test_a_page_with_nothing_to_fold_draws_no_fold_lines(ui):
    _open_review(ui, [a_card(work=a_candidate(work_id="judge-1"))])

    assert ui.page.locator("#view details.fold").count() == 0


def test_a_fold_of_one_reads_in_the_singular(ui):
    _open_review(
        ui,
        [
            a_card(work=a_candidate(work_id="judge-1")),
            _found_none("lost-1", "Nowhere To Be Found"),
            a_card(work=a_candidate(work_id="taken", verdict=Verdict.ACCEPTED.value)),
        ],
    )

    assert ui.page.locator("#view details.fold-found-none > summary").inner_text().strip() == "1 found no image"
    assert ui.page.locator("#view details.fold-decided > summary").inner_text().strip() == "1 decided"


def test_a_page_with_nothing_left_to_judge_says_so(ui):
    _open_review(
        ui,
        [
            _found_none("lost-1", "Nowhere To Be Found"),
            a_card(work=a_candidate(work_id="taken", verdict=Verdict.ACCEPTED.value)),
        ],
    )

    assert "Nothing here is left to judge by its picture." in ui.page.inner_text("#view")


def test_a_page_with_a_card_to_judge_does_not_say_nothing_is_left(mixed):
    assert "Nothing here is left to judge by its picture." not in mixed.page.inner_text("#view")


# -- a Get still looking, whose page redraws every poll ------------------------------

GET_ID = "get-under-test"


def _a_get_still_looking(ui, pages):
    """A Get of chosen works mid-search, its run changing on every poll so each one repaints."""
    from payloads import a_run, a_run_view, a_spend

    from arrt.persistence.discovery_records import RunStatus, WorkProvenance

    def chosen(work_id, verdict=Verdict.PENDING.value, **more):
        return a_candidate(work_id=work_id, provenance=WorkProvenance.CHOSEN.value, verdict=verdict, **more)

    cards = [[card(chosen) for card in page] for page in pages]
    runs = [
        a_run(
            run_id=GET_ID,
            kind="get",
            intent=None,
            status=RunStatus.RESOLVING_IMAGES.value,
            is_terminal=False,
            actual_cost_usd=f"0.0{n}",
        )
        for n in range(1, 10)
    ]
    ui.serve(f"**/api/runs/{GET_ID}", [a_run_view(run=run, works=[c.work for c in cards[-1]]) for run in runs])
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", [a_candidate_page(page, run=runs[0]) for page in cards])
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("#view li.review-card", state="attached")


def _repainted(ui, times=2):
    """Wait until the page has read the cards `times` more times, which it does only to repaint."""
    needle = f"/api/runs/{GET_ID}/candidates"
    before = ui.page.evaluate(f"() => performance.getEntriesByType('resource').filter((e) => e.name.includes('{needle}')).length")
    ui.page.wait_for_function(
        f"() => performance.getEntriesByType('resource').filter((e) => e.name.includes('{needle}')).length >= {before + times}",
        timeout=15000,
    )


def test_a_card_decided_while_a_get_looks_stays_where_it_was(ui):
    def judge(chosen):
        return a_card(work=chosen("judge"))

    def decided_later(chosen):
        return a_card(work=chosen("judge", verdict=Verdict.ACCEPTED.value))

    _a_get_still_looking(ui, [[judge], [decided_later]])
    _repainted(ui)

    card = ui.page.locator("#view li.review-card[data-work='judge']")
    assert card.is_visible(), "the card decided this visit moved out from under the curator"
    assert ui.page.locator("#view details.fold-decided").count() == 0


def test_a_fold_opened_while_a_get_looks_stays_open(ui):
    def lost(chosen):
        return a_card(
            work=chosen(
                "lost", resolution_status=ResolutionStatus.UNRESOLVED.value, unresolved_reason=UnresolvedReason.NOT_HELD.value
            ),
            shown=None,
        )

    def judge(chosen):
        return a_card(work=chosen("judge"))

    _a_get_still_looking(ui, [[judge, lost]])
    ui.page.click("#view details.fold-found-none > summary")
    _repainted(ui)

    assert ui.page.locator("#view details.fold-found-none").get_attribute("open") is not None
    assert ui.page.locator("#view li.review-card[data-work='lost']").is_visible()


def test_a_card_whose_search_ends_with_nothing_folds_while_the_get_looks(ui):
    def searching(chosen):
        return a_card(work=chosen("lost", resolution_status=ResolutionStatus.PENDING.value), shown=None)

    def found_none(chosen):
        return a_card(
            work=chosen(
                "lost",
                resolution_status=ResolutionStatus.UNRESOLVED.value,
                unresolved_reason=UnresolvedReason.NOT_HELD.value,
            ),
            shown=None,
        )

    def judge(chosen):
        return a_card(work=chosen("judge"))

    _a_get_still_looking(ui, [[judge, searching], [judge, found_none]])
    _repainted(ui)

    fold = ui.page.locator("#view details.fold-found-none")
    assert fold.count() == 1
    assert fold.locator("li.review-card[data-work='lost']").count() == 1
