"""The route for the Library's history of events."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from arrt.http.models import HistoryEventOut, HistoryPageOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.services.catalogue import DEFAULT_LIST_LIMIT
from arrt.persistence.records import HistoryEvent

router = APIRouter(prefix=API_PREFIX)


@router.get("/history")
def list_history(
    request: Request,
    kind: Annotated[list[str] | None, Query()] = None,
    wall_id: Annotated[str | None, Query()] = None,
    artwork_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query()] = 0,
) -> HistoryPageOut:
    """What happened, newest first: Gets started and finished, verdicts, archives, restores, hangs.

    `kind` repeats, and any of those named matches (`?kind=work.accepted&kind=
    work.rejected`); none named is every kind. `wall_id` narrows to one wall's
    history: what was hung there, and what was kept off from there. `artwork_id`
    narrows to one work's: the Get it was accepted from, its archive and restore,
    and what kept it off walls; both together are what both name. Events are
    recorded from the day the history arrived, and nothing earlier is recovered.
    """
    page = _services(request).catalogue.list_events(
        kinds=kind or (), wall_id=wall_id, work_id=artwork_id, limit=limit, offset=offset
    )
    return HistoryPageOut(
        events=[_history_event(event) for event in page.events],
        total=page.total,
        # The service's default, stated so a reader can page without guessing it.
        limit=DEFAULT_LIST_LIMIT if limit is None else limit,
        offset=offset,
    )


def _history_event(event: HistoryEvent) -> HistoryEventOut:
    return HistoryEventOut(
        event_id=event.id,
        kind=str(event.kind),
        occurred_at=event.occurred_at.isoformat(),
        artwork_id=event.work_id,
        run_id=event.run_id,
        wall_id=event.wall_id,
        theme_id=event.theme_id,
        detail=dict(event.detail or {}),
    )
