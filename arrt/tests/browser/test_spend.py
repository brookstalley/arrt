"""Spend as a budget and tiers, in a real browser against a real server.

The sidebar says what is left of this month's budget, honestly for each state
the server can be in. Every spending control shows its tier — free, `$`, `$$`
or `$$$`, the server's — before it is pressed, but for a work card's Get in Ask
(`information-architecture.md`, the owner's ruling of 2026-10-09). No run
stops for approval any more, so Approve and Decline are offered only on a run
stored awaiting approval before then; a run halted at the cap says the month's
budget is spent, in the server's words.
"""

import pytest
from payloads import a_candidate, a_run, a_run_view, an_estimate

from arrt.http.models import BudgetOut, CostTiersOut
from arrt.persistence.discovery_records import RunStatus

expect = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
).expect

RUN_ID = "run-under-test"
TIERS = CostTiersOut(cents_below_usd="0.05", dimes_below_usd="0.50")


def a_budget(state, *, remaining=None, budget=None, spent=None, note=None) -> dict:
    return BudgetOut(state=state, remaining_usd=remaining, budget_usd=budget, spent_usd=spent, note=note, tiers=TIERS).model_dump(
        mode="json"
    )


def _budget_said(ui) -> list[str]:
    ui.page.wait_for_selector("#sidebar .budget .budget-line")
    # The line is a link since audit-6 finding 10 and its note a paragraph; one
    # union locator keeps them in the order they are drawn.
    return [
        " ".join(text.split())
        for text in ui.page.locator("#sidebar .budget .budget-line, #sidebar .budget .budget-note").all_inner_texts()
    ]


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


@pytest.mark.parametrize("state", ["known", "uncapped", "not_configured", "unavailable"])
def test_the_budget_line_is_a_link_to_the_history_of_gets_in_every_state(ui, state):
    """Checking spend has somewhere to go (audit-6 finding 10): History, filtered to Gets."""
    ui.serve("**/api/budget", a_budget(state, remaining="12.4" if state == "known" else None))
    ui.open("#collection")
    line = ui.page.locator("#sidebar .budget a.budget-line")
    expect(line).to_have_count(1)
    expect(line).to_have_attribute("href", "#history?kind=gets")

    line.click()

    ui.page.wait_for_function("() => window.location.hash === '#history?kind=gets'")
    expect(ui.page.locator("#view ul.history-kinds a[aria-current='page']")).to_have_text("Gets")


def test_the_budget_line_is_a_tab_stop_after_the_sidebar_s_pages(ui):
    ui.serve("**/api/budget", a_budget("known", remaining="12.4", budget="20", spent="7.6"))
    ui.open("#collection")
    expect(ui.page.locator("#sidebar .budget a.budget-line")).to_be_visible()

    ui.page.locator("#sidebar ul a:visible").last.focus()
    ui.page.keyboard.press("Tab")

    focused = ui.page.evaluate("() => document.activeElement.className + ' ' + document.activeElement.getAttribute('href')")
    assert focused == "budget-line #history?kind=gets"


def test_following_the_budget_line_on_a_phone_closes_the_drawer_it_was_in(ui):
    ui.serve("**/api/budget", a_budget("known", remaining="12.4", budget="20", spent="7.6"))
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#collection")
    ui.page.click("button.menu-button")
    expect(ui.page.locator("#sidebar")).to_have_attribute("data-open", "")

    ui.page.click("#sidebar .budget a.budget-line")

    ui.page.wait_for_function("() => window.location.hash === '#history?kind=gets'")
    expect(ui.page.locator("#sidebar")).not_to_have_attribute("data-open", "")


def test_a_budget_that_cannot_be_read_says_so_and_is_asked_again(ui):
    ui.serve("**/api/budget", [(500, {"error": "boom"}), a_budget("known", remaining="1", budget="5", spent="4")])
    ui.open("")

    assert _budget_said(ui)[0] == "Budget unknown"
    ui.page.evaluate("() => { window.location.hash = '#discover'; }")
    ui.page.wait_for_function("() => document.querySelector('#sidebar .budget-line').textContent === '$1.00 left this month'")


# -- tiers -----------------------------------------------------------------------


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
