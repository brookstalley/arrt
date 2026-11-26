"""The routes for discovery runs and the money they spend: runs, gets, the estimate, the budget and the spend ledger."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import (
    BudgetOut,
    CandidatePageOut,
    CostTiersOut,
    EstimateOut,
    GetOut,
    RunListOut,
    RunOut,
    RunTallyOut,
    RunViewOut,
    SearchUsageOut,
    SkippedOut,
    SpendByCategoryOut,
    SpendHistoryOut,
    SpendMonthOut,
    SpendOnGetOut,
    SpendOut,
    StartGet,
    StartResolve,
    StartRun,
    UnknownCostCallOut,
)
from arrt.http.routes.candidates import _candidate_card, _candidate_work
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.services import spend_history
from arrt.library.services.discovery import DiscoveryService
from arrt.library.services.review import CandidatePage
from arrt.library.services.runner import Estimate, RunView, SpendReport
from arrt.library.services.spending import CENTS_BELOW, DIMES_BELOW
from arrt.persistence.discovery_records import DiscoveryRun, InitiatedBy

router = APIRouter(prefix=API_PREFIX)


@router.get("/estimate")
def get_estimate(request: Request, run_id: Annotated[str | None, Query()] = None) -> EstimateOut:
    """What a search would cost, before anyone commits to it.

    Answered without a run id for "what does asking cost", and with one for "what
    does resolving what this run found cost". Estimating spends nothing, which is
    what lets a Get's approval gate, and an agent over MCP, show the price before
    the decision rather than after it.
    """
    return _estimate(_services(request).runner.estimate(run_id))


@router.get("/budget")
def get_budget(request: Request) -> BudgetOut:
    """What is left of this month's budget, for the sidebar, read from the provider's key.

    Always a 200: `state` says how the figure is known, or why there is none.
    Display only, and up to a minute old; the provider's own refusal at its
    limit is what stops spending. The tier boundaries ride along so every
    spending control words its estimate the same way.
    """
    view = _services(request).budget.view()
    return BudgetOut(
        state=str(view.state),
        remaining_usd=_usd(view.remaining_usd),
        budget_usd=_usd(view.budget_usd),
        spent_usd=_usd(view.spent_usd),
        note=view.note,
        tiers=CostTiersOut(cents_below_usd=str(CENTS_BELOW), dimes_below_usd=str(DIMES_BELOW)),
    )


def _usd(amount: Decimal | None) -> str | None:
    return None if amount is None else str(amount)


@router.post("/runs")
def start_run(request: Request, body: StartRun) -> RunOut:
    """Begin a discovery run and return its handle at once.

    Phase 1 proceeds on a worker behind this response. Waiting for it here would
    hold the request open for the minutes the search takes, which no browser will
    sit through — so the client is handed an id and follows it.
    """
    services = _services(request)
    return _run(
        services.runner.start(
            intent_text=body.intent,
            # Provenance, never authorisation: every surface has identical
            # authority, and this records which one asked so that "who wanted
            # forty Dalí candidates" is answerable from the data afterwards.
            initiated_by=InitiatedBy.WEB_UI,
        ),
        services.discovery,
    )


@router.post("/gets")
def start_get(request: Request, body: StartGet) -> GetOut:
    """Get the works these Wikidata items name, and say which were skipped.

    Returns at once with the run, which looks for images behind the response as
    any run does. Held items, items a Get is already looking for, and items the
    registry does not have are skipped and listed rather than refused.

    With a `theme_id`, the accepted works join that theme instead of the
    default. Two calls composed, with no branch on the first's answer:
    Programming says the theme exists (refusing an unknown one, so nothing
    starts), and the Library starts the Get.
    """
    services = _services(request)
    destination = None if body.theme_id is None else services.display.get_listed_theme(body.theme_id).id
    outcome = services.get.start(body.qids, initiated_by=InitiatedBy.WEB_UI, destination_theme_id=destination)
    return GetOut(
        run=None if outcome.run is None else _run(outcome.run, services.discovery),
        skipped=[SkippedOut(qid=entry.qid, reason=str(entry.reason)) for entry in outcome.skipped],
    )


@router.get("/runs")
def list_runs(
    request: Request,
    status: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    awaiting: Annotated[bool, Query()] = False,  # noqa: FBT002 -- a query parameter FastAPI passes by name
) -> RunListOut:
    """The newest runs, optionally narrowed, capped in the service layer.

    **`status` and `kind` are filters, not limits.** Omit both and this asked for
    the whole `discovery_runs` table — one row per search plus one per re-search,
    for ever, with nothing pruning them. What made it tolerable was a fact about
    the deployment rather than a mechanism: one household, one operator, so a
    year of use is hundreds of rows. A real bound, but an editorial one, and it
    stopped holding the moment this surface served anything else.

    The cap is `RunnerService.list_runs`', not this handler's, so this surface
    and the MCP twin cannot come to disagree about how much history exists —
    which is what the note here used to warn would happen if either were fixed
    alone. Both now read the same bound and report the same total.

    **There is still no paging parameter**, and that is a smaller gap than the
    one just closed: `total` says what was left out, and the two filters are how
    a caller reaches it. A `limit`/`offset` pair would change the contract of a
    shipped surface and earns its own review rather than riding along here.
    """
    services = _services(request)
    listing = services.runner.list_runs(status=status, kind=kind, awaiting=awaiting)
    return RunListOut(
        runs=[_run(run, services.discovery) for run in listing.runs],
        awaiting_works=listing.awaiting_works,
        awaiting={run.id: listing.awaiting[run.id] for run in listing.runs if run.id in listing.awaiting},
        count=len(listing.runs),
        total=listing.total,
        truncated=listing.truncated,
    )


@router.get("/runs/{run_id}")
def get_run(request: Request, run_id: str) -> RunViewOut:
    """Where a run is, answered immediately rather than held open.

    **The MCP surface long-polls here and this one deliberately does not.** A
    model calls `status` once and waits, so holding the call is what keeps it
    from spinning. A browser is already an event loop: it polls on a timer, and a
    held request would occupy one of the worker threads Starlette runs these
    synchronous handlers in for the whole hold window — with a couple of tabs
    open that starves the same pool that serves thumbnails. The client asks
    again; nothing is lost but the hold.
    """
    services = _services(request)
    return _run_view(services.runner.run_status(run_id, wait=False), services.discovery)


@router.post("/runs/{run_id}/approve")
def approve_run(request: Request, run_id: str) -> RunViewOut:
    """Accept the work list and its price; phase 2 begins behind the response."""
    services = _services(request)
    return _run_view(services.runner.approve(run_id), services.discovery)


@router.post("/runs/{run_id}/decline")
def decline_run(request: Request, run_id: str) -> RunViewOut:
    """Refuse the work list. The run ends without phase 2 ever spending."""
    services = _services(request)
    return _run_view(services.runner.decline(run_id), services.discovery)


@router.post("/runs/{run_id}/cancel")
def cancel_run(request: Request, run_id: str) -> RunViewOut:
    """Stop a run from wherever it is. Money already spent stays recorded."""
    services = _services(request)
    return _run_view(services.runner.cancel(run_id), services.discovery)


@router.get("/spend")
def get_spend_history(request: Request) -> SpendHistoryOut:
    """Months of spending, newest first: where it went, which Gets spent it, and the calls whose cost is unknown."""
    return _spend_history(spend_history.read(_services(request).discovery))


@router.get("/runs/{run_id}/spend")
def get_run_spend(request: Request, run_id: str) -> SpendOut:
    """What a run has actually cost, including every re-search descended from it."""
    return _spend(_services(request).runner.spend_report(run_id=run_id))


@router.post("/runs/resolve")
def start_resolve_run(request: Request, body: StartResolve) -> RunOut:
    """Look again for images of works whose scans the curator turned down.

    A re-search is a run, which is what lets the run view follow it with nothing
    special to know — `status`, `cancel` and `spend` all take its id. The handle
    comes back at once and the search proceeds behind it, exactly as `start` does
    and for the same reason: this takes minutes.

    **Where it is registered is not what makes this safe** — the paths
    do not overlap, since nothing serves `POST /api/runs/{id}`. It sits here
    because it is the third way a run begins and belongs beside the other two.
    """
    services = _services(request)
    return _run(
        services.runner.resolve_images(
            candidate_work_ids=body.work_ids,
            initiated_by=InitiatedBy.WEB_UI,
        ),
        services.discovery,
    )


@router.get("/runs/{run_id}/candidates")
def list_candidates(
    request: Request,
    run_id: str,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> CandidatePageOut:
    """A page of the works a run is responsible for, each with a picture.

    Paged where the run view's own work list is not, and the difference is the
    payload rather than an inconsistency: that list is text, and this one carries
    a card per work. A curator scrolls a grid; they do not scroll two hundred
    pictures fetched at once on a Pi.
    """
    # `pictures=False`: this surface fetches each picture by URL, so inlining
    # them here would re-encode thirty images per page and discard the output.
    services = _services(request)
    return _candidate_page(services.review.list_works(run_id, limit=limit, offset=offset, pictures=False), services.discovery)


def _run(run: DiscoveryRun, discovery: DiscoveryService) -> RunOut:
    return RunOut(
        run_id=run.id,
        kind=str(run.kind),
        status=str(run.status),
        is_terminal=run.status.is_terminal,
        initiated_by=str(run.initiated_by),
        intent=run.intent_text,
        strategy=run.strategy,
        approval_required=run.approval_required,
        estimated_cost_usd=None if run.estimated_cost_usd is None else str(run.estimated_cost_usd),
        actual_cost_usd=None if run.actual_cost_usd is None else str(run.actual_cost_usd),
        summary=discovery.run_summary(run),
        unresolved_work_count=run.unresolved_work_count,
        parent_run_id=run.parent_run_id,
        started_at=run.started_at.isoformat(),
        completed_at=None if run.completed_at is None else run.completed_at.isoformat(),
        destination_theme_id=run.destination_theme_id,
        end_reason=run.end_reason,
        watch_id=run.watch_id,
    )


def _run_view(view: RunView, discovery: DiscoveryService) -> RunViewOut:
    """A run with its works and both of its tallies.

    Every figure is read off the view's own properties rather than recomputed
    here. The counts and the list they describe would otherwise be two
    derivations of one fact, and the second is the one that goes wrong — which is
    not hypothetical: a run-level figure computed as `len(works)` beside a view
    that counted provenance apart is exactly the defect that reached a review.
    """
    return RunViewOut(
        run=_run(view.run, discovery),
        tally=RunTallyOut(
            total=view.work_count,
            proposed=view.proposed_count,
            offered=view.offered_count,
            chosen=view.chosen_count,
            resolved=view.resolved,
            resolved_proposals=view.resolved_proposals,
            unresolved=view.unresolved,
            pending=view.pending,
        ),
        works=[_candidate_work(work) for work in view.works],
        searches=SearchUsageOut(
            used=view.searches_used,
            allowance=view.search_allowance,
            exhausted=view.searches_exhausted,
        ),
        image_resolution_available=view.image_resolution_available,
    )


def _candidate_page(page: CandidatePage, discovery: DiscoveryService) -> CandidatePageOut:
    return CandidatePageOut(
        run=_run(page.run, discovery),
        works=[_candidate_card(entry) for entry in page.entries],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        # The page's own property, not `offset + len(works) < total` recomputed
        # here. Two derivations of one fact is how a grid comes to promise a next
        # page that does not exist, and the second derivation is the wrong one.
        truncated=page.truncated,
    )


def _estimate(estimate: Estimate) -> EstimateOut:
    return EstimateOut(
        phase=estimate.phase,
        # A string rather than a float, for the same reason the MCP surface does
        # it: a price through binary floating point comes back as
        # 0.12699999999999999.
        estimated_cost_usd=str(estimate.cost_usd),
        tier=str(estimate.tier),
        basis=estimate.basis,
        run_id=estimate.run_id,
    )


def _spend(report: SpendReport) -> SpendOut:
    return SpendOut(
        scope=report.scope,
        cost_usd=str(report.cost_usd),
        run_id=report.run_id,
        year=report.year,
        month=report.month,
        unknown_cost_calls=report.unknown_cost_calls,
        summary=report.summary,
    )


def _spend_history(history: spend_history.SpendHistory) -> SpendHistoryOut:
    return SpendHistoryOut(
        months=[
            SpendMonthOut(
                year=month.year,
                month=month.month,
                cost_usd=str(month.total.cost_usd),
                unknown_cost_calls=month.total.unknown_calls,
                summary=month.total.words,
                categories=[
                    SpendByCategoryOut(
                        category=str(each.category),
                        calls=each.calls,
                        cost_usd=str(each.total.cost_usd),
                        unknown_cost_calls=each.total.unknown_calls,
                        summary=each.total.words,
                    )
                    for each in month.categories
                ],
                gets=[
                    SpendOnGetOut(
                        run_id=each.run.id,
                        kind=str(each.run.kind),
                        intent=each.run.intent_text,
                        watch_id=each.run.watch_id,
                        started_at=each.run.started_at.isoformat(),
                        calls=each.calls,
                        cost_usd=str(each.total.cost_usd),
                        unknown_cost_calls=each.total.unknown_calls,
                        summary=each.total.words,
                    )
                    for each in month.gets
                ],
                unknown_calls=[
                    UnknownCostCallOut(
                        spend_id=call.spend_id,
                        category=str(call.category),
                        occurred_at=call.occurred_at.isoformat(),
                        model_id=call.model_id,
                        run_id=call.run_id,
                    )
                    for call in month.unknown_calls
                ],
            )
            for month in history.months
        ],
        older_months=history.older_months,
    )
