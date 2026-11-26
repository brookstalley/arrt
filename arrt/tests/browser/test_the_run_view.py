"""The run view: its poll loop, its supersession, and the words it puts on a card.

This is the most stateful screen the product had when this harness was built, and
every behaviour below is one a test reading JSON cannot see. Two of them are
about what the page does *not* do — repaint, and poll twice — which is why each
is paired with the assertion that would fail if it stopped doing the thing at
all.
"""

import re
from pathlib import Path

import pytest
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view, a_spend, an_estimate, an_instance

from arrt.http.models import RunListOut
from arrt.persistence.discovery_records import ResolutionStatus, RunStatus, UnresolvedReason, WorkProvenance

# At import time, not in a fixture. A marker deselection still *collects* this
# module, so the default run — which does not install the browser group — has to
# skip here rather than fail on the missing plugin.
pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from playwright.sync_api import expect

RUN_ID = "run-under-test"

#: The client's poll interval, read from `screens/run.js`, which owns it: the
#: windows below are expressed in whole polls, so they follow a change to it.
POLL_MS = int(
    re.search(
        r"^export const RUN_POLL_MS = (\d+);$",
        (Path(__file__).resolve().parents[2] / "src/arrt/http/static/screens/run.js").read_text(encoding="utf-8"),
        re.MULTILINE,
    ).group(1)
)

#: Counts the timers the page sets at the run poll's interval, over whatever
#: `setTimeout` is installed when the document starts (the clock's, in the one
#: test that installs it).
COUNT_POLL_TIMERS = f"""
window.__pollTimers = 0;
const scheduled = window.setTimeout;
window.setTimeout = function (callback, ms, ...rest) {{
  if (ms === {POLL_MS}) window.__pollTimers += 1;
  return scheduled.call(this, callback, ms, ...rest);
}};
"""


def _text_is(text: str, *, trimmed: bool = False):
    """A pattern for `has_text=` that is the element's whole text content, as `==` was.

    `has_text` sees the raw text content, so a heading whose words are `text`
    is found only by a pattern that anchors both ends; `trimmed` allows the
    whitespace a `.strip()` dropped.
    """
    flank = r"\s*" if trimmed else ""
    return re.compile(f"^{flank}{re.escape(text)}{flank}$")


def _headings(ui):
    """Every section heading on a Get's page."""
    return ui.page.locator("#view section h3")


def _has_heading(ui, text: str):
    """The headings whose words are `text`, a membership the list read answered with `in`."""
    return _headings(ui).filter(has_text=_text_is(text, trimmed=True)).first


@pytest.fixture
def at_the_gate(ui):
    """A run stopped at the approval gate, with the estimate the gate fetches.

    The gate is the state worth holding the harness at: it is the one screen with
    a decision on it, it is the only state that fetches a second endpoint mid-
    paint, and it is where a curator actually stands still long enough for a
    repaint to cost them something.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    # The page reads the works' cards for their pictures, as it does for a real run.
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))
    ui.serve("**/api/estimate?*", an_estimate())
    return ui


# -- a poll that changes nothing --------------------------------------------


def test_a_poll_that_changes_nothing_leaves_the_focus_alone(at_the_gate):
    """The defect this whole harness was moved up the order for.

    `render` replaces the entire view, which destroys whatever the keyboard user
    was standing on. Tabbing to "Approve the list" and pausing to read lost the
    focus two seconds later, every time, on the one screen whose whole job is to
    be decided on.
    """
    ui = at_the_gate
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    ui.page.focus("button:has-text('Approve the list')")
    # Half a poll of slack on top of the two being waited for: the second tick
    # lands at the very edge of a tighter window, and on a loaded CI runner an
    # edge is a flake.
    # What is claimed is that focus survives two polls, which only time passing shows.
    ui.page.wait_for_timeout(POLL_MS * 2 + POLL_MS // 2)  # sleep: focus must survive two polls

    # Two polls have been and gone. The button is still under the keyboard.
    assert ui.focused() == "Approve the list"
    # Not decoration: if no poll actually happened, focus surviving says nothing
    # at all, and this test would pass against a client that stopped polling.
    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) >= 3


def test_a_poll_that_changes_something_does_repaint(ui):
    """The paired negative: suppression must not become never repainting.

    A run whose work list fills in underneath a settled status is exactly the
    change worth repainting for, and a signature check written too broadly would
    leave the page frozen while the run moved on.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        [
            a_run_view(works=[a_candidate(work_id="w1", title="First")]),
            a_run_view(
                works=[
                    a_candidate(work_id="w1", title="First"),
                    a_candidate(work_id="w2", title="Second arrival"),
                ]
            ),
        ],
    )
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("td:has-text('First')")

    # Not yet: the first answer is on screen and the second has not been asked
    # for, anchored on the first's row above.
    expect(ui.view).not_to_contain_text("Second arrival", use_inner_text=True)
    ui.page.wait_for_selector("td:has-text('Second arrival')", timeout=POLL_MS * 3)


# -- two paints racing ------------------------------------------------------


def test_two_concurrent_paints_leave_only_one_poll_chain(at_the_gate):
    """Pressing a button while a poll is mid-request must not double the rate.

    Each paint schedules the next look at the run, so two chains do not merely
    duplicate one request — they double the request rate on every tick
    thereafter, for as long as the page stays open.

    What holds the rate down is the check `scheduleRunPoll` makes when the timer
    *fires*, not the one the paint makes when its answer lands: a superseded
    paint still schedules, and its timer then finds the world moved on and does
    nothing. The paint-time check earns its place elsewhere, and the test below
    is what pins it.
    """
    ui = at_the_gate
    # The window is the page's clock, not the runner's: installed before the
    # page loads, every timer the client sets is the clock's, and the test moves
    # it one poll at a time. Each paint of the run sets one timer for its next
    # look (`schedulePollUnlessDone`), so the timers set at `POLL_MS` are counted
    # by a wrapper put over the clock's `setTimeout` (added after the clock, so
    # it wraps the clock's and not the other way round).
    ui.page.clock.install()
    ui.page.add_init_script(COUNT_POLL_TIMERS)
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")
    ui.page.wait_for_function("() => window.__pollTimers === 1")

    # A second paint started while the first is still the one on screen — the
    # same collision as pressing Approve during a poll, without the timing
    # dependence of actually racing a click against one. Both land, and each
    # sets its timer: the superseded one's is the one that must do nothing.
    ui.page.evaluate("() => { refresh(); refresh(); }")
    ui.page.wait_for_function("() => window.__pollTimers === 3")

    per_tick = []
    for tick in range(1, 4):
        before = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))  # one-shot: the count this tick adds to
        ui.page.clock.run_for(POLL_MS)
        # The tick's paint has landed when it has set the next timer, and every
        # request the tick's timers sent went out before that answer came back.
        ui.page.wait_for_function("(n) => window.__pollTimers >= n", arg=3 + tick)
        per_tick.append(len(ui.requests_matching(f"/api/runs/{RUN_ID}")) - before)

    # One chain asks once a tick; a second would ask twice, and a stopped one
    # never, so the wait above would have timed out.
    assert per_tick == [1, 1, 1], f"requests per poll {per_tick}: a second chain is running"


def test_a_paint_superseded_in_flight_never_reaches_the_page(ui):
    """A curator who moves on must not have the page they left painted over them.

    The paint claims a generation before its request goes out and checks it again
    when the answer lands. Without that check a run's answer arriving after the
    curator navigated away paints that run's works into whatever replaced it —
    the id in the fragment saying one thing and the page showing another.

    Driven by superseding the paint directly rather than by racing a real click
    against a real response, because the defect is a *lost race* and a test that
    had to win one to see it would report a green that meant only that the
    machine was fast that time.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value)))
    ui.serve(
        "**/api/runs/left-behind",
        a_run_view(run=a_run(run_id="left-behind", intent="A run left behind", status=RunStatus.RESOLVING_WORKS.value)),
    )

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    # A paint begins, and something supersedes it before its answer lands — which
    # is what navigating away does, expressed without the timing.
    ui.page.evaluate("() => { const painting = viewRun('left-behind'); state.poll += 1; return painting; }")

    expect(ui.view).to_contain_text("Something by Dalí", use_inner_text=True)
    expect(ui.view).not_to_contain_text("A run left behind", use_inner_text=True)


def test_leaving_the_run_view_stops_its_polling(at_the_gate):
    """A run page left behind must not keep repainting under what replaced it."""
    ui = at_the_gate
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    # Health left the navigation in the reshape, so the way to it is the
    # masthead indicator that replaced the tab. What this test is about is
    # unchanged: navigating away from a run must stop its watch.
    ui.page.click("#status")
    ui.page.wait_for_selector("h1:has-text('Status')")

    settled = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    ui.page.wait_for_timeout(POLL_MS * 2 + 500)  # sleep: proves a left page makes no further request for two polls' time

    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) == settled


# -- the costs panel --------------------------------------------------------


@pytest.fixture
def a_finished_run(ui):
    """A run that has stopped, which is the only state that fetches the rollup."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card()]))
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(
                status=RunStatus.COMPLETED.value,
                is_terminal=True,
                completed_at="2026-08-05T10:05:00+00:00",
                actual_cost_usd="0.0134",
            ),
            works=[a_candidate()],
        ),
    )
    return ui


def test_a_family_total_that_cannot_be_read_says_so(a_finished_run):
    """The one figure with no second home must not go missing quietly.

    `facts` drops a null pair outright, so a failed rollup fetch used to remove
    the row with nothing in its place — leaving a panel whose largest number is
    what this run alone spent, which is exactly the reading the family total was
    added to prevent.
    """
    ui = a_finished_run
    ui.page.route(f"**/api/runs/{RUN_ID}/spend", lambda route: route.fulfill(status=503, body="{}"))

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    expect(ui.view).to_contain_text("What it cost with the Gets that retried it could not be read", use_inner_text=True)
    # The panel survives the failure: the Get's own cost is read off the run
    # record and is still true, so losing the rollup must not cost it.
    # *(Since 2026-10-14, #359: one Cost row where "Spent by this Get alone"
    # was one of four.)*
    cost = ui.page.locator("#view .panel:has(h2:text-is('What it cost')) dl.facts")
    expect(cost.locator("dt")).to_have_text(["Cost"], use_inner_text=True)
    # The run's own figure in the server's words (`RunOut.summary`): $0.0134 as it is, not "$0.01".
    expect(cost.locator("dd")).to_have_text("$0.0134", use_inner_text=True)


def test_a_run_that_has_stopped_is_not_polled_again(a_finished_run):
    """The other end of the watch, and the end no test reached until a sweep said so.

    `test_leaving_the_run_view_stops_its_polling` covers the curator walking
    away; this covers them staying. A finished run has nothing left to report, so
    a page that went on asking would request it every two seconds for as long as
    the tab stayed open — the same unbounded retry a stale bookmark used to
    cause, arrived at from the other direction and with nothing on screen
    looking wrong.

    Deliberately paired with the two tests above rather than written as a
    variant of them: "stopped" is the run view's own reading, passed to the
    shared poll chain, so a test of the chain alone says nothing about it.
    """
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    settled = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    # Not decoration: a page that never asked at all would satisfy the equality
    # below and prove nothing about when it stops.
    assert settled >= 1

    ui.page.wait_for_timeout(POLL_MS * 2 + 500)  # sleep: proves a finished run is not asked about again for two polls' time

    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) == settled


def test_a_family_total_that_reads_fine_says_nothing(a_finished_run):
    """The paired negative — the notice appears on failure and not otherwise —
    and a family total that differs from the Get's own is said beside it.

    *(Since 2026-10-14, #359: in the Cost row, "$0.25 with the Gets that
    retried it", where "Spent including every Get again" was a row of its own.)*
    """
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend(cost_usd="0.25"))

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    expect(ui.view).to_contain_text("$0.0134, $0.25 with the Gets that retried it", use_inner_text=True)
    expect(ui.view).not_to_contain_text("could not be read", use_inner_text=True)


@pytest.fixture
def a_finished_run_with_nothing_of_its_own(ui):
    """A Get that finished with no cost recorded of its own, as a cancelled one can."""
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(
                status=RunStatus.CANCELLED.value,
                is_terminal=True,
                completed_at="2026-08-05T10:05:00+00:00",
                actual_cost_usd=None,
            ),
            works=[a_candidate()],
        ),
    )
    return ui


def _cost(ui):
    return ui.page.locator("#view .panel:has(h2:text-is('What it cost')) dl.facts dd")


def test_a_finished_get_with_nothing_recorded_says_so(a_finished_run_with_nothing_of_its_own):
    ui = a_finished_run_with_nothing_of_its_own
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend(cost_usd="0"))
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    expect(_cost(ui)).to_have_text("None recorded", use_inner_text=True)


def test_a_get_with_nothing_of_its_own_keeps_what_its_retries_cost(a_finished_run_with_nothing_of_its_own):
    """The family total is the one figure with no second home; an empty own row must not take it away."""
    ui = a_finished_run_with_nothing_of_its_own
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend(cost_usd="0.25"))
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    expect(_cost(ui)).to_have_text("None recorded for this Get, $0.25 with the Gets that retried it", use_inner_text=True)


def test_a_family_total_equal_to_the_gets_own_is_not_said_twice(a_finished_run):
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend(cost_usd="0.0134"))

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    cost = ui.page.locator("#view .panel:has(h2:text-is('What it cost')) dl.facts")
    expect(cost.locator("dt")).to_have_text(["Cost"], use_inner_text=True)
    expect(ui.view).not_to_contain_text("retried", use_inner_text=True)


# -- which kind of nothing --------------------------------------------------


@pytest.mark.parametrize("reason", list(UnresolvedReason))
def test_an_unresolved_work_says_which_kind_of_nothing(ui, reason):
    """Every reason reaches the page as words, and never as its raw token.

    Parametrised over the enum rather than over a list written here: a sixth
    reason added to `UnresolvedReason` arrives as a failure in this test, which
    is the only thing that stops it reaching a curator's card as
    `identity_refused`-shaped noise.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=a_run(status=RunStatus.COMPLETED.value, is_terminal=True, completed_at="2026-08-05T10:05:00+00:00"),
            works=[
                a_candidate(
                    resolution_status=ResolutionStatus.UNRESOLVED.value,
                    unresolved_reason=reason.value,
                )
            ],
        ),
    )
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("table")

    # Both halves of the badge, read off the one element: the short phrase it
    # shows, and the sentence behind it saying what that phrase means. A badge
    # with an empty title looks correct in a screenshot and tells a curator
    # nothing about which kind of nothing they are looking at.
    badge = ui.page.locator("#view span.badge[title]").filter(has=ui.page.locator("span.glyph", has_text="▲"))
    expect(badge).to_have_count(1)
    expect(ui.view, f"the raw token {reason.value!r} reached the page").not_to_contain_text(reason.value, use_inner_text=True)
    expect(badge, f"{reason.value} reached the page with no words").to_have_text(re.compile(r"\S"), use_inner_text=True)

    # A sentence: it has words and its last is full-stopped.
    expect(badge, f"{reason.value} reached the page with no sentence behind it, or not one").to_have_attribute(
        "title", re.compile(r"\.$")
    )

    # The *resolution* badge beside it, which is a different element and was the
    # untested third of the reword. `RESOLUTION_WORDS` was changed from
    # present-tense claims about the work to statements about what the run found,
    # and only the `resolved` entry got a guard — the assertions above all
    # concern `unresolved_reason`, and they locate `span.badge[title]`, which
    # `resolutionBadge` does not set. So `"no image"` survived every suite.
    #
    # Both halves, because only the pair says the reword happened: the new
    # wording present proves it renders, and the old wording absent proves it is
    # gone rather than sitting beside it.
    expect(ui.view).to_contain_text("the Get found none", use_inner_text=True)
    expect(
        ui.view,
        "a present-tense claim about the work is what the reword removed — `resolution_status` "
        "records what the run found, and only a resolution attempt recomputes it",
    ).not_to_contain_text("no image", use_inner_text=True)


# -- a watch that cannot recover --------------------------------------------


#: The client gives up after this many consecutive failures. Read from the module
#: under test would be better; it is a `const` in a script, so it is restated
#: here and `test_the_client_and_this_test_agree_on_the_limit` holds the pair
#: together rather than leaving two numbers to drift.
MAX_FAILURES = 5

#: A server that keeps failing in a way that could pass: the case the failure
#: limit exists for, now that a refusal ends the watch at once.
DOWN = (502, {"error": "The server answered 502."})


def test_the_client_and_this_test_agree_on_the_limit(ui):
    """Two numbers, one meaning. Asserted rather than assumed.

    If the client's limit rises and this one does not, the terminate test below
    waits too short a window and reports a stopped poll that is merely slow —
    green for the wrong reason, which is worse than red.
    """
    ui.open("")

    assert ui.page.evaluate("() => RUN_POLL_MAX_FAILURES") == MAX_FAILURES


def test_a_run_that_will_never_answer_stops_being_watched(ui):
    """The loop proved to terminate, rather than read to.

    A server failing over and over (a 502 that never passes) once had the catch
    re-arm and the tab request that run every two seconds for as long as it
    stayed open — bounded only by navigation, with nothing on screen saying the
    watch was still retrying. The limit ends it.

    Asserted on the request count across a window several polls longer than the
    limit, because that is the only thing that distinguishes a loop that stopped
    from one that is between ticks.

    *(This test held a 400 until 2026-10-14. A 400 is the service saying the
    run does not exist, which now ends the watch at its first answer with the
    not-found page (#361) — pinned by the test below — so the limit is held
    here by the failure it was always for: one that might pass.)*
    """
    ui.serve(f"**/api/runs/{RUN_ID}", DOWN)

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")

    # Long enough for several more polls than the limit allows, so a loop that
    # merely slowed down would still be caught.
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 3))  # sleep: proves the watch stopped, as no more requests come
    attempts = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))

    assert attempts == MAX_FAILURES, f"{attempts} requests for a run that will never answer — the watch did not stop"


def test_a_run_that_is_gone_is_a_page_saying_so_and_no_watch(ui):
    """A bookmarked Get whose run is gone: one request, one page, no banner.

    **The answer served is the server's own.** A bookmarked `#get/<id>` outlives its run,
    and the server says so with a 404 and its own sentence; the stub is
    what the real route answers for an id it does not hold, asked here, never a status and
    a sentence written in this file, which could be one no server sends.
    """
    answer = ui.page.request.get(f"{ui.base_url}/api/runs/{RUN_ID}")
    assert answer.status == 404, "the server's answer for a run it does not hold is the premise of this test"
    assert answer.json()["error"], "and it says why"
    ui.serve(f"**/api/runs/{RUN_ID}", (answer.status, answer.json()))

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#view .not-found")
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 1))  # sleep: proves a gone run is asked for once and not again

    expect(ui.page.locator("#view h1")).to_have_text("That Get is not here", use_inner_text=True)
    # Under the heading, the server's own sentence for why, as text: the
    # router's general line guessed the Get "was most likely removed".
    expect(ui.page.locator("#view .not-found h1 + p")).to_have_text(answer.json()["error"], use_inner_text=True)
    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) == 1
    expect(ui.page.locator("#error")).to_be_hidden()


def test_a_watch_that_gave_up_says_so_rather_than_only_what_failed(ui):
    """ "The server answered 502" leaves a live page indistinguishable from a dead one.

    The curator needs two facts and the message used to carry one: what went
    wrong, and whether anything is still trying. Only the second tells them
    whether to keep looking at the screen.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", DOWN)

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")

    # The message changes as the watch gives up: the fifth failure is what
    # says so, which the wait is for.
    message = ui.page.locator("#error")
    expect(message).to_contain_text("Gave up watching this Get", use_inner_text=True)
    expect(message, "saying it stopped without saying how to resume leaves the curator stuck").to_contain_text(
        "reload", use_inner_text=True
    )
    expect(message, "the original fault must survive; it is the diagnosis").to_contain_text(
        "The server answered 502.", use_inner_text=True
    )


def test_one_blip_does_not_end_the_watch(ui):
    """The behaviour the unconditional re-arm was right about, kept.

    A curator watching a live run through a single 502 must not be left on a
    stale page. The failure count exists to end a watch that *cannot* recover,
    and a fix that ended this one too would trade a rare annoyance for a common
    one.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        [
            (502, {"error": "The server answered 502."}),
            a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value)),
        ],
    )

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")

    # The run's own content arriving is the recovery: it can only be painted by
    # a poll that the blip did not stop.
    ui.page.wait_for_selector("#view p.note")
    expect(ui.view).to_contain_text("Something by Dalí", use_inner_text=True)
    expect(ui.page.locator("#error"), "a recovered watch must clear the message, not leave it accusing").to_be_hidden()


def test_a_success_clears_the_failure_count(ui):
    """Consecutive, not cumulative — asserted on the count itself.

    The behavioural version below is the one that matters, but it takes a window
    of several polls to become decisive and a shorter one leaves this exact
    mutation alive: a sweep that deleted the reset survived, because failures
    separated by successes had not yet added up to the limit inside the window
    being watched. This reads the count directly, so nothing rests on how long
    the test waited.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    good = a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value))
    bad = (502, {"error": "The server answered 502."})
    ui.serve(f"**/api/runs/{RUN_ID}", [bad, bad, good])

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    assert ui.page.evaluate("() => state.watch.failures") == 0, (
        "two failures then a success left the count standing — counted that way, a flaky "
        "connection exhausts the budget over a long session and stops a watch that is working"
    )


def test_failures_with_a_success_between_them_never_end_the_watch(ui):
    """The same rule as behaviour: a watch that keeps recovering is never ended.

    A flaky connection that fails four times, recovers, and fails four more must
    not be stopped — counted cumulatively it would be, on the sixth request.

    **The window is sized so that the two rules disagree inside it**, which is the
    part a shorter version got wrong: four-failure bursts separated by a success
    exhaust a cumulative budget at request six, so anything past six proves the
    count is consecutive rather than proving only that the test was impatient.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    good = a_run_view(run=a_run(status=RunStatus.RESOLVING_WORKS.value))
    bad = (502, {"error": "The server answered 502."})
    ui.serve(f"**/api/runs/{RUN_ID}", [bad, bad, bad, bad, good, bad, bad, bad, bad, good])

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#view p.note")

    # The seventh request is the claim: one the watch would never make were it
    # ended at the sixth. Waited for as the request is made, and bounded by the
    # page's own default wait.
    def the_seventh(_request) -> bool:
        return len(ui.requests_matching(f"/api/runs/{RUN_ID}")) > 6

    with ui.page.expect_event("request", the_seventh):
        pass


# -- the discovery listing's own truncation ---------------------------------


def _a_run_list(count: int, total: int) -> dict:
    """A `/api/runs` payload as the capped service now produces one."""
    return RunListOut(
        runs=[a_run(run_id=f"r{index}", intent=f"request {index}") for index in range(count)],
        count=count,
        total=total,
        truncated=total > count,
        awaiting_works=0,
        awaiting={},
    ).model_dump(mode="json")


def test_a_truncated_search_list_says_how_much_history_it_is_not_showing(ui):
    """The signal the server gained and the client dropped for one commit.

    Capping `list_runs` bounded a payload that had grown with every search ever
    made. It also made "Searches (50)" over a history of four hundred a silently
    short list — indistinguishable from a complete one, which is how a curator
    concludes their older searches are gone. `total` and `truncated` were on the
    wire and nothing here read them.
    """
    ui.serve("**/api/runs*", _a_run_list(count=50, total=407))

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('In flight')")

    expect(ui.view).to_contain_text("50 most recent of 407", use_inner_text=True)
    expect(ui.view, "a note implying paging sends a curator to an affordance that does not exist").to_contain_text(
        "does not page", use_inner_text=True
    )


def test_a_complete_search_list_says_nothing_about_truncation(ui):
    """Saying nothing is the honest answer when nothing was left behind."""
    ui.serve("**/api/runs*", _a_run_list(count=4, total=4))

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('In flight')")

    expect(ui.view).to_contain_text("In flight (4)", use_inner_text=True)
    expect(ui.view, "a complete list must not be dressed as a partial one").not_to_contain_text("of 4", use_inner_text=True)
    expect(ui.view).not_to_contain_text("does not page", use_inner_text=True)


def test_the_run_table_does_not_head_a_column_with_the_works_own_provenance(ui):
    """ "Where it came from" meant how a row entered the run; it reads as which museum holds it.

    Removed rather than renamed. The offered/asked-for distinction is real, and
    this table was its fourth statement — after the tally's separate counts, the
    run sentence, and the line directly above these rows. What a per-row badge
    added was which *particular* work was offered, on a screen where nothing is
    decided per work.

    Asserted on both halves: the misleading heading is gone, and the counts that
    carry the distinction are still there. Dropping the column and the counts
    together would have removed the fact rather than the fourth copy of it.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    offered = a_candidate(
        work_id="gift",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=2,
    )
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate(), offered]))
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card(), a_card(work=offered)]))

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("table")

    why = (
        "the offered/asked-for distinction must survive its per-row copy being removed — "
        "it is what tells a curator the list is longer than the one they authorised"
    )
    expect(_has_heading(ui, "Asked for (1)"), why).to_be_attached()
    expect(_has_heading(ui, "Also offered by Art Institute of Chicago (1)"), why).to_be_attached()
    expect(ui.view).not_to_contain_text("Where it came from", use_inner_text=True)


def test_the_review_card_still_says_which_works_were_offered(ui):
    """The distinction stays where the deciding happens.

    A curator judging a card may reasonably hold an offered work to a different
    standard: they did not ask for it. That is a per-work fact on the one surface
    where per-work decisions are made, which is exactly what the run table is not.
    """
    ui.serve("**/api/estimate?*", an_estimate())
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(works=[a_candidate()]))
    ui.serve(
        f"**/api/runs/{RUN_ID}/candidates*",
        a_candidate_page([a_card(work=a_candidate(provenance="offered"))]),
    )

    ui.open(f"#review/{RUN_ID}")
    ui.page.wait_for_selector(".card")

    expect(ui.view).to_contain_text("offered", use_inner_text=True)


def test_the_run_sentence_agrees_with_itself_at_a_count_of_one(ui):
    """One work, and every word in the sentence that has to agree with it.

    **The verb is asserted as hard as the noun**, because a fix that reaches for
    a plural noun and stops is the one this defect already survived: this file's
    sibling test above pinned "1 more work" correctly while five sentences in the
    same function said "1 works", and two more got the noun right and the verb
    wrong ("1 ... are reported").

    Driven at one proposed work that resolved to nothing, which puts three of the
    agreeing sentences on the page at once — the rate, the unresolved clause and
    the pending clause — and is a state a real run reaches whenever the single
    work it was asked for is not held.
    """
    named = a_candidate(
        work_id="named",
        title="The Persistence of Memory",
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    _a_finished_discovery(ui, [named], [a_card(work=named, shown=None)])

    # Said as counts now, which carry no agreement to get wrong; the plural
    # spellings stay asserted absent so a sentence creeping back is caught.
    assert _counts(ui) == {"Asked for": "1", "Found with an image": "0", "Not matched": "1"}
    expect(ui.view).not_to_contain_text("1 works", use_inner_text=True)
    expect(ui.view).not_to_contain_text("and are reported", use_inner_text=True)


def test_a_settled_work_list_of_one_says_so_in_the_singular(ui):
    """The in-flight sentence, which no completed-run fixture reaches.

    Separate from the test above because `resolving_images` and `completed` are
    different branches of `runSentence`, and the branch that says the list is
    settled carries its own "There is/are" as well as its own noun.
    """
    run = a_run(status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=run, works=[a_candidate(resolution_status=ResolutionStatus.PENDING.value)]),
    )
    ui.open(f"#get/{RUN_ID}")

    ui.page.wait_for_selector("text=The work list of 1 work is settled")
    expect(ui.view).not_to_contain_text("1 works", use_inner_text=True)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        # A Get from words says counts, not this sentence
        # (`test_a_finished_get_says_three_counts_rather_than_a_paragraph`).
        ("resolve", "1 of the 2 works it covers has an image"),
    ],
)
def test_one_of_several_works_takes_the_singular_verb(ui, kind, expected):
    """ "N of M works … has/have" agrees with N, and only one-of-several shows it.

    The count-of-one test below drives a single work that resolved to nothing,
    where the numerator and the denominator are 0 and 1 — and every spelling of
    this verb reads the same there. One work resolved out of two is where the two
    candidate numbers disagree, which is why "1 of the 2 works it covers **have**
    an image" survived the plural fix and the sweep that followed it: the
    disagreement moved from the trailing count to the leading one rather than
    going away.

    Both kinds, because they are separate sentences over separate tallies and a
    fix to one says nothing about the other.
    """
    works = [
        a_candidate(work_id="found", title="The Persistence of Memory"),
        a_candidate(
            work_id="missing",
            title="Swans Reflecting Elephants",
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason=UnresolvedReason.NOT_HELD.value,
        ),
    ]
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True, kind=kind)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=works))
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("table")

    expect(ui.view).to_contain_text(expected, use_inner_text=True)
    # The spelling that shipped, so this fails on the agreement rather than on
    # the sentence merely being present.
    expect(ui.view).not_to_contain_text("have an image", use_inner_text=True)


def test_a_run_that_cannot_look_for_images_says_so_in_the_singular(ui):
    """The deployment-has-no-provider branch, which the two tests above never enter.

    `runSentence` has four sentences under `resolving_images` and only one of
    them was pinned at a count of one. This is the branch a deployment with no
    image provider sits in for as long as the run exists, so its sentence is the
    one a curator reads longest, and it carries both the verb and the noun.
    """
    run = a_run(status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(
            run=run,
            # An offered work beside the proposed one, so the sentence shows it
            # counts what the run proposed and not everything it holds.
            works=[
                a_candidate(resolution_status=ResolutionStatus.PENDING.value),
                a_candidate(
                    work_id="offered-1",
                    provenance=WorkProvenance.OFFERED.value,
                    offered_for_artist="Salvador Dalí",
                    offered_artist_matched=1,
                    resolution_status=ResolutionStatus.RESOLVED.value,
                ),
            ],
            image_resolution_available=False,
        ),
    )
    ui.open(f"#get/{RUN_ID}")

    ui.page.wait_for_selector("text=There is 1 work to find images for")
    expect(ui.view).not_to_contain_text("1 works", use_inner_text=True)
    expect(ui.view).not_to_contain_text("There are 1", use_inner_text=True)


@pytest.mark.parametrize(
    ("kind", "provenance"),
    [
        pytest.param("get", WorkProvenance.CHOSEN.value, id="a Get"),
        pytest.param("resolve", WorkProvenance.OFFERED.value, id="a re-search of offered works"),
    ],
)
def test_a_run_with_no_phase_one_that_cannot_look_counts_every_work_it_holds(ui, kind, provenance):
    """Neither run proposed anything, so a proposed count would tell the curator there is nothing to find.

    The works are not `proposed` here, so a sentence counting proposals reads
    "There are 0 works" over a run holding two.
    """
    run = a_run(kind=kind, intent=None, status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False)
    works = [
        a_candidate(work_id=f"w{n}", provenance=provenance, resolution_status=ResolutionStatus.PENDING.value) for n in range(2)
    ]
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=works, image_resolution_available=False))
    ui.open(f"#get/{RUN_ID}")

    ui.page.wait_for_selector("text=There are 2 works to find images for")


def test_a_re_search_over_one_work_says_so_in_the_singular(ui):
    """The re-search's own in-flight sentence, which a discovery run never reaches.

    Both kinds share the `resolving_images` status and say different things about
    different numbers, which is exactly why one being right proves nothing about
    the other.
    """
    run = a_run(status=RunStatus.RESOLVING_IMAGES.value, is_terminal=False, kind="resolve")
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=run, works=[a_candidate(resolution_status=ResolutionStatus.PENDING.value)]),
    )
    ui.open(f"#get/{RUN_ID}")

    ui.page.wait_for_selector("text=Looking again for images of the 1 work this Get covers")
    expect(ui.view).not_to_contain_text("1 works", use_inner_text=True)


def test_one_work_the_provider_could_not_be_asked_about_reads_in_the_singular(ui):
    """The pending clause, which carries three agreeing words and no noun at all.

    "unreachable for **them** … whether **they exist**" over a count of one is the
    same defect as "1 works" with none of its tells: there is no plural noun on
    screen to look wrong. The completed-run test above drives UNRESOLVED, which
    leaves `tally.pending` at zero and this clause unwritten.
    """
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(
        f"**/api/runs/{RUN_ID}",
        a_run_view(run=run, works=[a_candidate(resolution_status=ResolutionStatus.PENDING.value)]),
    )
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("table")

    expect(ui.view).to_contain_text("the image provider was unreachable for it", use_inner_text=True)
    expect(ui.view).to_contain_text("says nothing about whether it exists", use_inner_text=True)
    # The plural spellings of the same clause, so a partial fix fails here rather
    # than passing on the sentence merely being present.
    expect(ui.view).not_to_contain_text("unreachable for them", use_inner_text=True)
    expect(ui.view).not_to_contain_text("whether they exist", use_inner_text=True)


def test_the_run_sentence_does_not_deny_the_works_listed_underneath_it(ui):
    """Issue #95's denial lived on this page too, and this is the page seen first.

    The review grid's version was the reported one, but the same claim — that the
    run named nothing it could confirm for those artists — was composed here, in
    the sentence printed directly above the table that lists those very works with
    their `not held` badges. Fixing one surface and not the other would have left
    the defect standing exactly where a curator meets it first, while the records
    said it was gone.

    This page now says the offered works by a section heading naming the museum,
    which makes no claim about the works asked for. The review grid and the MCP
    run summary still say "found no image for"; the MCP one is pinned in
    `tests/unit/test_offered_works.py`.
    """
    named = a_candidate(
        work_id="named",
        title="The Persistence of Memory",
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    offered = a_candidate(
        work_id="gift",
        title="Lobster Telephone",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
    )
    _a_finished_discovery(ui, [named, offered], [a_card(work=named, shown=None), a_card(work=offered)])

    # The offered work is said by its section's heading, which names the museum
    # and denies nothing about the works asked for.
    expect(ui.view).to_contain_text("Also offered by Art Institute of Chicago (1)", use_inner_text=True)
    expect(ui.view).not_to_contain_text("1 more works", use_inner_text=True)
    expect(ui.view, "the run view still denies work it lists directly below").not_to_contain_text(
        "could not confirm", use_inner_text=True
    )

    # The column heading, over the cell that answers it. The run named none of
    # the offered works and that cell says so, so a heading asserting naming is
    # contradicted one column across — the same defect this change removes.
    # `all_text_contents`, not `all_inner_texts`: the header cells carry
    # `text-transform: uppercase`, and inner_text returns what the transform
    # renders rather than what the client wrote.
    expect(ui.page.locator("#view section.asked-for table th").filter(has_text=_text_is("Why it is here")).first).to_be_attached()
    # A membership claim has no retrying form (`docs/testing.md`, hazard 10): the
    # headings are read once, after the heading above has shown the table drawn.
    headings = ui.page.locator("table th").all_text_contents()  # one-shot: a membership, read once the table is drawn
    assert "Why the run named it" not in headings


# -- why a run ended ----------------------------------------------------------------


def _ended(ui, *, status: RunStatus, end_reason: str | None):
    """A run that has ended in `status`, with the reason the worker stored, opened."""
    run = a_run(status=status.value, is_terminal=True, completed_at="2026-10-05T10:05:00+00:00", end_reason=end_reason)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=[]))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    return ui.view


@pytest.mark.parametrize(
    ("status", "sentence"),
    [
        (RunStatus.FAILED, "This Get hit an error and stopped."),
        (RunStatus.HALTED_BY_BUDGET, "The provider refused further spend"),
    ],
)
def test_a_run_that_ended_badly_says_why_beside_what_happened(ui, status, sentence):
    """The worker's reason is on the page a curator lands on, under the sentence it explains.

    Until it was stored, a failed run's page could only send a curator to the
    server log, which on the deployment means somebody with a shell on the NAS.
    """
    reason = "Phase 1 returned an empty answer (it stopped on 'length')."

    shown = _ended(ui, status=status, end_reason=reason)

    expect(shown).to_contain_text(sentence, use_inner_text=True)
    expect(shown).to_contain_text(f"Why it stopped: {reason}", use_inner_text=True)
    expect(shown, "the log pointer is the fallback for a run with no reason").not_to_contain_text(
        "The server log has the details", use_inner_text=True
    )


def test_a_failed_run_from_before_reasons_were_kept_still_points_at_the_log(ui):
    shown = _ended(ui, status=RunStatus.FAILED, end_reason=None)

    expect(shown).to_contain_text("This Get hit an error and stopped. The server log has the details.", use_inner_text=True)
    expect(shown).not_to_contain_text("Why it stopped", use_inner_text=True)


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.INTERRUPTED])
def test_a_run_with_no_reason_shows_no_reason_line(ui, status):
    """The paired negative: the line appears when there is a reason, and not otherwise."""
    shown = _ended(ui, status=status, end_reason=None)

    expect(shown).not_to_contain_text("Why it stopped", use_inner_text=True)


def test_a_reason_quoting_the_provider_reaches_the_page_as_text(ui):
    """A halt's reason quotes the provider's own words, so it is outside text and never markup."""
    shown = _ended(ui, status=RunStatus.HALTED_BY_BUDGET, end_reason="OpenRouter refused the call: <b>Key</b> limit exceeded.")

    expect(shown).to_contain_text("Why it stopped: OpenRouter refused the call: <b>Key</b> limit exceeded.", use_inner_text=True)
    expect(ui.page.locator("#view b")).to_have_count(0)


# -- a Get's page: asked for, and offered by whom ----------------------------------


def _a_finished_discovery(ui, works, cards):
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=works))
    ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page(cards, run=run))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.serve_image("**/api/candidate-images/**")
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view section.asked-for")


def _counts(ui):
    """The summary's counts, as label → figure."""
    return ui.page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#view .run-counts dt')]
              .map((dt) => [dt.textContent.trim(), dt.nextElementSibling.textContent.trim()]))""")


def test_a_finished_get_says_three_counts_rather_than_a_paragraph(ui):
    """Asked for, found with an image, not matched."""
    found = a_candidate(work_id="found", title="The Persistence of Memory")
    missing = [
        a_candidate(
            work_id=f"missing-{n}",
            title=f"Lost {n}",
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason=UnresolvedReason.NOT_HELD.value,
        )
        for n in range(2)
    ]
    offered = a_candidate(
        work_id="gift",
        title="Lobster Telephone",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
    )
    # An offered work turned down and searched again in vain: unresolved, but
    # not one of the works asked for, so not among "Not matched".
    offered_lost = a_candidate(
        work_id="gift-lost",
        title="Mae West Lips Sofa",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    works = [found, *missing, offered, offered_lost]
    _a_finished_discovery(ui, works, [a_card(work=w) for w in works])

    # Distinct figures, so a count read from the wrong tally field cannot pass.
    assert _counts(ui) == {"Asked for": "3", "Found with an image": "1", "Not matched": "2"}
    expect(ui.view).not_to_contain_text("it was asked for has an image", use_inner_text=True)
    expect(ui.view).not_to_contain_text("Separately, the collection offered", use_inner_text=True)


def test_offered_works_sit_under_the_museum_that_offered_them_without_a_reason(ui):
    asked = a_candidate(work_id="asked", title="The Persistence of Memory", rationale="The intent names melting clocks.")
    by_artic = a_candidate(
        work_id="gift-1",
        title="Lobster Telephone",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
        rationale="Offered by the collection, not proposed by the model: one of 25 works …",
    )
    by_met = a_candidate(
        work_id="gift-2",
        title="Mae West Lips Sofa",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=3,
        offered_by="met",
        rationale="Offered by the collection, not proposed by the model: one of 3 works …",
    )
    cards = [
        a_card(work=asked),
        a_card(work=by_artic, shown=an_instance(work_id="gift-1", image_id="img-artic", provider="artic")),
        a_card(work=by_met, shown=an_instance(work_id="gift-2", image_id="img-met", provider="met")),
    ]
    _a_finished_discovery(ui, [asked, by_artic, by_met], cards)

    expect(_headings(ui)).to_have_text(
        [
            "Asked for (1)",
            "Also offered by Art Institute of Chicago (1)",
            "Also offered by Metropolitan Museum of Art (1)",
        ]
    )
    asked_section = ui.page.locator("#view section.asked-for")
    expect(asked_section.locator("th").filter(has_text=_text_is("Why it is here")).first).to_be_attached()
    expect(asked_section).to_contain_text("The intent names melting clocks.", use_inner_text=True)
    offered_sections = ui.page.locator("#view section.offered")
    expect(offered_sections).to_have_count(2)
    expect(offered_sections.locator("th").filter(has_text=_text_is("Why it is here"))).to_have_count(0)
    # The stored per-row sentence is gone with its column: the heading says it once.
    expect(ui.view).not_to_contain_text("not proposed by the model", use_inner_text=True)
    met = ui.page.locator("#view section.offered", has_text="Metropolitan Museum of Art")
    expect(met).to_contain_text("Mae West Lips Sofa", use_inner_text=True)
    expect(met).not_to_contain_text("Lobster Telephone", use_inner_text=True)


def test_each_row_shows_the_picture_found_for_it(ui):
    found = a_candidate(work_id="found", title="The Persistence of Memory")
    none = a_candidate(
        work_id="none",
        title="Lost",
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    cards = [a_card(work=found, shown=an_instance(work_id="found", image_id="img-found")), a_card(work=none, shown=None)]
    _a_finished_discovery(ui, [found, none], cards)

    rows = ui.page.locator("#view section.asked-for tbody tr")
    first = rows.filter(has_text="The Persistence of Memory")
    first.locator("img").wait_for()
    expect(first.locator("img")).to_have_attribute("src", re.compile(re.escape("/api/candidate-images/img-found/preview")))
    # Loaded, not merely present: waited for, since an image arrives after its element.
    ui.page.wait_for_function("(i) => i.complete && i.naturalWidth > 0", arg=first.locator("img").element_handle())
    lost = rows.filter(has_text="Lost")
    expect(lost).to_contain_text("No image found", use_inner_text=True)
    expect(lost.locator("img")).to_have_count(0)


@pytest.mark.parametrize(
    ("cards_answer", "status", "said"),
    [
        ("fails", ResolutionStatus.RESOLVED.value, "Its picture could not be read just now."),
        ("reads", ResolutionStatus.PENDING.value, "Still being looked for."),
    ],
)
def test_a_row_without_a_picture_says_which_kind_of_nothing(ui, cards_answer, status, said):
    work = a_candidate(work_id="w", title="The Persistence of Memory", resolution_status=status)
    run = a_run(status=RunStatus.COMPLETED.value, is_terminal=True)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=[work]))
    if cards_answer == "fails":
        ui.serve(f"**/api/runs/{RUN_ID}/candidates*", [(500, {"detail": "down"})])
    else:
        ui.serve(f"**/api/runs/{RUN_ID}/candidates*", a_candidate_page([a_card(work=work, shown=None)], run=run))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view section.asked-for")

    row = ui.page.locator("#view section.asked-for tbody tr")
    expect(row).to_contain_text(said, use_inner_text=True)
    expect(row).not_to_contain_text("No image found", use_inner_text=True)


def test_a_row_s_picture_stays_small_on_a_phone(ui):
    """Stacked into a card, a row's picture would otherwise fill the phone's width."""
    found = a_candidate(work_id="found", title="The Persistence of Memory")
    ui.page.set_viewport_size({"width": 390, "height": 844})
    _a_finished_discovery(ui, [found], [a_card(work=found, shown=an_instance(work_id="found", image_id="img-found"))])

    image = ui.page.locator("#view section.asked-for img")
    image.wait_for()
    width = image.evaluate("(i) => i.getBoundingClientRect().width")
    rem = ui.page.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)")
    assert width <= 8 * rem + 0.5, f"{width}px wide on a 390px screen"


def test_an_offered_work_stays_under_the_museum_that_offered_it_when_its_picture_changes(ui):
    """Its scan turned down and another museum's found: the offer is still the first museum's."""
    gift = a_candidate(
        work_id="gift",
        title="Lobster Telephone",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
        offered_by="artic",
    )
    asked = a_candidate(work_id="asked")
    cards = [a_card(work=asked), a_card(work=gift, shown=an_instance(work_id="gift", image_id="img-met", provider="met"))]
    _a_finished_discovery(ui, [asked, gift], cards)

    expect(_has_heading(ui, "Also offered by Art Institute of Chicago (1)")).to_be_attached()
    expect(_headings(ui).filter(has_text=re.compile("Metropolitan"))).to_have_count(0)


def test_an_offered_work_recorded_before_its_museum_was_kept_says_the_collection(ui):
    gift = a_candidate(
        work_id="gift",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Salvador Dalí",
        offered_artist_matched=25,
        offered_by=None,
    )
    asked = a_candidate(work_id="asked")
    _a_finished_discovery(ui, [asked, gift], [a_card(work=asked), a_card(work=gift)])

    expect(_has_heading(ui, "Also offered by the collection (1)")).to_be_attached()


# -- the Get page shows pictures, links, and only acts that lead somewhere (#363) --


#: What the server says of a picture it cannot show: a sentence for whoever asks
#: why, which in a 128-px cell was cut off at both ends.
_SERVER_NOTE = (
    "No local copy of this image is on disk, so it cannot be shown here: the file its record names "
    "is no longer there. Its source URL is reported beside it."
)


def test_a_row_whose_picture_is_not_kept_shows_a_placeholder_not_the_server_s_explanation(ui):
    offered = a_candidate(
        work_id="gift",
        title="Homage to Blériot",
        provenance=WorkProvenance.OFFERED.value,
        offered_for_artist="Robert Delaunay",
        offered_artist_matched=4,
    )
    gone = an_instance(work_id="gift", image_id="img-gone", preview_available=False, preview_note=_SERVER_NOTE)
    asked = a_candidate(work_id="asked", title="Rhythm")
    _a_finished_discovery(ui, [asked, offered], [a_card(work=asked), a_card(work=offered, shown=gone)])

    cell = ui.page.locator("#view section.offered tbody tr .row-picture")
    expect(cell).to_have_text("No picture kept", use_inner_text=True)
    expect(ui.view).not_to_contain_text("cannot be shown here", use_inner_text=True)


def _review_links(ui):
    return ui.page.locator(f'#view a[href^="#review/{RUN_ID}"]')


def test_review_these_works_is_offered_while_a_card_is_left_to_judge(ui):
    waiting = a_candidate(work_id="waiting", title="Rhythm")
    decided = a_candidate(work_id="decided", title="Saint-Séverin", verdict="accepted", artwork_id="art-9")
    _a_finished_discovery(ui, [waiting, decided], [a_card(work=waiting), a_card(work=decided)])

    expect(_review_links(ui)).to_have_text(["Review these works"], use_inner_text=True)


def test_nothing_left_to_judge_offers_no_way_into_an_empty_review(ui):
    """The owner's walk: every card decided, and the one filled act opened onto "Nothing here is left to judge"."""
    works = [a_candidate(work_id=f"d{n}", title=f"Decided {n}", verdict="rejected") for n in range(2)]
    _a_finished_discovery(ui, works, [a_card(work=w) for w in works])

    # The decided works are listed, so the page has drawn when no way into Review is found on it.
    expect(ui.view).to_contain_text("Decided 1", use_inner_text=True)
    expect(_review_links(ui)).to_have_count(0)
    expect(ui.view).not_to_contain_text("Review these works", use_inner_text=True)


def test_only_works_found_with_no_image_left_says_what_there_is_to_decide(ui):
    """Their cards fold behind "found no image" on Review, where Want and Forget are; the link says so."""
    lost = [
        a_candidate(
            work_id=f"lost-{n}",
            title=f"Rhythm No. {n}",
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason=UnresolvedReason.NOT_HELD.value,
        )
        for n in range(2)
    ]
    _a_finished_discovery(ui, lost, [a_card(work=w, shown=None) for w in lost])

    expect(_review_links(ui)).to_have_text(["Want or forget the 2 works it found no image for"], use_inner_text=True)


def test_each_work_s_title_links_to_the_page_it_has(ui):
    """Accepted, held by the library under another record, chosen by its Wikidata item, or none of these."""
    accepted = a_candidate(work_id="acc", title="Champs de Mars", verdict="accepted", artwork_id="art-accepted")
    twin = a_candidate(work_id="twin", title="The Persistence of Memory")
    chosen = a_candidate(work_id="chosen", title="Rhythm", provenance=WorkProvenance.CHOSEN.value, wikidata_qid="Q20166468")
    plain = a_candidate(work_id="plain", title="Rhythm No. 2")
    cards = [
        a_card(work=accepted),
        a_card(work=twin, held_artwork_id="art-held"),
        a_card(work=chosen),
        a_card(work=plain),
    ]
    _a_finished_discovery(ui, [accepted, twin, chosen, plain], cards)

    def title_link(title):
        row = ui.page.locator("#view section.asked-for tbody tr", has_text=title)
        return row.get_by_role("link", name=title, exact=True)

    expect(title_link("Champs de Mars")).to_have_attribute("href", re.compile("^" + re.escape("#work/art-accepted")))
    expect(title_link("The Persistence of Memory")).to_have_attribute("href", re.compile("^" + re.escape("#work/art-held")))
    expect(title_link("Rhythm")).to_have_attribute("href", re.compile("^" + re.escape("#work/Q20166468")))
    # Nothing to open: proposed, never accepted, no copy in the library, no item.
    # The other titles' links are there, so the rows have drawn.
    expect(title_link("Rhythm No. 2")).to_have_count(0)


def test_a_work_the_library_holds_says_so_rather_than_not_held(ui):
    """P-6: The Persistence of Memory, held with a working picture, read "No image found / not held"."""
    twin = a_candidate(
        work_id="twin",
        title="The Persistence of Memory",
        resolution_status=ResolutionStatus.UNRESOLVED.value,
        unresolved_reason=UnresolvedReason.NOT_HELD.value,
    )
    _a_finished_discovery(ui, [twin], [a_card(work=twin, shown=None, held_artwork_id="art-held")])

    row = ui.page.locator("#view section.asked-for tbody tr")
    held = row.get_by_role("link", name="In your library")
    expect(held).to_have_attribute("href", re.compile("^" + re.escape("#work/art-held")))
    # What the run found is still said, in words that cannot be read as the library's.
    expect(row).to_contain_text("in no collection", use_inner_text=True)
    expect(row).not_to_contain_text("not held", use_inner_text=True)


def test_an_accepted_work_with_a_library_copy_is_not_told_twice(ui):
    """Its title already opens the work it became; "In your library" is for a work the run did not add."""
    accepted = a_candidate(work_id="acc", title="Champs de Mars", verdict="accepted", artwork_id="art-accepted")
    _a_finished_discovery(ui, [accepted], [a_card(work=accepted, held_artwork_id="art-held")])

    row = ui.page.locator("#view section.asked-for tbody tr")
    expect(row.get_by_role("link", name="Champs de Mars")).to_have_attribute(
        "href", re.compile("^" + re.escape("#work/art-accepted"))
    )
    expect(row.get_by_role("link", name="In your library")).to_have_count(0)
