"""Watches through the real server: the route and the MCP tool write the same records and refuse alike."""

import json

import httpx

WORDS = "new abstract expressionist paintings in museum collections"


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """One MCP tool call over the mounted surface, as an agent would make it."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def route(server_url: str, method: str, path: str, **body) -> httpx.Response:
    return httpx.request(method, f"{server_url}/api{path}", json=body or None, timeout=30)


def allow(server_url: str, amount: str) -> None:
    assert route(server_url, "POST", "/settings/unattended_allowance_usd", value=amount).status_code == 200


async def test_a_watch_written_over_mcp_reads_back_the_same_from_the_route(server_url):
    allow(server_url, "5")

    written, errored = await call(
        server_url, "art_watches", action="create", intent_text=WORDS, cadence="weekly", monthly_cap_usd="2"
    )
    assert not errored, written
    watch = written["watch"]
    assert (watch["created_by"], watch["effective_cadence"], watch["monthly_cap_usd"]) == ("mcp_client", "weekly", "2.00")

    assert route(server_url, "GET", f"/watches/{watch['watch_id']}").json() == watch
    assert route(server_url, "GET", "/watches").json() == {"watches": [watch]}
    listed, _ = await call(server_url, "art_watches", action="list")
    assert listed["watches"] == [watch]


def test_the_browser_writes_changes_and_removes_a_watch(server_url):
    created = route(server_url, "POST", "/watches", intent_text=WORDS)
    assert created.status_code == 200
    watch = created.json()
    assert (watch["enabled"], watch["cadence"], watch["effective_cadence"], watch["created_by"]) == (
        True,
        None,
        "daily",
        "web_ui",
    )

    paused = route(server_url, "POST", f"/watches/{watch['watch_id']}", enabled=False)
    assert paused.status_code == 200
    assert (paused.json()["enabled"], paused.json()["intent_text"]) == (False, WORDS)

    removed = route(server_url, "DELETE", f"/watches/{watch['watch_id']}")
    assert removed.json()["watch_id"] == watch["watch_id"]
    assert route(server_url, "GET", "/watches").json() == {"watches": []}
    gone = route(server_url, "GET", f"/watches/{watch['watch_id']}")
    assert gone.status_code == 400
    assert "No Watch with id" in gone.json()["error"]


async def test_a_cap_above_the_allowance_is_refused_alike_by_the_route_and_the_tool(server_url):
    allow(server_url, "1")

    refused = route(server_url, "POST", "/watches", intent_text=WORDS, monthly_cap_usd="1.01")
    assert refused.status_code == 400
    assert "cannot be more than it; got $1.01" in refused.json()["error"]

    payload, errored = await call(server_url, "art_watches", action="create", intent_text=WORDS, monthly_cap_usd="1.01")
    assert errored
    assert "cannot be more than it; got $1.01" in payload["error"]
    assert route(server_url, "GET", "/watches").json() == {"watches": []}


async def test_a_watch_changed_over_mcp_names_mcp_as_its_last_writer(server_url):
    watch = route(server_url, "POST", "/watches", intent_text=WORDS).json()

    changed, errored = await call(server_url, "art_watches", action="update", watch_id=watch["watch_id"], cadence="hourly")

    assert not errored, changed
    assert (changed["watch"]["created_by"], changed["watch"]["updated_by"], changed["watch"]["cadence"]) == (
        "web_ui",
        "mcp_client",
        "hourly",
    )
