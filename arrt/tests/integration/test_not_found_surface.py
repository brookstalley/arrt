"""Not found is 404 on `/api`, every other refusal stays 400, and the Player's routes keep their answers.

`NotFound` (`services/errors.py`) is the one distinction the service layer draws
between its refusals: the caller named a thing, by its id or by the name that is
its identity, that is not there. `app.py`'s handler answers it with 404 in the
one error shape, `{"error": <the service's sentence>}`, and only under `/api`;
a refusal a Player's route meets keeps the contract's 400 (`player-contract.md`,
`contract/transport.json`).
"""

import httpx
import pytest

from arrt.programming.lookups import no_wall
from arrt.services.errors import NotFound

#: One route per kind of thing a person names by its id on `/api`, and the
#: sentence's head the service refuses it with.
MISSING = [
    pytest.param("GET", "/api/works/awk_none", None, "No artwork with id 'awk_none'", id="work"),
    pytest.param("GET", "/api/artists/art_none", None, "No artist with id 'art_none'", id="artist"),
    pytest.param("GET", "/api/themes/thm_none", None, "No theme with id 'thm_none'", id="theme"),
    pytest.param("POST", "/api/walls/wal_none", {"name": "The hall"}, "No wall with id 'wal_none'", id="wall"),
    pytest.param("POST", "/api/clients/cli_none", {"name": "Hall Pi"}, "No client with id 'cli_none'", id="player"),
    pytest.param("GET", "/api/watches/wat_none", None, "No Watch with id 'wat_none'", id="watch"),
    pytest.param("GET", "/api/runs/run_none", None, "No Get with id 'run_none'", id="get"),
    pytest.param("GET", "/api/candidates/cnd_none", None, "No candidate work with id 'cnd_none'", id="candidate"),
    pytest.param("POST", "/api/scenes/scn_none/apply", {"lifetime": "hold"}, "No scene with id 'scn_none'", id="scene"),
    pytest.param("POST", "/api/settings/units", {"value": "metric"}, "There is no setting 'units'", id="setting"),
    pytest.param("DELETE", "/api/affinities/aff_none", None, "No affinity with id 'aff_none'", id="taste"),
]


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.mark.parametrize(("method", "path", "body", "says"), MISSING)
def test_a_thing_that_is_not_there_answers_404_in_the_error_shape(http, method, path, body, says):
    answered = http.request(method, path, json=body)

    assert answered.status_code == 404, answered.text
    assert list(answered.json()) == ["error"]
    assert answered.json()["error"].startswith(says)


def test_a_wall_that_is_not_there_answers_404_with_the_lookups_own_sentence(http):
    """Acceptance 1: the sentence is the one `lookups.no_wall` owns, not one the route wrote."""
    answered = http.delete("/api/walls/wal_none")

    assert (answered.status_code, answered.json()) == (404, {"error": no_wall("wal_none")})


def test_deleting_the_default_theme_is_refused_with_400(http, services):
    """Acceptance 2: the theme is there; what refuses is that it is the default (`test_default_theme.py` holds the words)."""
    default = services.display.add_theme(name="All works")
    services.display.make_default(default.id)

    answered = http.delete(f"/api/themes/{default.id}")

    assert answered.status_code == 400
    assert "is the default" in answered.json()["error"]


def test_a_wall_with_nothing_hanging_is_refused_with_400_not_404(http):
    """The wall is there and only its state refuses, so this is not a not found."""
    wall = http.post("/api/walls", json={"name": "The landing"}).json()

    answered = http.delete(f"/api/walls/{wall['wall_id']}/theme")

    assert answered.status_code == 400
    assert answered.json()["error"].startswith("Nothing is hanging on wall")


def test_a_not_found_a_players_route_meets_keeps_the_contracts_400(server_url, services, monkeypatch):
    """The handler is the application's, so it also catches a refusal on a Player's route; 404 is `/api`'s alone.

    Reached in life only when a client is forgotten between its token's admission
    and the write (`ClientService.record_heartbeat` reads the client again), so the
    write is made to refuse as it would then.
    """
    client = services.clients.add_client(name="Hall Pi")
    token = services.access.issue(client.id).token

    def forgotten(client_id, document):
        raise NotFound(f"No client with id {client_id!r} is recorded.")

    monkeypatch.setattr(services.clients, "record_heartbeat", forgotten)
    answered = httpx.post(
        f"{server_url}/client/heartbeat", json={"outputs": []}, headers={"Authorization": f"Bearer {token}"}, timeout=30.0
    )

    assert answered.status_code == 400
    assert answered.json() == {"error": f"No client with id {client.id!r} is recorded."}
