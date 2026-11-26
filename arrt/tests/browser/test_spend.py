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
from page_ui import Ui
from payloads import a_candidate, a_run, a_run_view, a_spend, a_spend_history, an_estimate

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


def _the_budget_says(ui, said: list[str]) -> None:
    """The sidebar's budget words are exactly `said`, in the order drawn, each with its whitespace folded.

    The line is a link since audit-6 finding 10 and its note a paragraph; one
    union locator keeps them in the order they are drawn.
    """
    expect(ui.page.locator("#sidebar .budget .budget-line, #sidebar .budget .budget-note")).to_have_text(
        said, use_inner_text=True
    )


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

    _the_budget_says(ui, said)
    if budget["state"] != "known":
        assert "left this month" not in " ".join(said[1:]), "only a figure the provider or the budget gives is 'left'"


def test_the_real_server_without_a_key_says_nothing_spends(ui):
    ui.open("")

    expect(ui.page.locator("#sidebar .budget .budget-line")).to_have_text("Nothing spends", use_inner_text=True)


@pytest.mark.parametrize("state", ["known", "uncapped", "not_configured", "unavailable"])
def test_the_budget_line_is_a_link_to_the_spend_page_in_every_state(ui, state):
    """Checking spend has somewhere to go: System › Spend, a page of what was spent, not History filtered to Gets."""
    ui.serve("**/api/budget", a_budget(state, remaining="12.4" if state == "known" else None))
    ui.serve("**/api/spend", a_spend_history())
    ui.open("#collection")
    line = ui.page.locator("#sidebar .budget a.budget-line")
    expect(line).to_have_count(1)
    expect(line).to_have_attribute("href", "#spend")

    line.click()

    ui.page.wait_for_function("() => window.location.hash === '#spend'")
    expect(ui.page.locator("#view h1")).to_have_text("Spend")
    expect(ui.page.locator("#sidebar a[data-view='spend'][aria-current='page']")).to_have_text("Spend", use_inner_text=True)


def test_the_budget_line_is_a_tab_stop_after_the_sidebar_s_pages(ui):
    ui.serve("**/api/budget", a_budget("known", remaining="12.4", budget="20", spent="7.6"))
    ui.open("#collection")
    expect(ui.page.locator("#sidebar .budget a.budget-line")).to_be_visible()

    ui.page.locator("#sidebar ul a:visible").last.focus()
    ui.page.keyboard.press("Tab")

    focused = ui.page.evaluate("() => document.activeElement.className + ' ' + document.activeElement.getAttribute('href')")
    assert focused == "budget-line #spend"


def test_following_the_budget_line_on_a_phone_closes_the_drawer_it_was_in(ui):
    ui.serve("**/api/budget", a_budget("known", remaining="12.4", budget="20", spent="7.6"))
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#collection")
    ui.page.click("button.menu-button")
    expect(ui.page.locator("#sidebar")).to_have_attribute("data-open", "")

    ui.page.click("#sidebar .budget a.budget-line")

    ui.page.wait_for_function("() => window.location.hash === '#spend'")
    expect(ui.page.locator("#sidebar")).not_to_have_attribute("data-open", "")


def test_in_a_phone_s_drawer_the_budget_line_is_a_finger_s_target_and_not_a_button(browser, server_url):
    """A finger needs 44px (`accessibility-spec.md` § Touch targets), and the
    line gets them by its height alone: still the underlined words on the
    sidebar's ground, with no box, fill or border, so the sidebar gains a target
    and not a button. Measured in the drawer, where a phone sees it, with a
    note beneath, since the note is what the taller line could crowd."""
    context = browser.new_context(has_touch=True, is_mobile=True, viewport={"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.route(lambda url: not url.startswith(f"{server_url}/"), lambda route: route.abort())
        ui = Ui(page, server_url)
        ui.serve("**/api/budget", a_budget("configured", remaining="12.4", budget="20", spent="7.6", note="Nothing enforces it."))
        ui.open("#collection")
        ui.page.click("button.menu-button")
        line = ui.page.locator("#sidebar .budget a.budget-line")
        expect(line).to_be_visible()
        expect(line).to_have_text("$12.40 left this month")

        drawn = line.evaluate("""(node) => {
              const style = getComputedStyle(node);
              const note = node.parentElement.querySelector('.budget-note').getBoundingClientRect();
              return {
                height: node.getBoundingClientRect().height,
                underlined: style.textDecorationLine,
                fill: style.backgroundColor,
                border: ['Top', 'Right', 'Bottom', 'Left'].map((side) => style[`border${side}Width`]),
                overlap: node.getBoundingClientRect().bottom - note.top,
              };
            }""")
        assert drawn["height"] >= 44 - 0.5, f"the budget line is {drawn['height']}px tall on a touch screen"
        assert drawn["underlined"] == "underline"
        assert drawn["fill"] == "rgba(0, 0, 0, 0)", f"the budget line has a fill: {drawn['fill']}"
        assert drawn["border"] == ["0px"] * 4, f"the budget line has a border: {drawn['border']}"
        assert drawn["overlap"] <= 0.5, "the taller line runs into its note"
    finally:
        context.close()


def test_a_budget_that_cannot_be_read_says_so_and_is_asked_again(ui):
    ui.serve("**/api/budget", [(500, {"error": "boom"}), a_budget("known", remaining="1", budget="5", spent="4")])
    ui.open("")

    expect(ui.page.locator("#sidebar .budget .budget-line")).to_have_text("Budget unknown", use_inner_text=True)
    ui.page.evaluate("() => { window.location.hash = '#discover'; }")
    ui.page.wait_for_function("() => document.querySelector('#sidebar .budget-line').textContent === '$1.00 left this month'")


# -- a Get's cost, in the server's sentence ---------------------------------------


def _cost_row(ui):
    return ui.page.locator("#view .panel:has(h2:text-is('What it cost')) dl.facts dd")


def _a_finished_get(ui, spend, *, own="0.0134"):
    """A finished Get whose run record says `own` and whose family total is `spend`, as the server answers both."""
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True, approval_required=False, actual_cost_usd=own)
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run, works=[a_candidate()]))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", spend)
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")


@pytest.mark.parametrize(
    ("spend", "own", "said"),
    [
        pytest.param(
            a_spend(cost_usd="0.25", unknown_cost_calls=2),
            "0.0134",
            "$0.0134, at least $0.25, and 2 calls whose cost is unknown with the Gets that retried it",
            id="retries cost more and two calls are unknown",
        ),
        pytest.param(
            a_spend(cost_usd="0.0134", unknown_cost_calls=1),
            "0.0134",
            "at least $0.0134, and 1 call whose cost is unknown",
            id="the same figure, one call unknown: the sentence stands for the whole",
        ),
        pytest.param(
            a_spend(cost_usd="0", unknown_cost_calls=3),
            None,
            "at least $0.00, and 3 calls whose cost is unknown",
            id="nothing recorded of its own, three calls unknown",
        ),
        pytest.param(
            a_spend(cost_usd="0.25", unknown_cost_calls=1),
            None,
            "None recorded for this Get, at least $0.25, and 1 call whose cost is unknown with the Gets that retried it",
            id="nothing of its own, its retries cost and one call is unknown",
        ),
    ],
)
def test_a_gets_cost_is_said_in_the_servers_sentence_when_a_call_is_unknown(ui, spend, own, said):
    """No screen words a total from `cost_usd` itself; the server's `summary` says "at least"."""
    _a_finished_get(ui, spend, own=own)

    expect(_cost_row(ui)).to_have_text(said, use_inner_text=True)


def test_a_gets_cost_with_no_unknown_call_says_no_at_least(ui):
    """The paired negative, with a positive anchor: the row is there and says its figure."""
    _a_finished_get(ui, a_spend(cost_usd="0.25"))

    expect(_cost_row(ui)).to_have_text("$0.0134, $0.25 with the Gets that retried it", use_inner_text=True)
    expect(ui.view).not_to_contain_text("at least", use_inner_text=True)


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
    expect(approve.locator("xpath=following-sibling::*[1]")).to_have_text("Cost: Free", use_inner_text=True)
    expect(ui.page.locator("button:text-is('Decline it')")).to_have_count(1)
    expect(ui.view, "no threshold stops a run any more").not_to_contain_text("threshold", use_inner_text=True)


@pytest.mark.parametrize(
    "status", [RunStatus.RESOLVING_IMAGES, RunStatus.COMPLETED, RunStatus.HALTED_BY_BUDGET, RunStatus.CANCELLED]
)
def test_no_other_run_offers_approve_or_decline(ui, status):
    terminal = status is not RunStatus.RESOLVING_IMAGES
    run = a_run(status=status.value, is_terminal=terminal, approval_required=False)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run, works=[a_candidate()]))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend(cost_usd="0"))
    ui.open(f"#get/{RUN_ID}")
    # The run's own page is drawn when it says what was asked: only then does a missing act mean it was left off.
    expect(ui.view).to_contain_text("Something by Dalí", use_inner_text=True)

    expect(ui.page.locator("button:text-is('Approve the list'), button:text-is('Decline it')")).to_have_count(0)


def test_a_run_halted_at_the_cap_says_the_months_budget_is_spent(ui):
    reason = "This month's budget is spent: OpenRouter refused the request (402)."
    run = a_run(status=RunStatus.HALTED_BY_BUDGET.value, is_terminal=True, approval_required=False, end_reason=reason)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run, works=[a_candidate()]))
    ui.open(f"#get/{RUN_ID}")

    line = ui.page.locator("#view .run-end-reason")
    line.wait_for()
    expect(line).to_have_text(f"Why it stopped: {reason}", use_inner_text=True)
    expect(ui.view).not_to_contain_text("credit limit", use_inner_text=True)
