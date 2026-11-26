"""The routes for the works a person asked a wall not to show again."""

from fastapi import APIRouter, Request

from arrt.http.models import ExcludedWorkListOut, ExcludedWorkOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.services.container import Services

router = APIRouter(prefix=API_PREFIX)


@router.get("/exclusions")
def list_exclusions(request: Request) -> ExcludedWorkListOut:
    """Every work kept off every wall, oldest first. Each is still held."""
    return _exclusions(_services(request))


@router.delete("/exclusions/{artwork_id}")
def allow_again(request: Request, artwork_id: str) -> ExcludedWorkListOut:
    """Let a work kept off every wall go on walls again: the undo, from the work's page.

    Every wall hanging a theme that holds the work takes it back now, as with a
    restored work. Answers with the exclusions that remain.
    """
    services = _services(request)
    services.display.allow_work(artwork_id)
    return _exclusions(services)


def _exclusions(services: Services) -> ExcludedWorkListOut:
    return ExcludedWorkListOut(
        exclusions=[
            ExcludedWorkOut(artwork_id=exclusion.artwork_id, excluded_at=exclusion.excluded_at.isoformat())
            for exclusion in services.display.excluded_works()
        ]
    )
