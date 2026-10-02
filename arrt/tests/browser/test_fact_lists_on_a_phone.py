"""Labelled fact lists read as words on a phone.

At 375 px the run page's *What it cost* list broke "1 of an allowance of 10"
mid-word: each label took its whole width on one line and left the value a
column too narrow for "allowance". The list is one shared style, so every page
that draws one is measured here at that width.
"""

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view, a_spend

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from arrt.persistence.discovery_records import RunStatus, WorkProvenance  # noqa: E402

#: Every word of every fact list's labels and values whose line boxes sit on more
#: than one line. Words are split at spaces, hyphens and slashes, which are where
#: a line may break; a run longer than any phone line (a content hash) is left
#: out, since breaking it is the only way it fits.
BROKEN_WORDS = """
() => {
  const broken = [];
  for (const cell of document.querySelectorAll('#view dl.facts dt, #view dl.facts dd')) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const pattern = /[^\\s\\-\\u2013\\u2014\\/]+/g;
      for (let m = pattern.exec(node.textContent); m; m = pattern.exec(node.textContent)) {
        if (m[0].length > 24) continue;
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)));
        if (tops.size > 1) broken.push(m[0]);
      }
    }
  }
  return broken;
}
"""

GET_ID = "a-get"


def at_phone_width(ui):
    ui.page.set_viewport_size({"width": 375, "height": 740})


def measured(ui, *, at_least):
    assert ui.page.locator("#view dl.facts dd").count() >= at_least, "the measurement found no facts to measure"
    assert ui.page.evaluate(BROKEN_WORDS) == []
    assert ui.page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth") <= 0


def test_the_run_page_s_costs_break_between_words(ui):
    work = a_candidate(provenance=WorkProvenance.CHOSEN.value, wikidata_qid="Q3226397")
    run = a_run(
        run_id=GET_ID,
        kind="get",
        intent=None,
        status=RunStatus.COMPLETED.value,
        is_terminal=True,
        estimated_cost_usd="0.00",
        actual_cost_usd="0.00",
    )
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(run=run, works=[work]))
    ui.serve(f"**/api/runs/{GET_ID}/spend", a_spend())
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([a_card(work=work)], run=run))
    at_phone_width(ui)
    ui.open(f"#run/{GET_ID}")
    ui.page.wait_for_selector("#view dd:has-text('of an allowance of')")

    measured(ui, at_least=4)


def test_the_work_page_s_facts_break_between_words(ui, work_with_an_image):
    """The work's own facts, and its master image's, which carry a path and a hash."""
    work = work_with_an_image("Untitled (Purple, White, and Red)")
    at_phone_width(ui)
    ui.open(f"#work/{work.id}")
    ui.page.wait_for_selector("#view dt:text-is('Content hash')")

    measured(ui, at_least=6)


def test_the_health_page_s_facts_break_between_words(ui):
    """Its sentences name the files it read, and a path is wider than a phone."""
    at_phone_width(ui)
    ui.open("#health")
    ui.page.wait_for_selector("#view dl.facts dd")

    measured(ui, at_least=2)


def test_the_artist_page_s_facts_break_between_words(ui, service):
    artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=artist.id, date_created="1953")
    at_phone_width(ui)
    ui.open(f"#artist/{artist.id}")
    ui.page.wait_for_selector("#view dl.facts dd")

    measured(ui, at_least=1)
