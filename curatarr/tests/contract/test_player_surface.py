"""The Player's surface over real HTTP: the manifest, media by hash, the heartbeat, and wall tokens.

Against a real booted server, as every surface test here is, because the thing a
Player depends on is the wire: the status, the headers and the bytes.
`player-contract.md` § Transport is the specification and `contract/routes.json`
holds the spelling of the three routes.
"""

import hashlib
import json
import logging
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from scenarios import connect

from curatarr.http import player
from curatarr.library.readiness import MEDIA_PATH_TEMPLATE
from curatarr.programming.access import REFUSAL_LOG_INTERVAL_SECONDS

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
def token(services, wall_id) -> str:
    return services.access.issue(wall_id).token


@pytest.fixture
def study(services) -> str:
    return services.display.add_wall(name="Study").id


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


def test_media_answers_to_any_walls_token(server_url, services, playing, token, wall_id, study):
    other = services.access.issue(study).token
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]

    assert httpx.get(server_url + entry["media"]["url"], headers=_bearer(other)).status_code == 200


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


# -- tokens -----------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["manifest", "heartbeat"])
def test_every_wall_route_refuses_without_a_valid_token(server_url, services, playing, token, wall_id, study, route):
    other = services.access.issue(study).token
    url = server_url + _path(route, wall_id=wall_id)
    send = (
        (lambda headers: httpx.get(url, headers=headers))
        if route == "manifest"
        else (lambda headers: httpx.post(url, json={"reported_at": "2026-09-30T12:00:00+00:00"}, headers=headers))
    )

    assert send({}).status_code == 401
    assert send(_bearer("not-a-token")).status_code == 401
    assert send({"Authorization": f"Basic {token}"}).status_code == 401
    assert send(_bearer(other)).status_code == 403
    assert send(_bearer(token)).status_code in (200, 204)


def test_media_refuses_without_a_valid_token(server_url, playing, token, wall_id):
    entry = httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).json()["entries"][0]

    assert httpx.get(server_url + entry["media"]["url"]).status_code == 401
    assert httpx.get(server_url + entry["media"]["url"], headers=_bearer("not-a-token")).status_code == 401


def test_a_rotated_out_token_is_refused(server_url, services, playing, token, wall_id):
    url = server_url + _path("manifest", wall_id=wall_id)
    rotated = services.access.issue(wall_id).token

    assert httpx.get(url, headers=_bearer(token)).status_code == 401
    assert httpx.get(url, headers=_bearer(rotated)).status_code == 200


def test_a_wall_with_no_token_yet_admits_nobody(server_url, playing, wall_id):
    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer("anything")).status_code == 401


def test_the_token_is_stored_only_as_a_verifier(services, wall_id, store):
    issued = services.access.issue(wall_id)
    wall = store.get_wall(wall_id)

    assert wall.token_verifier == hashlib.sha256(issued.token.encode()).hexdigest()
    assert issued.token not in json.dumps({"verifier": wall.token_verifier})
    assert wall.token_issued_at == issued.issued_at


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
    assert services.display.get_wall(wall_id).name in refusals[0].getMessage()


def test_invented_wall_ids_share_one_refusal_line_and_never_reach_the_journal(server_url, caplog):
    """The id in the URL is the caller's choice, so it keys nothing and is never written down."""
    invented = [f"invented-{n}%0Aforged-line" for n in range(3)]

    with caplog.at_level(logging.DEBUG):
        for wall_id in invented:
            assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer("x")).status_code == 401

    # The server's journal, not the test client's own request log beside it.
    journal = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("curatarr"))
    assert "invented-" not in journal and "forged-line" not in journal
    refusals = [record for record in caplog.records if record.getMessage().startswith("Refused a Player request")]
    assert len(refusals) == 1
    assert "an unknown wall" in refusals[0].getMessage()


# -- issuing, from each surface ---------------------------------------------------------


def test_a_token_issued_over_http_opens_the_wall_and_is_never_read_back(server_url, playing, wall_id):
    issued = httpx.post(server_url + f"/api/walls/{wall_id}/token")
    assert issued.status_code == 200
    token = issued.json()["token"]

    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(token)).status_code == 200
    walls = httpx.get(server_url + "/api/walls")
    wall = next(entry for entry in walls.json()["walls"] if entry["wall_id"] == wall_id)
    assert wall["token_issued_at"] == issued.json()["token_issued_at"]
    assert token not in walls.text


def test_a_wall_with_no_token_says_so(server_url, wall_id):
    wall = next(entry for entry in httpx.get(server_url + "/api/walls").json()["walls"] if entry["wall_id"] == wall_id)

    assert wall["token_issued_at"] is None


async def test_a_token_issued_through_the_tool_opens_the_wall_and_is_never_read_back(server_url, playing, wall_id):
    async with connect(server_url) as caller:
        issued = await caller.ok("art_display", "issue_token", wall_id=wall_id)
        walls = await caller.ok("art_display", "walls")

    assert httpx.get(server_url + _path("manifest", wall_id=wall_id), headers=_bearer(issued["token"])).status_code == 200
    wall = next(entry for entry in walls["walls"] if entry["wall_id"] == wall_id)
    assert wall["token_issued_at"] == issued["token_issued_at"]
    assert issued["token"] not in json.dumps(walls)
