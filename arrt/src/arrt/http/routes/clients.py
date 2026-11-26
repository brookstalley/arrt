"""The routes for the Players the server knows: add, rename, remove and issue a token."""

from fastapi import APIRouter, Request

from arrt.http.models import (
    ClientHeartbeatOut,
    ClientListOut,
    ClientOut,
    ClientTokenOut,
    ClientWallOut,
    LabelOutputOut,
    NameClient,
    OutputStateOut,
    PlayerStateOut,
    ReportedLabelOutputOut,
    ReportedOutputOut,
)
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.shapes import _instant
from arrt.http.routes.walls import _display, _fault
from arrt.programming.clients import ClientView, PlacementSurvey
from arrt.programming.player_state import PlayerReading
from arrt.services.container import Services

router = APIRouter(prefix=API_PREFIX)


@router.get("/clients")
def list_clients(request: Request) -> ClientListOut:
    """Every client, with its walls and what it last reported about its outputs."""
    return _clients(_services(request))


@router.post("/clients")
def add_client(request: Request, body: NameClient) -> ClientOut:
    """Record a client. It has no token until one is issued."""
    services = _services(request)
    added = services.clients.add_client(name=body.name)
    return _one_client(services, added.id)


@router.post("/clients/{client_id}")
def rename_client(request: Request, client_id: str, body: NameClient) -> ClientOut:
    """Rename a client. Its token and its walls are unchanged."""
    services = _services(request)
    services.clients.rename_client(client_id, name=body.name)
    return _one_client(services, client_id)


@router.delete("/clients/{client_id}")
def remove_client(request: Request, client_id: str) -> ClientListOut:
    """Forget a client. Its token stops working and its walls become unassigned."""
    services = _services(request)
    services.clients.remove_client(client_id)
    return _clients(services)


@router.post("/clients/{client_id}/token")
def issue_client_token(request: Request, client_id: str) -> ClientTokenOut:
    """Issue the client's token, replacing any it had. It is shown here once.

    Nothing can read it back afterwards, because only a verifier is kept. The
    host puts it in the Player's environment file.
    """
    issued = _services(request).access.issue(client_id)
    return ClientTokenOut(client_id=issued.client_id, token=issued.token, token_issued_at=issued.issued_at.isoformat())


def _clients(services: Services) -> ClientListOut:
    """Every Player's answer, from one reading taken now (`ClientService.read_clients`)."""
    reading = services.clients.read_clients()
    return ClientListOut(clients=[_client(view, reading.survey) for view in reading.views])


def _one_client(services: Services, client_id: str) -> ClientOut:
    """One Player's answer, from a reading of it taken now: after the act that answers with it has written."""
    reading = services.clients.read_clients(client_id)
    [view] = reading.views
    return _client(view, reading.survey)


def _client(view: ClientView, survey: PlacementSurvey) -> ClientOut:
    """One Player's answer, every part of it from `survey`, the one reading `view` was built from (`ClientsReading`)."""
    client = view.client
    reading = view.heartbeat
    return ClientOut(
        client_id=client.id,
        name=client.name,
        created_at=client.created_at.isoformat(),
        token_issued_at=None if client.token_issued_at is None else client.token_issued_at.isoformat(),
        walls=[ClientWallOut(wall_id=shown.wall.id, name=shown.wall.name, output=shown.display.output) for shown in view.walls],
        displays=[_display(display, survey) for display in view.displays],
        label_outputs=[
            LabelOutputOut(label_id=label.id, output=label.output, wall_id=label.wall_id) for label in view.label_outputs
        ],
        faults=[_fault(fault) for fault in view.faults],
        heartbeat=ClientHeartbeatOut(
            reported_at=None if reading.reported_at is None else reading.reported_at.isoformat(),
            age_seconds=reading.age_seconds,
            absent=reading.absent,
            problem=reading.problem,
            description=reading.describe(),
            outputs=[
                ReportedOutputOut(
                    name=output.name,
                    kind=output.kind,
                    connected=output.connected,
                    screen=None if output.screen is None else list(output.screen),
                    identity=output.identity,
                )
                for output in reading.outputs
            ],
            label_outputs=[
                ReportedLabelOutputOut(
                    name=label.name,
                    kind=label.kind,
                    connected=label.connected,
                    size=None if label.size is None else list(label.size),
                )
                for label in reading.label_outputs
            ],
        ),
        state=_player_state(view.player),
        settings_url=reading.settings_url,
    )


def _player_state(reading: PlayerReading) -> PlayerStateOut:
    return PlayerStateOut(
        state=str(reading.state),
        since=_instant(reading.since),
        outputs=[
            OutputStateOut(kind=str(output.kind), name=output.name, state=str(output.state), connected=output.connected)
            for output in reading.outputs
        ],
    )
