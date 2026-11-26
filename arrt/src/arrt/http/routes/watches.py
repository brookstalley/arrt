"""The routes for watches: what a discovery run is set to look for on a schedule."""

from fastapi import APIRouter, Request

from arrt.http.models import CreateWatch, UpdateWatch, WatchListOut, WatchOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.services.watches import WatchService
from arrt.persistence.discovery_records import InitiatedBy, Watch

router = APIRouter(prefix=API_PREFIX)


@router.get("/watches")
def list_watches(request: Request) -> WatchListOut:
    """Every Watch, in the order the household wrote them. Unpaged: a household's Watches are a handful."""
    services = _services(request)
    return WatchListOut(watches=[_watch(services.watches, watch) for watch in services.watches.list()])


@router.get("/watches/{watch_id}")
def get_watch(request: Request, watch_id: str) -> WatchOut:
    service = _services(request).watches
    return _watch(service, service.get(watch_id))


@router.post("/watches")
def create_watch(request: Request, body: CreateWatch) -> WatchOut:
    """Write a new Watch. Refused, by name, for empty words, an unknown cadence, or a cap above the allowance."""
    service = _services(request).watches
    created = service.create(
        intent_text=body.intent_text,
        cadence=body.cadence,
        monthly_cap_usd=body.monthly_cap_usd,
        enabled=body.enabled,
        surface=InitiatedBy.WEB_UI,
    )
    return _watch(service, created)


@router.post("/watches/{watch_id}")
def update_watch(request: Request, watch_id: str, body: UpdateWatch) -> WatchOut:
    """Change what the body gives and leave the rest. `POST`, as this surface writes everywhere."""
    service = _services(request).watches
    updated = service.update(
        watch_id,
        intent_text=body.intent_text,
        cadence=body.cadence,
        monthly_cap_usd=body.monthly_cap_usd,
        enabled=body.enabled,
        surface=InitiatedBy.WEB_UI,
    )
    return _watch(service, updated)


@router.delete("/watches/{watch_id}")
def delete_watch(request: Request, watch_id: str) -> WatchOut:
    """Remove a Watch and answer with what was removed. What it found stays in To review."""
    service = _services(request).watches
    return _watch(service, service.delete(watch_id, surface=InitiatedBy.WEB_UI))


def _watch(service: WatchService, watch: Watch) -> WatchOut:
    standing = service.standing(watch)
    return WatchOut(
        watch_id=watch.id,
        intent_text=watch.intent_text,
        enabled=watch.enabled,
        cadence=watch.cadence,
        effective_cadence=str(service.cadence_of(watch)),
        monthly_cap_usd=None if watch.monthly_cap_usd is None else f"{watch.monthly_cap_usd:.2f}",
        effective_cap_usd=f"{service.effective_cap(watch):.2f}",
        created_at=watch.created_at.isoformat(),
        created_by=str(watch.created_by),
        updated_at=watch.updated_at.isoformat(),
        updated_by=str(watch.updated_by),
        last_attempt_at=None if watch.last_attempt_at is None else watch.last_attempt_at.isoformat(),
        last_run_id=watch.last_run_id,
        last_run_status=None if standing.last_run_status is None else str(standing.last_run_status),
        last_refusal=watch.last_refusal,
        next_due_at=None if standing.next_due_at is None else standing.next_due_at.isoformat(),
        overdue=standing.overdue,
        in_flight=standing.in_flight,
        spent_usd=f"{standing.spent_usd:.2f}",
        sentence=standing.sentence,
        summary=standing.summary,
    )
