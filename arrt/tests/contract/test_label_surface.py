"""A label renderer's route, `GET /labels/{label_id}`, over real HTTP.

`player-contract.md` § Transport is the specification, `contract/routes.json` the
spelling and `contract/schemas/label.v1.schema.json` the shape: every document
served here is validated against it. The document's state is the wall's as Walls
states it, so a label and Walls cannot give two answers for one wall; each case
below reads both and compares them.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from arrt.programming.manifest.heartbeat import STALE_AFTER_SECONDS, heartbeat_path_in

CONTRACT = Path(__file__).resolve().parents[3] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]

# The label schema reuses the manifest's label text by reference, so every schema
# is registered under its $id.
_REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema))
    for schema in (json.loads(path.read_text(encoding="utf-8")) for path in (CONTRACT / "schemas").glob("*.json"))
)
_LABEL = Draft202012Validator(
    json.loads((CONTRACT / "schemas" / "label.v1.schema.json").read_text(encoding="utf-8")),
    registry=_REGISTRY,
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)
_CLIENT = Draft202012Validator(json.loads((CONTRACT / "schemas" / "client.v1.schema.json").read_text(encoding="utf-8")))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _instant(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


@pytest.fixture
def hall_pi(services, wall_id):
    """The client showing the wall on its HDMI connector."""
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    return client


@pytest.fixture
def panel_pi(services):
    """A client holding a panel and no screen at all, which is an ordinary client."""
    return services.clients.add_client(name="The Pi by the door")


@pytest.fixture
def label_id(services, wall_id, hall_pi, panel_pi) -> str:
    return services.clients.add_label(wall_id, client_id=panel_pi.id, output="epd-0").label.id


@pytest.fixture
def token(services, panel_pi) -> str:
    return services.access.issue(panel_pi.id).token


@pytest.fixture
def label_url(server_url, label_id) -> str:
    return server_url + ROUTES["label"]["path"].format(label_id=label_id)


@pytest.fixture
def work(ready_work):
    return ready_work(title="Nighthawks")


def _write_heartbeat(wall_settings, wall_id, document, *, age=timedelta(seconds=2)):
    """What the wall's controller last wrote, as the file the server reads."""
    stamped = {**document, "reported_at": _instant(datetime.now(UTC) - age)}
    heartbeat_path_in(wall_settings.art_root, wall_id).write_text(json.dumps(stamped), encoding="utf-8")


def _minor_3(state, work_id=None, since="2026-10-08T19:00:00+00:00", current=None):
    document = {"schema": {"major": 1, "minor": 3}, "display_state": {"state": state, "work_id": work_id, "since": since}}
    if current is not None:
        document["current_work_id"] = current
    return document


def _fetch(label_url, token):
    response = httpx.get(label_url, headers=_bearer(token))
    assert response.status_code == 200, response.text
    document = response.json()
    assert not list(_LABEL.iter_errors(document)), [error.message for error in _LABEL.iter_errors(document)]
    return response, document


def _walls_state(server_url, wall_id):
    wall = next(entry for entry in httpx.get(server_url + "/api/walls").json()["walls"] if entry["wall_id"] == wall_id)
    shown = wall["display_state"]
    return {"state": shown["state"], "work_id": shown["work_id"], "since": shown["since"]}


# -- the document ----------------------------------------------------------------------------


def test_a_wall_showing_a_work_gives_its_label_the_works_text(server_url, label_url, token, wall_id, wall_settings, work):
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", work.id))

    response, document = _fetch(label_url, token)

    assert document["schema"] == {"major": 1, "minor": 0}
    assert (document["wall_id"], document["wall_name"]) == (wall_id, "The wall")
    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["display_state"]["state"] == "showing_art"
    assert document["label"]["title"] == "Nighthawks"
    assert document["label"]["date_created"] == "1942"
    assert set(document["label"]) == {
        "title",
        "artist",
        "artist_family_name",
        "artist_given_name",
        "artist_nationality",
        "artist_dates",
        "date_created",
        "medium",
        "dimensions",
        "commentary",
    }
    assert response.headers["etag"] == f'"{hashlib.sha256(response.content).hexdigest()}"'


def test_the_label_text_is_the_manifests_text_for_that_work(services, label_url, token, wall_id, wall_settings, work):
    """One function sets both, so a wall's manifest and its label cannot set one work two ways."""
    playable = services.library.playable([work.id])[work.id]
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", work.id))

    _, document = _fetch(label_url, token)

    assert document["label"] == dict(playable.label)


@pytest.mark.parametrize("state", ["in_use", "dark", "no_screen"])
def test_a_screen_somebody_else_has_or_none_carries_no_label(server_url, label_url, token, wall_id, wall_settings, state):
    _write_heartbeat(wall_settings, wall_id, _minor_3(state, current="w-old"))

    _, document = _fetch(label_url, token)

    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["display_state"]["state"] == state
    assert document["label"] is None


def test_a_picture_this_wall_did_not_put_there_carries_no_label(server_url, label_url, token, wall_id, wall_settings):
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", None))

    _, document = _fetch(label_url, token)

    assert document["display_state"] == {"state": "showing_art", "work_id": None, "since": "2026-10-08T19:00:00+00:00"}
    assert document["label"] is None


def test_a_silent_wall_carries_the_work_it_last_showed(server_url, label_url, token, wall_id, wall_settings, work):
    age = timedelta(seconds=STALE_AFTER_SECONDS + 30)
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", work.id), age=age)

    _, document = _fetch(label_url, token)

    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["display_state"]["state"] == "silent"
    assert document["display_state"]["work_id"] is None
    assert document["display_state"]["since"] is not None
    assert document["label"]["title"] == "Nighthawks"


def test_a_silent_wall_that_last_showed_no_art_carries_no_label(label_url, token, wall_id, wall_settings, work):
    age = timedelta(seconds=STALE_AFTER_SECONDS + 30)
    _write_heartbeat(wall_settings, wall_id, _minor_3("in_use", current=work.id), age=age)

    _, document = _fetch(label_url, token)

    assert document["display_state"]["state"] == "silent"
    assert document["label"] is None


def test_an_unreachable_screen_carries_the_work_the_heartbeat_last_named(
    server_url, label_url, token, wall_id, wall_settings, work
):
    _write_heartbeat(wall_settings, wall_id, _minor_3("unreachable", current=work.id))

    _, document = _fetch(label_url, token)

    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["display_state"]["state"] == "unreachable"
    assert document["label"]["title"] == "Nighthawks"


def test_a_wall_that_has_never_reported_is_silent_with_nothing_to_say(server_url, label_url, token, wall_id):
    _, document = _fetch(label_url, token)

    assert document["display_state"] == {"state": "silent", "work_id": None, "since": None}
    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["label"] is None


def test_a_wall_no_client_shows_is_unassigned_whatever_its_file_says(
    server_url, services, label_url, token, wall_id, wall_settings, work
):
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", work.id))
    services.clients.unassign_wall(wall_id)

    _, document = _fetch(label_url, token)

    assert document["display_state"] == {"state": "unassigned", "work_id": None, "since": None}
    assert document["display_state"] == _walls_state(server_url, wall_id)
    assert document["label"] is None


# -- conditional requests ----------------------------------------------------------------------


def test_an_unchanged_label_answers_304_and_a_changed_one_does_not(label_url, token, wall_id, wall_settings, work):
    _write_heartbeat(wall_settings, wall_id, _minor_3("showing_art", work.id))
    first, _ = _fetch(label_url, token)
    etag = first.headers["etag"]

    unchanged = httpx.get(label_url, headers={**_bearer(token), "If-None-Match": etag})
    assert unchanged.status_code == 304
    assert unchanged.content == b""

    _write_heartbeat(wall_settings, wall_id, _minor_3("in_use", since="2026-10-08T21:00:00+00:00"))
    changed = httpx.get(label_url, headers={**_bearer(token), "If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag


# -- admission ----------------------------------------------------------------------------------


def test_the_label_route_refuses_without_a_valid_client_token(label_url, token):
    assert httpx.get(label_url).status_code == 401
    assert httpx.get(label_url, headers=_bearer("not-a-token")).status_code == 401
    assert httpx.get(label_url, headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_another_clients_label_or_an_unknown_one_is_403(server_url, services, label_url, hall_pi):
    """The client showing the wall does not hold its label; holding the panel is what opens it."""
    other = services.access.issue(hall_pi.id).token

    refused = httpx.get(label_url, headers=_bearer(other))
    unknown = httpx.get(server_url + ROUTES["label"]["path"].format(label_id="no-such-label"), headers=_bearer(other))

    for response in (refused, unknown):
        assert response.status_code == 403
        assert response.json() == {"error": "That label output is not this client's."}


def test_a_label_output_captioning_no_wall_is_404_to_its_own_client(server_url, services, wall_id, label_id, token):
    services.clients.remove_label(wall_id, label_id=label_id)

    response = httpx.get(server_url + ROUTES["label"]["path"].format(label_id=label_id), headers=_bearer(token))

    assert response.status_code == 404
    assert response.json() == {"error": "This label output captions no wall."}


# -- the client document names it -----------------------------------------------------------------


def test_the_client_document_lists_its_mapped_labels_and_validates(server_url, label_id, token, wall_id, panel_pi):
    response = httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(token))

    document = response.json()
    assert _CLIENT.is_valid(document)
    assert document["walls"] == []
    assert document["labels"] == [{"label_id": label_id, "output": "epd-0", "wall_id": wall_id}]


def test_the_client_document_of_a_client_showing_a_wall_validates_and_names_its_display(server_url, services, hall_pi, wall_id):
    response = httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(services.access.issue(hall_pi.id).token))

    document = response.json()
    assert _CLIENT.is_valid(document)
    assert document["walls"][0]["display"] == services.display.get_wall(wall_id).display_id
