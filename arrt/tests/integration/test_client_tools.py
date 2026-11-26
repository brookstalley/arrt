"""Clients and wall assignment through `art_players`, driven by a real MCP client.

`art_display` carried these before the MCP break, when every act on a wall was gathered
there and the Player actions moved to `art_players`, unrenamed (the owner's
ruling 3 of 2026-11-19); the walls themselves are still `art_display`'s.

`clients.md` makes a client — an installed Player — something the server knows,
and Settings › Players is where a curator keeps them. These are the same acts on
the tool surface: thin bindings over `ClientService` and `PlayerAccess`, which
the browser's routes call too. Every id below comes out of an earlier answer on
this surface, never out of the store, because an action whose arguments no
caller can obtain is an action nobody can use.

What the tool surface owes beyond reaching the service is checked against the
other surfaces: a token issued here opens `GET /client` over HTTP, and a listing
here carries the fields `GET /api/clients` does.
"""

import json
from dataclasses import fields
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from async_http import request
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from unit.test_surface_parity import WALL_RENAMES, check_renamed, in_http_names

from arrt import observations
from arrt.http import api as http_api
from arrt.mcp import bindings
from arrt.persistence.records import AcquisitionMethod, QueuedAcquisition, RightsStatus, SourceClass
from arrt.programming import clients as clients_module
from arrt.programming.client_heartbeat import client_heartbeat_path_in
from arrt.programming.manifest.heartbeat import heartbeat_path_in
from arrt.services.health import WallsNow


def _services_clock() -> datetime:
    raise AssertionError("the services' clock is read only inside a test (`_now_is_the_services`)")


@pytest.fixture(autouse=True)
def _now_is_the_services(shared_clock, monkeypatch):
    """`_now` reads the services' clock (`shared_clock`), so what a test writes beside them is on their time."""
    monkeypatch.setitem(globals(), "_services_clock", shared_clock)


def _now() -> datetime:
    return _services_clock()


_REPORT = {
    "reported_at": "2026-10-02T14:00:05+00:00",
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": False, "screen": None},
    ],
}


#: The actions this file calls on `art_display`; every other it calls is `art_players`'.
_ON_THE_WALL_TOOL = frozenset({"walls", "add_wall", "status"})


def _tool(action: str) -> str:
    return "art_display" if action in _ON_THE_WALL_TOOL else "art_players"


async def call(server_url: str, action: str, **arguments) -> tuple[dict, bool]:
    """Call the action's tool over real HTTP; return its payload and the protocol's error flag."""
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(_tool(action), {"action": action, **arguments})
    return json.loads(result.content[0].text), bool(result.isError)


async def ok(server_url: str, action: str, **arguments) -> dict:
    payload, errored = await call(server_url, action, **arguments)
    assert errored is False, f"{_tool(action)}(action={action!r}) refused: {payload}"
    assert payload["success"] is True, f"{_tool(action)}(action={action!r}) refused: {payload}"
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

    assert errored is True
    assert refused["success"] is False
    assert len((await ok(server_url, "clients"))["clients"]) == 1


async def test_the_listing_carries_what_the_client_reported_in_the_browsers_field_names(server_url, settings, hall):
    """Parity with `GET /api/clients`: one fact, one set of names, on both surfaces."""
    # A token and a report, so the Player is `reporting`; a settings page address
    # the contract's pattern passes, so `settings_url` is a value and not the null default.
    await ok(server_url, "issue_client_token", client_id=hall)
    _report(settings, hall, {**_REPORT, "reported_at": _now().isoformat(), "settings_url": "http://player.example:8080/"})

    [client] = (await ok(server_url, "clients"))["clients"]
    [browser] = (await request("GET", f"{server_url}/api/clients")).json()["clients"]

    assert client.keys() == browser.keys()
    # The Player's state, each output's, and its settings page: the tool carries
    # them in the route's values.
    assert client["state"] == browser["state"]
    assert client["state"]["state"] == "reporting"
    assert [output["name"] for output in client["state"]["outputs"]] == ["hdmi-a-1", "hdmi-a-2"]
    assert client["settings_url"] == browser["settings_url"] == "http://player.example:8080/"
    assert client["heartbeat"].keys() == browser["heartbeat"].keys()
    assert client["heartbeat"]["outputs"] == browser["heartbeat"]["outputs"]
    assert [output["name"] for output in client["heartbeat"]["outputs"]] == ["hdmi-a-1", "hdmi-a-2"]
    assert client["heartbeat"]["outputs"][1] == {
        "name": "hdmi-a-2",
        "kind": "framebuffer",
        "connected": False,
        "screen": None,
        "identity": None,
    }
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
    assert (
        await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"})
    ).status_code == 200


# -- the token -----------------------------------------------------------------------------


async def test_a_token_issued_here_opens_the_players_route_and_is_never_listed(server_url, hall):
    issued = await ok(server_url, "issue_client_token", client_id=hall)

    assert issued["client_id"] == hall
    assert "only time" in issued["notice"]
    assert "CLIENT_TOKEN" in issued["notice"]
    assert "SERVER_URL" in issued["notice"]
    answered = await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"})
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
    assert (
        await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {first['token']}"})
    ).status_code == 401
    assert (
        await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {second['token']}"})
    ).status_code == 200


# -- assignment ------------------------------------------------------------------------------


async def test_assigning_to_a_reported_output_carries_no_notice_and_reaches_the_client(server_url, settings, hall, wall):
    _report(settings, hall)
    issued = await ok(server_url, "issue_client_token", client_id=hall)

    assigned = await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-2")

    assert assigned["notice"] is None
    assert (assigned["wall"]["wall_id"], assigned["wall"]["client_id"], assigned["wall"]["output"]) == (wall, hall, "hdmi-a-2")
    assert assigned["client"]["name"] == "Hall Pi"
    document = (await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"})).json()
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
    assert (
        await request("GET", f"{server_url}/client", headers={"Authorization": f"Bearer {issued['token']}"})
    ).status_code == 401


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


# -- each wall's display state ------------------------------------------------------------


async def test_the_walls_read_carries_each_walls_display_state_in_the_browsers_shape(server_url, settings, hall, wall):
    """Parity with `GET /api/walls`: an assigned wall says what its screen reported, an unassigned one says so."""
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    await ok(server_url, "add_wall", name="Study")
    heartbeat_path_in(settings.art_root, wall).write_text(
        json.dumps(
            {
                "reported_at": _now().isoformat(timespec="seconds"),
                "current_work_id": "w-dali-1",
                "schema": {"major": 1, "minor": 3},
                "display_state": {"state": "in_use", "work_id": None, "since": "2026-10-08T20:15:00-06:00"},
            }
        ),
        encoding="utf-8",
    )

    tool = {each["wall_id"]: each["display_state"] for each in (await ok(server_url, "walls"))["walls"]}
    browser = {
        each["wall_id"]: each["display_state"] for each in (await request("GET", f"{server_url}/api/walls")).json()["walls"]
    }

    # The age is read at each request, so it is the one field the two may differ in; and the work is
    # `artwork_id` on the tool, `work_id` on the route, the rename map's one pair.
    renames = WALL_RENAMES["DisplayState"]
    check_renamed("DisplayState", set(tool[wall]), set(browser[wall]), renames)
    assert {k: {f: v for f, v in s.items() if f != "age_seconds"} for k, s in in_http_names(tool, renames).items()} == {
        k: {f: v for f, v in s.items() if f != "age_seconds"} for k, s in browser.items()
    }
    assert tool[wall]["state"] == "in_use"
    assert tool[wall]["artwork_id"] is None
    assert tool[wall]["since"] == "2026-10-08T20:15:00-06:00"
    assert tool[wall]["last"] is None
    [study] = [state for wall_id, state in tool.items() if wall_id != wall]
    assert study == {
        "state": "unassigned",
        "artwork_id": None,
        "since": None,
        "reported_at": None,
        "age_seconds": None,
        "last": None,
    }


# -- displays and labels ----------------------------------------------------------------------

_FRAME = "uuid:8e7b6c2a-1f3d-4e5a-9b0c-2d4e6f8a0b1c"


def _frame_report() -> dict:
    return {
        "reported_at": _now().isoformat(timespec="seconds"),
        "outputs": [{"name": "frame", "kind": "frame", "connected": True, "screen": None, "identity": _FRAME}],
        "label_outputs": [{"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]}],
    }


async def test_a_wall_is_mapped_to_a_display_by_the_id_the_listing_gives(server_url, services, hall, wall):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(hall)
    services.clients.record_heartbeat(hall, _frame_report())
    [client] = (await ok(server_url, "clients"))["clients"]
    [display] = client["displays"]
    assert (display["identity"], display["kind"], display["output"], display["wall_id"]) == (_FRAME, "frame", "frame", None)

    assigned = await ok(server_url, "assign_display", wall_id=wall, display_id=display["display_id"])

    assert assigned["notice"] is None
    assert (assigned["wall"]["display_id"], assigned["wall"]["client_id"], assigned["wall"]["output"]) == (
        display["display_id"],
        hall,
        "frame",
    )
    assert assigned["wall"]["display"]["identity"] == _FRAME


async def test_labels_are_added_and_removed_by_ids_the_surface_gives(server_url, services, hall, wall):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(hall)
    services.clients.record_heartbeat(hall, _frame_report())
    [client] = (await ok(server_url, "clients"))["clients"]
    assert client["label_outputs"][0]["output"] == "epd-0"

    added = await ok(server_url, "add_label", wall_id=wall, client_id=hall, output="epd-0")

    assert added["notice"] is None
    [label] = added["wall"]["labels"]
    assert (label["label_id"], label["client_id"], label["client_name"], label["output"]) == (
        added["label_id"],
        hall,
        "Hall Pi",
        "epd-0",
    )
    listed = next(entry for entry in (await ok(server_url, "walls"))["walls"] if entry["wall_id"] == wall)
    assert [entry["label_id"] for entry in listed["labels"]] == [added["label_id"]]

    removed = await ok(server_url, "remove_label", wall_id=wall, label_id=listed["labels"][0]["label_id"])

    assert removed["wall"]["labels"] == []


async def test_a_wall_reads_the_same_on_both_surfaces_display_and_labels_included(server_url, services, hall, wall):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(hall)
    services.clients.record_heartbeat(hall, _frame_report())
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="frame")
    await ok(server_url, "add_label", wall_id=wall, client_id=hall, output="epd-0")

    tool = next(entry for entry in (await ok(server_url, "walls"))["walls"] if entry["wall_id"] == wall)
    browser = next(
        entry for entry in (await request("GET", f"{server_url}/api/walls")).json()["walls"] if entry["wall_id"] == wall
    )

    for key in ("client_id", "output", "display_id", "display", "labels"):
        assert tool[key] == browser[key], key
    assert browser["display"]["identity"] == _FRAME
    assert len(browser["labels"]) == 1


async def test_a_display_two_clients_report_is_named_on_both_surfaces_with_both_names(server_url, services, hall, wall):
    # A Player reports only with a token, and one with none is `no_token` whatever it reports (`player_state.py`).
    services.access.issue(hall)
    services.clients.record_heartbeat(hall, _frame_report())
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="frame")
    other = (await ok(server_url, "add_client", name="Study Mac"))["client"]["client_id"]
    services.access.issue(other)
    services.clients.record_heartbeat(other, _frame_report())

    tool = {entry["client_id"]: entry for entry in (await ok(server_url, "clients"))["clients"]}
    browser = {entry["client_id"]: entry for entry in (await request("GET", f"{server_url}/api/clients")).json()["clients"]}
    walls = (await request("GET", f"{server_url}/api/walls")).json()["walls"]

    for client_id in (hall, other):
        [fault] = tool[client_id]["faults"]
        assert fault == browser[client_id]["faults"][0]
        assert [entry["name"] for entry in fault["clients"]] == ["Hall Pi", "Study Mac"]
        assert fault["wall_id"] == wall
        assert "Hall Pi and Study Mac both report" in fault["description"]
        assert tool[client_id]["walls"] == []
    shown = next(entry for entry in walls if entry["wall_id"] == wall)
    assert shown["display"]["fault"]["description"] == fault["description"]
    assert shown["display_state"]["state"] == "unassigned"


# -- the status: art_display(action='status') beside GET /api/health ---------------------------


async def test_the_status_carries_the_health_models_readings_value_for_value(
    server_url, services, settings, store, service, hall, wall
):
    """Each Player's state, each wall's display state, the failed fetches, the troubles and the setup steps.

    One reading, held still so its ages are one instant's, built through both
    surfaces' own formatters: `art_display(action='status')`'s binding and
    `GET /api/health`'s. The household is made over the tool surface to hold one
    of each thing the top bar can say: a Player not heard from for three hours
    and the wall it shows (one trouble), a wall no Player shows and a Player with
    no token (two setup steps), and a work whose picture failed to fetch.
    """
    stale = (_now() - timedelta(hours=3)).isoformat()
    await ok(server_url, "issue_client_token", client_id=hall)
    _report(settings, hall, {**_REPORT, "reported_at": stale})
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    settings.heartbeat_path(wall).write_text(json.dumps({"reported_at": stale}), encoding="utf-8")
    spare = (await ok(server_url, "add_wall", name="The landing"))["wall"]["wall_id"]
    untokened = (await ok(server_url, "add_client", name="Spare Pi"))["client"]["client_id"]
    work = service.add_artwork(title="Nighthawks")
    service.add_source(
        artwork_id=work.id,
        url=f"https://museum.example/{work.id}.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )
    store.set_queued_acquisition(
        QueuedAcquisition(artwork_id=work.id, failures=2, next_try_at=_now() + timedelta(hours=20), detail="a 404.")
    )

    reading = services.health.observe()
    tool = bindings._wall_status(SimpleNamespace(health=SimpleNamespace(observe=lambda: reading)), {})
    route = http_api._health(reading).model_dump()

    for key in ("players", "failed_fetches", "troubles", "setup_steps"):
        assert tool[key] == route[key], key
    by_wall = {entry["wall_id"]: entry for entry in route["walls"]}
    for entry in tool["walls"]:
        assert in_http_names(entry["display_state"], WALL_RENAMES["DisplayState"]) == by_wall[entry["wall_id"]]["display_state"]
    # The case itself, so a quiet household cannot pass as agreement.
    assert {player["client_id"]: player["state"]["state"] for player in tool["players"]} == {
        hall: "not_heard_from",
        untokened: "no_token",
    }
    # A fresh Library has never been backed up, which is a trouble too; the rest are this case's.
    assert [(t["about"], t["subject"]) for t in tool["troubles"]] == [
        ("player", hall),
        ("backup", None),
        ("failed_fetches", None),
    ]
    assert [(s["about"], s["subject"]) for s in tool["setup_steps"]] == [("wall", spare), ("player", untokened)]
    assert tool["failed_fetches"]["count"] == 1
    assert {entry["wall_id"]: entry["display_state"]["state"] for entry in tool["walls"]} == {
        wall: "silent",
        spare: "unassigned",
    }
    # And over the wire, the status answers every one of them.
    payload = await ok(server_url, "status")
    assert {"players", "failed_fetches", "troubles", "setup_steps"} <= payload.keys()
    assert [player["client_id"] for player in payload["players"]] == [player["client_id"] for player in tool["players"]]
    assert all("display_state" in entry for entry in payload["walls"])


async def test_the_walls_of_a_player_still_being_set_up_are_setup_steps_on_both_surfaces(server_url, hall, wall):
    """A Player with a token and no report, and one with no token: each shows a wall, and neither wall is a trouble.

    Each wall has never reported, which by itself reads `silent`; it has not
    because its Player has not yet been able to, so `GET /api/health` and
    `art_display(action='status')` both name it in its Player's one setup step
    (one step for one cause, not a step for the wall beside the
    Player's), never among the troubles, and both say so in their sentence.
    """
    await ok(server_url, "issue_client_token", client_id=hall)
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    landing = (await ok(server_url, "add_wall", name="The landing"))["wall"]["wall_id"]
    spare = (await ok(server_url, "add_client", name="Spare Pi"))["client"]["client_id"]
    await ok(server_url, "assign_wall", wall_id=landing, client_id=spare, output="hdmi-a-1")

    route = (await request("GET", f"{server_url}/api/health")).json()
    tool = await ok(server_url, "status")

    for answer in (route, tool):
        assert {entry["wall_id"]: entry["display_state"]["state"] for entry in answer["walls"]} == {
            wall: "silent",
            landing: "silent",
        }
        assert not [t for t in answer["troubles"] if t["about"] in {"wall", "player"}], answer["troubles"]
        names = {entry["wall_id"]: entry["wall_name"] for entry in answer["walls"]}
        # One step per Player, each naming the wall that waits for it; no wall's own.
        assert {(s["about"], s["subject"]): (s["state"], s["words"]) for s in answer["setup_steps"]} == {
            ("player", hall): ("awaiting_report", f"Hall Pi is waiting for its first report, and so is {names[wall]}"),
            ("player", spare): ("no_token", "Spare Pi has no token yet, so The landing waits for it"),
        }
        assert [s["about"] for s in answer["setup_steps"]] == ["player", "player"]
        assert "has not reported" not in (answer["description"] if answer is route else answer["observation"])
    # The route's walls say which Player each waits for; the tool's twin is the step.
    assert {entry["wall_id"]: entry["waiting_for"]["state"] for entry in route["walls"]} == {
        wall: "awaiting_report",
        landing: "no_token",
    }


async def test_one_player_with_no_token_showing_two_walls_is_one_step_on_the_route_and_the_status(server_url, hall, wall):
    """On both surfaces: one step naming both walls, one sentence, and no trouble.

    Before, both answered three steps for this household: one for each wall,
    and the Player's.
    """
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    study = (await ok(server_url, "add_wall", name="The study"))["wall"]["wall_id"]
    await ok(server_url, "assign_wall", wall_id=study, client_id=hall, output="hdmi-a-2")

    route = (await request("GET", f"{server_url}/api/health")).json()
    tool = await ok(server_url, "status")

    names = sorted(entry["wall_name"] for entry in route["walls"])
    one = [("player", hall, "no_token", f"Hall Pi has no token yet, so {names[0]} and {names[1]} wait for it")]
    for answer in (route, tool):
        assert [(s["about"], s["subject"], s["state"], s["words"]) for s in answer["setup_steps"]] == one
        assert not [t for t in answer["troubles"] if t["about"] in {"wall", "player"}], answer["troubles"]
    said = f"{names[0]} and {names[1]} wait for Hall Pi, which has no token yet."
    assert route["description"] == tool["observation"] == said


async def test_whom_a_wall_waits_for_is_said_by_the_status_the_walls_and_the_walls_answer(server_url, services, hall, wall):
    """MCP's status, MCP's walls and `GET /api/walls` each name the Player both walls wait for.

    In the health answer's own words (`services.health.walls_waiting`), value
    for value with `GET /api/health`'s; and a wall a Player shows, beside them,
    waits for nothing on every surface. Before, only the health answer said it,
    and the status's walls read as a wall no Player had reported for.
    """
    await ok(server_url, "assign_wall", wall_id=wall, client_id=hall, output="hdmi-a-1")
    study = (await ok(server_url, "add_wall", name="The study"))["wall"]["wall_id"]
    await ok(server_url, "assign_wall", wall_id=study, client_id=hall, output="hdmi-a-2")
    shown = (await ok(server_url, "add_wall", name="The landing"))["wall"]["wall_id"]
    reporting = (await ok(server_url, "add_client", name="Landing Pi"))["client"]["client_id"]
    services.access.issue(reporting)
    services.clients.record_heartbeat(reporting, _frame_report())
    await ok(server_url, "assign_wall", wall_id=shown, client_id=reporting, output="frame")

    health = {e["wall_id"]: e["waiting_for"] for e in (await request("GET", f"{server_url}/api/health")).json()["walls"]}
    walls_answer = {e["wall_id"]: e["waiting_for"] for e in (await request("GET", f"{server_url}/api/walls")).json()["walls"]}
    status = {e["wall_id"]: e["waiting_for"] for e in (await ok(server_url, "status"))["walls"]}
    listed = {e["wall_id"]: e["waiting_for"] for e in (await ok(server_url, "walls"))["walls"]}

    # The case itself, so a household where nothing waits cannot pass as agreement.
    assert {key: (wait and (wait["client_id"], wait["state"])) for key, wait in health.items()} == {
        wall: (hall, "no_token"),
        study: (hall, "no_token"),
        shown: None,
    }
    assert health[study]["words"] == "The study waits for Hall Pi, which has no token yet"
    assert walls_answer == status == listed == health
    # One wall's answer says it too, not only the list.
    renamed = (await request("POST", f"{server_url}/api/walls/{study}", json={"name": "The study"})).json()
    assert renamed["waiting_for"] == health[study]


# -- one answer, one reading --------------------------------------------------------------

#: Every answer that says a wall's display state beside who shows it, whom it
#: waits for or whether its Player reads the feed.
_WALL_ANSWERS = ("GET /api/walls", "one wall's answer", "art_display walls", "GET /api/health", "art_display status")


async def _answer_about(server_url: str, surface: str, wall: str, name: str) -> dict | None:
    """The one wall's entry in `surface`'s answer; None when the answer does not hold the wall."""
    if surface == "GET /api/walls":
        walls = (await request("GET", f"{server_url}/api/walls")).json()["walls"]
    elif surface == "one wall's answer":
        answer = await request("POST", f"{server_url}/api/walls/{wall}", json={"name": name})
        return None if answer.status_code == 404 else answer.json()
    elif surface == "art_display walls":
        walls = (await ok(server_url, "walls"))["walls"]
    elif surface == "GET /api/health":
        walls = (await request("GET", f"{server_url}/api/health")).json()["walls"]
    else:
        walls = (await ok(server_url, "status"))["walls"]
    return next((entry for entry in walls if entry["wall_id"] == wall), None)


def _wall_report(work_id: str, majors: list[int] | None = None) -> str:
    document: dict = {"reported_at": _now().isoformat(timespec="seconds"), "current_work_id": work_id}
    if majors is not None:
        document["capabilities"] = {"backend": "frame", "label_modes": ["none"], "manifest_majors": majors}
    return json.dumps(document)


def _says_one_instant(entry: dict) -> list[str]:
    """What in one wall's entry contradicts the rest of it, in words; empty when it says one instant.

    Each field is checked where the answer carries it: the health answers carry
    the state and the wait, the walls answers who shows the wall too.
    """
    state = entry["display_state"]["state"]
    wait = entry["waiting_for"]
    wrong = []
    if wait is not None and state != "silent":
        wrong.append(f"waits for {wait['name']} beside display_state {state!r}")
    if "client_id" in entry:
        display = entry["display"]
        shown = entry["client_id"] is not None and (display is None or display["fault"] is None)
        if shown == (state == "unassigned"):
            wrong.append(f"display_state {state!r} beside client_id {entry['client_id']!r}")
        if wait is not None and wait["client_id"] != entry["client_id"]:
            wrong.append(f"waits for {wait['client_id']!r} beside client_id {entry['client_id']!r}")
        if display is None and entry["display_id"] is not None:
            wrong.append(f"display_id {entry['display_id']!r} beside no display")
        if display is not None and (display["display_id"], display["wall_id"]) != (entry["display_id"], entry["wall_id"]):
            wrong.append(f"display_id {entry['display_id']!r} beside display {display['display_id']!r} on {display['wall_id']!r}")
    return wrong


class _Household:
    """A wall and a Player made for one landing and taken away after it, so every landing meets the same household."""

    def __init__(self, services, settings, step: int) -> None:
        self.services = services
        self.settings = settings
        self.name = f"Wall {step}"
        self.wall = services.display.add_wall(name=self.name).id
        self.player = services.clients.add_client(name=f"Player {step}").id

    def assign(self) -> None:
        self.services.clients.assign_wall(self.wall, client_id=self.player, output="hdmi-a-1")

    def report(self, document: str) -> None:
        self.settings.heartbeat_path(self.wall).write_text(document, encoding="utf-8")

    def leave(self) -> None:
        if any(view.wall.id == self.wall for view in self.services.display.survey_walls()):
            self.services.display.delete_wall(self.wall)
        self.services.clients.remove_client(self.player)


def _nothing_more(_entry: dict) -> list[str]:
    return []


def _waits_exactly_while_silent(entry: dict) -> list[str]:
    # The Player stays in setup throughout, so nothing but its wait can explain a silence.
    if (entry["waiting_for"] is None) == (entry["display_state"]["state"] == "silent"):
        return [f"display_state {entry['display_state']['state']!r} beside waiting_for {entry['waiting_for']}"]
    return []


def _reads_feed_of_the_report_its_state_is(entry: dict) -> list[str]:
    if "reads_feed" not in entry:
        return []
    shown = entry["display_state"].get("work_id", entry["display_state"].get("artwork_id"))
    if (shown == "wrk_before") != (entry["reads_feed"] is True) or (entry["feed_notice"] is None) != (
        entry["reads_feed"] is not False
    ):
        return [f"display_state showing {shown!r} beside reads_feed {entry['reads_feed']!r}"]
    return []


def _report_arrives(house: _Household):
    """Its Player has a token and has not reported; the wall's first report lands."""
    house.services.access.issue(house.player)
    house.assign()
    return (lambda: house.report(_wall_report("wrk_1"))), _waits_exactly_while_silent


def _player_assigned(house: _Household):
    """An unassigned wall; a Player with no token is assigned to it."""
    return house.assign, _nothing_more


def _feed_major_changes(house: _Household):
    """The wall shows a work from a Player reading major 2; its Player, updated, reports another work and major 1 alone."""
    house.services.access.issue(house.player)
    house.assign()
    house.report(_wall_report("wrk_before", [2]))
    return (lambda: house.report(_wall_report("wrk_after", [1]))), _reads_feed_of_the_report_its_state_is


def _wall_deleted(house: _Household):
    """A wall its Player, with no token, would show; the wall is deleted."""
    house.assign()
    return (lambda: house.services.display.delete_wall(house.wall)), _nothing_more


_LANDINGS = {
    "a report arrives": _report_arrives,
    "a Player is assigned": _player_assigned,
    "a Player is updated across a feed major": _feed_major_changes,
    "the wall is deleted": _wall_deleted,
}


class _Landing:
    """Runs `land` once, just before the report read numbered `before` (from 0): every read an answer makes is one."""

    def __init__(self, read) -> None:
        self._read = read
        self.reads = 0
        self.before: int | None = None
        self.land = None
        self.landed = False

    def arm(self, land, before: int) -> None:
        self.reads, self.before, self.land, self.landed = 0, before, land, False

    def disarm(self) -> None:
        self.before = None

    def __call__(self, path, **kwargs):
        if self.before is not None and self.reads == self.before and not self.landed:
            self.landed = True
            self.land()
        self.reads += 1
        return self._read(path, **kwargs)


@pytest.mark.parametrize("landing", _LANDINGS)
@pytest.mark.parametrize("surface", _WALL_ANSWERS)
async def test_whatever_lands_between_an_answers_reads_it_says_one_instant_of_the_wall(
    server_url, services, settings, monkeypatch, surface, landing
):
    """Everything an answer says of a wall is one reading's: its state, its wait, who shows it, its display, its feed.

    What lands is written just before the answer's first read of a report
    file, then before its second, and so on until the answer makes fewer reads
    than that: deterministically, before every read it makes (the reads are
    wrapped; no thread races them). Each landing meets a household made for it
    and taken away after, so every one meets the same. However many reads the
    answer makes, it never says two instants of the wall at once. Before, a
    walls answer read the reports and the placements more than once, and a
    landing between two reads made it say both.
    """
    landings = _Landing(observations.observe)
    monkeypatch.setattr(observations, "observe", landings)
    wrong: list[str] = []
    before = 0
    while True:
        house = _Household(services, settings, before)
        land, agrees = _LANDINGS[landing](house)
        landings.arm(land, before)
        entry = await _answer_about(server_url, surface, house.wall, house.name)
        landings.disarm()
        if entry is not None:
            wrong += [f"{surface}, landing before read {before}: {each}" for each in _says_one_instant(entry) + agrees(entry)]
        house.leave()
        if not landings.landed:
            break
        before += 1

    assert before >= 2, f"{surface} made {before} report reads, so nothing could land between two"
    assert not wrong, "\n".join(wrong)


async def test_a_walls_or_health_answer_reads_each_report_file_once_however_many_walls_and_players(
    server_url, services, settings, monkeypatch
):
    """Every walls answer and every health answer reads each report file once, and one wall's answer no other wall's.

    With W walls and P Players a list reads W + P report files, each once:
    every wall's, and every Player's, since who shows a wall depends on every
    Player's report (a display two report now is in fault). One wall's answer
    reads its own report and every Player's. Before, one list read each wall's
    report three times and each Player's 2W + 2 times, the walls' survey taking
    a survey of every Player for each wall; the health answer read each
    Player's twice, once for the walls and once for the Players.
    """
    walls = [services.display.add_wall(name=name).id for name in ("Study", "Landing", "Attic")]
    players = [services.clients.add_client(name=name).id for name in ("Study Pi", "Landing Pi")]
    for each in players:
        services.access.issue(each)
        _report(settings, each, {**_REPORT, "reported_at": _now().isoformat()})
    services.clients.assign_wall(walls[0], client_id=players[0], output="hdmi-a-1")
    services.clients.assign_wall(walls[1], client_id=players[0], output="hdmi-a-2")
    services.clients.assign_wall(walls[2], client_id=players[1], output="hdmi-a-1")
    for each in walls:
        settings.heartbeat_path(each).write_text(_wall_report("wrk_1", [2]), encoding="utf-8")
    every_wall = [view.wall.id for view in services.display.survey_walls()]
    named = {str(settings.heartbeat_path(each)): f"wall {each}'s report" for each in every_wall} | {
        str(client_heartbeat_path_in(settings.art_root, each)): f"Player {each}'s report" for each in players
    }
    read = observations.observe
    counted: list[str] = []

    def counting(path, **kwargs):
        counted.append(str(path))
        return read(path, **kwargs)

    monkeypatch.setattr(observations, "observe", counting)

    async def reads_of(answer) -> dict[str, int]:
        counted.clear()
        await answer
        return {named[path]: counted.count(path) for path in named if path in counted}

    for surface, answer in (
        ("GET /api/walls", request("GET", f"{server_url}/api/walls")),
        ("art_display walls", ok(server_url, "walls")),
        ("GET /api/health", request("GET", f"{server_url}/api/health")),
        ("art_display status", ok(server_url, "status")),
    ):
        seen = await reads_of(answer)
        assert seen == dict.fromkeys(named.values(), 1), f"{surface}, W={len(every_wall)} P={len(players)}: {seen}"
    one = await reads_of(request("POST", f"{server_url}/api/walls/{walls[0]}", json={"name": "Study"}))
    own = [f"wall {walls[0]}'s report", *(f"Player {each}'s report" for each in players)]
    assert one == dict.fromkeys(own, 1), f"one wall's answer: {one}"


# -- one Players answer, one reading ------------------------------------------------------

#: Every answer that says what a Player shows beside the wall on each of its displays.
_PLAYER_ANSWERS = ("GET /api/clients", "art_players clients", "renaming a Player")


async def _player_entry(server_url: str, surface: str, player: str, name: str) -> dict:
    """The one Player's entry in `surface`'s answer; a refused answer fails here, since none should refuse."""
    if surface == "renaming a Player":
        answer = await request("POST", f"{server_url}/api/clients/{player}", json={"name": name})
        assert answer.status_code == 200, answer.text
        return answer.json()
    if surface == "GET /api/clients":
        answer = await request("GET", f"{server_url}/api/clients")
        assert answer.status_code == 200, answer.text
        players = answer.json()["clients"]
    else:
        players = (await ok(server_url, "clients"))["clients"]
    [entry] = [each for each in players if each["client_id"] == player]
    return entry


def _says_one_instant_of_the_player(entry: dict) -> list[str]:
    """What in one Player's entry contradicts the rest of it, in words; empty when it says one instant.

    The walls it shows and the wall on each of its displays are one fact said
    twice: a display out of fault holding a wall is a wall it shows.
    """
    shown = {wall["wall_id"] for wall in entry["walls"]}
    on_displays = {display["wall_id"] for display in entry["displays"] if display["wall_id"] and display["fault"] is None}
    return [] if shown == on_displays else [f"shows walls {sorted(shown)} beside displays holding {sorted(on_displays)}"]


class _PlayerHousehold:
    """A Player that has reported its screens and a wall it does not show yet, made for one landing and taken away after."""

    def __init__(self, services, step: int) -> None:
        self.services = services
        self.name = f"Player {step}"
        self.wall = services.display.add_wall(name=f"Wall {step}").id
        self.player = services.clients.add_client(name=self.name).id
        services.clients.record_heartbeat(self.player, {**_REPORT, "reported_at": _now().isoformat()})

    def assign(self) -> None:
        self.services.clients.assign_wall(self.wall, client_id=self.player, output="hdmi-a-1")

    def leave(self) -> None:
        if any(view.wall.id == self.wall for view in self.services.display.survey_walls()):
            self.services.display.delete_wall(self.wall)
        self.services.clients.remove_client(self.player)


def _shows_it_now(house: _PlayerHousehold):
    """The Player is assigned the wall while the answer is read."""
    return house.assign


def _its_wall_is_deleted(house: _PlayerHousehold):
    """The Player shows the wall; the wall is deleted while the answer is read."""
    house.assign()
    return lambda: house.services.display.delete_wall(house.wall)


_PLAYER_LANDINGS = {"the Player is assigned a wall": _shows_it_now, "the wall it shows is deleted": _its_wall_is_deleted}


@pytest.mark.parametrize("landing", _PLAYER_LANDINGS)
@pytest.mark.parametrize("surface", _PLAYER_ANSWERS)
async def test_whatever_lands_between_a_players_answers_reads_it_says_one_instant_of_the_player(
    server_url, services, monkeypatch, surface, landing
):
    """The walls a Player shows and the wall on each of its displays are one reading's, on both surfaces.

    What lands is written just before the answer's first read of a report
    file, then before its second, and so on until the answer makes fewer reads
    than that, as the walls answers' test does. Before, a Players answer took a
    survey of who shows what for its views and a second for its displays, and
    a Player assigned between the two was answered showing a wall beside a
    display holding none. A wall deleted while the answer is read is
    answered, never refused.
    """
    landings = _Landing(observations.observe)
    monkeypatch.setattr(observations, "observe", landings)
    wrong: list[str] = []
    before = 0
    while True:
        house = _PlayerHousehold(services, before)
        land = _PLAYER_LANDINGS[landing](house)
        landings.arm(land, before)
        entry = await _player_entry(server_url, surface, house.player, house.name)
        landings.disarm()
        wrong += [f"{surface}, landing before read {before}: {each}" for each in _says_one_instant_of_the_player(entry)]
        house.leave()
        if not landings.landed:
            break
        before += 1

    assert before >= 1, f"{surface} read no report, so nothing could land while it was read"
    assert not wrong, "\n".join(wrong)


async def test_a_players_answer_reads_each_players_report_once_and_no_walls(server_url, services, settings, monkeypatch):
    """Every Players answer reads each Player's report once, and no wall's: three Players, four walls.

    Before, the list read each Player's report twice, once for the views and
    once for the survey its displays were said from, and so did the answers
    to adding and renaming one.
    """
    walls = [services.display.add_wall(name=name).id for name in ("Study", "Landing", "Attic")]
    players = [services.clients.add_client(name=name).id for name in ("Study Pi", "Landing Pi", "Attic Pi")]
    for each in players:
        services.access.issue(each)
        _report(settings, each, {**_REPORT, "reported_at": _now().isoformat()})
    for wall, player in zip(walls, players, strict=True):
        services.clients.assign_wall(wall, client_id=player, output="hdmi-a-1")
    every_wall = [view.wall.id for view in services.display.survey_walls()]
    assert len(every_wall) == 4, every_wall
    for each in every_wall:
        settings.heartbeat_path(each).write_text(_wall_report("wrk_1", [2]), encoding="utf-8")
    walls_reports = {str(settings.heartbeat_path(each)) for each in every_wall}
    read = observations.observe
    counted: list[str] = []

    def counting(path, **kwargs):
        counted.append(str(path))
        return read(path, **kwargs)

    for surface, answer in (
        ("GET /api/clients", lambda: request("GET", f"{server_url}/api/clients")),
        ("art_players clients", lambda: ok(server_url, "clients")),
        ("renaming a Player", lambda: request("POST", f"{server_url}/api/clients/{players[0]}", json={"name": "Study Pi"})),
        ("adding a Player", lambda: request("POST", f"{server_url}/api/clients", json={"name": "Hall Pi"})),
    ):
        counted.clear()
        monkeypatch.setattr(observations, "observe", counting)
        await answer()
        monkeypatch.setattr(observations, "observe", read)
        seen = {path: counted.count(path) for path in set(counted)}
        every_player = {
            str(client_heartbeat_path_in(settings.art_root, view.client.id)) for view in services.clients.list_clients()
        }
        assert not walls_reports & seen.keys(), f"{surface} read a wall's report"
        assert seen == dict.fromkeys(every_player, 1), f"{surface}, P={len(every_player)} W={len(every_wall)}: {seen}"


async def test_a_players_answer_names_every_output_it_reported_several_labels_and_no_display(server_url, services):
    """A Player with two label panels and no screen is answered with both, on both surfaces (ruling 8)."""
    door = services.clients.add_client(name="Door Pi").id
    services.access.issue(door)
    labels = [{"name": name, "kind": "epaper", "connected": True, "size": [800, 480]} for name in ("epd-0", "epd-1")]
    services.clients.record_heartbeat(door, {"reported_at": _now().isoformat(), "outputs": [], "label_outputs": labels})

    [tool] = [each for each in (await ok(server_url, "clients"))["clients"] if each["client_id"] == door]
    listed = (await request("GET", f"{server_url}/api/clients")).json()["clients"]
    [route] = [each for each in listed if each["client_id"] == door]
    renamed = (await request("POST", f"{server_url}/api/clients/{door}", json={"name": "Door Pi"})).json()

    for answer in (tool, route, renamed):
        assert answer["displays"] == []
        assert answer["walls"] == []
        assert [label["output"] for label in answer["label_outputs"]] == ["epd-0", "epd-1"]
        assert [label["name"] for label in answer["heartbeat"]["label_outputs"]] == ["epd-0", "epd-1"]
        assert answer["heartbeat"]["outputs"] == []


def test_a_walls_answer_judges_each_walls_state_once_and_carries_it_once(services, settings, monkeypatch):
    """`WallsNow` holds a wall's display state in its view alone, and its wait is judged from that one.

    Before, `observe_walls` judged each wall's state for its view and again
    for a second copy it carried beside the view: two places for one fact.
    """
    for name in ("Study", "Landing"):
        services.display.add_wall(name=name)
    judged: list[str] = []
    judge = clients_module.display_state_of

    def counting(reading, *, shown):
        judged.append(str(reading.path))
        return judge(reading, shown=shown)

    monkeypatch.setattr(clients_module, "display_state_of", counting)
    now = services.health.observe_walls()

    assert {field.name for field in fields(WallsNow)} == {"views", "waiting", "survey", "report_problems"}
    assert len(now.views) >= 3, "the walls the test added, and the one a catalogue starts with"
    assert sorted(judged) == sorted(str(settings.heartbeat_path(view.wall.id)) for view in now.views)
