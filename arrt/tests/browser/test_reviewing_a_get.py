"""A Get reviewed on its own page, on wide cards, with its scans readable.

The owner looked at a Get of *The Magpie* (2026-10-02) and found: the Get's page
said "1 work" and offered *Review these works*, a second page for works they had
already chosen; Review's card was a fixed narrow column, and with *Scans* open
each scan's facts wrapped in a column a few characters wide; the card did not
say the scan's resolution, and "native — would show at 28.2″" meant nothing
without knowing the panel; and clicking the picture did nothing. They ruled: a
Get is reviewed on its own page; pixels, and no inches; on this branch.

Each test below holds one of those answers, and the geometry ones are measured
at the width the owner saw it, 1280 px.
"""

import re

import pytest
from payloads import (
    a_candidate,
    a_candidate_page,
    a_card,
    a_run,
    a_run_view,
    a_spend,
    a_verdict,
    an_estimate,
    an_instance,
    an_instance_listing,
)
from playwright.sync_api import expect

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.discovery_records import RunStatus, Verdict, WorkProvenance

GET_ID = "a-get"
RUN_ID = "a-search"

#: A rationale as long as the ones phase 2 writes, so the second row under a
#: scan holds a real sentence rather than a word.
RATIONALE = (
    "artic holds this as 'The Magpie' by Claude Monet, matching the requested title and artist. "
    "It is 3,840 × 2,604 px, enough to fill the artwork box."
)


def chosen(work_id="work-1", title="The Magpie", **overrides):
    return a_candidate(
        work_id=work_id,
        title=title,
        artist="Claude Monet",
        provenance=WorkProvenance.CHOSEN.value,
        wikidata_qid="Q3226397",
        **overrides,
    )


def a_finished_get(ui, cards=None):
    """A finished Get holding one chosen work, its card and its two scans, all stubbed."""
    cards = [a_card(work=chosen())] if cards is None else cards
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[card.work for card in cards]))
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page(cards, run=run))
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.serve(
        "**/api/candidates/work-1/images",
        an_instance_listing(
            [
                an_instance(image_id="image-1", selection_rationale=RATIONALE),
                an_instance(
                    image_id="image-2",
                    url="https://commons.wikimedia.org/wiki/File:Claude_Monet_-_The_Magpie_-_Google_Art_Project.jpg",
                    provider="commons",
                    is_selected=False,
                    width=1600,
                    height=1085,
                    selection_rationale=RATIONALE,
                ),
            ],
            work=chosen(),
        ),
    )
    return ui


def at_desktop(ui):
    ui.page.set_viewport_size({"width": 1280, "height": 900})
    return ui


# -- a Get's page is its review --------------------------------------------------


def test_a_get_s_page_is_where_its_works_are_judged(ui):
    """Accept and Reject on the Get's own page, and no second page to go to."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    expect(ui.page.locator("li.card button:text-is('Reject')")).to_have_count(1)
    expect(ui.view).not_to_contain_text("Review these works", use_inner_text=True)
    # The cards stand where the work table stood, rather than beside it.
    expect(ui.page.locator("#view table")).to_have_count(0)


def test_a_verdict_on_the_get_s_page_is_recorded_there(ui):
    """The cards on the Get's page are the review's own, not pictures of them."""
    a_finished_get(ui)
    ui.serve("**/api/candidates/work-1/verdict", a_verdict(work=chosen(verdict=Verdict.ACCEPTED.value)))
    ui.serve("**/api/candidates/work-1", a_card(work=chosen(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    ui.open(f"#get/{GET_ID}")

    ui.page.click("li.card button:text-is('Accept')")

    ui.page.wait_for_selector("li.card .badge:has-text('accepted')")
    assert ui.page.evaluate("() => window.location.hash") == f"#get/{GET_ID}"


def test_a_discovery_run_s_page_is_unchanged(ui):
    """The paired negative: only a Get's page became its review."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=a_run(run_id=RUN_ID, status=RunStatus.COMPLETED.value, is_terminal=True), works=[a_candidate()]),
    )
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view table")

    expect(ui.page.locator("a:text-is('Review these works')")).to_have_count(1)
    expect(ui.page.locator("li.card")).to_have_count(0)
    # Its cards are read since 2026-10-08, but only for each row's picture and
    # the museum that offered it: the page still draws a table, never cards.
    expect(ui.page.locator("#view section.asked-for table")).to_have_count(1)


def test_review_still_answers_for_a_get(ui):
    """An address outlives the links that made it: `#review/<get>` still judges."""
    a_finished_get(ui)
    ui.open(f"#review/{GET_ID}")

    ui.page.wait_for_selector("li.card button:text-is('Accept')")
    expect(ui.page.locator("#view a:text-is('← Get')")).to_have_count(1)


def test_a_work_opened_from_a_get_s_card_returns_to_the_get(ui):
    """As a Work opened from Review returns to Review, one opened from a Get's card returns to the Get."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    ui.page.click("li.card .card-meta a:text-is('Q3226397')")
    ui.page.wait_for_selector("#view a:has-text('← Get')")
    assert ui.page.evaluate("() => window.location.hash") == f"#work/Q3226397?from=get%2F{GET_ID}"

    ui.page.click("#view a:has-text('← Get')")
    ui.page.wait_for_function(f"() => window.location.hash === '#get/{GET_ID}'")


def test_a_get_s_page_that_cannot_read_its_cards_says_so_and_keeps_the_rest(ui):
    """The run's sentence and costs are still worth having when the cards are not."""
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[chosen()]))
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", (500, {"error": "The listing broke."}))
    ui.open(f"#get/{GET_ID}")

    ui.page.wait_for_selector("text=This Get's works could not be read")
    expect(ui.view).to_contain_text("This Get finished", use_inner_text=True)


def test_a_card_for_a_work_not_yet_looked_up_does_not_say_nothing_was_found(ui):
    """A Get's page shows its cards while it is still looking."""
    card = a_card(work=chosen(resolution_status="pending"), shown=None)
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[card.work]))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=run))
    ui.open(f"#get/{GET_ID}")

    ui.page.wait_for_selector("li.card .card-image-absent")
    expect(ui.page.locator("li.card .card-image-absent")).to_have_text(
        "This work has not been looked up, so there is no scan to show yet.", use_inner_text=True
    )


# -- the card is wide ----------------------------------------------------------------


def test_one_card_is_wider_than_half_the_page_at_desktop_width(ui):
    """One work to a row: the narrow column was what wrapped everything on it."""
    at_desktop(a_finished_get(ui))
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    card = ui.page.locator("li.card").bounding_box()  # one-shot: geometry, measured once the card is drawn
    content = ui.page.locator("#view").bounding_box()  # one-shot: geometry, as above
    assert card["width"] > content["width"] / 2, (card["width"], content["width"])
    # The picture on the left and the facts on its right, not above them.
    picture = ui.page.locator("li.card > .card-image").bounding_box()  # one-shot: geometry, as above
    body = ui.page.locator("li.card > .card-body").bounding_box()  # one-shot: geometry, as above
    assert body["x"] >= picture["x"] + picture["width"] - 1
    assert abs(body["y"] - picture["y"]) < 2


def test_on_a_phone_the_card_is_one_column(ui):
    """The picture above its facts at phone width, and nothing wider than the screen."""
    a_finished_get(ui)
    ui.page.set_viewport_size({"width": 375, "height": 740})
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    picture = ui.page.locator("li.card > .card-image").bounding_box()  # one-shot: geometry, measured once the scans are open
    body = ui.page.locator("li.card > .card-body").bounding_box()  # one-shot: geometry, as above
    assert body["y"] >= picture["y"] + picture["height"] - 1
    assert ui.page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth") <= 0


# -- scans as a table -----------------------------------------------------------------

#: Every line box of every text node in the scans table's header and fact cells,
#: its action buttons, and the labels of the sentence row under each scan,
#: counted by distinct top. A label that wraps has two.
WRAPPED_LABELS = """
() => {
  const wrapped = [];
  const cells = document.querySelectorAll(
    'details[open] table.scans th, details[open] table.scans td.scan-fact,' +
    ' details[open] table.scans td.scan-actions button, details[open] table.scans dt'
  );
  for (const cell of cells) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)));
      if (tops.size > 1) wrapped.push(node.textContent.trim());
    }
  }
  return wrapped;
}
"""


def test_scans_are_a_table_one_row_a_scan(ui):
    """The columns a curator compares scans by, as an *arr app lists releases."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    # Each header whole, in any case (the read lower-cased them).
    expect(ui.page.locator("table.scans thead th")).to_have_text(
        [
            re.compile(rf"^\s*{header}\s*$", re.IGNORECASE)
            for header in ["scan", "resolution", "source", "rights", "confidence", "chosen", "actions"]
        ],
        use_inner_text=True,
    )
    rows = ui.page.locator("tr.alternate")
    expect(rows).to_have_count(2)
    for fact in ["3,840 × 2,604 px", "Art Institute of Chicago", "Public domain", "on offer"]:
        expect(rows.nth(0)).to_contain_text(fact, use_inner_text=True)
    for fact in ["1,600 × 1,085 px", "Wikimedia Commons", "Use this one"]:
        expect(rows.nth(1)).to_contain_text(fact, use_inner_text=True)
    # What does not compare down a column is still there, under its scan.
    expect(ui.view).to_contain_text(RATIONALE, use_inner_text=True)


def test_scans_start_collapsed(ui):
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    expect(ui.page.locator("li.card details[open]")).to_have_count(0)
    assert ui.requests_matching("/api/candidates/work-1/images") == []


def test_no_label_in_the_scans_wraps_onto_two_lines_at_desktop_width(ui):
    """The owner's card ran to about 7,000 px at 1280 with every fact wrapped."""
    at_desktop(a_finished_get(ui))
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    # Four facts a row over the two scans. The museum's name is not among them:
    # it is a name that wraps within a bounded column by design, since museums'
    # names run to "The Metropolitan Museum of Art"; the overflow check below
    # is what holds it.
    expect(ui.page.locator("table.scans td.scan-fact").nth(7), "the measurement found no cells to measure").to_be_attached()
    expect(ui.page.locator("table.scans td.scan-source").nth(1)).to_be_attached()
    assert ui.page.evaluate(WRAPPED_LABELS) == []
    # The table fits the card at this width rather than escaping sideways.
    table = ui.page.locator("table.scans").bounding_box()  # one-shot: geometry, measured once the cells are drawn
    card = ui.page.locator("li.card").bounding_box()  # one-shot: geometry, as above
    assert table["x"] + table["width"] <= card["x"] + card["width"] + 1
    # Nor does it scroll sideways inside the card. The edge check above has the
    # card's padding as slack, and a table already scrolling within its box
    # passed it on one machine's fonts and failed it on CI's wider ones.
    overflow = ui.page.evaluate(
        "() => { const s = document.querySelector('table.scans').closest('.table-scroll');"
        " return s.scrollWidth - s.clientWidth; }"
    )
    assert overflow <= 0, f"the scans scroll {overflow}px sideways at desktop width"


# -- resolution in pixels, and no inches anywhere -------------------------------------


def test_the_card_states_the_scan_s_pixels_above_the_fold(ui):
    at_desktop(a_finished_get(ui))
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card .card-resolution")

    expect(ui.page.locator("li.card .card-resolution")).to_have_text("3,840 × 2,604 px", use_inner_text=True)
    resolution = ui.page.locator(
        "li.card .card-resolution"
    ).bounding_box()  # one-shot: geometry, measured once its words are drawn
    assert resolution["y"] + resolution["height"] <= 900, "the pixels are below the fold"
    expect(ui.view).not_to_contain_text("″", use_inner_text=True)
    expect(ui.view).not_to_contain_text("would show at", use_inner_text=True)
    # The scan meets the minimum, which is not news, so it carries no size badge.
    expect(ui.page.locator("li.card .badge-below_minimum")).to_have_count(0)


def test_a_scan_whose_size_nobody_recorded_says_so_rather_than_inventing_one(ui):
    unsized = an_instance(width=None, height=None, fit=None, fit_note="The provider did not report this image's dimensions.")
    a_finished_get(ui, [a_card(work=chosen(), shown=unsized)])
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    expect(ui.view).to_contain_text("size unrecorded", use_inner_text=True)
    expect(ui.page.locator("li.card .card-resolution")).to_have_count(0)


def _held_work_with_a_fit(work_with_an_image, services):
    # Below the minimum, because a work that meets it draws no badge at all.
    work = work_with_an_image("Nighthawks", width=800, height=600)
    theme = services.display.add_theme(name="Night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=0)
    return work, theme


FIT_BADGE = ".badge-below_minimum"


@pytest.mark.parametrize("screen", ["work", "theme", "collection"])
def test_no_screen_that_draws_a_fit_badge_says_inches(ui, services, work_with_an_image, screen):
    """Everywhere `fitBadge` draws, the verdict word stays and the inches go."""
    work, theme = _held_work_with_a_fit(work_with_an_image, services)
    fragment = {"work": f"#work/{work.id}", "theme": f"#theme/{theme.id}", "collection": "#collection"}[screen]
    ui.open(fragment)
    ui.page.wait_for_selector(f"#view :is({FIT_BADGE})")

    # Its last two words, whatever comes before them.
    expect(ui.page.locator(f"#view :is({FIT_BADGE})").first).to_have_text(
        re.compile(r"(^|\s)below\s+minimum\s*$"), use_inner_text=True
    )
    expect(ui.view).not_to_contain_text("″", use_inner_text=True)
    expect(ui.view).not_to_contain_text("would show at", use_inner_text=True)


# -- clicking a picture enlarges it in place ------------------------------------------


def test_clicking_the_picture_enlarges_it_without_leaving_the_page(ui):
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card > button.card-image")
    before = ui.page.url

    with ui.page.expect_request("**/api/candidate-images/image-1/preview?size=large"):
        ui.page.click("li.card > button.card-image")

    ui.page.wait_for_selector("dialog.enlarged[open] img")
    assert ui.page.url == before
    expect(ui.page.locator("dialog.enlarged img")).to_have_attribute("alt", "The Magpie, by Claude Monet")


@pytest.mark.parametrize("closed_by", ["escape", "button", "outside"])
def test_the_enlarged_picture_closes_and_gives_focus_back(ui, closed_by):
    a_finished_get(ui)
    at_desktop(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card > button.card-image")
    before = ui.page.url
    ui.page.focus("li.card > button.card-image")
    ui.page.keyboard.press("Enter")
    ui.page.wait_for_selector("dialog.enlarged[open]")

    if closed_by == "escape":
        ui.page.keyboard.press("Escape")
    elif closed_by == "button":
        ui.page.click("dialog.enlarged button:text-is('Close')")
    else:
        # The corner of the viewport is backdrop whatever the picture's size.
        ui.page.mouse.click(5, 5)

    ui.page.wait_for_selector("dialog.enlarged", state="detached")
    assert ui.page.url == before
    # The state the read below is about, waited for: focus returns as the dialog goes.
    expect(ui.page.locator("li.card > button.card-image")).to_be_focused()
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Enlarge the picture of The Magpie"


def test_a_click_on_the_enlarged_picture_itself_does_not_close_it(ui):
    """The paired negative: only a click outside the picture is a click away."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card > button.card-image")
    ui.page.wait_for_selector("dialog.enlarged[open] img")

    ui.page.click("dialog.enlarged img")

    # A click that closed the dialog would do it at once; nothing marks a click having had no effect.
    ui.page.wait_for_timeout(200)  # sleep: a click's effect, absent, has no sign
    expect(ui.page.locator("dialog.enlarged[open]")).to_have_count(1)


def test_a_scan_in_the_table_enlarges_too(ui):
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    with ui.page.expect_request("**/api/candidate-images/image-2/preview?size=large"):
        ui.page.locator("tr.alternate").nth(1).locator("button.card-image").click()

    ui.page.wait_for_selector("dialog.enlarged[open]")
    expect(ui.page.locator("tr.alternate").nth(1).locator("button.card-image")).to_have_attribute(
        "aria-label", "Enlarge this scan of The Magpie"
    )


def test_a_scan_enlarged_from_the_table_is_named_for_the_picture_not_the_button(ui):
    """The button says what pressing it does; what opens is the picture, and says which."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    ui.page.locator("tr.alternate").nth(1).locator("button.card-image").click()
    ui.page.wait_for_selector("dialog.enlarged[open] img")

    named = "The Magpie, by Claude Monet — the scan from Wikimedia Commons, 1,600 × 1,085 px"
    expect(ui.page.locator("dialog.enlarged")).to_have_attribute("aria-label", named)
    expect(ui.page.locator("dialog.enlarged img")).to_have_attribute("alt", named)
    # The button keeps its own name: it is the control, not the picture.
    expect(ui.page.locator("tr.alternate").nth(1).locator("button.card-image")).to_have_attribute(
        "aria-label", "Enlarge this scan of The Magpie"
    )


def test_the_card_s_own_picture_enlarged_is_named_for_the_work(ui):
    """The paired case: the card's picture was already named for the work, and stays so."""
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.click("li.card > button.card-image")
    ui.page.wait_for_selector("dialog.enlarged[open] img")

    expect(ui.page.locator("dialog.enlarged")).to_have_attribute("aria-label", "The Magpie, by Claude Monet")
    expect(ui.page.locator("dialog.enlarged img")).to_have_attribute("alt", "The Magpie, by Claude Monet")


# -- a card listing that failed says how to try again ---------------------------------


def test_a_finished_get_whose_cards_could_not_be_read_says_to_reload(ui):
    """A finished Get is not watched, so nothing on the page will ask again."""
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[chosen()]))
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", (500, {"error": "The listing broke."}))
    ui.open(f"#get/{GET_ID}")

    ui.page.wait_for_selector("text=This Get's works could not be read")
    expect(ui.page.locator(".get-review p.note")).to_have_text(
        re.compile(re.escape("Reload the page to try again.") + "$"), use_inner_text=True
    )


def test_a_running_get_whose_cards_could_not_be_read_asks_again_by_itself(ui):
    """The paired negative: a Get still looking is watched, and the next look retries."""
    card = a_card(work=chosen())
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[card.work]))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", [(500, {"error": "The listing broke."}), a_candidate_page([card], run=run)])
    ui.serve_image("**/api/candidate-images/*/preview*")
    ui.open(f"#get/{GET_ID}")

    ui.page.wait_for_selector("text=This Get's works could not be read")
    expect(ui.page.locator(".get-review p.note")).not_to_contain_text("Reload", use_inner_text=True)
    # And the claim the missing sentence rests on: the next look reads them.
    ui.page.wait_for_selector("li.card button:text-is('Accept')")


# -- a running Get's redraw keeps the review in progress ------------------------------

WHY = "The light on the snow"
USE_THE_SECOND_SCAN = "li.card[data-work='work-1'] button[aria-label='Use this scan for The Magpie']"


def a_get_still_looking(ui):
    """The Magpie found and being reviewed; Haystacks not looked up yet.

    Returns what the run becomes once Haystacks is found, for the test to serve
    when it has done its reviewing.
    """
    magpie = a_card(work=chosen(), instances_held=2, instances_surviving=2)
    haystacks = chosen(work_id="work-2", title="Haystacks")
    waiting = a_card(work=chosen(work_id="work-2", title="Haystacks", resolution_status="pending"), shown=None)
    found = a_card(work=haystacks, shown=an_instance(image_id="image-3", work_id="work-2"))
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    a_finished_get(ui, [magpie])
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[magpie.work, waiting.work]))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([magpie, waiting], run=run))

    def haystacks_found():
        ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[magpie.work, found.work]))
        ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([magpie, found], run=run))
        ui.page.wait_for_selector("li.card[data-work='work-2'] > button.card-image")

    return haystacks_found


def test_a_running_get_s_redraw_keeps_the_why_the_open_scans_and_the_focus(ui):
    """Each work the Get finds redraws the page; the card being judged must not notice."""
    haystacks_found = a_get_still_looking(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card[data-work='work-2'] .card-image-absent")

    ui.page.fill("#reason-work-1", WHY)
    ui.page.click("li.card[data-work='work-1'] summary")
    ui.page.wait_for_selector(USE_THE_SECOND_SCAN)
    ui.page.focus(USE_THE_SECOND_SCAN)

    haystacks_found()

    expect(ui.page.locator("#reason-work-1")).to_have_value(WHY)
    expect(ui.page.locator("li.card[data-work='work-1'] details[open] tr.alternate")).to_have_count(2)
    # Read at the redraw, not waited for: the claim is that the focus was never
    # lost, and `haystacks_found` waits for the new card, drawn in the same turn.
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Use this scan for The Magpie"
    assert ui.page.evaluate("() => document.activeElement.isConnected")
    # Kept rather than rebuilt and refilled: the scans were not asked for again.
    assert len(ui.requests_matching("/api/candidates/work-1/images")) == 1


def test_a_card_kept_across_a_redraw_still_reaches_the_offer_to_look_again(ui):
    """A kept card tells the page it is now on about its verdict, not the page it came from."""
    haystacks_found = a_get_still_looking(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("li.card[data-work='work-1'] summary")
    ui.page.click("li.card[data-work='work-1'] summary")
    ui.page.wait_for_selector(USE_THE_SECOND_SCAN)

    haystacks_found()
    ui.serve("**/api/candidate-images/image-1/reject", {})
    ui.serve(
        "**/api/candidates/work-1",
        a_card(work=chosen(verdict=Verdict.WANTED.value), instances_held=2, instances_surviving=1).model_dump(mode="json"),
    )
    ui.page.click("li.card[data-work='work-1'] tr.alternate >> nth=0 >> button:text-is('Turn it down')")

    ui.page.wait_for_selector("#view h2:text-is('Wanted')")
    expect(ui.view).to_contain_text("1 work is wanted.", use_inner_text=True)


def test_a_get_s_page_opened_again_is_built_afresh(ui):
    """Kept across the Get's own redraws, not across visits: a page left and come back to is read anew.

    The scans behind a card left open on an earlier visit may have been chosen
    or turned down since, so the cards of a visit that ended are not reused.
    """
    a_finished_get(ui)
    ui.open(f"#get/{GET_ID}")
    ui.page.fill("#reason-work-1", WHY)
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    ui.page.click("li.card .card-meta a:text-is('Q3226397')")
    ui.page.wait_for_selector("#view a:has-text('← Get')")
    ui.page.click("#view a:has-text('← Get')")
    ui.page.wait_for_selector("li.card summary")

    expect(ui.page.locator("#reason-work-1")).to_have_value("")
    expect(ui.page.locator("li.card details[open]")).to_have_count(0)
