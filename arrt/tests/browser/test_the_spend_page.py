"""System › Spend, in a real browser.

What was spent, month by month, where it went, which Gets spent it, and the
calls whose cost nobody was told, each said in the server's own
sentence. The page lists them apart from the rest, offers no limit to set, and
works by keyboard alone and at phone width.

The answers served are built through `payloads.py`, which words every figure by
the service's own function, so a screen cannot be shown a sentence no server
would say. At least one month served here has a non-zero unknown count, so the
default (none) is not the only value any screen test ever reads.
"""

import pytest
from payloads import a_category_spend, a_get_spend, a_spend_history, a_spend_month, an_unknown_call

from arrt.persistence.discovery_records import SpendCategory

expect = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
).expect

GET_ID = "get-under-test"
OTHER_ID = "get-of-chosen-works"


def a_month_with_two_unknown_calls():
    """November: $0.0213 known, two calls that never said what they cost, one of them in a Get."""
    return a_spend_month(
        2026,
        11,
        categories=[
            a_category_spend("discovery_tokens", calls=3, cost_usd="0.0213", unknown_cost_calls=1),
            a_category_spend("ask_tokens", calls=2, cost_usd="0", unknown_cost_calls=1),
        ],
        gets=[a_get_spend(GET_ID, intent="Something by Dalí", calls=3, cost_usd="0.0213", unknown_cost_calls=1)],
        unknown_calls=[
            an_unknown_call("u-ask", category="ask_tokens", occurred_at="2026-11-07T09:00:00+00:00", model_id=None),
            an_unknown_call("u-get", category="discovery_tokens", occurred_at="2026-11-05T10:01:00+00:00", run_id=GET_ID),
        ],
    )


@pytest.fixture
def two_months(ui):
    """November with its unknown calls, and an October whose every cost is known."""
    october = a_spend_month(
        2026,
        10,
        categories=[a_category_spend("mat_color_vision", calls=4, cost_usd="0.08")],
        gets=[a_get_spend(OTHER_ID, kind="get", intent=None, started_at="2026-10-02T08:00:00+00:00", calls=4, cost_usd="0.08")],
    )
    ui.serve("**/api/spend", a_spend_history(a_month_with_two_unknown_calls(), october, older_months=1))
    return ui


def month(ui, key):
    return ui.page.locator(f"#view section.spend-month[data-month='{key}']")


# -- where it is ---------------------------------------------------------------------


def test_spend_is_listed_under_system_beside_status(ui, two_months):
    ui.open("#spend")
    expect(ui.page.locator("#view h1")).to_have_text("Spend")

    system = ui.page.locator("nav.sidebar li.section[data-section='system']")
    expect(system).to_have_attribute("data-open", "")
    expect(system.locator("ul.pages a .label")).to_have_text(["Status", "Spend"], use_inner_text=True)
    expect(ui.page.locator("nav.sidebar a[data-view='spend'][aria-current='page']")).to_have_count(1)


def test_status_links_to_spend(ui, a_health_reading):
    ui.serve("**/api/health", a_health_reading())
    ui.serve("**/api/spend", a_spend_history())
    ui.open("#health")
    link = ui.page.locator("#view .spend-reading a")
    expect(link).to_have_text("System › Spend", use_inner_text=True)

    link.click()

    ui.page.wait_for_function("() => window.location.hash === '#spend'")
    expect(ui.page.locator("#view h1")).to_have_text("Spend")


# -- what it says --------------------------------------------------------------------


def test_the_month_says_at_least_and_how_many_calls_are_unknown(two_months):
    ui = two_months
    ui.open("#spend")

    sentence = "at least $0.0213, and 2 calls whose cost is unknown"
    expect(month(ui, "2026-11").locator(".spend-total")).to_have_text(sentence, use_inner_text=True)
    expect(ui.page.locator("#view .page-facts")).to_have_text(f"November 2026 so far: {sentence}.", use_inner_text=True)


def test_a_month_whose_every_cost_is_known_says_no_at_least(two_months):
    ui = two_months
    ui.open("#spend")
    # The page has painted both months before anything is said to be absent from one.
    expect(month(ui, "2026-10").locator(".spend-total")).to_have_text("$0.08", use_inner_text=True)

    expect(month(ui, "2026-10")).not_to_contain_text("at least", use_inner_text=True)
    expect(month(ui, "2026-10").locator("section.spend-unknown")).to_have_count(0)


def test_the_unknown_calls_are_listed_apart_with_what_when_and_which_get(two_months):
    ui = two_months
    ui.open("#spend")

    unknown = month(ui, "2026-11").locator("section.spend-unknown")
    expect(unknown.locator("h3")).to_have_text("Calls whose cost is unknown", use_inner_text=True)
    expect(unknown).to_contain_text("the provider may have billed them", use_inner_text=True)
    expect(unknown.locator("thead th")).to_have_text(["When", "What", "Model", "Get"])
    # Newest first, each with what it was, the model if one is known, and its Get if it had one.
    expect(unknown.locator("tbody tr")).to_have_count(2)
    expect(unknown.locator("tbody tr").nth(0).locator("td").nth(1)).to_have_text("Ask's replies", use_inner_text=True)
    expect(unknown.locator("tbody tr").nth(0).locator("td").nth(2)).to_have_text("—", use_inner_text=True)
    expect(unknown.locator("tbody tr").nth(0).locator("td").nth(3)).to_have_text("Not part of a Get", use_inner_text=True)
    expect(unknown.locator("tbody tr").nth(1).locator("td").nth(1)).to_have_text("Proposing works", use_inner_text=True)
    expect(unknown.locator("tbody tr").nth(1).locator("td").nth(2)).to_have_text("the-model", use_inner_text=True)
    expect(unknown.locator("tbody tr").nth(1).locator("td").nth(3).locator("a")).to_have_text(
        "Something by Dalí", use_inner_text=True
    )
    expect(unknown.locator("tbody tr").nth(1).locator("time")).to_have_attribute("datetime", "2026-11-05T10:01:00+00:00")


def test_what_it_was_spent_on_and_which_gets_spent_it(two_months):
    ui = two_months
    ui.open("#spend")

    categories = month(ui, "2026-11").locator("section.spend-categories")
    expect(categories.locator("tbody td")).to_have_text(
        [
            "Proposing works",
            "3",
            "at least $0.0213, and 1 call whose cost is unknown",
            "Ask's replies",
            "2",
            "at least $0.00, and 1 call whose cost is unknown",
        ],
        use_inner_text=True,
    )
    spent_by = month(ui, "2026-11").locator("section.spend-gets")
    expect(spent_by.locator("thead th")).to_have_text(["Get", "Started", "Calls", "Cost"])
    expect(spent_by.locator("tbody tr")).to_have_count(1)
    expect(spent_by.locator("tbody td").nth(0)).to_have_text("Something by Dalí", use_inner_text=True)
    expect(spent_by.locator("tbody td").nth(2)).to_have_text("3", use_inner_text=True)
    expect(spent_by.locator("tbody td").nth(3)).to_have_text(
        "at least $0.0213, and 1 call whose cost is unknown", use_inner_text=True
    )


def test_a_get_with_no_words_of_its_own_is_named_by_its_kind(two_months):
    ui = two_months
    ui.open("#spend")

    expect(month(ui, "2026-10").locator("section.spend-gets tbody td").nth(0)).to_have_text(
        "Get of chosen works", use_inner_text=True
    )


def test_months_are_listed_newest_first_and_the_older_ones_are_counted(two_months):
    ui = two_months
    ui.open("#spend")

    expect(ui.page.locator("#view section.spend-month h2")).to_have_text(["November 2026", "October 2026"], use_inner_text=True)
    expect(ui.page.locator("#view .spend-older")).to_have_text(
        "1 earlier month that spent something is not listed.", use_inner_text=True
    )


def test_older_months_are_counted_in_the_plural(ui):
    ui.serve("**/api/spend", a_spend_history(older_months=3))
    ui.open("#spend")

    expect(ui.page.locator("#view .spend-older")).to_have_text(
        "3 earlier months that spent something are not listed.", use_inner_text=True
    )


def test_a_month_with_nothing_spent_says_so_beside_its_total(ui):
    ui.serve("**/api/spend", a_spend_history())
    ui.open("#spend")

    current = ui.page.locator("#view section.spend-month").first
    expect(current.locator(".spend-total")).to_have_text("$0.00", use_inner_text=True)
    expect(current).to_contain_text("Nothing has been spent this month.", use_inner_text=True)
    expect(current.locator("table")).to_have_count(0)


@pytest.mark.parametrize("category", [str(each) for each in SpendCategory])
def test_every_kind_of_spending_has_words_and_none_is_a_raw_token(ui, category):
    """Parametrised over the enum, so a seventh kind arrives here as a failure and not on a screen as `ask_tokens`."""
    ui.serve("**/api/spend", a_spend_history(a_spend_month(categories=[a_category_spend(category, cost_usd="0.01")])))
    ui.open("#spend")

    cell = ui.page.locator("#view section.spend-categories tbody td").first
    expect(cell).not_to_have_text(category, use_inner_text=True)
    expect(cell).not_to_have_text("", use_inner_text=True)
    expect(cell).not_to_contain_text("_", use_inner_text=True)


def test_a_kind_the_client_has_no_word_for_is_shown_as_the_server_spells_it(ui):
    """Never dropped: a row left off is money left off the page."""
    ui.serve("**/api/spend", a_spend_history(a_spend_month(categories=[a_category_spend("invented_kind", cost_usd="0.01")])))
    ui.open("#spend")

    expect(ui.page.locator("#view section.spend-categories tbody td").first).to_have_text("invented_kind", use_inner_text=True)


# -- nothing is enforced, and nothing implies it is ------------------------------------


def test_the_page_offers_no_limit_to_set_and_says_none_is_set_here(two_months):
    ui = two_months
    ui.open("#spend")
    expect(month(ui, "2026-11").locator(".spend-total")).to_be_visible()

    expect(ui.page.locator("#view input, #view select, #view textarea, #view button")).to_have_count(0)
    expect(ui.view).to_contain_text("Arrt sets no limit and enforces none", use_inner_text=True)
    expect(ui.view).not_to_contain_text("budget", use_inner_text=True)
    expect(ui.view).not_to_contain_text("cap", use_inner_text=True)


# -- by keyboard, and on a phone --------------------------------------------------------


def test_a_get_is_opened_from_the_keyboard_alone(two_months):
    ui = two_months
    ui.open("#spend")
    link = month(ui, "2026-11").locator("section.spend-gets a.row-link")
    expect(link).to_have_text("Something by Dalí", use_inner_text=True)

    link.focus()
    ui.page.keyboard.press("Enter")

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#get/{GET_ID}')")


def test_the_tables_are_stacked_cards_on_a_phone_with_each_value_under_its_heading(two_months):
    ui = two_months
    ui.page.set_viewport_size({"width": 390, "height": 844})
    ui.open("#spend")
    expect(month(ui, "2026-11").locator(".spend-total")).to_be_visible()

    first_row = month(ui, "2026-11").locator("section.spend-categories tbody tr").first
    expect(first_row).to_have_css("display", "block")
    ui.page.wait_for_function("""() => {
          const cell = document.querySelector("section.spend-month section.spend-categories tbody td:nth-child(3)");
          return cell !== null && getComputedStyle(cell, "::before").content === '"Cost"';
        }""")
    # The page never scrolls sideways.
    ui.page.wait_for_function("() => document.documentElement.scrollWidth <= window.innerWidth")


# -- when it cannot be read ----------------------------------------------------------


def test_a_ledger_that_cannot_be_read_says_why_and_guesses_no_total(ui):
    ui.serve("**/api/spend", (500, {"error": "The spend ledger could not be read."}))
    ui.open("#spend")

    expect(ui.page.locator("#error")).to_have_text("The spend ledger could not be read.", use_inner_text=True)
    expect(ui.page.locator("#view .spend-total")).to_have_count(0)
