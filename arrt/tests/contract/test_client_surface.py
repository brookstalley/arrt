"""A client's two routes, and the curator's client routes, over real HTTP.

`GET /client` tells a client which walls are its and on which outputs;
`POST /client/heartbeat` is how it reports those outputs. Both are judged against
`contract/schemas/client.v1.schema.json` and `client-heartbeat.v1.schema.json`
and their fixtures, so the server and a Player in another repository agree on
them without either importing the other. The curator's routes under `/api` are
the bindings Settings › Clients uses.
"""

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from arrt.programming import client_heartbeat
from arrt.programming.client_heartbeat import client_heartbeat_path_in

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]
INDEX = json.loads((CONTRACT / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]
HEARTBEATS = [row for row in INDEX if row["schema"] == "schemas/client-heartbeat.v1.schema.json"]


def _schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((CONTRACT / "schemas" / name).read_text(encoding="utf-8")))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _fixture(relative: str) -> dict:
    return json.loads((CONTRACT / relative).read_text(encoding="utf-8"))


@pytest.fixture
def hall_pi(services, wall_id):
    """A client driving the established wall and a second one, with a third wall that is not its."""
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    landing = services.display.add_wall(name="Landing")
    services.clients.assign_wall(landing.id, client_id=client.id, output="hdmi-a-2")
    services.display.add_wall(name="Study")
    return client


@pytest.fixture
def token(services, hall_pi) -> str:
    return services.access.issue(hall_pi.id).token


@pytest.fixture
def client_url(server_url) -> str:
    return server_url + ROUTES["client"]["path"]


@pytest.fixture
def heartbeat_url(server_url) -> str:
    return server_url + ROUTES["client_heartbeat"]["path"]


# -- GET /client ------------------------------------------------------------------------


def test_the_client_document_lists_its_own_walls_and_outputs_and_no_others(client_url, token, hall_pi, wall_id, services):
    response = httpx.get(client_url, headers=_bearer(token))

    assert response.status_code == 200
    document = response.json()
    assert _schema("client.v1.schema.json").is_valid(document)
    assert (document["client_id"], document["name"]) == (hall_pi.id, "The Pi in the hall")
    landing = next(wall for wall in services.display.survey_walls() if wall.wall.name == "Landing").wall
    assert document["walls"] == [
        {"wall_id": landing.id, "name": "Landing", "output": "hdmi-a-2"},
        {"wall_id": wall_id, "name": services.display.get_wall(wall_id).name, "output": "hdmi-a-1"},
    ]
    assert "Study" not in response.text


def test_a_client_with_no_walls_gets_an_empty_list(client_url, services):
    idle = services.clients.add_client(name="A spare Pi")
    response = httpx.get(client_url, headers=_bearer(services.access.issue(idle.id).token))

    assert response.status_code == 200
    assert response.json() == {"client_id": idle.id, "name": "A spare Pi", "walls": []}


def test_the_client_document_is_etagged_and_answers_304_until_an_assignment_changes(
    client_url, token, hall_pi, services, wall_id
):
    first = httpx.get(client_url, headers=_bearer(token))
    etag = first.headers["etag"]
    assert etag == f'"{hashlib.sha256(first.content).hexdigest()}"'

    unchanged = httpx.get(client_url, headers={**_bearer(token), "If-None-Match": etag})
    assert unchanged.status_code == 304
    assert unchanged.content == b""

    services.clients.unassign_wall(wall_id)
    changed = httpx.get(client_url, headers={**_bearer(token), "If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
    assert wall_id not in changed.text


def test_the_client_route_refuses_without_a_valid_client_token(client_url, token):
    assert httpx.get(client_url).status_code == 401
    assert httpx.get(client_url, headers=_bearer("not-a-token")).status_code == 401
    assert httpx.get(client_url, headers={"Authorization": f"Basic {token}"}).status_code == 401


# -- POST /client/heartbeat -------------------------------------------------------------


def test_a_client_heartbeat_is_written_beside_the_wall_heartbeats(heartbeat_url, token, hall_pi, wall_settings, server_url):
    document = _fixture("fixtures/client-heartbeat.v1/valid/two-connectors-one-unplugged.json")

    response = httpx.post(heartbeat_url, json=document, headers=_bearer(token))

    assert response.status_code == 204
    written = client_heartbeat_path_in(wall_settings.art_root, hall_pi.id)
    assert written.parent == wall_settings.heartbeat_path("any-wall").parent
    assert json.loads(written.read_text(encoding="utf-8")) == document
    listed = next(entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == hall_pi.id)
    assert listed["heartbeat"]["absent"] is False
    assert listed["heartbeat"]["problem"] is None
    assert [output["name"] for output in listed["heartbeat"]["outputs"]] == ["hdmi-a-1", "hdmi-a-2"]
    assert listed["heartbeat"]["outputs"][0]["screen"] == [1920, 1080]
    assert listed["heartbeat"]["age_seconds"] is not None


@pytest.mark.parametrize("row", [row for row in HEARTBEATS if not row["valid"]], ids=lambda row: row["path"])
def test_every_invalid_client_heartbeat_in_the_contract_is_refused_with_400_and_not_written(
    heartbeat_url, token, hall_pi, wall_settings, row
):
    response = httpx.post(heartbeat_url, json=_fixture(row["path"]), headers=_bearer(token))

    assert response.status_code == 400
    assert response.json()["error"].startswith("That is not a client heartbeat this server can read: ")
    assert not client_heartbeat_path_in(wall_settings.art_root, hall_pi.id).exists()


@pytest.mark.parametrize(
    ("body", "names"),
    [
        (b"not json at all", "not JSON"),
        (b"[1, 2]", "JSON object"),
        (b'{"reported_at": "2026-10-02T14:00:05", "outputs": []}', "reported_at"),
        (
            (
                b'{"reported_at": "2026-10-02T14:00:05Z", "outputs": ['
                b'{"name": "hdmi-a-1", "kind": "framebuffer", "connected": true, "screen": null},'
                b'{"name": "hdmi-a-1", "kind": "framebuffer", "connected": false, "screen": null}]}'
            ),
            "both called 'hdmi-a-1'",
        ),
        (
            (
                b'{"reported_at": "2026-10-02T14:00:05Z", "outputs": ['
                b'{"name": "hdmi-a-1", "kind": "framebuffer", "connected": true, "screen": [true, 1080]}]}'
            ),
            "'screen'",
        ),
    ],
    ids=["not-json", "not-an-object", "instant-without-offset", "two-outputs-one-name", "screen-of-booleans"],
)
def test_a_malformed_client_heartbeat_is_refused_with_400_naming_the_problem(heartbeat_url, token, body, names):
    response = httpx.post(heartbeat_url, content=body, headers={**_bearer(token), "Content-Type": "application/json"})

    assert response.status_code == 400
    assert names in response.json()["error"]


def test_the_client_heartbeat_refuses_without_a_valid_client_token(heartbeat_url, hall_pi, wall_settings):
    document = _fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json")

    assert httpx.post(heartbeat_url, json=document).status_code == 401
    assert httpx.post(heartbeat_url, json=document, headers=_bearer("not-a-token")).status_code == 401
    assert not client_heartbeat_path_in(wall_settings.art_root, hall_pi.id).exists()


# -- the server's reader agrees with the contract --------------------------------------


@pytest.mark.parametrize("row", HEARTBEATS, ids=lambda row: row["path"])
def test_the_servers_reader_agrees_with_the_contract_about_every_client_heartbeat(row):
    """Every fixture the schema accepts, the server accepts; every one it refuses, the server refuses."""
    assert (client_heartbeat.problem_with(_fixture(row["path"])) is None) is row["valid"], row["path"]


# -- the curator's routes ---------------------------------------------------------------


def test_a_client_is_added_renamed_given_a_token_and_removed_over_http(server_url, services, wall_id):
    added = httpx.post(server_url + "/api/clients", json={"name": "The Pi in the hall"})
    assert added.status_code == 200
    client_id = added.json()["client_id"]
    assert added.json()["token_issued_at"] is None
    assert added.json()["walls"] == []
    assert added.json()["heartbeat"]["absent"] is True

    renamed = httpx.post(server_url + f"/api/clients/{client_id}", json={"name": "The hall Pi"})
    assert renamed.json()["name"] == "The hall Pi"

    issued = httpx.post(server_url + f"/api/clients/{client_id}/token").json()
    assert issued["client_id"] == client_id
    listed = httpx.get(server_url + "/api/clients").json()["clients"]
    assert [entry["name"] for entry in listed] == ["The hall Pi"]
    assert listed[0]["token_issued_at"] == issued["token_issued_at"]

    assigned = httpx.post(server_url + f"/api/walls/{wall_id}/client", json={"client_id": client_id, "output": "frame"})
    assert assigned.status_code == 200
    assert (assigned.json()["wall"]["client_id"], assigned.json()["wall"]["output"]) == (client_id, "frame")
    listed = httpx.get(server_url + "/api/clients").json()["clients"]
    assert listed[0]["walls"] == [{"wall_id": wall_id, "name": services.display.get_wall(wall_id).name, "output": "frame"}]

    removed = httpx.delete(server_url + f"/api/clients/{client_id}")
    assert removed.status_code == 200
    assert removed.json()["clients"] == []
    wall = next(entry for entry in httpx.get(server_url + "/api/walls").json()["walls"] if entry["wall_id"] == wall_id)
    assert (wall["client_id"], wall["output"]) == (None, None)
    assert httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(issued["token"])).status_code == 401


def test_assigning_an_output_the_client_has_not_reported_says_so_and_one_it_has_does_not(
    server_url, services, wall_id, heartbeat_url
):
    client = services.clients.add_client(name="The Pi in the hall")
    token = services.access.issue(client.id).token
    url = server_url + f"/api/walls/{wall_id}/client"

    before = httpx.post(url, json={"client_id": client.id, "output": "hdmi-a-1"}).json()
    assert "has not reported its outputs yet" in before["notice"]

    httpx.post(heartbeat_url, json=_fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json"), headers=_bearer(token))
    reported = httpx.post(url, json={"client_id": client.id, "output": "hdmi-a-1"}).json()
    assert reported["notice"] is None
    unknown = httpx.post(url, json={"client_id": client.id, "output": "hdmi-a-9"}).json()
    assert "'hdmi-a-9' is not among them" in unknown["notice"]
    assert unknown["wall"]["output"] == "hdmi-a-9"


def test_unassigning_over_http_leaves_the_wall_with_no_client(server_url, services, wall_id):
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="frame")

    response = httpx.delete(server_url + f"/api/walls/{wall_id}/client")

    assert response.status_code == 200
    assert (response.json()["client_id"], response.json()["output"]) == (None, None)


@pytest.mark.parametrize(
    ("method", "path", "body", "names"),
    [
        ("POST", "/api/clients", {"name": "  "}, "name cannot be empty"),
        ("POST", "/api/clients/no-such-client", {"name": "x"}, "No client with id"),
        ("DELETE", "/api/clients/no-such-client", None, "No client with id"),
        ("POST", "/api/clients/no-such-client/token", None, "No client with id"),
        ("POST", "/api/walls/no-such-wall/client", {"client_id": "x", "output": "frame"}, "No wall with id"),
        ("DELETE", "/api/walls/no-such-wall/client", None, "No wall with id"),
    ],
)
def test_the_curator_routes_refuse_with_the_services_words(server_url, method, path, body, names):
    response = httpx.request(method, server_url + path, json=body)

    assert response.status_code == 400
    assert names in response.json()["error"]
