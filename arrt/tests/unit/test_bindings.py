"""The MCP bindings' own behaviour — the formatting a binding is allowed to do.

A binding unpacks arguments, calls one service method, and shapes the result for
a model to read. The shaping is the part worth testing here, because it is the
only part a binding decides, and because a message that gives a caller advice it
cannot act on is a defect the service layer cannot see.

Separate from `test_catalogue_service.py`, which declares itself independent of
any surface: the binding layer is where the thin-binding norm is enforced, and
scattering its tests into a file that disclaims it is how that boundary stops
being legible.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from arrt.library.acquisition.dezoomify import DezoomifyUnavailable
from arrt.library.acquisition.queue import AcquisitionPhase, AcquisitionState
from arrt.library.acquisition.service import DEPLOYMENT_FAULTS, DEPLOYMENT_REMEDIES, SourcePluginUnavailable, remedy_for
from arrt.library.acquisition.space import NotEnoughSpace
from arrt.library.services.catalogue import MAX_LIST_LIMIT
from arrt.library.services.runner import MAX_RUNS_LISTED, RunListing, RunView
from arrt.mcp.bindings import (
    _RUN_DETAIL_ONLY,
    MAX_WORKS_LISTED,
    _retry_notice,
    _run_fields,
    _run_notice,
    _run_summary,
    _run_view,
    _runs_truncation_notice,
    _truncation_notice,
)
from arrt.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    RunKind,
    RunStatus,
    WorkProvenance,
)


def test_a_complete_page_gets_no_notice(seeded_service):
    """Saying nothing is the honest answer when nothing was left behind."""
    assert _truncation_notice(seeded_service.list_artworks()) is None


def test_a_notice_names_the_limit_that_produced_the_page(seeded_service):
    """ "Raise limit" is advice a caller cannot act on without knowing the current one.

    A caller who passed no limit at all is looking at a default it never chose.
    """
    notice = _truncation_notice(seeded_service.list_artworks(limit=1))

    assert notice == "showing 1-1 of 3 at limit 1; raise limit or page with offset, or narrow with status to see the rest"


def test_at_the_ceiling_the_notice_stops_recommending_a_limit_that_cannot_rise(service):
    """`MAX_LIST_LIMIT` is enforced in the service and declared in the tool schema.

    So a caller already at the maximum who follows "raise limit" gets a refusal.
    `offset` is the affordance that works there, and it is on the same action.
    """
    for index in range(MAX_LIST_LIMIT + 1):
        service.add_artwork(title=f"Work {index:03d}")

    at_ceiling = _truncation_notice(service.list_artworks(limit=MAX_LIST_LIMIT))

    assert at_ceiling is not None
    assert "the maximum" in at_ceiling
    assert "raise limit" not in at_ceiling
    assert "page with offset" in at_ceiling


def test_a_notice_says_where_in_the_set_the_page_sits(service):
    """A message that steers a caller to `offset` must change when they use it.

    Reporting only "showing 20 of 84" reads identically at every offset, so the
    one signal a caller needs — that paging moved — is the one it withholds.
    """
    for index in range(10):
        service.add_artwork(title=f"Work {index:03d}")

    first_page = _truncation_notice(service.list_artworks(limit=4))
    second_page = _truncation_notice(service.list_artworks(limit=4, offset=4))

    assert first_page.startswith("showing 1-4 of 10")
    assert second_page.startswith("showing 5-8 of 10")


def test_the_last_page_reached_by_paging_carries_no_notice(service):
    """Truncation is about what the page leaves behind, not about where it starts."""
    for index in range(10):
        service.add_artwork(title=f"Work {index:03d}")

    assert _truncation_notice(service.list_artworks(limit=4, offset=8)) is None


# -- what a run's state means to whoever asked ----------------------------------


def _works(*, resolved: int = 0, unresolved: int = 0, pending: int = 0) -> tuple[CandidateWork, ...]:
    """Works in the three resolution states, which is what a view's tallies count.

    Built rather than asserted as numbers, because the view derives its counts
    from the works themselves — a fixture that supplied both could describe a run
    with three resolved works and an empty list.
    """
    counts = (
        (ResolutionStatus.RESOLVED, resolved),
        (ResolutionStatus.UNRESOLVED, unresolved),
        (ResolutionStatus.PENDING, pending),
    )
    return tuple(
        CandidateWork(
            id=f"w{status}{index}",
            discovery_run_id="r1",
            proposed_title=f"Work {index}",
            rationale="Central to what was asked for.",
            work_dedup_key=f"key-{status}-{index}",
            resolution_status=status,
        )
        for status, count in counts
        for index in range(count)
    )


@pytest.mark.parametrize("status", list(RunStatus))
def test_every_state_a_run_can_be_read_in_carries_guidance(status):
    """A state name says what happened; the notice says what to do about it.

    Parametrised over the enum rather than over a list written here, so a state
    added later arrives already covered instead of silently falling through to
    whatever the default says. That matters most for the states nobody expects
    to meet: an agent reading an unfamiliar one has the notice and nothing else.
    """
    view = RunView(
        run=DiscoveryRun(
            id="r1",
            kind=RunKind.DISCOVERY,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=status,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        ),
        works=_works(resolved=1, unresolved=1),
        searches_used=3,
        search_allowance=14,
        image_resolution_available=True,
    )

    notice = _run_notice(view)

    assert notice.strip(), f"{status} carries no guidance"
    assert notice.endswith("."), f"{status}'s guidance is not a sentence"


@pytest.mark.parametrize(
    ("status", "must_say"),
    [
        (RunStatus.HALTED_BY_BUDGET, "retrying will fail"),
        (RunStatus.INTERRUPTED, "nothing to investigate"),
        (RunStatus.FAILED, "worth investigating"),
    ],
)
def test_the_three_endings_an_agent_must_tell_apart_each_say_what_to_do_next(status, must_say):
    """Stop, run it again, and investigate are three different instructions.

    An agent that reads them as one will either retry a real fault forever or
    escalate a routine deploy restart as a bug. The state alone distinguishes
    them; this is the sentence that says why it matters.
    """
    view = RunView(
        run=DiscoveryRun(
            id="r1",
            kind=RunKind.DISCOVERY,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=status,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        ),
        works=(),
        searches_used=0,
        search_allowance=10,
        image_resolution_available=True,
    )

    assert must_say in _run_notice(view)


def _resolving(kind: RunKind) -> RunView:
    return RunView(
        run=DiscoveryRun(
            id="r1",
            kind=kind,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=RunStatus.RESOLVING_IMAGES,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
            parent_run_id="r0" if kind is RunKind.RESOLVE else None,
        ),
        works=_works(pending=2),
        searches_used=0,
        search_allowance=4,
        image_resolution_available=True,
    )


def test_a_long_work_list_is_capped_and_says_how_much_it_left_out():
    """The contract's rule where it bites hardest: truncation is never silent.

    Phase 1 is deliberately uncapped and the approval gate is computed after the
    whole list is recorded — it pauses the run without shortening it. So the run
    that stops for a human decision is the broad one by construction, and the
    human decides it by reading this payload. A short list read as a complete one
    is worse here than in a catalogue listing, because the run's own count sits
    beside it and the two would disagree inside one result.
    """
    view = replace(_resolving(RunKind.DISCOVERY), works=_works(pending=MAX_WORKS_LISTED + 12))

    payload = _run_view(view)

    works = payload["works"]
    assert works["total"] == MAX_WORKS_LISTED + 12
    assert len(works["each"]) == works["listed"] == MAX_WORKS_LISTED
    assert works["truncated"] is True
    assert f"first {MAX_WORKS_LISTED} of this run's {MAX_WORKS_LISTED + 12} works" in payload["notice"]
    # The state guidance survives alongside it rather than being replaced.
    assert "Call status again" in payload["notice"]


def test_a_list_that_fits_says_nothing_about_truncation():
    """Saying nothing is the honest answer when nothing was left behind."""
    payload = _run_view(_resolving(RunKind.DISCOVERY))

    assert payload["works"]["truncated"] is False
    assert payload["works"]["listed"] == payload["works"]["total"] == 2
    assert "omitted" not in payload["notice"]


def test_a_re_search_is_not_told_its_work_list_has_settled():
    """The two run kinds share this state and reached it by different routes.

    A re-search never ran phase 1 — the curator named its works — so the
    sentence written for a discovery run describes a step this run did not
    perform, on the state a client sees for the whole time it is working.
    """
    discovery_notice = _run_notice(_resolving(RunKind.DISCOVERY))
    resolve_notice = _run_notice(_resolving(RunKind.RESOLVE))

    assert "work list" in discovery_notice
    assert "work list" not in resolve_notice
    assert "re-search" in resolve_notice
    assert "2 works it covers" in resolve_notice


def _a_get(status: RunStatus = RunStatus.RESOLVING_IMAGES) -> RunView:
    view = _resolving(RunKind.GET)
    chosen = tuple(replace(work, provenance=WorkProvenance.CHOSEN, wikidata_qid="Q1") for work in view.works)
    return replace(view, run=replace(view.run, status=status), works=chosen)


def test_a_get_is_told_it_is_finding_the_works_chosen():
    """A Get proposed nothing, so neither the work-list sentence nor a proposed count fits it."""
    notice = _run_notice(_a_get())

    assert "work list" not in notice
    assert "2 works you chose" in notice


def test_a_get_with_no_provider_counts_the_works_it_holds():
    notice = _run_notice(replace(_a_get(), image_resolution_available=False))

    assert "are 2 works to find images for" in notice


def test_an_interrupted_get_is_told_to_get_its_items_again_not_to_repeat_an_intent():
    notice = _run_notice(_a_get(RunStatus.INTERRUPTED))

    assert "Get the same items again" in notice
    assert "intent" not in notice


def test_a_deployment_with_no_provider_says_so_whichever_kind_of_run_is_asking():
    """The absent capability outranks the run kind: neither can advance, for one reason."""
    for kind in RunKind:
        view = _resolving(kind)
        notice = _run_notice(replace(view, image_resolution_available=False))

        assert "no image provider is configured" in notice


# -- what a retry says, now that it fetches nothing in the call ----------------
#
# `retry_acquisition` queues the work and returns (2026-10-02, `api-contract.md`
# § Versioning). What the fetch came to is read afterwards, on `get`'s
# `acquisition` and on `sources`; what the call itself owes is a sentence saying
# nothing was fetched, or that the queue is paused and what ends the pause.


def _state(phase, **fields):
    return AcquisitionState("w1", phase, **fields)


def test_a_retry_says_nothing_was_fetched_and_where_to_watch():
    notice = _retry_notice(_state(AcquisitionPhase.QUEUED))

    assert "nothing was fetched in this call" in notice
    assert "action='get'" in notice


@pytest.mark.parametrize("condition", DEPLOYMENT_FAULTS, ids=lambda c: c.__name__)
def test_a_retry_into_a_paused_queue_names_the_pause_and_its_remedy(condition):
    notice = _retry_notice(_state(AcquisitionPhase.PAUSED, detail="the deployment refused", condition=condition.__name__))

    assert "paused" in notice
    assert _REMEDY_FOR[condition] in notice, "the caller is told nothing it can act on"


def test_a_retry_into_a_queue_paused_by_a_surprise_points_at_the_journal():
    notice = _retry_notice(_state(AcquisitionPhase.PAUSED, detail="database disk image is malformed", condition="OSError"))

    assert "acquisition.queue_error" in notice


# -- the deployment faults, which the caller cannot fix ------------------------
#
# Three conditions refuse acquisition before it starts, and none of them is the
# caller's doing: a full disk, a missing binary, an unset user agent. Each breaks
# EVERY acquisition in the deployment. What every surface owes them is the
# **remedy** — the sentence naming what an operator changes — held once, beside
# the conditions, in `DEPLOYMENT_REMEDIES`.
#
# The journal line is owed by `AcquisitionService`, and is asserted there
# (`test_acquisition_service.py`) by driving `acquire()` with no surface in the
# picture.

#: The environment variable each condition's remedy must name, keyed by the
#: condition. A table rather than three literals in the parametrisation, so the
#: test below can be driven from `DEPLOYMENT_FAULTS` itself while still
#: asserting the one thing that differs per condition — what an operator changes.
_REMEDY_FOR = {
    NotEnoughSpace: "MIN_FREE_BYTES",
    DezoomifyUnavailable: "DEZOOMIFY_PATH",
    SourcePluginUnavailable: "ARTIC_USER_AGENT",
}


def test_every_raise_rather_than_record_condition_has_a_remedy_of_its_own():
    """`service.py` says a new raise-rather-record condition needs a remedy; this asserts it.

    A condition with no entry would pause the queue with nothing to say about
    what ends the pause, and the Work page, Activity › Queue and MCP would all
    show a detail with no remedy beside it.
    """
    assert set(_REMEDY_FOR) == set(DEPLOYMENT_FAULTS), "a condition was added or removed without its operator remedy"
    assert set(DEPLOYMENT_REMEDIES) == {condition.__name__ for condition in DEPLOYMENT_FAULTS}


@pytest.mark.parametrize("condition", DEPLOYMENT_FAULTS, ids=lambda c: c.__name__)
def test_each_remedy_names_what_an_operator_changes(condition):
    """Driven from `DEPLOYMENT_FAULTS`, so the coverage cannot fall behind the set it covers."""
    assert _REMEDY_FOR[condition] in remedy_for(condition.__name__)


def test_an_error_nothing_anticipated_has_no_remedy_to_invent():
    assert remedy_for("OSError") is None


# -- the run listing's cap -------------------------------------------------------


def _runs(count: int, *, kind: RunKind = RunKind.DISCOVERY) -> tuple[DiscoveryRun, ...]:
    """`count` runs, newest first, each carrying prose an operator typed.

    The intent and the strategy are real strings rather than None because they
    are the reason this listing needed a cap at all: every other field on a run
    is short and bounded, and these two grow with what people wrote.
    """
    return tuple(
        DiscoveryRun(
            id=f"r{index}",
            kind=kind,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
            intent_text=f"Find me something restful for the hallway, request {index}",
            strategy=f"I read that as early-twentieth-century landscape painting, attempt {index}",
        )
        for index in range(count)
    )


def _listing(count: int) -> RunListing:
    """What the service would return for a store holding `count` runs."""
    runs = _runs(count)
    return RunListing(runs=runs[:MAX_RUNS_LISTED], total=len(runs))


def test_the_run_listing_is_capped_and_says_how_much_history_it_left_out():
    """The contract's rule on the one listing that had neither a limit nor a notice.

    `api-contract.md § Conditional Patterns`: a truncated result says so
    explicitly and gives the total, never a silent cut. `list_runs` had the
    filters and neither, so a household box that had been discovering art for a
    year returned its whole history in one payload — into a model's context
    window on this surface.
    """
    listing = _listing(MAX_RUNS_LISTED + 12)

    notice = _runs_truncation_notice(listing)

    assert notice is not None
    assert f"{MAX_RUNS_LISTED} most recent of {MAX_RUNS_LISTED + 12} runs" in notice


def test_a_complete_run_listing_says_nothing_about_truncation():
    """Saying nothing is the honest answer when nothing was left behind."""
    assert _runs_truncation_notice(_listing(MAX_RUNS_LISTED - 1)) is None


def test_the_notice_steers_to_the_filters_because_this_action_has_no_offset():
    """Advice a caller cannot act on is the failure this whole family avoids.

    `list_runs` takes `status` and `kind` and no paging parameter, so telling
    someone to page would send them to an argument the action refuses. Both
    filters are on this same action, which is what makes the advice actionable.
    """
    notice = _runs_truncation_notice(_listing(MAX_RUNS_LISTED + 1))

    assert "status=" in notice and "kind=" in notice
    assert "no paging" in notice
    assert "offset" not in notice, "there is no offset on this action; naming one sends a caller to a refusal"


def test_the_capped_rows_are_the_newest_ones():
    """A cap that kept the oldest would bound the payload and answer nobody's question.

    The store returns runs newest-first and the run somebody is looking for is
    nearly always recent, which is the only thing that makes dropping the tail
    acceptable rather than merely cheap.
    """
    listing = _listing(MAX_RUNS_LISTED + 5)

    assert [run.id for run in listing.runs] == [f"r{index}" for index in range(MAX_RUNS_LISTED)]


def test_a_listing_row_drops_the_engine_s_prose_and_keeps_the_operator_s():
    """`api-contract.md § Summary then detail`, applied to the two unbounded fields.

    `strategy` is the engine's reading of the intent in its own words, on every
    row; `action='status'` returns one run in full, which is where a caller goes
    once the listing has told them which run they want. The verbatim `intent`
    stays even though it is unbounded too — it is the only human-readable way to
    tell one run from another, so trimming it would save bytes by making the
    listing stop answering the question it exists for.
    """
    row = _run_summary(_runs(1)[0])

    assert "strategy" not in row
    assert row["intent"] == "Find me something restful for the hallway, request 0"


def test_a_field_added_to_a_run_reaches_the_listing_without_being_added_twice():
    """The summary is the full shape minus a named set, not a second literal shape.

    Written as two literal shapes, a new field would land in one and not the
    other — the drift the candidate-work projections took four coordinated edits
    to maintain before they were collapsed. Asserted by construction: every key
    of the full shape is in the summary except the ones deliberately named.
    """
    run = _runs(1)[0]

    assert set(_run_fields(run)) - set(_run_summary(run)) == _RUN_DETAIL_ONLY
