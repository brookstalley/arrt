"""Review says what it doesn't know, holds a verdict for Undo, and opens scans across the card.

A card whose model note says no source confirms the work carries *Not
confirmed*, and one nobody asked about *Unchecked*; neither ever reads as
confirmed. The model's Markdown reaches the page as words and links, never as
brackets and asterisks, and never as markup. A verdict waits a few seconds with
Undo beside it before it is sent, because the server cannot take an acceptance
back; leaving the page sends it rather than losing it.
"""

import re

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_verdict, an_instance, an_instance_listing
from playwright.sync_api import expect

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

    def footer(work_id):
        # The card's badges are all the words its footer holds, so a claim about
        # "no badge says it" is a claim about the footer's words.
        return _card(ui, work_id).locator(".card-footer")

    def badge(work_id, words):
        return footer(work_id).locator(".badge").filter(has_text=words)

    # Drawn in the order the server sorts them: the work that may not exist last.
    expect(ui.page.locator("li.card h2")).to_have_text(["Found", "Unasked", "Invented"], use_inner_text=True)
    expect(badge("unasked", "Unchecked")).to_have_text("? Unchecked", use_inner_text=True)
    expect(badge("invented", "Not confirmed")).to_have_text("? Not confirmed", use_inner_text=True)
    expect(footer("found")).not_to_contain_text(re.compile(r"onfirm|Unchecked"), use_inner_text=True)
    expect(footer("unasked"), "unknown is not the model saying no").not_to_contain_text("Not confirmed", use_inner_text=True)
    # The sentence only where the model said no; unknown claims neither way.
    expect(_card(ui, "invented").locator(".note.not-confirmed")).to_have_text(
        re.compile(r"^No source the Get found"), use_inner_text=True
    )
    expect(_card(ui, "unasked").locator(".note.not-confirmed")).to_have_count(0)
    expect(_card(ui, "found").locator(".note.not-confirmed")).to_have_count(0)


# -- Markdown --------------------------------------------------------------------


def test_the_models_markdown_is_words_and_links_never_brackets_or_markup(ui):
    note = (
        "I found it at [the Met](https://www.metmuseum.org/art/1) as **Wheat Field** with *Cypresses*; "
        "see [this](javascript:window.pwned=1) and `code`. <img src=x onerror=window.pwned=1>"
    )
    _review(ui, [a_card(a_candidate(rationale=note))])

    meta = _card(ui).locator(".card-meta")
    expect(meta).to_have_text(
        "I found it at the Met as Wheat Field with Cypresses; see this and code. <img src=x onerror=window.pwned=1>",
        use_inner_text=True,
    )
    links = meta.locator("a")
    expect(links, "only an http(s) address becomes a link").to_have_count(1)
    expect(links).to_have_text("the Met", use_inner_text=True)
    expect(links).to_have_attribute("href", "https://www.metmuseum.org/art/1")
    expect(links).to_have_attribute("rel", "noopener noreferrer")
    expect(meta.locator("strong")).to_have_text("Wheat Field", use_inner_text=True)
    expect(meta.locator("em")).to_have_text("Cypresses", use_inner_text=True)
    expect(meta.locator("img")).to_have_count(0)
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

    expect(why).to_have_text("The largest scan, from Commons.", use_inner_text=True)
    expect(why.locator("a")).to_have_attribute("href", "https://commons.wikimedia.org/x")


# -- Undo ----------------------------------------------------------------------


def test_a_verdict_waits_with_undo_and_then_is_sent_once(ui):
    sent = _verdicts(ui)
    _review(ui, [a_card()])

    _card(ui).locator("button:text-is('Accept')").click()

    undo = _card(ui).locator("button:text-is('Undo')")
    expect(undo).to_be_visible()
    expect(undo).to_be_focused()  # the state `ui.focused()` reads next, waited for rather than read once
    assert ui.focused() == "Undo", "the keyboard stands on Undo, not on a button that left the page"
    ui.page.wait_for_function("() => document.querySelector('.verdict-held [role=status]').textContent.length > 0")
    expect(_card(ui).locator(".verdict-held [role='status']")).to_have_text(
        "Accepting The Persistence of Memory in a few seconds.", use_inner_text=True
    )
    expect(_card(ui).locator("button:text-is('Accept')")).to_be_hidden()
    # Nothing is sent while Undo can still take the verdict back, which no condition marks.
    ui.page.wait_for_timeout(1000)  # sleep: part of the hold, with Undo still offered
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
    expect(reject).to_be_visible()
    expect(reject).to_be_focused()  # the state `ui.focused()` reads next, waited for rather than read once
    assert ui.focused() == "Reject"
    expect(_card(ui).locator(".verdict-held")).to_have_count(0)
    expect(_card(ui).locator("input[type='text']"), "the reason typed is kept").to_have_value("Wrong one")
    # The hold runs out and sends nothing: only its running out shows that.
    ui.page.wait_for_timeout((HOLD_SECONDS + 1) * 1000)  # sleep: the hold's own length, undone
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
    expect(accept).to_be_visible()
    expect(_card(ui).locator(".verdict-held")).to_have_count(0)


def test_a_held_verdict_that_fails_after_leaving_is_said_on_the_page_left_for(ui):
    """Sent because the curator navigated away, a failed verdict is said at page level, naming the act and the work.

    Its card is gone, so beside the button is nowhere; and the error banner is
    cleared by the next page's paint, which can land after the failure.
    """
    ui.serve("**/api/candidates/work-1/verdict", (500, {"error": "The catalogue is locked."}))
    _review(ui, [a_card()])

    _card(ui).locator("button:text-is('Accept')").click()
    ui.page.evaluate("() => { window.location.hash = '#queue'; }")
    ui.page.wait_for_selector("#view h1:text-is('Queue')")

    # Any alert on the page, so the claim is that it is said and stays said,
    # not where the markup happens to put it; then still there once the new
    # page has painted and settled.
    said = ui.page.locator("[role='alert']:visible", has_text="Couldn't accept The Persistence of Memory")
    said.first.wait_for(timeout=3000)
    # The failure must outlast the next page's paint, which can land after it
    # and has no sign of its own to wait for.
    ui.page.wait_for_timeout(1000)  # sleep: the next page's paint has no sign of its own
    expect(said).to_have_count(1)
    expect(said.first).to_contain_text("the server failed while doing it: The catalogue is locked.", use_inner_text=True)

    elsewhere = ui.page.locator("#failures-elsewhere p")
    elsewhere.first.locator("button:text-is('Dismiss')").click()
    expect(ui.page.locator("#failures-elsewhere")).to_have_count(0)


def test_a_card_drawn_again_during_the_hold_shows_the_hold_and_its_undo_works(ui):
    """A redraw while a verdict is held draws the hold, Undo and the seconds left, never Accept again."""
    sent = _verdicts(ui)
    _review(ui, [a_card()])

    _card(ui).locator("button:text-is('Accept')").click()
    ui.page.evaluate(
        "() => { document.querySelector(\"li.card[data-work='work-1']\").dataset.before = 'yes'; window.refresh(); }"
    )
    ui.page.wait_for_selector("li.card[data-work='work-1']:not([data-before])")

    expect(_card(ui).locator(".verdict-countdown")).to_have_text(re.compile(r" s$"), use_inner_text=True)
    expect(_card(ui).locator("button:text-is('Accept')")).to_be_hidden()
    _card(ui).locator("button:text-is('Undo')").click()

    expect(_card(ui).locator("button:text-is('Accept')")).to_be_visible()
    # The undone hold runs out and sends nothing: only its running out shows that.
    ui.page.wait_for_timeout((HOLD_SECONDS + 1) * 1000)  # sleep: the hold's own length, undone
    assert sent == [], "the hold undone on the redrawn card is never sent"


# -- the scans take the card's whole width ------------------------------------------


def test_open_scans_take_the_cards_whole_width_not_its_column(ui):
    ui.serve("**/api/candidates/work-1/images", an_instance_listing())
    ui.page.set_viewport_size({"width": 1280, "height": 900})
    _review(ui, [a_card()])

    _card(ui).locator("summary").click()
    table = _card(ui).locator("table.scans")
    table.wait_for()

    card = _card(ui).bounding_box()  # one-shot: geometry, measured once the scans table is open
    body = _card(ui).locator(".card-body").bounding_box()  # one-shot: geometry, as above
    scans = _card(ui).locator(".scans-disclosure").bounding_box()  # one-shot: geometry, as above
    assert scans["width"] > body["width"] * 1.4, "wider than the facts column it sits under"
    assert scans["width"] > card["width"] * 0.95, "the card's whole row"
    assert scans["y"] >= body["y"] + body["height"] - 1, "beneath the picture and the facts both"
