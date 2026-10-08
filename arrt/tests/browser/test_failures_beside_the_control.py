"""A failed act is said beside the control that sent it, naming the act and what became of it.

`ux-review-2026-10.md` finding 11: a refused action said "Failed to fetch", at the
top of the page, often off-screen from the button pressed. `core/acting.js` is
the one helper every write goes through; these pin what it promises, through
three of the acts that use it — a verdict, a theme hang, and (in
`test_getting.py`) a Get:

- the sentence sits directly after the control, not in the banner;
- it names the act and the thing it was done to, then the outcome;
- *Nothing was changed* is said for a refusal and only for a refusal — a fault
  or no answer cannot know that;
- the control is left as it was, so trying again is one more press, and a
  success takes the sentence away.
"""

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_verdict, an_instance_listing

from arrt.persistence.discovery_records import Verdict

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"
TITLE = "The Persistence of Memory"
REFUSAL = "That work was already judged in another tab."


@pytest.fixture
def review(ui):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card(work=a_candidate(title=TITLE))]))
    ui.serve("**/api/candidates/work-1/images", an_instance_listing())
    rejected = a_card(work=a_candidate(title=TITLE, verdict=Verdict.REJECTED.value))
    ui.serve("**/api/candidates/work-1", rejected.model_dump(mode="json"))
    return ui


def test_a_refused_verdict_is_said_beside_reject_and_the_retry_is_one_press(review):
    review.serve("**/api/candidates/work-1/verdict", [(409, {"error": REFUSAL}), a_verdict()])
    review.open(f"#review/{RUN_ID}")
    reject = review.page.locator("li.card[data-work='work-1'] button:text-is('Reject')")

    reject.click()

    assert review.said_beside(reject) == f"Couldn't reject {TITLE}: {REFUSAL} Nothing was changed."
    assert reject.is_enabled()

    reject.click()
    review.page.wait_for_selector("li.card[data-work='work-1'] .badge:has-text('rejected')")
    assert review.page.locator(".act-failure").count() == 0


def test_a_verdict_that_got_no_answer_does_not_claim_nothing_changed(review):
    """No answer may still have landed; saying otherwise invites recording it twice."""
    review.page.route("**/api/candidates/work-1/verdict", lambda route: route.abort())
    review.open(f"#review/{RUN_ID}")
    reject = review.page.locator("li.card[data-work='work-1'] button:text-is('Reject')")

    reject.click()

    said = review.said_beside(reject)
    assert said == f"Couldn't reject {TITLE}: the server didn't answer."
    assert "Nothing was changed" not in said
    assert "Failed to fetch" not in said


def test_a_server_fault_does_not_claim_nothing_changed(review):
    review.serve("**/api/candidates/work-1/verdict", (500, {"error": "The catalogue could not be written."}))
    review.open(f"#review/{RUN_ID}")
    accept = review.page.locator("li.card[data-work='work-1'] button:text-is('Accept')")

    accept.click()

    said = review.said_beside(accept)
    assert said == f"Couldn't accept {TITLE}: the server failed while doing it: The catalogue could not be written."
    assert "Nothing was changed" not in said


def test_a_refused_hang_is_said_beside_the_hang_control(ui, services):
    services.display.add_theme(name="Late night")
    refusal = "The wall is being rebuilt; try again in a moment."
    ui.serve("**/api/themes/*/activate", (409, {"error": refusal}))
    ui.open("#theme")
    hang = ui.page.locator("button:text-is('Hang on The wall')")

    hang.click()
    ui.page.wait_for_selector("dialog.confirm[open]")
    ui.page.click("dialog.confirm .confirm-actions button:has-text('Hang')")

    assert ui.said_beside(hang) == f"Couldn't hang Late night on The wall: {refusal} Nothing was changed."
    # The screen stayed: a refused hang is not a reason to leave for the walls.
    assert ui.page.url.endswith("#theme")
    assert hang.is_enabled()
