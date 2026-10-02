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

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.discovery_records import RunStatus, Verdict, WorkProvenance  # noqa: E402

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
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card button:text-is('Accept')")

    assert ui.page.locator("li.card button:text-is('Reject')").count() == 1
    assert "Review these works" not in ui.text()
    # The cards stand where the work table stood, rather than beside it.
    assert ui.page.locator("#view table").count() == 0


def test_a_verdict_on_the_get_s_page_is_recorded_there(ui):
    """The cards on the Get's page are the review's own, not pictures of them."""
    a_finished_get(ui)
    ui.serve("**/api/candidates/work-1/verdict", a_verdict(work=chosen(verdict=Verdict.ACCEPTED.value)))
    ui.serve("**/api/candidates/work-1", a_card(work=chosen(verdict=Verdict.ACCEPTED.value)).model_dump(mode="json"))
    ui.open(f"#run/{GET_ID}")

    ui.page.click("li.card button:text-is('Accept')")

    ui.page.wait_for_selector("li.card .badge:has-text('accepted')")
    assert ui.page.evaluate("() => window.location.hash") == f"#run/{GET_ID}"


def test_a_discovery_run_s_page_is_unchanged(ui):
    """The paired negative: only a Get's page became its review."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=a_run(run_id=RUN_ID, status=RunStatus.COMPLETED.value, is_terminal=True), works=[a_candidate()]),
    )
    ui.open(f"#run/{RUN_ID}")
    ui.page.wait_for_selector("#view table")

    assert ui.page.locator("button:text-is('Review these works')").count() == 1
    assert ui.page.locator("li.card").count() == 0
    assert ui.requests_matching(f"/api/runs/{RUN_ID}/candidates") == []


def test_review_still_answers_for_a_get(ui):
    """An address outlives the links that made it: `#review/<get>` still judges."""
    a_finished_get(ui)
    ui.open(f"#review/{GET_ID}")

    ui.page.wait_for_selector("li.card button:text-is('Accept')")
    assert ui.page.locator("#view button:text-is('← The Get')").count() == 1


def test_a_work_opened_from_a_get_s_card_returns_to_the_get(ui):
    """As a Work opened from Review returns to Review, one opened from a Get's card returns to the Get."""
    a_finished_get(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    ui.page.click("li.card .card-meta button:text-is('Q3226397')")
    ui.page.wait_for_selector("#view button:has-text('← The Get')")
    assert ui.page.evaluate("() => window.location.hash") == f"#work/Q3226397?from=run%2F{GET_ID}"

    ui.page.click("#view button:has-text('← The Get')")
    ui.page.wait_for_function(f"() => window.location.hash === '#run/{GET_ID}'")


def test_a_get_s_page_that_cannot_read_its_cards_says_so_and_keeps_the_rest(ui):
    """The run's sentence and costs are still worth having when the cards are not."""
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[chosen()]))
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", (500, {"error": "The listing broke."}))
    ui.open(f"#run/{GET_ID}")

    ui.page.wait_for_selector("text=This Get's works could not be read")
    assert "This Get finished" in ui.text()


def test_a_card_for_a_work_not_yet_looked_up_does_not_say_nothing_was_found(ui):
    """A Get's page shows its cards while it is still looking."""
    card = a_card(work=chosen(resolution_status="pending"), shown=None)
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[card.work]))
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=run))
    ui.open(f"#run/{GET_ID}")

    ui.page.wait_for_selector("li.card .card-image-absent")
    said = ui.page.locator("li.card .card-image-absent").inner_text()
    assert said == "This work has not been looked up, so there is no scan to show yet."


# -- the card is wide ----------------------------------------------------------------


def test_one_card_is_wider_than_half_the_page_at_desktop_width(ui):
    """One work to a row: the narrow column was what wrapped everything on it."""
    at_desktop(a_finished_get(ui))
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    card = ui.page.locator("li.card").bounding_box()
    content = ui.page.locator("#view").bounding_box()
    assert card["width"] > content["width"] / 2, (card["width"], content["width"])
    # The picture on the left and the facts on its right, not above them.
    picture = ui.page.locator("li.card > .card-image").bounding_box()
    body = ui.page.locator("li.card > .card-body").bounding_box()
    assert body["x"] >= picture["x"] + picture["width"] - 1
    assert abs(body["y"] - picture["y"]) < 2


def test_on_a_phone_the_card_is_one_column(ui):
    """The picture above its facts at phone width, and nothing wider than the screen."""
    a_finished_get(ui)
    ui.page.set_viewport_size({"width": 375, "height": 740})
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    picture = ui.page.locator("li.card > .card-image").bounding_box()
    body = ui.page.locator("li.card > .card-body").bounding_box()
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
    ui.open(f"#run/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    headers = ui.page.locator("table.scans thead th").all_inner_texts()
    assert [h.strip().lower() for h in headers] == [
        "scan",
        "resolution",
        "provider",
        "rights",
        "confidence",
        "chosen",
        "actions",
    ]
    rows = [" ".join(row.split()) for row in ui.page.locator("tr.alternate").all_inner_texts()]
    assert len(rows) == 2
    assert "3,840 × 2,604 px" in rows[0] and "artic" in rows[0] and "on offer" in rows[0], rows[0]
    assert "1,600 × 1,085 px" in rows[1] and "commons" in rows[1] and "Use this one" in rows[1], rows[1]
    # What does not compare down a column is still there, under its scan.
    assert RATIONALE in ui.text()


def test_scans_start_collapsed(ui):
    a_finished_get(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("li.card details[open]").count() == 0
    assert ui.requests_matching("/api/candidates/work-1/images") == []


def test_no_label_in_the_scans_wraps_onto_two_lines_at_desktop_width(ui):
    """The owner's card ran to about 7,000 px at 1280 with every fact wrapped."""
    at_desktop(a_finished_get(ui))
    ui.open(f"#run/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    assert ui.page.locator("table.scans td.scan-fact").count() >= 10, "the measurement found no cells to measure"
    assert ui.page.evaluate(WRAPPED_LABELS) == []
    # The table fits the card at this width rather than escaping sideways.
    table = ui.page.locator("table.scans").bounding_box()
    card = ui.page.locator("li.card").bounding_box()
    assert table["x"] + table["width"] <= card["x"] + card["width"] + 1


# -- resolution in pixels, and no inches anywhere -------------------------------------


def test_the_card_states_the_scan_s_pixels_above_the_fold(ui):
    at_desktop(a_finished_get(ui))
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card .card-resolution")

    assert ui.page.locator("li.card .card-resolution").inner_text() == "3,840 × 2,604 px"
    resolution = ui.page.locator("li.card .card-resolution").bounding_box()
    assert resolution["y"] + resolution["height"] <= 900, "the pixels are below the fold"
    assert "″" not in ui.text() and "would show at" not in ui.text()
    assert ui.page.locator("li.card .badge-native").inner_text().split() == ["●", "native"]


def test_a_scan_whose_size_nobody_recorded_says_so_rather_than_inventing_one(ui):
    unsized = an_instance(width=None, height=None, fit=None, fit_note="The provider did not report this image's dimensions.")
    a_finished_get(ui, [a_card(work=chosen(), shown=unsized)])
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("li.card .card-resolution").count() == 0
    assert "size unrecorded" in ui.text()


def _held_work_with_a_fit(work_with_an_image, services):
    work = work_with_an_image("Nighthawks", width=1600, height=1200)
    theme = services.display.add_theme(name="Night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=0)
    return work, theme


FIT_BADGE = ".badge-native, .badge-matted_small, .badge-below_floor"


@pytest.mark.parametrize("screen", ["work", "theme", "collection"])
def test_no_screen_that_draws_a_fit_badge_says_inches(ui, services, work_with_an_image, screen):
    """Everywhere `fitBadge` draws, the verdict word stays and the inches go."""
    work, theme = _held_work_with_a_fit(work_with_an_image, services)
    fragment = {"work": f"#work/{work.id}", "theme": f"#theme/{theme.id}", "collection": "#collection"}[screen]
    ui.open(fragment)
    ui.page.wait_for_selector(f"#view :is({FIT_BADGE})")

    badge = ui.page.locator(f"#view :is({FIT_BADGE})").first.inner_text()
    assert badge.split()[-1] in {"native", "small", "floor"}, badge
    assert "″" not in ui.text() and "would show at" not in ui.text()


# -- clicking a picture enlarges it in place ------------------------------------------


def test_clicking_the_picture_enlarges_it_without_leaving_the_page(ui):
    a_finished_get(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("li.card > button.card-image")
    before = ui.page.url

    with ui.page.expect_request("**/api/candidate-images/image-1/preview?size=large"):
        ui.page.click("li.card > button.card-image")

    ui.page.wait_for_selector("dialog.enlarged[open] img")
    assert ui.page.url == before
    assert ui.page.locator("dialog.enlarged img").get_attribute("alt") == "The Magpie, by Claude Monet"


@pytest.mark.parametrize("closed_by", ["escape", "button", "outside"])
def test_the_enlarged_picture_closes_and_gives_focus_back(ui, closed_by):
    a_finished_get(ui)
    at_desktop(ui)
    ui.open(f"#run/{GET_ID}")
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
    assert ui.page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Enlarge the picture of The Magpie"


def test_a_click_on_the_enlarged_picture_itself_does_not_close_it(ui):
    """The paired negative: only a click outside the picture is a click away."""
    a_finished_get(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.click("li.card > button.card-image")
    ui.page.wait_for_selector("dialog.enlarged[open] img")

    ui.page.click("dialog.enlarged img")

    ui.page.wait_for_timeout(200)
    assert ui.page.locator("dialog.enlarged[open]").count() == 1


def test_a_scan_in_the_table_enlarges_too(ui):
    a_finished_get(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.click("li.card summary")
    ui.page.wait_for_selector("tr.alternate")

    with ui.page.expect_request("**/api/candidate-images/image-2/preview?size=large"):
        ui.page.locator("tr.alternate").nth(1).locator("button.card-image").click()

    ui.page.wait_for_selector("dialog.enlarged[open]")
    label = ui.page.locator("tr.alternate").nth(1).locator("button.card-image").get_attribute("aria-label")
    assert label == "Enlarge this scan of The Magpie"
