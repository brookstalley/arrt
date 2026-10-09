"""The run view: its poll loop, its supersession, and the words it puts on a card.

This is the most stateful screen the product had when this harness was built, and
every behaviour below is one a test reading JSON cannot see. Two of them are
about what the page does *not* do — repaint, and poll twice — which is why each
is paired with the assertion that would fail if it stopped doing the thing at
all.
"""

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

RUN_ID = "run-under-test"

#: The client polls every two seconds. Windows below are expressed in whole
#: polls so they survive a change to that interval being read here rather than
#: recomputed by hand at each call site.
POLL_MS = 2000


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
    ui.page.wait_for_timeout(POLL_MS * 2 + POLL_MS // 2)

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

    assert "Second arrival" not in ui.text()
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
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("button:has-text('Approve the list')")

    before = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    # A second paint started while the first is still the one on screen — the
    # same collision as pressing Approve during a poll, without the timing
    # dependence of actually racing a click against one.
    ui.page.evaluate("() => { refresh(); refresh(); }")

    ui.page.wait_for_timeout(POLL_MS * 3 + 500)
    polls = len(ui.requests_matching(f"/api/runs/{RUN_ID}")) - before

    # Two immediate paints, then one chain ticking three times. A second chain
    # would add three more, so this sits either side of the two outcomes.
    assert polls <= 6, f"{polls} requests in three polls — a second chain is running"
    assert polls >= 3, f"only {polls} requests — the poll chain stopped altogether"


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

    assert "A run left behind" not in ui.text()
    assert "Something by Dalí" in ui.text()


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
    ui.page.wait_for_timeout(POLL_MS * 2 + 500)

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

    shown = ui.text()
    assert "The total including every Get again could not be read" in shown
    # The panel survives the failure: the two figures beside it are read off the
    # run record and are still true, so losing the rollup must not cost them.
    assert "Spent by this Get alone" in shown


def test_a_run_that_has_stopped_is_not_polled_again(a_finished_run):
    """The other end of the watch, and the end no test reached until a sweep said so.

    `test_leaving_the_run_view_stops_its_polling` covers the curator walking
    away; this covers them staying. A finished run has nothing left to report, so
    a page that went on asking would request it every two seconds for as long as
    the tab stayed open — the same unbounded retry a stale bookmark used to
    cause, arrived at from the other direction and with nothing on screen
    looking wrong.

    Deliberately paired with the two tests above rather than written as a
    variant of them: what makes this the run view's own branch is that the
    conversation screen has its own reading of "stopped", so a test over one
    says nothing about the other.
    """
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    settled = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))
    # Not decoration: a page that never asked at all would satisfy the equality
    # below and prove nothing about when it stops.
    assert settled >= 1

    ui.page.wait_for_timeout(POLL_MS * 2 + 500)

    assert len(ui.requests_matching(f"/api/runs/{RUN_ID}")) == settled


def test_a_family_total_that_reads_fine_says_nothing(a_finished_run):
    """The paired negative — the notice appears on failure and not otherwise."""
    ui = a_finished_run
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())

    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")

    shown = ui.text()
    assert "could not be read" not in shown
    assert "Spent including every Get again" in shown


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

    shown = ui.text()
    assert reason.value not in shown, f"the raw token {reason.value!r} reached the page"

    # Both halves of the badge, read off the one element: the short phrase it
    # shows, and the sentence behind it saying what that phrase means. A badge
    # with an empty title looks correct in a screenshot and tells a curator
    # nothing about which kind of nothing they are looking at.
    badge = ui.page.locator("#view span.badge[title]").filter(has=ui.page.locator("span.glyph", has_text="▲"))
    assert badge.count() == 1
    assert badge.inner_text().strip(), f"{reason.value} reached the page with no words"

    sentence = badge.get_attribute("title")
    assert sentence, f"{reason.value} reached the page with no sentence behind it"
    assert sentence.endswith("."), f"the sentence for {reason.value} is not one: {sentence!r}"

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
    assert "the Get found none" in shown
    assert "no image" not in shown, (
        "a present-tense claim about the work is what the reword removed — `resolution_status` "
        "records what the run found, and only a resolution attempt recomputes it"
    )


# -- a watch that cannot recover --------------------------------------------


#: The client gives up after this many consecutive failures. Read from the module
#: under test would be better; it is a `const` in a script, so it is restated
#: here and `test_the_client_and_this_test_agree_on_the_limit` holds the pair
#: together rather than leaving two numbers to drift.
MAX_FAILURES = 5

#: What the service answers for a run id it does not know — the case that made
#: this necessary. A bookmarked `#get/<id>` outlives its run.
GONE = (400, {"error": "There is no run with that id."})


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

    Opening a stale bookmarked `#get/<id>` after the run is gone had the service
    answer 400, the catch re-arm, and the tab request that run every two seconds
    for as long as it stayed open — bounded only by navigation, with nothing on
    screen saying the watch was still retrying.

    Asserted on the request count across a window several polls longer than the
    limit, because that is the only thing that distinguishes a loop that stopped
    from one that is between ticks.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", GONE)

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")

    # Long enough for several more polls than the limit allows, so a loop that
    # merely slowed down would still be caught.
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 3))
    attempts = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))

    assert attempts == MAX_FAILURES, f"{attempts} requests for a run that will never exist — the watch did not stop"


def test_a_watch_that_gave_up_says_so_rather_than_only_what_failed(ui):
    """ "The server answered 400" leaves a live page indistinguishable from a dead one.

    The curator needs two facts and the message used to carry one: what went
    wrong, and whether anything is still trying. Only the second tells them
    whether to keep looking at the screen.
    """
    ui.serve(f"**/api/runs/{RUN_ID}", GONE)

    ui.page.goto(f"{ui.base_url}/#get/{RUN_ID}")
    ui.page.wait_for_selector("#error:not([hidden])")
    ui.page.wait_for_timeout(POLL_MS * (MAX_FAILURES + 1))

    message = ui.page.inner_text("#error")
    assert "Gave up watching this Get" in message
    assert "reload" in message, "saying it stopped without saying how to resume leaves the curator stuck"
    assert "There is no run with that id." in message, "the original fault must survive; it is the diagnosis"


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
    assert "Something by Dalí" in ui.text()
    assert ui.page.is_hidden("#error"), "a recovered watch must clear the message, not leave it accusing"


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
    ui.page.wait_for_timeout(POLL_MS * 4 + 500)

    attempts = len(ui.requests_matching(f"/api/runs/{RUN_ID}"))

    assert attempts > 6, (
        f"only {attempts} requests — a cumulative count gives up on the sixth, so the watch "
        "was ended by failures that had a success between them"
    )


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

    text = ui.text()
    assert "50 most recent of 407" in text
    assert "does not page" in text, "a note implying paging sends a curator to an affordance that does not exist"


def test_a_complete_search_list_says_nothing_about_truncation(ui):
    """Saying nothing is the honest answer when nothing was left behind."""
    ui.serve("**/api/runs*", _a_run_list(count=4, total=4))

    ui.open("#queue")
    ui.page.wait_for_selector("h2:has-text('In flight')")

    text = ui.text()
    assert "In flight (4)" in text
    assert "of 4" not in text, "a complete list must not be dressed as a partial one"
    assert "does not page" not in text


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

    text = ui.text()
    assert "Where it came from" not in text
    why = (
        "the offered/asked-for distinction must survive its per-row copy being removed — "
        "it is what tells a curator the list is longer than the one they authorised"
    )
    headings = [h.strip() for h in ui.page.locator("#view section h3").all_text_contents()]
    assert "Asked for (1)" in headings, why
    assert "Also offered by Art Institute of Chicago (1)" in headings, why


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

    assert "offered" in ui.text()


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
    shown = ui.text()
    assert "1 works" not in shown
    assert "and are reported" not in shown


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
    assert "1 works" not in ui.text()


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

    shown = ui.text()
    assert expected in shown
    # The spelling that shipped, so this fails on the agreement rather than on
    # the sentence merely being present.
    assert "have an image" not in shown


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
    assert "1 works" not in ui.text()
    assert "There are 1" not in ui.text()


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
    assert "1 works" not in ui.text()


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

    shown = ui.text()
    assert "the image provider was unreachable for it" in shown
    assert "says nothing about whether it exists" in shown
    # The plural spellings of the same clause, so a partial fix fails here rather
    # than passing on the sentence merely being present.
    assert "unreachable for them" not in shown
    assert "whether they exist" not in shown


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

    shown = ui.text()
    # The offered work is said by its section's heading, which names the museum
    # and denies nothing about the works asked for.
    assert "Also offered by Art Institute of Chicago (1)" in shown
    assert "1 more works" not in shown
    assert "could not confirm" not in shown, "the run view still denies work it lists directly below"

    # The column heading, over the cell that answers it. The run named none of
    # the offered works and that cell says so, so a heading asserting naming is
    # contradicted one column across — the same defect this change removes.
    # `all_text_contents`, not `all_inner_texts`: the header cells carry
    # `text-transform: uppercase`, and inner_text returns what the transform
    # renders rather than what the client wrote.
    headings = ui.page.locator("#view section.asked-for table th").all_text_contents()
    assert "Why it is here" in headings, headings
    assert "Why the run named it" not in ui.page.locator("table th").all_text_contents()


# -- why a run ended ----------------------------------------------------------------


def _ended(ui, *, status: RunStatus, end_reason: str | None):
    """A run that has ended in `status`, with the reason the worker stored, opened."""
    run = a_run(status=status.value, is_terminal=True, completed_at="2026-10-05T10:05:00+00:00", end_reason=end_reason)
    ui.serve(f"**/api/runs/{RUN_ID}", a_run_view(run=run, works=[]))
    ui.serve(f"**/api/runs/{RUN_ID}/spend", a_spend())
    ui.open(f"#get/{RUN_ID}")
    ui.page.wait_for_selector("#view dl.facts")
    return ui.text()


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

    assert sentence in shown
    assert f"Why it stopped: {reason}" in shown
    assert "The server log has the details" not in shown, "the log pointer is the fallback for a run with no reason"


def test_a_failed_run_from_before_reasons_were_kept_still_points_at_the_log(ui):
    shown = _ended(ui, status=RunStatus.FAILED, end_reason=None)

    assert "This Get hit an error and stopped. The server log has the details." in shown
    assert "Why it stopped" not in shown


@pytest.mark.parametrize("status", [RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.INTERRUPTED])
def test_a_run_with_no_reason_shows_no_reason_line(ui, status):
    """The paired negative: the line appears when there is a reason, and not otherwise."""
    shown = _ended(ui, status=status, end_reason=None)

    assert "Why it stopped" not in shown


def test_a_reason_quoting_the_provider_reaches_the_page_as_text(ui):
    """A halt's reason quotes the provider's own words, so it is outside text and never markup."""
    shown = _ended(ui, status=RunStatus.HALTED_BY_BUDGET, end_reason="OpenRouter refused the call: <b>Key</b> limit exceeded.")

    assert "Why it stopped: OpenRouter refused the call: <b>Key</b> limit exceeded." in shown
    assert ui.page.locator("#view b").count() == 0


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
    """Asked for, found with an image, not matched (`build-plan-get-and-review-clarity.md`)."""
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
    assert "it was asked for has an image" not in ui.text()
    assert "Separately, the collection offered" not in ui.text()


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

    headings = [h.strip() for h in ui.page.locator("#view section h3").all_text_contents()]
    assert headings == [
        "Asked for (1)",
        "Also offered by Art Institute of Chicago (1)",
        "Also offered by Metropolitan Museum of Art (1)",
    ]
    asked_section = ui.page.locator("#view section.asked-for")
    assert "Why it is here" in asked_section.locator("th").all_text_contents()
    assert "The intent names melting clocks." in asked_section.inner_text()
    for offered_section in ui.page.locator("#view section.offered").all():
        assert "Why it is here" not in offered_section.locator("th").all_text_contents()
    # The stored per-row sentence is gone with its column: the heading says it once.
    assert "not proposed by the model" not in ui.text()
    met = ui.page.locator("#view section.offered", has_text="Metropolitan Museum of Art")
    assert "Mae West Lips Sofa" in met.inner_text()
    assert "Lobster Telephone" not in met.inner_text()


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
    assert "/api/candidate-images/img-found/preview" in first.locator("img").get_attribute("src")
    assert first.locator("img").evaluate("(i) => i.complete && i.naturalWidth") > 0
    lost = rows.filter(has_text="Lost")
    assert lost.locator("img").count() == 0
    assert "No image found" in lost.inner_text()


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
    assert said in row.inner_text()
    assert "No image found" not in row.inner_text()


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

    headings = [h.strip() for h in ui.page.locator("#view section h3").all_text_contents()]
    assert "Also offered by Art Institute of Chicago (1)" in headings
    assert not any("Metropolitan" in heading for heading in headings)


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

    headings = [h.strip() for h in ui.page.locator("#view section h3").all_text_contents()]
    assert "Also offered by the collection (1)" in headings
