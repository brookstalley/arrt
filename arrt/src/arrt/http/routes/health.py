"""The route for the health panel."""

from fastapi import APIRouter, Request

from arrt.http.models import (
    BackupOut,
    FailedFetchesOut,
    HealthOut,
    HeartbeatOut,
    PicturesOut,
    PlayerHealthOut,
    SetupStepOut,
    TroubleOut,
    WallHeartbeatOut,
    WatchesHealthOut,
)
from arrt.http.routes.clients import _player_state
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.shapes import _instant
from arrt.http.routes.sources import _source_plugin
from arrt.http.routes.walls import _display_state, _wall_wait
from arrt.persistence.records import BackupReading
from arrt.programming.manifest.heartbeat import HeartbeatReading
from arrt.services.health import FailedFetches, HealthReading, PicturesReading, walls_waiting

router = APIRouter(prefix=API_PREFIX)


@router.get("/health")
def get_health(request: Request) -> HealthOut:
    """Every observation the panel states, read at one instant.

    One service call, not several. Assembling the panel in the handler would make
    "what signals does the panel make" a decision taken in the binding — and the
    next signal would have to be added in two places with nothing to notice if it
    reached only one. The assembly is `HealthService.observe`'s, and this is a
    dispatch.
    """
    return _health(_services(request).health.observe())


def _health(reading: HealthReading) -> HealthOut:
    waiting = walls_waiting(reading.walls, reading.players)
    return HealthOut(
        walls=[
            WallHeartbeatOut(
                wall_id=seen.wall.id,
                wall_name=seen.wall.name,
                heartbeat=_heartbeat(seen.heartbeat),
                display_state=_display_state(seen.state),
                waiting_for=_wall_wait(waiting.get(seen.wall.id)),
            )
            for seen in reading.walls
        ],
        description=reading.describe(),
        backup=_backup(reading.backup),
        sources=[_source_plugin(each) for each in reading.sources],
        pictures=_pictures(reading.pictures),
        watches=WatchesHealthOut(overdue=list(reading.watches.overdue), allowance_spent=reading.watches.allowance_spent),
        players=[
            PlayerHealthOut(client_id=view.client.id, name=view.client.name, state=_player_state(view.player))
            for view in reading.players
        ],
        failed_fetches=None if reading.failed_fetches is None else _failed_fetches(reading.failed_fetches),
        troubles=[
            TroubleOut(about=str(trouble.about), subject=trouble.subject, state=trouble.state, words=trouble.words)
            for trouble in reading.troubles()
        ],
        setup_steps=[
            SetupStepOut(about=str(step.about), subject=step.subject, state=step.state, words=step.words)
            for step in reading.setup_steps()
        ],
    )


def _failed_fetches(found: FailedFetches) -> FailedFetchesOut:
    return FailedFetchesOut(
        count=found.count,
        will_retry=found.will_retry,
        given_up=found.given_up,
        newest_failed_at=_instant(found.newest_failed_at),
        newest_age_seconds=found.newest_age_seconds,
        age_unknown=found.age_unknown,
        description=found.describe(),
    )


def _pictures(reading: PicturesReading) -> PicturesOut:
    return PicturesOut(
        pictures_bytes=reading.pictures_bytes,
        pictures_files=reading.pictures_files,
        age_seconds=reading.age_seconds,
        unreadable=reading.unreadable,
        description=reading.describe(),
    )


def _heartbeat(reading: HeartbeatReading) -> HeartbeatOut:
    return HeartbeatOut(
        path=str(reading.path),
        reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )


def _backup(reading: BackupReading) -> BackupOut:
    return BackupOut(
        path=str(reading.path),
        completed_at=None if reading.completed_at is None else reading.completed_at.isoformat(),
        age_seconds=reading.age_seconds,
        absent=reading.absent,
        problem=reading.problem,
        description=reading.describe(),
        reported=reading.contents,
    )
