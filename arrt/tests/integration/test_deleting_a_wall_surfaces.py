"""Deleting a wall over both surfaces: `DELETE /api/walls/{id}` and `art_display(action='delete_wall')`.

Each is one call to `DisplayService.delete_wall`, whose rules are held in
`tests/unit/test_deleting_a_wall.py`. What is held here is that each surface
reaches it with a wall that exists, answers in its own shape, and carries the
service's refusal of one that does not.
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
def study(http):
    return http.post("/api/walls", json={"name": "The study"}).json()


async def _display(server_url: str, action: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_display", {"action": action, **arguments})
    return json.loads(result.content[0].text), bool(result.isError)


# -- HTTP ----------------------------------------------------------------------------------


def test_the_route_deletes_the_wall_and_answers_with_the_walls_that_remain(http, study):
    deleted = http.delete(f"/api/walls/{study['wall_id']}")

    assert deleted.status_code == 200
    listed = http.get("/api/walls").json()
    assert deleted.json() == listed
    assert study["wall_id"] not in {each["wall_id"] for each in listed["walls"]}
    assert len(listed["walls"]) == 1, "the other wall stays"


def test_the_route_refuses_an_unknown_wall_by_its_id(http, study):
    refused = http.delete("/api/walls/nobody")

    assert refused.status_code == 400
    assert "No wall with id 'nobody'" in refused.json()["error"]
    assert len(http.get("/api/walls").json()["walls"]) == 2


# -- MCP -----------------------------------------------------------------------------------


async def test_the_tool_deletes_the_wall_and_names_it(server_url, study):
    payload, errored = await _display(server_url, "delete_wall", wall_id=study["wall_id"])

    assert errored is False, payload
    assert payload["deleted"] == {"wall_id": study["wall_id"], "name": "The study"}
    listed, _ = await _display(server_url, "walls")
    assert "The study" not in [each["name"] for each in listed["walls"]]
    assert listed["count"] == 1


async def test_the_tool_carries_the_services_refusal(server_url, study):
    payload, errored = await _display(server_url, "delete_wall", wall_id="nobody")

    assert errored is True
    assert "No wall with id 'nobody'" in payload["error"]
