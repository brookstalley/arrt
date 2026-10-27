"""Renaming a wall over both surfaces: `POST /api/walls/{id}` and `art_display(action='rename_wall')`.

Each is one call to `DisplayService.rename_wall`, whose rules are held in
`tests/unit/test_renaming_a_wall.py`. What is held here is that each surface
reaches it, answers in its own shape, and carries the service's refusal.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def wall(http):
    [wall] = http.get("/api/walls").json()["walls"]
    return wall


async def _display(server_url: str, action: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_display", {"action": action, **arguments})
    return json.loads(result.content[0].text), bool(result.isError)


# -- HTTP ----------------------------------------------------------------------------------


def test_the_route_renames_the_wall_and_answers_as_the_walls_read_does(http, wall):
    renamed = http.post(f"/api/walls/{wall['wall_id']}", json={"name": "  The hall  "})

    assert renamed.status_code == 200
    [listed] = http.get("/api/walls").json()["walls"]
    assert renamed.json() == listed
    assert listed["name"] == "The hall"


def test_the_route_refuses_another_walls_name_and_keeps_the_old_one(http, wall):
    http.post("/api/walls", json={"name": "The study"})

    refused = http.post(f"/api/walls/{wall['wall_id']}", json={"name": "The study"})

    assert refused.status_code == 400
    assert "The study" in refused.json()["error"]
    names = {each["wall_id"]: each["name"] for each in http.get("/api/walls").json()["walls"]}
    assert names[wall["wall_id"]] == wall["name"]


def test_the_route_refuses_an_unknown_wall_by_its_id(http):
    refused = http.post("/api/walls/nobody", json={"name": "The hall"})

    assert refused.status_code == 400
    assert "No wall with id 'nobody'" in refused.json()["error"]


# -- MCP -----------------------------------------------------------------------------------


async def test_the_tool_renames_the_wall(server_url, wall):
    payload, errored = await _display(server_url, "rename_wall", wall_id=wall["wall_id"], name="The hall")

    assert errored is False, payload
    assert payload["wall"]["wall_id"] == wall["wall_id"]
    assert payload["wall"]["name"] == "The hall"
    listed, _ = await _display(server_url, "walls")
    assert [each["name"] for each in listed["walls"]] == ["The hall"]


async def test_the_tool_refuses_a_blank_name(server_url, wall):
    payload, errored = await _display(server_url, "rename_wall", wall_id=wall["wall_id"], name="   ")

    assert errored is True
    assert "name cannot be empty" in payload["error"]
