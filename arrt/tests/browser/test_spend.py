"""Spend as a budget and tiers, in a real browser against a real server.

The sidebar says what is left of this month's budget, honestly for each state
the server can be in. Every spending control shows its tier — free, `$`, `$$`
or `$$$`, the server's — before it is pressed, Ask's button included. No run
stops for approval any more, so Approve and Decline are offered only on a run
stored awaiting approval before then; a run halted at the cap says the month's
budget is spent, in the server's words.
"""

import pytest
from payloads import a_candidate, a_run, a_run_view, an_estimate

from arrt.http.models import BudgetOut, CostTiersOut
from arrt.persistence.discovery_records import RunStatus

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

RUN_ID = "run-under-test"
TIERS = CostTiersOut(cents_below_usd="0.05", dimes_below_usd="0.50")


def a_budget(state, *, remaining=None, budget=None, spent=None, note=None) -> dict:
    return BudgetOut(state=state, remaining_usd=remaining, budget_usd=budget, spent_usd=spent, note=note, tiers=TIERS).model_dump(
        mode="json"
    )


def _budget_said(ui) -> list[str]:
    ui.page.wait_for_selector("#sidebar .budget .budget-line")
    return [" ".join(text.split()) for text in ui.page.locator("#sidebar .budget p").all_inner_texts()]


# -- the sidebar's budget ---------------------------------------------------------


@pytest.mark.parametrize(
    ("budget", "said"),
    [
        pytest.param(
            a_budget("known", remaining="12.4", budget="20", spent="7.6"),
            ["$12.40 left this month"],
            id="known",
        ),
        pytest.param(
            a_budget(
                "configured",
                remaining="3.05",
                budget="10",
                spent="6.95",
                note="The OpenRouter key has no limit, so nothing stops spending at this budget.",
            ),
            ["$3.05 left this month", "The OpenRouter key has no limit, so nothing stops spending at this budget."],
            id="configured",
        ),
        pytest.param(
            a_budget("uncapped", spent="4.2", note="The OpenRouter key has no limit and no monthly budget is set."),
            ["$4.20 spent this month", "The OpenRouter key has no limit and no monthly budget is set."],
            id="uncapped",
        ),
        pytest.param(
            a_budget("not_configured", note="No OpenRouter key is configured, so nothing here spends money."),
            ["Nothing spends", "No OpenRouter key is configured, so nothing here spends money."],
            id="not configured",
        ),
        pytest.param(
            a_budget("unavailable", note="What is left of this month's budget could not be read just now."),
            ["Budget unknown", "What is left of this month's budget could not be read just now."],
            id="unavailable",
        ),
    ],
)
def test_the_sidebar_says_what_is_left_this_month_for_each_state(ui, budget, said):
    ui.serve("**/api/budget", budget)
    ui.open("")

    assert _budget_said(ui) == said
    if budget["state"] != "known":
        assert "left this month" not in " ".join(said[1:]), "only a figure the provider or the budget gives is 'left'"


def test_the_real_server_without_a_key_says_nothing_spends(ui):
    ui.open("")

    assert _budget_said(ui)[0] == "Nothing spends"


def test_a_budget_that_cannot_be_read_says_so_and_is_asked_again(ui):
    ui.serve("**/api/budget", [(500, {"error": "boom"}), a_budget("known", remaining="1", budget="5", spent="4")])
    ui.open("")

    assert _budget_said(ui)[0] == "Budget unknown"
    ui.page.evaluate("() => { window.location.hash = '#discover'; }")
    ui.page.wait_for_function("() => document.querySelector('#sidebar .budget-line').textContent === '$1.00 left this month'")


# -- tiers -----------------------------------------------------------------------


#: Under Get, a caption tied to it for a screen reader: what is said, read back.
CAPTION = """(button) => {
  const id = button.getAttribute('aria-describedby');
  const caption = id && document.getElementById(id);
  if (!caption) return null;
  const c = caption.getBoundingClientRect(), b = button.getBoundingClientRect();
  const below = c.top >= b.bottom - 0.5;
  // Starts where its act starts: centred under a narrower button, the caption
  // ran into its neighbour's and the two read as one sentence.
  const aligned = Math.abs(c.left - b.left) < 1;
  const s = getComputedStyle(caption);
  return {
    text: caption.textContent.trim(),
    below,
    aligned,
    act: caption.matches('button, a, [role=button]') || !!caption.querySelector('button, a'),
    border: s.borderTopStyle,
    wrap: s.whiteSpace,
  };
}"""


@pytest.mark.parametrize(
    ("bound", "said"),
    [
        ("0.004", "About $0.01"),
        ("0.012", "About $0.01"),
        ("0.12", "About $0.10"),
        ("0.04", "About $0.10"),
        ("0.90", "About $1"),
        ("4.00", "About $10"),
        ("0.00", "Free"),
    ],
)
def test_ask_says_about_what_a_get_costs_under_it(ui, bound, said):
    """The owner's ruling (2026-10-08): the order of magnitude, not the bound."""
    ui.serve("**/api/estimate", an_estimate(phase="phase_1", estimated_cost_usd=bound, run_id=None))
    ui.open("#discover")

    caption = ui.page.locator("#view button:text-is('Get')").evaluate(CAPTION)
    assert caption is not None, "Get has no caption tied to it"
    assert caption["text"] == said
    assert caption["below"]
    assert caption["aligned"]
    assert not caption["act"]
    assert caption["border"] == "none"
    assert caption["wrap"] == "nowrap"
    # The bound sentence and the tier mark are gone, not shown beside it.
    assert "costs at most" not in ui.text()
    assert ui.page.locator("#view .badge-tier").count() == 0


def test_an_estimate_that_is_not_a_figure_reads_as_unknown_not_as_a_price(ui):
    """Served by hand: the server's model cannot build one, and the client says so anyway."""
    ui.serve("**/api/estimate", {"phase": "phase_1", "estimated_cost_usd": None, "basis": "", "run_id": None, "tier": "$"})
    ui.open("#discover")

    caption = ui.page.locator("#view button:text-is('Get')").evaluate(CAPTION)
    assert caption["text"] == "Cost unknown just now"


def test_ask_still_opens_when_the_estimate_cannot_be_read(ui):
    ui.page.route("**/api/estimate", lambda route: route.fulfill(status=500, body="no"))
    ui.open("#discover")

    caption = ui.page.locator("#view button:text-is('Get')").evaluate(CAPTION)
    assert caption["text"] == "Cost unknown just now"


def test_a_tier_mark_is_words_on_one_line_not_a_box(ui):
    """Every other priced act keeps "Cost: <tier>"; Approve on a Get's page is one."""
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    ui.serve("**/api/estimate?*", an_estimate())
    ui.open(f"#get/{RUN_ID}")

    mark = ui.page.locator("button:text-is('Approve the list') + .badge-tier")
    look = mark.evaluate("""(node) => {
          const s = getComputedStyle(node);
          return {border: s.borderTopStyle, background: s.backgroundColor, wrap: s.whiteSpace};
        }""")
    assert look == {"border": "none", "background": "rgba(0, 0, 0, 0)", "wrap": "nowrap"}


def test_an_approval_gate_stored_before_offers_approve_with_its_tier(ui):
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    ui.serve("**/api/estimate?*", an_estimate())
    ui.open(f"#get/{RUN_ID}")

    approve = ui.page.locator("button:text-is('Approve the list')")
    approve.wait_for()
    assert " ".join(approve.locator("xpath=following-sibling::*[1]").inner_text().split()) == "Cost: Free"
    assert ui.page.locator("button:text-is('Decline it')").count() == 1
    assert "threshold" not in ui.text(), "no threshold stops a run any more"


@pytest.mark.parametrize(
    "status", [RunStatus.RESOLVING_IMAGES, RunStatus.COMPLETED, RunStatus.HALTED_BY_BUDGET, RunStatus.CANCELLED]
)
def test_no_other_run_offers_approve_or_decline(ui, status):
    terminal = status is not RunStatus.RESOLVING_IMAGES
    run = a_run(status=status.value, is_terminal=terminal, approval_required=False)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run, works=[a_candidate()]))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", {"scope": "run_family", "cost_usd": "0", "run_id": RUN_ID})
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view h1")

    assert ui.page.locator("button:text-is('Approve the list'), button:text-is('Decline it')").count() == 0


def test_a_run_halted_at_the_cap_says_the_months_budget_is_spent(ui):
    reason = "This month's budget is spent: OpenRouter refused the request (402)."
    run = a_run(status=RunStatus.HALTED_BY_BUDGET.value, is_terminal=True, approval_required=False, end_reason=reason)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run, works=[a_candidate()]))
    ui.open(f"#get/{RUN_ID}")

    line = ui.page.locator("#view .run-end-reason")
    line.wait_for()
    assert line.inner_text() == f"Why it stopped: {reason}"
    assert "credit limit" not in ui.text()
