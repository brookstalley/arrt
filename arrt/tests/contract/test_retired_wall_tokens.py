"""A token issued under the retired per-wall scheme opens nothing, on a catalogue that held one.

The server here is booted over a catalogue written in the wall-token shape, its
wall carrying the verifier of a token a Player really held, and upgraded by the
ordinary open. That is the one deployment's situation on the day this ships: its
Player still has the wall token in its environment file. It must be refused as
unauthenticated everywhere, and the wall itself must survive to be assigned to a
client.
"""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from arrt.persistence.durable import SqliteDurableStore
from arrt.persistence.file import open_catalogue_file
from arrt.programming.access import Admission, verifier_of

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]

#: The token a Player configured before 2026-10-02 carries as `WALL_TOKEN`.
FORMER_WALL_TOKEN = "a-wall-token-issued-before-clients"

_MOMENT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC).isoformat()


@pytest.fixture
def catalogue_file(tmp_path) -> Iterator[SqliteDurableStore]:
    """The wall-token catalogue, opened (and so upgraded) the way the plane opens it."""
    path = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
            CREATE TABLE walls (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                token_verifier TEXT, token_issued_at TEXT
            );
            CREATE TABLE directives (
                wall_id TEXT PRIMARY KEY REFERENCES walls(id), sequence INTEGER NOT NULL, pinned_work_id TEXT
            );
            """)
        connection.execute(
            "INSERT INTO walls VALUES ('w-living', 'Living room', ?, ?, ?)",
            (_MOMENT, verifier_of(FORMER_WALL_TOKEN), _MOMENT),
        )
        connection.execute("INSERT INTO directives VALUES ('w-living', 3, NULL)")
        connection.commit()
    finally:
        connection.close()
    opened = open_catalogue_file(path)
    yield opened
    opened.close()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_former_wall_token_is_unauthenticated_on_every_route(server_url, wall_id):
    assert wall_id == "w-living", "the upgraded catalogue keeps the wall the Player was configured for"
    requests = {
        "client": lambda url: httpx.get(url, headers=_bearer(FORMER_WALL_TOKEN)),
        "client_heartbeat": lambda url: httpx.post(
            url, json={"reported_at": "2026-10-02T12:00:00Z", "outputs": []}, headers=_bearer(FORMER_WALL_TOKEN)
        ),
        "manifest": lambda url: httpx.get(url, headers=_bearer(FORMER_WALL_TOKEN)),
        "media": lambda url: httpx.get(url, headers=_bearer(FORMER_WALL_TOKEN)),
        "heartbeat": lambda url: httpx.post(
            url, json={"reported_at": "2026-10-02T12:00:00+00:00"}, headers=_bearer(FORMER_WALL_TOKEN)
        ),
        "label": lambda url: httpx.get(url, headers=_bearer(FORMER_WALL_TOKEN)),
    }
    assert set(requests) == set(ROUTES), "every route the contract names is asked"

    for name, send in requests.items():
        url = server_url + ROUTES[name]["path"].format(wall_id=wall_id, sha256="0" * 64, label_id="some-label")
        assert send(url).status_code == 401, name


def test_the_access_service_does_not_know_the_former_token(services, wall_id):
    assert services.access.admit(wall_id, FORMER_WALL_TOKEN) is Admission.UNKNOWN
    assert services.access.identify(FORMER_WALL_TOKEN) is None


def test_the_wall_survives_and_a_client_token_opens_it(server_url, services, wall_id):
    client = services.clients.add_client(name="The Pi")
    services.clients.assign_wall(wall_id, client_id=client.id, output="frame")
    token = services.access.issue(client.id).token

    response = httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(token))

    display = services.clients.placement_of(wall_id).display
    assert response.json()["walls"] == [{"wall_id": "w-living", "name": "Living room", "output": "frame", "display": display.id}]
    heartbeat = server_url + ROUTES["heartbeat"]["path"].format(wall_id=wall_id)
    assert httpx.post(heartbeat, json={"reported_at": "2026-10-02T12:00:00+00:00"}, headers=_bearer(token)).status_code == 204
