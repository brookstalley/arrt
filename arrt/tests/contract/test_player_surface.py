"""The Player's surface over real HTTP: the manifest, media by hash, the heartbeat, and client tokens.

Against a real booted server, as every surface test here is, because the thing a
Player depends on is the wire: the status, the headers and the bytes.
`player-contract.md` § Transport is the specification and `contract/routes.json`
holds the spelling of the routes. The two client routes, `GET /client` and
`POST /client/heartbeat`, are `test_client_surface.py`'s.

**Every request carries a client's token** (`clients.md`), admitted for the walls
assigned to that client. Wall tokens are retired; `test_retired_wall_tokens.py`
holds that a token issued under the old scheme opens nothing.
"""

import hashlib
import json
import logging
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from scenarios import connect

from arrt.http import player
from arrt.library.readiness import MEDIA_PATH_TEMPLATE
from arrt.mcp.tools import TOOLS
from arrt.programming.access import REFUSAL_LOG_INTERVAL_SECONDS

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]


def _path(name: str, **values: str) -> str:
    return ROUTES[name]["path"].format(**values)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def render_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"a composed render" * 64


@pytest.fixture
def playing(services, ready_work, wall_id, wall_settings, render_bytes):
    """A wall with a published manifest whose one work has a real render file."""
    work = ready_work()
    render = next(view.rendition for view in services.catalogue.list_renditions(work.id))
    target = wall_settings.art_root / render.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_bytes)
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    return work


@pytest.fixture
def hall_pi(services, wall_id):
    """The client the wall is assigned to."""
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    return client


@pytest.fixture
def token(services, hall_pi) -> str:
    """The token of the client the wall is assigned to."""
    return services.access.issue(hall_pi.id).token


@pytest.fixture
def study(services) -> str:
    return services.display.add_wall(name="Study").id


@pytest.fixture
def study_token(services, study) -> str:
    """A valid client token whose client drives another wall, not this one."""
    client = services.clients.add_client(name="The Pi in the study")
    services.clients.assign_wall(study, client_id=client.id, output="hdmi-a-1")
    return services.access.issue(client.id).token


# -- the routes are the contract's ----------------------------------------------------


def test_the_player_router_holds_exactly_the_routes_the_contract_names():
    declared = {(method, route.path) for route in player.router.routes for method in route.methods}

    assert declared == {(route["method"], route["path"]) for route in ROUTES.values()}


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_each_contract_route_is_mounted_and_guarded(server_url, name):
    """Asked over the wire, so a route declared and never mounted fails here as a 404."""
    route = ROUTES[name]
    path = route["path"].format(wall_id="some-wall", sha256="0" * 64)

    response = httpx.request(route["method"], server_url + path, json={} if route["method"] == "POST" else None)

    assert response.status_code == 401, response.text


def test_the_media_url_a_manifest_names_is_the_route_that_serves_it():
    assert MEDIA_PATH_TEMPLATE == ROUTES["media"]["path"]


# -- the manifest -------------------------------------------------------------------


def test_a_served_manifest_conforms_to_the_contract(server_url, playing, token, wall_id):
    response = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token))

    assert response.status_code == 200
    schema = json.loads((CONTRACT / "schemas" / "manifest.v1.schema.json").read_text(encoding="utf-8"))
    errors = [error.message for error in Draft202012Validator(schema).iter_errors(response.json())]
    assert errors == []
    assert response.json()["entries"][0]["media"]["sha256"]


def test_an_unchanged_manifest_answers_304_and_a_changed_one_does_not(server_url, services, playing, token, wall_id):
    url = server_url + _path("manifest", wall_id=wall_id)
    first = httpx.get(url, headers=_bearer(token))
    etag = first.headers["etag"]
    assert etag == f'"{hashlib.sha256(first.content).hexdigest()}"'

    unchanged = httpx.get(url, headers={**_bearer(token), "If-None-Match": etag})
    assert unchanged.status_code == 304
    assert unchanged.content == b""

    services.display.step_display(wall_id)
    changed = httpx.get(url, headers={**_bearer(token), "If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


def test_a_wall_with_nothing_published_answers_404(server_url, token, wall_id):
    response = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token))

    assert response.status_code == 404


# -- media ------------------------------------------------------------------------------


def test_media_bytes_hash_to_their_name(server_url, services, playing, token, wall_id, render_bytes):
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]

    response = httpx.get(server_url + entry["media"]["url"], headers=_bearer(token))

    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == entry["media"]["sha256"]
    assert response.content == render_bytes
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_media_whose_file_changed_under_its_hash_is_not_served(
    server_url, services, playing, token, wall_id, wall_settings, render_bytes
):
    """A hash never serves different bytes, including while a re-render is being recorded."""
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]
    render = next(view.rendition for view in services.catalogue.list_renditions(playing.id))
    (wall_settings.art_root / render.relative_path).write_bytes(render_bytes + b"rewritten")

    response = httpx.get(server_url + entry["media"]["url"], headers=_bearer(token))

    assert response.status_code == 404


def test_media_answers_to_any_clients_token_even_one_with_no_walls(server_url, services, playing, token, wall_id):
    """A render is shared by every wall that shows it, so media asks only that the client is one."""
    idle = services.clients.add_client(name="A Pi with nothing assigned")
    idle_token = services.access.issue(idle.id).token
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]

    assert httpx.get(server_url + entry["media"]["url"], headers=_bearer(idle_token)).status_code == 200


def test_an_unknown_or_malformed_hash_answers_404(server_url, token):
    for name in ("0" * 64, "not-a-hash"):
        response = httpx.get(server_url + _path("media", sha256=name), headers=_bearer(token))
        assert response.status_code == 404, name


# -- the heartbeat ----------------------------------------------------------------------


def test_a_posted_heartbeat_is_read_back_by_the_health_surface(server_url, services, token, wall_id):
    document = json.loads((CONTRACT / "fixtures" / "heartbeat.v1" / "valid" / "minor-1-with-schema.json").read_text())

    response = httpx.post(server_url + _path("heartbeat", wall_id=wall_id), json=document, headers=_bearer(token))

    assert response.status_code == 204
    reading = next(entry for entry in services.display.survey_wall_status() if entry.wall.id == wall_id).heartbeat
    assert reading.problem is None
    assert reading.contents == document
    health = httpx.get(server_url + "/api/health").json()
    assert any(wall["wall_id"] == wall_id and wall["heartbeat"]["problem"] is None for wall in health["walls"])


@pytest.mark.parametrize(
    "fixture", sorted((CONTRACT / "fixtures" / "heartbeat.v1" / "valid").glob("*.json")), ids=lambda path: path.name
)
def test_every_valid_heartbeat_in_the_contract_is_accepted(server_url, token, wall_id, fixture):
    document = json.loads(fixture.read_text())

    response = httpx.post(server_url + _path("heartbeat", wall_id=wall_id), json=document, headers=_bearer(token))

    assert response.status_code == 204


def test_a_heartbeat_the_panel_could_not_read_is_refused_and_not_written(server_url, services, token, wall_id):
    fixture = CONTRACT / "fixtures" / "heartbeat.v1" / "invalid" / "timestamp-instead-of-reported-at.json"

    response = httpx.post(
        server_url + _path("heartbeat", wall_id=wall_id), json=json.loads(fixture.read_text()), headers=_bearer(token)
    )

    assert response.status_code == 400
    assert "reported_at" in response.json()["error"]
    reading = next(entry for entry in services.display.survey_wall_status() if entry.wall.id == wall_id).heartbeat
    assert reading.absent


# -- admission --------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["manifest", "heartbeat"])
def test_every_wall_route_admits_only_the_client_the_wall_is_assigned_to(server_url, playing, token, study_token, wall_id, route):
    """Own wall admitted; another client's token is 403; no valid client token is 401."""
    url = server_url + _path(route, wall_id=wall_id)
    send = (
        (lambda headers: httpx.get(url, headers=headers))
        if route == "manifest"
        else (lambda headers: httpx.post(url, json={"reported_at": "2026-09-30T12:00:00+00:00"}, headers=headers))
    )

    assert send({}).status_code == 401
    assert send(_bearer("not-a-token")).status_code == 401
    assert send({"Authorization": f"Basic {token}"}).status_code == 401
    assert send(_bearer(study_token)).status_code == 403
    assert send(_bearer(token)).status_code in (200, 204)


def test_the_study_clients_own_wall_admits_it(server_url, services, wall_id, token, study, study_token):
    """The 403 above is about assignment, not about the study client being refused everywhere."""
    url = server_url + _path("heartbeat", wall_id=study)
    document = {"reported_at": "2026-09-30T12:00:00+00:00"}

    assert httpx.post(url, json=document, headers=_bearer(study_token)).status_code == 204
    assert httpx.post(url, json=document, headers=_bearer(token)).status_code == 403


def test_reassigning_a_wall_moves_its_admission_with_it(server_url, services, playing, token, wall_id, hall_pi):
    url = server_url + _path("manifest", wall_id=wall_id)
    other = services.clients.add_client(name="The Pi in the kitchen")
    other_token = services.access.issue(other.id).token
    assert httpx.get(url, headers=_bearer(other_token)).status_code == 403

    services.clients.assign_wall(wall_id, client_id=other.id, output="hdmi-a-2")

    assert httpx.get(url, headers=_bearer(other_token)).status_code == 200
    assert httpx.get(url, headers=_bearer(token)).status_code == 403
    services.clients.unassign_wall(wall_id)
    assert httpx.get(url, headers=_bearer(other_token)).status_code == 403


def test_a_wall_assigned_to_no_client_admits_no_client(server_url, services, playing, wall_id, token):
    services.clients.unassign_wall(wall_id)

    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).status_code == 403


def test_media_refuses_without_a_valid_client_token(server_url, playing, token, wall_id):
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]

    assert httpx.get(server_url + entry["media"]["url"]).status_code == 401
    assert httpx.get(server_url + entry["media"]["url"], headers=_bearer("not-a-token")).status_code == 401


def test_a_rotated_out_client_token_is_refused(server_url, services, playing, token, wall_id, hall_pi):
    url = server_url + _path("manifest", wall_id=wall_id)
    rotated = services.access.issue(hall_pi.id).token

    assert httpx.get(url, headers=_bearer(token)).status_code == 401
    assert httpx.get(url, headers=_bearer(rotated)).status_code == 200


def test_a_client_with_no_token_yet_admits_nobody(server_url, playing, wall_id, hall_pi):
    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer("anything")).status_code == 401


def test_a_removed_clients_token_opens_nothing(server_url, services, playing, token, wall_id, hall_pi):
    services.clients.remove_client(hall_pi.id)

    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).status_code == 401
    assert httpx.get(server_url + _path("client"), headers=_bearer(token)).status_code == 401


def test_the_token_is_stored_only_as_a_verifier(services, hall_pi, store):
    issued = services.access.issue(hall_pi.id)
    client = store.get_client(hall_pi.id)

    assert client.token_verifier == hashlib.sha256(issued.token.encode()).hexdigest()
    assert issued.token not in json.dumps({"verifier": client.token_verifier})
    assert client.token_issued_at == issued.issued_at


# -- the refusal log --------------------------------------------------------------------


def test_a_refused_token_never_reaches_the_journal_and_is_logged_once(server_url, services, playing, token, wall_id, caplog):
    stale = "a-stale-token-that-must-not-be-logged"
    url = server_url + _path("manifest", wall_id=wall_id)

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            assert httpx.get(url, headers=_bearer(stale)).status_code == 401
        assert httpx.get(url, headers=_bearer(token)).status_code == 200

    journal = "\n".join(record.getMessage() for record in caplog.records)
    assert stale not in journal
    assert token not in journal
    refusals = [record for record in caplog.records if record.getMessage().startswith("Refused a Player request")]
    assert len(refusals) == 1, f"a Player retrying every second must be logged once per {REFUSAL_LOG_INTERVAL_SECONDS}s"
    assert "an unknown client" in refusals[0].getMessage()


def test_a_client_asking_for_another_wall_is_logged_once_by_name_and_never_by_token(
    server_url, services, playing, wall_id, study_token, caplog
):
    url = server_url + _path("manifest", wall_id=wall_id)

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            assert httpx.get(url, headers=_bearer(study_token)).status_code == 403

    journal = "\n".join(record.getMessage() for record in caplog.records)
    assert study_token not in journal
    refusals = [record for record in caplog.records if record.getMessage().startswith("Refused a Player request")]
    assert len(refusals) == 1
    assert "'The Pi in the study'" in refusals[0].getMessage()
    assert services.display.get_wall(wall_id).name in refusals[0].getMessage()


def test_invented_wall_ids_share_one_refusal_line_and_never_reach_the_journal(server_url, study_token, caplog):
    """The id in the URL is the caller's choice, so it keys nothing and is never written down."""
    invented = [f"invented-{n}%0Aforged-line" for n in range(3)]

    with caplog.at_level(logging.DEBUG):
        for wall_id in invented:
            assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer("x")).status_code == 401
            assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(study_token)).status_code == 403

    # The server's journal, not the test client's own request log beside it.
    journal = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("arrt"))
    assert "invented-" not in journal and "forged-line" not in journal
    refusals = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Refused a Player request")]
    assert len(refusals) == 2, refusals
    assert any("an unknown client" in refusal for refusal in refusals)
    assert any("a wall this server does not hold" in refusal for refusal in refusals)


# -- issuing ----------------------------------------------------------------------------


def test_a_client_token_issued_over_http_opens_its_wall_and_is_never_read_back(server_url, playing, wall_id, hall_pi):
    issued = httpx.post(server_url + f"/api/clients/{hall_pi.id}/token")
    assert issued.status_code == 200
    token = issued.json()["token"]

    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).status_code == 200
    clients = httpx.get(server_url + "/api/clients")
    client = next(entry for entry in clients.json()["clients"] if entry["client_id"] == hall_pi.id)
    assert client["token_issued_at"] == issued.json()["token_issued_at"]
    assert token not in clients.text
    assert token not in httpx.get(server_url + "/api/walls").text


def test_no_wall_token_can_be_issued_any_more(server_url, wall_id):
    """The route that issued them is gone, not merely unused."""
    assert httpx.post(server_url + f"/api/walls/{wall_id}/token").status_code in (404, 405)


def test_a_wall_assigned_to_no_client_says_so(server_url, wall_id):
    wall = next(entry for entry in httpx.get(server_url + "/api/walls").json()["walls"] if entry["wall_id"] == wall_id)

    assert (wall["client_id"], wall["output"]) == (None, None)
    assert "token_issued_at" not in wall


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_no_tool_still_issues_or_teaches_wall_tokens(record):
    """Retiring the wall token is a sweep of the sentences that taught it, not only the action."""
    prose = " ".join(
        [record.summary]
        + [part for action in record.actions for part in (action.name, action.description, action.example, *action.tips)]
    )

    assert "issue_token" not in prose
    assert "WALL_TOKEN" not in prose
    assert "Player token" not in prose


async def test_the_tool_surface_refuses_the_retired_action(server_url, wall_id):
    async with connect(server_url) as caller:
        refused = await caller.call("art_display", "issue_token", wall_id=wall_id)
        walls = await caller.ok("art_display", "walls")

    assert refused["success"] is False
    wall = next(entry for entry in walls["walls"] if entry["wall_id"] == wall_id)
    assert (wall["client_id"], wall["output"]) == (None, None)
    assert "token_issued_at" not in wall
