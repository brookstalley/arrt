"""The server answers every row of `contract/transport.json`, as the row says.

`transport.json` is the contract's statement, as data, of what each Player route
answers and what each answer means (`player-contract.md` § Transport). Arrt Player's
server double answers from it, so a row that is not what this server does would
teach the Player a server that does not exist. Here a real booted server is driven
through every row: each `(route, case)` has one scenario below that makes the
server meet that case, and the answer's status and body must be the row's.

**The scenarios and the rows are checked in both directions.** A row with no
scenario is a statement nobody tested, and a scenario with no row is an answer
the table does not tell a Player about. Either fails by name.

This file reads `contract/transport.json` through `arrt_contract`, which the
image's test stage installs from `/contract`.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
from arrt_contract import root, routes, transport, validator

from arrt.http import player

CONTRACT = root()
ROUTES = routes()
TABLE = transport()
ROWS = [(name, answer) for name, route in TABLE["routes"].items() for answer in route["answers"]]


def _fixture(relative: str) -> dict:
    return json.loads((CONTRACT / relative).read_text(encoding="utf-8"))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class World:
    """One server holding every thing a row needs: a wall with a feed, a label, and the clients that do and do not own them."""

    url: str
    services: object
    wall_id: str
    empty_wall_id: str
    token: str
    other_token: str
    panel_token: str
    label_id: str
    orphan_label_id: str
    media_url: str

    def path(self, name: str, **values: str) -> str:
        return self.url + ROUTES[name]["path"].format(**values)

    def get(self, name: str, token: str | None, headers: dict[str, str] | None = None, **values: str) -> httpx.Response:
        sent = {**(_bearer(token) if token else {}), **(headers or {})}
        return httpx.get(self.path(name, **values), headers=sent)

    def post(self, name: str, token: str | None, content: bytes, **values: str) -> httpx.Response:
        sent = {**(_bearer(token) if token else {}), "Content-Type": "application/json"}
        return httpx.post(self.path(name, **values), content=content, headers=sent)


@pytest.fixture
def world(server_url, services, ready_work, wall_id) -> World:
    hall = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=hall.id, output="hdmi-a-1")
    work = ready_work()
    theme = services.display.add_theme(name="Late night")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    services.display.activate_theme(theme.id, wall_id=wall_id)
    empty = services.display.add_wall(name="Landing").id
    services.clients.assign_wall(empty, client_id=hall.id, output="hdmi-a-2")

    study = services.clients.add_client(name="The Pi in the study")
    services.clients.assign_wall(services.display.add_wall(name="Study").id, client_id=study.id, output="hdmi-a-1")

    door = services.clients.add_client(name="The Pi by the door")
    label_id = services.clients.add_label(wall_id, client_id=door.id, output="epd-0").label.id
    orphan = services.clients.add_label(wall_id, client_id=door.id, output="epd-1").label.id
    services.clients.remove_label(wall_id, label_id=orphan)

    token = services.access.issue(hall.id).token
    feed = httpx.get(server_url + ROUTES["manifest_major"]["path"].format(wall_id=wall_id, major="2"), headers=_bearer(token))
    assert feed.status_code == 200, feed.text
    return World(
        url=server_url,
        services=services,
        wall_id=wall_id,
        empty_wall_id=empty,
        token=token,
        other_token=services.access.issue(study.id).token,
        panel_token=services.access.issue(door.id).token,
        label_id=label_id,
        orphan_label_id=orphan,
        media_url=server_url + feed.json()["works"][work.id]["media"]["url"],
    )


_OVER_THE_LIMIT = b'{"pad": "' + b"x" * (player.BODY_LIMIT_BYTES + 1) + b'"}'
_CLIENT_HEARTBEAT = json.dumps(_fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json")).encode()
_WALL_HEARTBEAT = json.dumps(_fixture("fixtures/heartbeat.v1/valid/minor-3-showing-art.json")).encode()


def _etag_of(world: World, name: str, token: str, **values: str) -> str:
    return world.get(name, token, **values).headers["etag"]


#: One scenario per row: how to make this server meet that case.
SCENARIOS: dict[tuple[str, str], Callable[[World], httpx.Response]] = {
    ("client", "ok"): lambda w: w.get("client", w.token),
    ("client", "unchanged"): lambda w: w.get("client", w.token, {"If-None-Match": _etag_of(w, "client", w.token)}),
    ("client", "no_valid_token"): lambda w: w.get("client", "not-a-token"),
    ("client_heartbeat", "accepted"): lambda w: w.post("client_heartbeat", w.token, _CLIENT_HEARTBEAT),
    ("client_heartbeat", "not_json"): lambda w: w.post("client_heartbeat", w.token, b"not json at all"),
    ("client_heartbeat", "not_a_client_heartbeat"): lambda w: w.post("client_heartbeat", w.token, b"{}"),
    ("client_heartbeat", "too_large"): lambda w: w.post("client_heartbeat", None, _OVER_THE_LIMIT),
    ("client_heartbeat", "no_valid_token"): lambda w: w.post("client_heartbeat", None, _CLIENT_HEARTBEAT),
    ("manifest_major", "ok"): lambda w: w.get("manifest_major", w.token, wall_id=w.wall_id, major="2"),
    ("manifest_major", "unchanged"): lambda w: w.get(
        "manifest_major",
        w.token,
        {"If-None-Match": _etag_of(w, "manifest_major", w.token, wall_id=w.wall_id, major="2")},
        wall_id=w.wall_id,
        major="2",
    ),
    ("manifest_major", "no_valid_token"): lambda w: w.get("manifest_major", None, wall_id=w.wall_id, major="2"),
    ("manifest_major", "not_this_clients_wall"): lambda w: w.get("manifest_major", w.other_token, wall_id=w.wall_id, major="2"),
    ("manifest_major", "major_not_published"): lambda w: w.get("manifest_major", w.token, wall_id=w.wall_id, major="1"),
    ("manifest_major", "nothing_hung"): lambda w: w.get("manifest_major", w.token, wall_id=w.empty_wall_id, major="2"),
    ("media", "ok"): lambda w: httpx.get(w.media_url, headers=_bearer(w.other_token)),
    ("media", "not_held"): lambda w: w.get("media", w.token, sha256="0" * 64),
    ("media", "no_valid_token"): lambda w: httpx.get(w.media_url),
    ("heartbeat", "accepted"): lambda w: w.post("heartbeat", w.token, _WALL_HEARTBEAT, wall_id=w.wall_id),
    ("heartbeat", "not_a_heartbeat"): lambda w: w.post("heartbeat", w.token, b"{}", wall_id=w.wall_id),
    ("heartbeat", "not_an_object"): lambda w: w.post("heartbeat", w.token, b"[1, 2]", wall_id=w.wall_id),
    ("heartbeat", "too_large"): lambda w: w.post("heartbeat", None, _OVER_THE_LIMIT, wall_id=w.wall_id),
    ("heartbeat", "no_valid_token"): lambda w: w.post("heartbeat", "not-a-token", _WALL_HEARTBEAT, wall_id=w.wall_id),
    ("heartbeat", "not_this_clients_wall"): lambda w: w.post("heartbeat", w.other_token, _WALL_HEARTBEAT, wall_id=w.wall_id),
    ("label", "ok"): lambda w: w.get("label", w.panel_token, label_id=w.label_id),
    ("label", "unchanged"): lambda w: w.get(
        "label", w.panel_token, {"If-None-Match": _etag_of(w, "label", w.panel_token, label_id=w.label_id)}, label_id=w.label_id
    ),
    ("label", "no_valid_token"): lambda w: w.get("label", None, label_id=w.label_id),
    ("label", "not_this_clients_label"): lambda w: w.get("label", w.token, label_id=w.label_id),
    ("label", "captions_no_wall"): lambda w: w.get("label", w.panel_token, label_id=w.orphan_label_id),
}


def _is_the_error_shape(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and set(body) == set(TABLE["error_body"]["required"]) and isinstance(body["error"], str)


def _check_body(world: World, name: str, kind: str, response: httpx.Response) -> None:
    """The body the row names, and nothing else: so a row that says `framework` fails once the route answers in the shape."""
    route = TABLE["routes"][name]
    if kind == "none":
        assert response.content == b""
    elif kind == "error":
        assert _is_the_error_shape(response), response.text
        for token in (world.token, world.other_token, world.panel_token):
            assert token not in response.text
    elif kind == "framework":
        assert not _is_the_error_shape(response), response.text
    elif kind == "document":
        assert list(validator(route["schema"]).iter_errors(response.json())) == []
        assert len(response.content) <= route["max_bytes"]
        assert response.headers["etag"] == f'"{hashlib.sha256(response.content).hexdigest()}"'
    elif kind == "media":
        assert response.request.url.path.endswith(hashlib.sha256(response.content).hexdigest())
    else:
        pytest.fail(f"a body this test does not know: {kind}")


def test_every_row_has_a_scenario_and_every_scenario_a_row():
    rows = {(name, answer["case"]) for name, answer in ROWS}

    assert rows - set(SCENARIOS) == set(), "rows this suite never drives the server through"
    assert set(SCENARIOS) - rows == set(), "answers the server gives that the table does not name"


@pytest.mark.parametrize(("name", "answer"), ROWS, ids=[f"{name}:{answer['case']}" for name, answer in ROWS])
def test_the_server_answers_each_row_as_the_table_says(world, name, answer):
    response = SCENARIOS[(name, answer["case"])](world)

    assert response.status_code == answer["status"], response.text
    _check_body(world, name, answer["body"], response)


#: How to change each conditional route's document, so a case's document B is one.
_CHANGES: dict[str, Callable[[World], None]] = {
    "client": lambda w: w.services.clients.unassign_wall(w.empty_wall_id),
    "manifest_major": lambda w: w.services.display.step_display(w.wall_id),
    "label": lambda w: w.post(
        "heartbeat", w.token, json.dumps(_fixture("fixtures/heartbeat.v1/valid/minor-3-in-use.json")).encode(), wall_id=w.wall_id
    ),
}

_ASKED: dict[str, Callable[[World, dict[str, str]], httpx.Response]] = {
    "client": lambda w, headers: w.get("client", w.token, headers),
    "manifest_major": lambda w, headers: w.get("manifest_major", w.token, headers, wall_id=w.wall_id, major="2"),
    "label": lambda w, headers: w.get("label", w.panel_token, headers, label_id=w.label_id),
}


def test_the_conditional_routes_are_the_ones_this_suite_replays():
    assert set(TABLE["conditional_get"]["routes"]) == set(_CHANGES) == set(_ASKED)


@pytest.mark.parametrize("name", sorted(TABLE["conditional_get"]["routes"]))
def test_each_conditional_get_case_is_answered_as_the_table_says(world, name):
    """Document A's cases first, then the change, then B's: the replay a Player's double runs, against the real server."""
    cases = sorted(TABLE["conditional_get"]["cases"], key=lambda case: case["document"])
    assert [case["document"] for case in cases][-1] == "B", "the cases never change the document"
    tags: dict[str, str] = {}
    changed = False
    for case in cases:
        if case["document"] == "B" and not changed:
            _CHANGES[name](world)
            changed = True
        sent = case["if_none_match"]
        if sent is not None and sent.startswith("etag("):
            sent = tags[sent]
        response = _ASKED[name](world, {"If-None-Match": sent} if sent is not None else {})

        assert response.status_code == case["status"], (case["name"], response.text)
        tags.setdefault(case["etag"], response.headers["etag"])
        assert response.headers["etag"] == tags[case["etag"]], case["name"]
        assert response.headers["cache-control"] == "no-cache", case["name"]
    assert tags["etag(A)"] != tags["etag(B)"]


#: What this server answered a wall heartbeat whose body is `[1, 2]` before contract
#: 1.3.0: the web framework's own 422 body, refused before the route read it. Copied
#: from the wire in a run of the test below against the server at 9889af78 (contract
#: 1.2.0), where `transport.json` recorded it as the `not_an_object` row's `framework`
#: body: `{"detail":[{"type":"dict_type","loc":["body"],"msg":"Input should be a valid
#: dictionary","input":[1,2]}]}`, answered 422.
_THE_FRAMEWORKS_422 = {
    "detail": [{"type": "dict_type", "loc": ["body"], "msg": "Input should be a valid dictionary", "input": [1, 2]}]
}


@pytest.mark.parametrize(
    "body",
    [b"[1, 2]", b'"a string"', b"null", b"7", b"not json at all", b""],
    ids=["list", "string", "null", "number", "not-json", "empty"],
)
def test_a_wall_heartbeat_that_is_not_a_json_object_is_refused_with_400_in_the_error_shape_and_not_written(world, body):
    """As the client heartbeat's route answers it: the contract's error shape, never the framework's (contract 1.3.0)."""
    response = world.post("heartbeat", world.token, body, wall_id=world.wall_id)

    assert response.status_code == 400, response.text
    assert _is_the_error_shape(response), response.text
    assert "JSON object" in response.json()["error"]
    reading = next(entry for entry in world.services.display.survey_wall_status() if entry.wall.id == world.wall_id).heartbeat
    assert reading.absent


def test_the_frameworks_body_the_wall_heartbeat_answered_is_gone(world):
    """The body copied above is what the not-an-object case answered at 1.2.0; at 1.3.0 it is not what it answers."""
    response = world.post("heartbeat", world.token, b"[1, 2]", wall_id=world.wall_id)

    assert response.json() != _THE_FRAMEWORKS_422
    assert "detail" not in response.json()


@pytest.mark.parametrize(("token", "status"), [(None, 401), ("not-a-token", 401), ("another client's", 403)])
def test_a_refused_token_is_answered_before_a_body_that_is_not_an_object(world, token, status):
    """The token is judged before the body, as it was while the framework read it: a stranger learns nothing of the route."""
    sent = world.other_token if token == "another client's" else token

    response = world.post("heartbeat", sent, b"[1, 2]", wall_id=world.wall_id)

    assert response.status_code == status, response.text
    assert _is_the_error_shape(response), response.text


def test_a_failure_inside_the_server_is_answered_in_the_unanswered_class(world, monkeypatch):
    """No route answers 5xx on purpose, so the class is met the way a Player meets it: something inside fails."""

    def fails(_client_id: str) -> bytes:
        raise RuntimeError("the store went away")

    monkeypatch.setattr(world.services.clients, "client_document", fails)

    response = world.get("client", world.token)

    assert TABLE["unanswered"]["status_class"] == "5xx"
    assert 500 <= response.status_code < 600
    _check_body(world, "client", TABLE["unanswered"]["body"], response)
