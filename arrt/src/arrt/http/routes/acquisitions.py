"""The acquisition queue's routes: what is owed an image, why a fetch failed, and the retry of one work or one cause."""

from collections.abc import Callable, Sequence
from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import (
    AcquisitionQueueOut,
    AcquisitionStateOut,
    CauseWorksOut,
    FailureCauseOut,
    FailureCausesOut,
    QueuedWorkOut,
    QueuePauseOut,
    RefusedRetryOut,
    RetryCause,
    RetryCauseOut,
)
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.acquisition.queue import AcquisitionState, FailureCause, QueueEntry, QueuePause
from arrt.library.services.catalogue import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
from arrt.services.errors import ServiceError

router = APIRouter(prefix=API_PREFIX)


@router.post("/works/{artwork_id}/acquisition/retry")
def retry_acquisition(request: Request, artwork_id: str) -> AcquisitionStateOut:
    """Forget the work's failures and put it at the front of the acquisition queue.

    Fetches nothing in the request: a tiled fetch may take half an hour, and the
    queue fetches one work at a time. Answers with where the work now stands.
    """
    return _acquisition(_services(request).acquisition_queue.retry(artwork_id))


@router.get("/acquisitions")
def list_acquisitions(
    request: Request,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> AcquisitionQueueOut:
    """The queue's pause if any, then one page of the works still in line, in the order it will try them.

    A work that failed or was given up on is listed under its cause instead
    (`/acquisitions/causes`), so thousands of works failing for one reason are
    one row there rather than thousands here; this answer counts them.
    """
    listing = _services(request).acquisition_queue.listing()
    in_line = listing.in_line
    limit, page = _queue_page(in_line, limit, offset)
    return AcquisitionQueueOut(
        pause=None if listing.pause is None else _queue_pause(listing.pause),
        works=[_queued_work(entry) for entry in page],
        total=len(in_line),
        limit=limit,
        offset=offset,
        failing=listing.failing,
        causes=listing.cause_count,
    )


@router.get("/acquisitions/causes")
def list_failure_causes(
    request: Request,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> FailureCausesOut:
    """Every reason the queue's failed works failed for, one row each with how many, the largest first.

    Grouped by the reason's words with the work's own name taken out, so works
    that failed the same way share a row whatever they are called.
    """
    services = _services(request)
    causes = services.acquisition_queue.listing().causes
    limit, page = _queue_page(causes, limit, offset)
    return FailureCausesOut(
        causes=[_failure_cause(each, services.health.museum_of) for each in page], total=len(causes), limit=limit, offset=offset
    )


@router.get("/acquisitions/causes/works")
def list_cause_works(
    request: Request,
    cause: Annotated[str, Query()],
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> CauseWorksOut:
    """One page of the works that failed for `cause`, worded as `/acquisitions/causes` words it.

    A cause no work holds any more answers with no works rather than a refusal:
    the group emptied because the queue tried them again, which is not an error.
    """
    group = next((each for each in _services(request).acquisition_queue.listing().causes if each.cause == cause), None)
    entries = () if group is None else group.entries
    limit, page = _queue_page(entries, limit, offset)
    return CauseWorksOut(
        cause=cause, works=[_queued_work(entry) for entry in page], total=len(entries), limit=limit, offset=offset
    )


@router.post("/acquisitions/causes/retry")
def retry_failure_cause(request: Request, body: RetryCause) -> RetryCauseOut:
    """A cause's Retry (Queue's *Retry 3*): every work that failed for `cause`, in one request, fetching nothing in it.

    Each is put back in line as its own Retry would put it; one the queue
    refuses (no source, being fetched now) is counted under why, naming no work.
    """
    result = _services(request).acquisition_queue.retry_cause(body.cause)
    return RetryCauseOut(
        cause=result.cause,
        retried=result.retried,
        refused=[RefusedRetryOut(reason=reason, works=count) for reason, count in result.refused.items()],
    )


def _acquisition(state: AcquisitionState) -> AcquisitionStateOut:
    return AcquisitionStateOut(
        artwork_id=state.artwork_id,
        phase=str(state.phase),
        failures=state.failures,
        detail=state.detail,
        next_try_at=None if state.next_try_at is None else state.next_try_at.isoformat(),
        since=None if state.since is None else state.since.isoformat(),
        condition=state.condition,
        remedy=state.remedy,
        outcome=None if state.outcome is None else str(state.outcome),
        plugin=state.plugin,
        failed_at=None if state.failed_at is None else state.failed_at.isoformat(),
    )


def _queue_pause(pause: QueuePause) -> QueuePauseOut:
    return QueuePauseOut(condition=pause.condition, detail=pause.detail, since=pause.since.isoformat(), remedy=pause.remedy)


def _queued_work(entry: QueueEntry) -> QueuedWorkOut:
    return QueuedWorkOut(title=entry.title, acquisition=_acquisition(entry.state))


def _failure_cause(group: FailureCause, museum_of: Callable[[str], str]) -> FailureCauseOut:
    return FailureCauseOut(
        cause=group.cause,
        works=len(group.entries),
        failed=group.failed,
        gave_up=group.gave_up,
        outcome=None if group.outcome is None else str(group.outcome),
        plugin=group.plugin,
        museum=None if group.plugin is None else museum_of(group.plugin),
    )


def _queue_page[T](items: Sequence[T], limit: int | None, offset: int) -> tuple[int, Sequence[T]]:
    """One page of a queue listing, at the service's default size and within its cap, as the other listings page.

    The listing is built whole and sliced here: the queue owes a few thousand
    works at most, and grouping by cause needs every one of them in hand.
    """
    resolved = DEFAULT_LIST_LIMIT if limit is None else limit
    if not 1 <= resolved <= MAX_LIST_LIMIT:
        raise ServiceError(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {resolved}.")
    if offset < 0:
        raise ServiceError(f"offset cannot be negative, got {offset}.")
    return resolved, items[offset : offset + resolved]
