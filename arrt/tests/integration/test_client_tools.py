"""Clients and wall assignment through `art_display`, driven by a real MCP client.

`clients.md` makes a client — an installed Player — something the server knows,
and Settings › Clients is where a curator keeps them. These are the same acts on
the tool surface: thin bindings over `ClientService` and `PlayerAccess`, which
the browser's routes call too. Every id below comes out of an earlier answer on
this surface, never out of the store, because an action whose arguments no
caller can obtain is an action nobody can use.

What the tool surface owes beyond reaching the service is checked against the
other surfaces: a token issued here opens `GET /client` over HTTP, and a listing
here carries the fields `GET /api/clients` does.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.programming.client_heartbeat import client_heartbeat_path_in

_REPORT = {
    "reported_at": "2026-10-02T14:00:05+00:00",
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


async def call(server_url: str, action: str, **arguments) -> tuple[dict, bool]:
    """Call `art_display` over real HTTP; return its payload and the protocol's error flag."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("art_display", {"action": action, **arguments})
    return json.loads(result.content[0].text), bool(result.isError)


async def ok(server_url: str, action: str, **arguments) -> dict:
    payload, errored = await call(server_url, action, **arguments)
    assert errored is False and payload["success"] is True, f"art_display(action={action!r}) refused: {payload}"
    return payload


@pytest.fixture
async def wall(server_url) -> str:
    payload = await ok(server_url, "walls")
    return payload["walls"][0]["wall_id"]


@pytest.fixture
async def hall(server_url) -> str:
    """A client recorded through the tool, its id as the tool answered it."""
    added = await ok(server_url, "add_client", name="Hall Pi")
    return added["client"]["client_id"]


def _report(settings, client_id: str, document: dict = _REPORT) -> None:
    """What the client's own heartbeat would have left: the file the server reads."""
    client_heartbeat_path_in(settings.art_root, client_id).write_text(json.dumps(document), encoding="utf-8")


# -- clients ------------------------------------------------------------------------------


async def test_a_client_added_here_is_listed_with_no_token_no_walls_and_no_report(server_url):
    added = await ok(server_url, "add_client", name="  Hall Pi  ")

    assert added["client"]["name"] == "Hall Pi"
    assert added["client"]["token_issued_at"] is None
    assert "issue_client_token" in added["notice"]
    listed = await ok(server_url, "clients")
    assert listed["count"] == 1
    [client] = listed["clients"]
    assert client["client_id"] == added["client"]["client_id"]
    assert client["walls"] == []
    assert client["heartbeat"]["absent"] is True
    assert client["heartbeat"]["description"] == "It has not reported its outputs yet."


async def test_a_client_name_already_taken_is_refused(server_url, hall):
    refused, errored = await call(server_url, "add_client", name="Hall Pi")

    assert errored is True and refused["success"] is False
    assert len((await ok(server_url, "clients"))["clients"]) == 1


async def test_the_listing_carries_what_the_client_reported_in_the_browsers_field_names(server_url, settings, hall):
    """Parity with `GET /api/clients`: one fact, one set of names, on both surfaces."""
    _report(settings, hall)

    [client] = (await ok(server_url, "clients"))["clients"]
    [browser] = httpx.get(f"{server_url}/api/clients").json()["clients"]

    assert client.keys() == browser.keys()
    assert client["heartbeat"].keys() == browser["heartbeat"].keys()
    assert client["heartbeat"]["outputs"] == browser["heartbeat"]["outputs"]
    assert [output["name"] for output in client["heartbeat"]["outputs"]] == ["hdmi-a-1", "hdmi-a-2"]
    assert client["heartbeat"]["outputs"][1] == {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None}
    assert client["heartbeat"]["description"].startswith("It last reported ")
    assert client["heartbeat"]["description"] == browser["heartbeat"]["description"]


async def test_a_report_that_cannot_be_read_is_said_to_be_one(server_url, settings, hall):
    client_heartbeat_path_in(settings.art_root, hall).write_text("{not json", encoding="utf-8")

    [client] = (await ok(server_url, "clients"))["clients"]

    assert client["heartbeat"]["absent"] is False
    assert client["heartbeat"]["outputs"] == []
    assert client["heartbeat"]["description"].startswith("Its last report could not be read: ")


async def test_renaming_a_client_keeps_its_token_and_its_walls(server_url, hall, wall):
    issued = await ok(server_url, "issue_client_token", client_id=hall)
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")

    renamed = await ok(server_url, "rename_client", client_id=hall, name="Study Pi")

    assert renamed["client"] == {**renamed["client"], "client_id": hall, "name": "Study Pi"}
    assert renamed["client"]["token_issued_at"] == issued["token_issued_at"]
    [client] = (await ok(server_url, "clients"))["clients"]
    assert [entry["wall_id"] for entry in client["walls"]] == [wall]
    assert httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"}).status_code == 200


# -- the token -----------------------------------------------------------------------------


async def test_a_token_issued_here_opens_the_players_route_and_is_never_listed(server_url, hall):
    issued = await ok(server_url, "issue_client_token", client_id=hall)

    assert issued["client_id"] == hall
    assert "only time" in issued["notice"]
    assert "CLIENT_TOKEN" in issued["notice"] and "SERVER_URL" in issued["notice"]
    answered = httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"})
    assert answered.status_code == 200
    assert answered.json()["client_id"] == hall
    listed = json.dumps(await ok(server_url, "clients"))
    assert issued["token"] not in listed
    [client] = (await ok(server_url, "clients"))["clients"]
    assert client["token_issued_at"] == issued["token_issued_at"]


async def test_rotating_refuses_the_old_token_and_admits_the_new(server_url, hall):
    first = await ok(server_url, "issue_client_token", client_id=hall)
    second = await ok(server_url, "issue_client_token", client_id=hall)

    assert second["token"] != first["token"]
    assert httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {first['token']}"}).status_code == 401
    assert httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {second['token']}"}).status_code == 200


# -- assignment ------------------------------------------------------------------------------


async def test_assigning_to_a_reported_output_carries_no_notice_and_reaches_the_client(server_url, settings, hall, wall):
    _report(settings, hall)
    issued = await ok(server_url, "issue_client_token", client_id=hall)

    assigned = await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-2")

    assert assigned["notice"] is None
    assert (assigned["wall"]["wall_id"], assigned["wall"]["client_id"], assigned["wall"]["output"]) == (wall, hall, "hdmi-a-2")
    assert assigned["client"]["name"] == "Hall Pi"
    document = httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"}).json()
    assert [(entry["wall_id"], entry["output"]) for entry in document["walls"]] == [(wall, "hdmi-a-2")]
    listed = await ok(server_url, "walls")
    assert next(entry for entry in listed["walls"] if entry["wall_id"] == wall)["client_id"] == hall


async def test_assigning_before_the_client_has_reported_is_kept_and_says_so(server_url, hall, wall):
    assigned = await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")

    assert "has not reported its outputs yet" in assigned["notice"]
    assert assigned["wall"]["output"] == "hdmi-a-1"


async def test_assigning_to_an_output_the_client_did_not_report_names_what_it_did(server_url, settings, hall, wall):
    _report(settings, hall)

    assigned = await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-b-9")

    assert "'hdmi-a-1', 'hdmi-a-2'" in assigned["notice"]
    assert "'hdmi-b-9' is not among them" in assigned["notice"]


async def test_an_output_already_showing_a_wall_refuses_a_second(server_url, hall, wall):
    study = (await ok(server_url, "add_wall", name="Study"))["wall"]["wall_id"]
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")

    refused, errored = await call(server_url, "assign_wall", wall_id=study, client_id=hall, output="hdmi-a-1")

    assert errored is True
    assert "already shows" in refused["error"]
    listed = await ok(server_url, "walls")
    assert next(entry for entry in listed["walls"] if entry["wall_id"] == study)["client_id"] is None


async def test_unassigning_takes_the_wall_off_its_client_and_is_quiet_when_repeated(server_url, hall, wall):
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")

    first = await ok(server_url, "unassign_wall", wall_id=wall)
    again = await ok(server_url, "unassign_wall", wall_id=wall)

    assert (first["wall"]["client_id"], first["wall"]["output"]) == (None, None)
    assert again["wall"]["client_id"] is None
    [client] = (await ok(server_url, "clients"))["clients"]
    assert client["walls"] == []


# -- removal -------------------------------------------------------------------------------


async def test_removing_a_client_names_the_walls_it_leaves_without_one(server_url, hall, wall):
    study = (await ok(server_url, "add_wall", name="Study"))["wall"]["wall_id"]
    await ok(server_url, "add_wall", name="Landing")
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    await ok(server_url, "assign_wall", wall_id=study, client_id=hall, output="hdmi-a-2")
    issued = await ok(server_url, "issue_client_token", client_id=hall)

    removed = await ok(server_url, "remove_client", client_id=hall)

    assert {entry["wall_id"] for entry in removed["released_walls"]} == {wall, study}
    assert "2 walls it showed now have no client" in removed["notice"]
    assert "'Study'" in removed["notice"]
    assert "'Landing'" not in removed["notice"]
    assert (await ok(server_url, "clients"))["clients"] == []
    assert httpx.get(f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"}).status_code == 401


async def test_removing_a_client_that_showed_nothing_says_no_wall_is_affected(server_url, hall):
    removed = await ok(server_url, "remove_client", client_id=hall)

    assert removed["released_walls"] == []
    assert "no wall is affected" in removed["notice"]
    assert "have no client" not in removed["notice"]


async def test_an_unknown_client_is_refused_by_every_act_that_names_one(server_url, wall):
    for action, arguments in [
        ("rename_client", {"name": "x"}),
        ("remove_client", {}),
        ("issue_client_token", {}),
        ("assign_wall", {"wall_id": wall, "output": "hdmi-a-1"}),
    ]:
        refused, errored = await call(server_url, action, client_id="nobody", **arguments)
        assert errored is True, action
        assert "No client with id 'nobody'" in refused["error"], action
