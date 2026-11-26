"""A client's two routes, and the curator's client routes, over real HTTP.

`GET /client` tells a client which walls are its and on which outputs;
`POST /client/heartbeat` is how it reports those outputs. Both are judged against
`contract/schemas/client.v1.schema.json` and `client-heartbeat.v1.schema.json`
and their fixtures, so the server and a Player in another repository agree on
them without either importing the other. The curator's routes under `/api` are
the bindings Settings › Players uses.
"""

import hashlib
import json
from datetime import UTC, datetime

import httpx
import pytest
from arrt_contract import MAX_OUTPUTS_PER_REPORT, fixtures, released, root, routes, validator
from arrt_contract import schema as contract_schema
from async_http import request
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.programming import client_heartbeat
from arrt.programming.client_heartbeat import client_heartbeat_path_in

CONTRACT = root()
ROUTES = routes()
INDEX = fixtures()
HEARTBEATS = [row for row in INDEX if row["schema"] == "schemas/client-heartbeat.v1.schema.json"]
#: The invalid client heartbeats the server refuses whole, and those it keeps,
#: ignoring what breaks the rule: the index's `server_must_refuse` says which.
REFUSED = [row for row in HEARTBEATS if not row["valid"] and row["server_must_refuse"]]
TOLERATED = [row for row in HEARTBEATS if not row["valid"] and not row["server_must_refuse"]]


def _schema(name: str) -> Draft202012Validator:
    return validator(f"schemas/{name}")


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
        {"wall_id": landing.id, "name": "Landing", "output": "hdmi-a-2", "display": landing.display_id},
        {
            "wall_id": wall_id,
            "name": services.display.get_wall(wall_id).name,
            "output": "hdmi-a-1",
            "display": services.display.get_wall(wall_id).display_id,
        },
    ]
    assert document["labels"] == []
    assert "Study" not in response.text


def test_a_client_with_no_walls_gets_an_empty_list(client_url, services):
    idle = services.clients.add_client(name="A spare Pi")
    response = httpx.get(client_url, headers=_bearer(services.access.issue(idle.id).token))

    assert response.status_code == 200
    assert response.json() == {"client_id": idle.id, "name": "A spare Pi", "walls": [], "labels": []}


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


@pytest.mark.parametrize("row", REFUSED, ids=lambda row: row["path"])
def test_every_invalid_client_heartbeat_the_server_must_refuse_is_refused_with_400_and_not_written(
    heartbeat_url, token, hall_pi, wall_settings, row
):
    response = httpx.post(heartbeat_url, json=_fixture(row["path"]), headers=_bearer(token))

    assert response.status_code == 400
    assert response.json()["error"].startswith("That is not a client heartbeat this server can read: ")
    assert not client_heartbeat_path_in(wall_settings.art_root, hall_pi.id).exists()


def test_the_servers_bound_on_outputs_is_the_contracts():
    """`client_heartbeat.MAX_OUTPUTS` quotes the package's `MAX_OUTPUTS_PER_REPORT`: the server cannot read it at run time."""
    assert client_heartbeat.MAX_OUTPUTS == MAX_OUTPUTS_PER_REPORT


#: The two fixtures past the bound, by the rule each breaks, with the words the server refuses them in.
_PAST_THE_BOUND = {
    f"more than {MAX_OUTPUTS_PER_REPORT} outputs": f"at most {MAX_OUTPUTS_PER_REPORT} outputs",
    f"more than {MAX_OUTPUTS_PER_REPORT} label outputs": f"at most {MAX_OUTPUTS_PER_REPORT} label outputs",
}


@pytest.mark.parametrize("row", [row for row in REFUSED if row["constraint"] in _PAST_THE_BOUND], ids=lambda row: row["path"])
def test_a_report_past_the_bound_on_outputs_is_refused_for_that_reason_and_no_other(heartbeat_url, token, hall_pi, row):
    response = httpx.post(heartbeat_url, json=_fixture(row["path"]), headers=_bearer(token))

    assert response.status_code == 400
    assert _PAST_THE_BOUND[row["constraint"]] in response.json()["error"], response.json()


def test_the_index_holds_both_reports_past_the_bound_on_outputs():
    assert sorted(row["constraint"] for row in REFUSED if row["constraint"] in _PAST_THE_BOUND) == sorted(_PAST_THE_BOUND)


def test_the_index_holds_client_heartbeats_the_server_refuses_and_ones_it_keeps():
    """The vacuity check: the parametrised tests either side of this one pass trivially over an empty list."""
    assert REFUSED
    assert TOLERATED


@pytest.mark.parametrize("row", TOLERATED, ids=lambda row: row["path"])
def test_an_invalid_client_heartbeat_the_server_tolerates_is_kept_with_its_outputs(
    heartbeat_url, token, hall_pi, wall_settings, server_url, row
):
    """A report whose `settings_url` fails the schema's check still records the Player's outputs.

    The contract makes the server the tolerant reader of `settings_url`: it links
    the address only after its own check, so a Player's wrong guess at its address
    must not cost it its outputs (`player-contract.md` § Transport).
    """
    document = _fixture(row["path"])

    response = httpx.post(heartbeat_url, json=document, headers=_bearer(token))

    assert response.status_code == 204, response.text
    assert json.loads(client_heartbeat_path_in(wall_settings.art_root, hall_pi.id).read_text(encoding="utf-8")) == document
    listed = next(entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == hall_pi.id)
    assert listed["heartbeat"]["problem"] is None
    assert [output["name"] for output in listed["heartbeat"]["outputs"]] == [output["name"] for output in document["outputs"]]


RELEASED_HEARTBEATS = [
    (version, row)
    for version, release in released().items()
    for row in json.loads((release / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]
    if row["schema"] == "schemas/client-heartbeat.v1.schema.json" and row["valid"]
]


@pytest.mark.parametrize("case", RELEASED_HEARTBEATS, ids=lambda case: f"{case[0]}:{case[1]['path']}")
def test_every_valid_client_heartbeat_of_a_released_contract_is_accepted(heartbeat_url, token, case):
    """What a Player pinned to an older tag writes, this server still takes (audit-7 M6)."""
    version, row = case
    document = json.loads((released()[version] / row["path"]).read_text(encoding="utf-8"))

    response = httpx.post(heartbeat_url, json=document, headers=_bearer(token))

    assert response.status_code == 204, (version, row["path"], response.text)


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
        (
            (
                b'{"reported_at": "2026-10-02T14:00:05Z", "outputs": [], "label_outputs": ['
                b'{"name": "epd-0", "kind": "epaper", "connected": true, "size": null},'
                b'{"name": "epd-0", "kind": "epaper", "connected": false, "size": null}]}'
            ),
            "both called 'epd-0'",
        ),
    ],
    ids=[
        "not-json",
        "not-an-object",
        "instant-without-offset",
        "two-outputs-one-name",
        "screen-of-booleans",
        "two-label-outputs-one-name",
    ],
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


# -- the Player's settings page address (contract 1.2.0) ------------------------------

#: Every client heartbeat fixture carrying `settings_url`, valid and invalid. A
#: fixture whose document is not an object (contract 1.3.0's must-refuse
#: `document-not-an-object`) carries no key at all.
WITH_SETTINGS_URL = [
    row
    for row in HEARTBEATS
    if isinstance(document := _fixture(row["path"]), dict) and client_heartbeat.SETTINGS_URL_KEY in document
]


def test_the_index_holds_settings_addresses_the_server_serves_and_ones_it_does_not():
    """The vacuity check for the parametrised test below, both ways."""
    assert any(row["valid"] for row in WITH_SETTINGS_URL)
    assert any(not row["valid"] for row in WITH_SETTINGS_URL)


def test_the_servers_settings_address_check_is_the_schemas_pattern():
    """The server quotes the schema's pattern (it carries no validator at run time); a quote that drifts is red here."""
    pattern = contract_schema("schemas/client-heartbeat.v1.schema.json")["properties"]["settings_url"]["pattern"]

    assert f"^{client_heartbeat.SETTINGS_URL.pattern}$" == pattern


@pytest.mark.parametrize("row", WITH_SETTINGS_URL, ids=lambda row: row["path"])
def test_a_settings_address_is_served_exactly_when_the_contract_calls_it_valid(heartbeat_url, token, hall_pi, server_url, row):
    """A valid address is served on the Player's row as it came; an invalid one, `javascript:` among them, not at all."""
    document = _fixture(row["path"])

    assert httpx.post(heartbeat_url, json=document, headers=_bearer(token)).status_code == 204
    [listed] = [entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == hall_pi.id]

    assert listed["settings_url"] == (document["settings_url"] if row["valid"] else None)


@pytest.mark.parametrize(
    "address",
    [
        'http://player.example:8771/"><script>alert(1)</script>',
        "http://player.example:8771/\n",
        "http://player.example:8771/ settings",
        "https://",
        "HTTP://player.example/",
        "data:text/html,<p>hi</p>",
    ],
    ids=["markup", "trailing-newline", "space", "no-host", "upper-scheme", "data"],
)
def test_an_address_markup_could_be_made_of_is_never_served(heartbeat_url, token, hall_pi, server_url, address):
    """Beyond the fixtures: nothing that could close an attribute or start a tag reaches the answer."""
    document = {**_fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json"), "settings_url": address}

    assert httpx.post(heartbeat_url, json=document, headers=_bearer(token)).status_code == 204
    [listed] = [entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == hall_pi.id]

    assert listed["settings_url"] is None
    assert listed["heartbeat"]["problem"] is None


def test_a_report_with_no_settings_address_serves_none(heartbeat_url, token, hall_pi, server_url):
    document = _fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json")
    assert "settings_url" not in document

    assert httpx.post(heartbeat_url, json=document, headers=_bearer(token)).status_code == 204
    [listed] = [entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == hall_pi.id]

    assert listed["settings_url"] is None


# -- a Player's state on its row -------------------------------------------------------


def test_each_players_row_carries_its_state_and_each_outputs(heartbeat_url, token, hall_pi, server_url, services):
    """No token, waiting for a first report, and reporting with each output's own state, on `GET /api/clients`."""
    spare = services.clients.add_client(name="A spare Pi")

    def rows():
        return {entry["client_id"]: entry for entry in httpx.get(server_url + "/api/clients").json()["clients"]}

    before = rows()
    assert before[spare.id]["state"] == {"state": "no_token", "since": None, "outputs": []}
    assert before[hall_pi.id]["state"]["state"] == "awaiting_report"
    assert {output["state"] for output in before[hall_pi.id]["state"]["outputs"]} == {"awaiting_report"}

    report = _fixture("fixtures/client-heartbeat.v1/valid/frame-with-identity-and-a-panel.json")
    report["reported_at"] = datetime.now(UTC).isoformat()
    assert httpx.post(heartbeat_url, json=report, headers=_bearer(token)).status_code == 204
    after = rows()[hall_pi.id]["state"]

    assert after["state"] == "reporting"
    assert after["since"] is not None
    reported = {(o["kind"], o["name"]): (o["state"], o["connected"]) for o in after["outputs"]}
    for output in report["outputs"]:
        assert reported[("display", output["name"])] == ("reporting", output["connected"])
    for label in report["label_outputs"]:
        assert reported[("label", label["name"])] == ("reporting", label["connected"])
    # The outputs the server recorded that this report does not list: named by
    # the curator before the Player had them, so each waits for its first report.
    recorded_only = {key for key in reported if key[1] not in {o["name"] for o in report["outputs"]}} - {
        ("label", label["name"]) for label in report["label_outputs"]
    }
    assert recorded_only
    assert {reported[key] for key in recorded_only} == {("awaiting_report", None)}


async def _art_players(server_url: str, action: str) -> dict:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_players", {"action": action})
    assert not result.isError
    return json.loads(result.content[0].text)


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (json.dumps({"reported_at": "2026-10-02T14:00:05+00:00", "outputs": [{"name": "hdmi-a-1", "kind": "hdmi"}]}), None),
        ("{ not json", "its body is not JSON."),
    ],
    ids=["unreadable-report", "not-json"],
)
async def test_a_player_whose_first_report_is_refused_reads_unreadable_with_the_servers_words_on_every_surface(
    heartbeat_url, token, hall_pi, server_url, body, said
):
    """Not waiting for its first report, a setup step: a trouble, with what the Player was told beside it."""
    headers = {**_bearer(token), "Content-Type": "application/json"}
    refused = await request("POST", heartbeat_url, content=body, headers=headers)
    assert refused.status_code == 400

    [row] = [
        each for each in (await request("GET", server_url + "/api/clients")).json()["clients"] if each["client_id"] == hall_pi.id
    ]
    problem = row["heartbeat"]["problem"]
    # The words the Player was refused in, as a person reads them on Players.
    assert problem is not None
    if said is None:
        assert refused.json()["error"].endswith(f": {problem}")
    else:
        assert problem == said
    assert row["state"]["state"] == "report_unreadable"
    assert row["heartbeat"]["description"] == f"Its last report could not be read: {problem}"

    health = (await request("GET", server_url + "/api/health")).json()
    assert [each["state"]["state"] for each in health["players"] if each["client_id"] == hall_pi.id] == ["report_unreadable"]
    assert [(t["about"], t["state"]) for t in health["troubles"] if t["subject"] == hall_pi.id] == [
        ("player", "report_unreadable")
    ]
    assert hall_pi.id not in {step["subject"] for step in health["setup_steps"]}
    # Since when, on each surface, and Status says it in the words Players does.
    since = row["state"]["since"]
    assert since is not None
    assert [each["state"]["since"] for each in health["players"] if each["client_id"] == hall_pi.id] == [since]
    [words] = [t["words"] for t in health["troubles"] if t["subject"] == hall_pi.id]
    assert words.startswith(f"{hall_pi.name}'s reports have been refused for ")
    assert words.endswith(f". {row['heartbeat']['description']}")

    listed = await _art_players(server_url, "clients")
    [player] = [each for each in listed["clients"] if each["client_id"] == hall_pi.id]
    assert player["state"]["state"] == "report_unreadable"
    assert player["state"]["since"] == since
    assert player["heartbeat"]["problem"] == problem

    # A report accepted clears it, on the same surfaces.
    report = _fixture("fixtures/client-heartbeat.v1/valid/frame-and-hdmi.json")
    report["reported_at"] = datetime.now(UTC).isoformat()
    assert (await request("POST", heartbeat_url, json=report, headers=_bearer(token))).status_code == 204
    [row] = [
        each for each in (await request("GET", server_url + "/api/clients")).json()["clients"] if each["client_id"] == hall_pi.id
    ]
    assert (row["state"]["state"], row["heartbeat"]["problem"]) == ("reporting", None)


def test_a_player_with_two_label_panels_and_no_screen_has_a_state_for_each(server_url, services, heartbeat_url):
    """Acceptance 4 (ruling 8): per output, so two panels on one Player read apart."""
    door = services.clients.add_client(name="The Pi by the door")
    token = services.access.issue(door.id).token
    report = _fixture("fixtures/client-heartbeat.v1/valid/panels-and-no-display.json")
    report["reported_at"] = datetime.now(UTC).isoformat()
    assert [label["connected"] for label in report["label_outputs"]] == [True, False]
    assert httpx.post(heartbeat_url, json=report, headers=_bearer(token)).status_code == 204

    [listed] = [entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == door.id]

    assert listed["state"]["outputs"] == [
        {"kind": "label", "name": label["name"], "state": "reporting", "connected": label["connected"]}
        for label in report["label_outputs"]
    ]


# -- the server's reader agrees with the contract --------------------------------------


@pytest.mark.parametrize("row", HEARTBEATS, ids=lambda row: row["path"])
def test_the_servers_reader_agrees_with_the_contract_about_every_client_heartbeat(row):
    """Every fixture the schema accepts, the server accepts; it refuses exactly those the index says it must."""
    must_refuse = not row["valid"] and row["server_must_refuse"]

    assert (client_heartbeat.problem_with(_fixture(row["path"])) is not None) is must_refuse, row["path"]


# -- a Player with several labels and no display (ruling 8 of 2026-11-19) ----------------


def test_a_player_with_several_labels_and_no_display_is_served_each_of_its_labels(server_url, services, heartbeat_url):
    """The shape the owner ruled must stay open: label outputs only, more than one, each captioning its own wall."""
    door = services.clients.add_client(name="The Pi by the door")
    token = services.access.issue(door.id).token
    report = _fixture("fixtures/client-heartbeat.v1/valid/panels-and-no-display.json")
    assert report["outputs"] == []
    assert len(report["label_outputs"]) > 1

    assert httpx.post(heartbeat_url, json=report, headers=_bearer(token)).status_code == 204
    [listed] = [entry for entry in httpx.get(server_url + "/api/clients").json()["clients"] if entry["client_id"] == door.id]
    assert listed["heartbeat"]["problem"] is None
    walls = [services.display.add_wall(name=f"Wall for {output['name']}").id for output in report["label_outputs"]]
    labels = [
        services.clients.add_label(wall, client_id=door.id, output=output["name"]).label.id
        for wall, output in zip(walls, report["label_outputs"], strict=True)
    ]

    response = httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(token))

    assert response.status_code == 200
    document = response.json()
    assert _schema("client.v1.schema.json").is_valid(document)
    assert document["walls"] == []
    assert sorted(document["labels"], key=lambda label: label["output"]) == [
        {"label_id": label_id, "output": output["name"], "wall_id": wall}
        for label_id, output, wall in zip(labels, report["label_outputs"], walls, strict=True)
    ]
    for label_id in labels:
        label = httpx.get(server_url + ROUTES["label"]["path"].format(label_id=label_id), headers=_bearer(token))
        assert label.status_code == 200, label.text


def test_the_contracts_several_labels_document_is_one_the_schema_accepts_with_no_walls():
    """The fixture a Player reads for ruling 8's shape: no walls, and more than one label on as many outputs."""
    document = _fixture("fixtures/client.v1/valid/several-labels-and-no-walls.json")

    assert _schema("client.v1.schema.json").is_valid(document)
    assert document["walls"] == []
    assert len({label["output"] for label in document["labels"]}) == len(document["labels"]) > 1


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


def test_a_wall_is_mapped_to_a_display_and_given_labels_over_http(server_url, services, wall_id, heartbeat_url):
    client = services.clients.add_client(name="The Pi in the hall")
    token = services.access.issue(client.id).token
    report = _fixture("fixtures/client-heartbeat.v1/valid/frame-with-identity-and-a-panel.json")
    assert httpx.post(heartbeat_url, json=report, headers=_bearer(token)).status_code == 204
    [listed] = httpx.get(server_url + "/api/clients").json()["clients"]
    display = next(entry for entry in listed["displays"] if entry["output"] == "hdmi-a-1")

    assigned = httpx.post(server_url + f"/api/walls/{wall_id}/display", json={"display_id": display["display_id"]})
    labelled = httpx.post(server_url + f"/api/walls/{wall_id}/labels", json={"client_id": client.id, "output": "epd-0"})

    assert assigned.status_code == 200
    assert (assigned.json()["wall"]["client_id"], assigned.json()["wall"]["output"]) == (client.id, "hdmi-a-1")
    assert assigned.json()["wall"]["display"]["display_id"] == display["display_id"]
    assert labelled.status_code == 200
    label_id = labelled.json()["label_id"]
    assert [entry["label_id"] for entry in labelled.json()["wall"]["labels"]] == [label_id]
    document = httpx.get(server_url + ROUTES["client"]["path"], headers=_bearer(token)).json()
    assert _schema("client.v1.schema.json").is_valid(document)
    assert document["labels"] == [{"label_id": label_id, "output": "epd-0", "wall_id": wall_id}]

    removed = httpx.delete(server_url + f"/api/walls/{wall_id}/labels/{label_id}")

    assert removed.status_code == 200
    assert removed.json()["labels"] == []


@pytest.mark.parametrize(
    ("method", "path", "body", "names", "status"),
    [
        # A wall or client named that is not there is not found (404); an empty name is refused (400).
        ("POST", "/api/walls/no-such-wall/display", {"display_id": "x"}, "No wall with id", 404),
        ("POST", "/api/walls/no-such-wall/labels", {"client_id": "x", "output": "epd-0"}, "No wall with id", 404),
        ("DELETE", "/api/walls/no-such-wall/labels/x", None, "No wall with id", 404),
        ("POST", "/api/clients", {"name": "  "}, "name cannot be empty", 400),
        ("POST", "/api/clients/no-such-client", {"name": "x"}, "No client with id", 404),
        ("DELETE", "/api/clients/no-such-client", None, "No client with id", 404),
        ("POST", "/api/clients/no-such-client/token", None, "No client with id", 404),
        ("POST", "/api/walls/no-such-wall/client", {"client_id": "x", "output": "frame"}, "No wall with id", 404),
        ("DELETE", "/api/walls/no-such-wall/client", None, "No wall with id", 404),
    ],
)
def test_the_curator_routes_refuse_with_the_services_words(server_url, method, path, body, names, status):
    response = httpx.request(method, server_url + path, json=body)

    assert response.status_code == status
    assert names in response.json()["error"]
