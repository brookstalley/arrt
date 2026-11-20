"""Every installed source plugin, over real HTTP: `GET /api/sources` and `art_discovery(action='source_plugins')`.

The services are built over the plugins this interpreter has installed, read
through their real entry points, so the distribution and version each answers
are the installed metadata's and not a fixture's.
"""

import importlib.metadata
import json

import pytest
from async_http import request
from fakes import FakeRegistry
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.sources import API_VERSION, SourceContext
from arrt.library.sources.loading import SourceRoster, load_sources

#: The could-not-be-asked and answered counts, as fields: on `/api/sources` first
#: (wave 2b, Chunk 32), and the search record's counts (Chunk 33); Chunk 53 gives
#: the tool their twins and removes this.
HTTP_ONLY = frozenset(
    {
        "unasked",
        "last_unasked_at",
        "last_unasked_age_seconds",
        "last_unasked",
        "answered",
        "searched",
        "searches_answered",
        "searches_unasked",
        "searches_owed",
        "last_search_answered_at",
    }
)


@pytest.fixture
def sources() -> SourceRoster:
    """The built-ins, with Wikidata's agent set and the Art Institute's not, so one declines."""
    return load_sources(
        SourceContext(
            environ={"WIKIDATA_USER_AGENT": "arrt-tests/0"},
            user_agent="arrt-tests/0",
            preview_max_bytes=1_000_000,
            registry=FakeRegistry(),
        )
    )


async def tool(server_url: str) -> dict:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_discovery", {"action": "source_plugins"})
    assert not result.isError
    return json.loads(result.content[0].text)


async def test_the_route_lists_each_plugin_with_its_distribution_version_and_parts(server_url):
    listing = (await request("GET", f"{server_url}/api/sources")).json()
    by_name = {source["name"]: source for source in listing["sources"]}

    assert listing["interface_version"] == "{}.{}".format(*API_VERSION)
    # 1.4: every plugin carries the name a curator knows it by.
    assert by_name["met"]["museum"] == "Metropolitan Museum of Art"
    assert all(source["museum"] for source in listing["sources"])
    assert [source["name"] for source in listing["sources"]][:3] == ["commons", "artic", "getty"]
    assert by_name["met"] | {"description": None} == {
        "name": "met",
        "museum": "Metropolitan Museum of Art",
        "state": "loaded",
        "reason": None,
        "faults": 0,
        "last_fault_at": None,
        "last_fault_age_seconds": None,
        "last_fault": None,
        "unasked": 0,
        "last_unasked_at": None,
        "last_unasked_age_seconds": None,
        "last_unasked": None,
        "answered": 0,
        # Never searched: the search record holds nothing of it (Chunk 33).
        "searched": 0,
        "searches_answered": 0,
        "searches_unasked": 0,
        "searches_owed": 0,
        "last_search_answered_at": None,
        "description": None,
        "distribution": "arrt",
        "version": importlib.metadata.version("arrt"),
        "api_major": 1,
        "provides": ["finds_images", "reads"],
    }
    assert by_name["artic"]["state"] == "declined"
    assert "ARTIC_USER_AGENT" in by_name["artic"]["reason"]
    assert by_name["artic"]["provides"] == []
    assert by_name["wikidata"]["provides"] == ["finds_pages"]


async def test_the_tool_answers_what_the_route_answers(server_url):
    """Parity with `GET /api/sources`: one reading, one set of names and values, on both surfaces."""
    browser = (await request("GET", f"{server_url}/api/sources")).json()
    model = await tool(server_url)

    assert model["success"] is True
    assert model["interface_version"] == browser["interface_version"]
    assert model["sources"] == [
        {name: value for name, value in each.items() if name not in HTTP_ONLY} for each in browser["sources"]
    ]
    assert all(
        set(each) >= HTTP_ONLY and not HTTP_ONLY & set(model_each)
        for each, model_each in zip(browser["sources"], model["sources"], strict=True)
    ), "an exemption for a field the tool now carries, or one the route no longer does"
    assert model["count"] == len(browser["sources"])
