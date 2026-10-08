"""Review says what it doesn't know, holds a verdict for Undo, and opens scans across the card.

A card whose model note says no source confirms the work carries *Not
confirmed*, and one nobody asked about *Unchecked*; neither ever reads as
confirmed. The model's Markdown reaches the page as words and links, never as
brackets and asterisks, and never as markup. A verdict waits a few seconds with
Undo beside it before it is sent, because the server cannot take an acceptance
back; leaving the page sends it rather than losing it.
"""

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_verdict, an_instance, an_instance_listing

from arrt.persistence.discovery_records import Verdict

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"

#: `VERDICT_HOLD_MS` in `core/reviewing.js`, read here as the seconds a test
#: waits past it; a test that the verdict is *not* sent waits less.
HOLD_SECONDS = 5


def _review(ui, cards):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page(cards))
    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector("li.card")


def _verdicts(ui, work_id="work-1", *, decided=Verdict.ACCEPTED):
    """Answer the card's verdict and its repaint, and return each verdict request as it is made."""
    sent = []
    ui.page.on("request", lambda request: sent.append(request) if request.url.endswith(f"/{work_id}/verdict") else None)
    ui.serve(f"**/api/candidates/{work_id}/verdict", a_verdict())
    ui.serve(
        f"**/api/candidates/{work_id}",
        a_card(a_candidate(work_id=work_id, verdict=decided.value)).model_dump(mode="json"),
    )
    return sent


def _card(ui, work_id="work-1"):
    return ui.page.locator(f"li.card[data-work='{work_id}']")


# -- confirmation ------------------------------------------------------------------


def test_each_confirmation_is_said_and_none_reads_as_confirmed(ui):
    _review(
        ui,
        [
            a_card(a_candidate(work_id="found", title="Found", confirmation="confirmed")),
            a_card(a_candidate(work_id="unasked", title="Unasked", confirmation="unknown")),
            a_card(a_candidate(work_id="invented", title="Invented", confirmation="unconfirmed")),
        ],
    )

    def badges(work_id):
        return [" ".join(text.split()) for text in _card(ui, work_id).locator(".card-footer .badge").all_inner_texts()]

    assert not any("onfirm" in badge or "Unchecked" in badge for badge in badges("found"))
    assert "? Unchecked" in badges("unasked")
    assert "? Not confirmed" in badges("invented")
    assert "Not confirmed" not in " ".join(badges("unasked")), "unknown is not the model saying no"
    # The sentence only where the model said no; unknown claims neither way.
    assert _card(ui, "invented").locator(".note.not-confirmed").inner_text().startswith("No source the search found")
    assert _card(ui, "unasked").locator(".note.not-confirmed").count() == 0
    assert _card(ui, "found").locator(".note.not-confirmed").count() == 0
    # Drawn in the order the server sorts them: the work that may not exist last.
    assert ui.page.locator("li.card h2").all_inner_texts() == ["Found", "Unasked", "Invented"]


# -- Markdown --------------------------------------------------------------------


def test_the_models_markdown_is_words_and_links_never_brackets_or_markup(ui):
    note = (
        "I found it at [the Met](https://www.metmuseum.org/art/1) as **Wheat Field** with *Cypresses*; "
        "see [this](javascript:window.pwned=1) and `code`. <img src=x onerror=window.pwned=1>"
    )
    _review(ui, [a_card(a_candidate(rationale=note))])

    meta = _card(ui).locator(".card-meta")
    assert meta.inner_text() == (
        "I found it at the Met as Wheat Field with Cypresses; see this and code. <img src=x onerror=window.pwned=1>"
    )
    links = meta.locator("a")
    assert links.count() == 1, "only an http(s) address becomes a link"
    assert (links.inner_text(), links.get_attribute("href")) == ("the Met", "https://www.metmuseum.org/art/1")
    assert links.get_attribute("rel") == "noopener noreferrer"
    assert meta.locator("strong").inner_text() == "Wheat Field"
    assert meta.locator("em").inner_text() == "Cypresses"
    assert meta.locator("img").count() == 0
    assert ui.page.evaluate("() => window.pwned") is None


def test_a_scans_why_this_one_is_words_and_links_too(ui):
    listing = an_instance_listing(
        [an_instance(selection_rationale="The **largest** scan, from [Commons](https://commons.wikimedia.org/x).")]
    )
    ui.serve("**/api/candidates/work-1/images", listing)
    _review(ui, [a_card()])

    _card(ui).locator("summary").click()
    why = ui.page.locator("tr.alternate-detail dd").first
    why.wait_for()

    assert why.inner_text() == "The largest scan, from Commons."
    assert why.locator("a").get_attribute("href") == "https://commons.wikimedia.org/x"


# -- Undo ----------------------------------------------------------------------


def test_a_verdict_waits_with_undo_and_then_is_sent_once(ui):
    sent = _verdicts(ui)
    _review(ui, [a_card()])

    _card(ui).locator("button:text-is('Accept')").click()

    undo = _card(ui).locator("button:text-is('Undo')")
    assert undo.is_visible()
    assert ui.focused() == "Undo", "the keyboard stands on Undo, not on a button that left the page"
    ui.page.wait_for_function("() => document.querySelector('.verdict-held [role=status]').textContent.length > 0")
    assert _card(ui).locator(".verdict-held [role='status']").inner_text() == (
        "Accepting The Persistence of Memory in a few seconds."
    )
    assert _card(ui).locator("button:text-is('Accept')").is_hidden()
    ui.page.wait_for_timeout(1000)
    assert sent == [], "nothing is sent while Undo can still take it back"

    _card(ui).locator(".decided").wait_for(timeout=(HOLD_SECONDS + 5) * 1000)
    assert len(sent) == 1
    assert sent[0].post_data_json == {"verdict": "accepted", "reason": None}


def test_undo_sends_nothing_and_gives_the_controls_back(ui):
    sent = _verdicts(ui, decided=Verdict.REJECTED)
    _review(ui, [a_card()])
    _card(ui).locator("input[type='text']").fill("Wrong one")

    _card(ui).locator("button:text-is('Reject')").click()
    _card(ui).locator("button:text-is('Undo')").click()

    reject = _card(ui).locator("button:text-is('Reject')")
    assert reject.is_visible()
    assert ui.focused() == "Reject"
    assert _card(ui).locator(".verdict-held").count() == 0
    assert _card(ui).locator("input[type='text']").input_value() == "Wrong one", "the reason typed is kept"
    ui.page.wait_for_timeout((HOLD_SECONDS + 1) * 1000)
    assert sent == [], "an undone verdict is never sent"


def test_leaving_the_page_sends_a_held_verdict(ui):
    sent = _verdicts(ui)
    ui.serve("**/api/runs/*", {"error": "not under test"})
    _review(ui, [a_card()])

    _card(ui).locator("button:text-is('Accept')").click()
    with ui.page.expect_request(lambda request: request.url.endswith("/work-1/verdict"), timeout=2000):
        ui.page.evaluate("() => { window.location.hash = '#activity'; }")

    assert len(sent) == 1
    assert sent[0].post_data_json["verdict"] == "accepted"


def test_a_held_verdict_that_fails_gives_the_controls_back_and_says_so_beside_the_button(ui):
    ui.serve("**/api/candidates/work-1/verdict", (400, {"error": "That work was already decided."}))
    _review(ui, [a_card()])

    accept = _card(ui).locator("button:text-is('Accept')")
    accept.click()

    assert ui.said_beside(accept) == (
        "Couldn't accept The Persistence of Memory: That work was already decided. Nothing was changed."
    )
    assert accept.is_visible()
    assert _card(ui).locator(".verdict-held").count() == 0


# -- the scans take the card's whole width ------------------------------------------


def test_open_scans_take_the_cards_whole_width_not_its_column(ui):
    ui.serve("**/api/candidates/work-1/images", an_instance_listing())
    ui.page.set_viewport_size({"width": 1280, "height": 900})
    _review(ui, [a_card()])

    _card(ui).locator("summary").click()
    table = _card(ui).locator("table.scans")
    table.wait_for()

    card = _card(ui).bounding_box()
    body = _card(ui).locator(".card-body").bounding_box()
    scans = _card(ui).locator(".scans-disclosure").bounding_box()
    assert scans["width"] > body["width"] * 1.4, "wider than the facts column it sits under"
    assert scans["width"] > card["width"] * 0.95, "the card's whole row"
    assert scans["y"] >= body["y"] + body["height"] - 1, "beneath the picture and the facts both"
