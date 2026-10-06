"""Every installed source plugin, over real HTTP: `GET /api/sources` and `art_discovery(action='sources')`.

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

from arrt.library.services.previews import PreviewSettings
from arrt.library.sources import SourceContext
from arrt.library.sources.loading import SourceRoster, load_sources


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


@pytest.fixture
def preview_settings(settings) -> PreviewSettings:
    """The built-ins include finders, and a roster with a finder needs somewhere to keep previews."""
    return PreviewSettings(art_root=settings.art_root, directory=settings.previews_path)


async def tool(server_url: str) -> dict:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_discovery", {"action": "sources"})
    assert not result.isError
    return json.loads(result.content[0].text)


async def test_the_route_lists_each_plugin_with_its_distribution_version_and_parts(server_url):
    listing = (await request("GET", f"{server_url}/api/sources")).json()
    by_name = {source["name"]: source for source in listing["sources"]}

    assert listing["interface_version"] == "1.1"
    assert [source["name"] for source in listing["sources"]][:3] == ["commons", "artic", "met"]
    assert by_name["met"] | {"description": None} == {
        "name": "met",
        "state": "loaded",
        "reason": None,
        "faults": 0,
        "last_fault_at": None,
        "last_fault_age_seconds": None,
        "last_fault": None,
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
    assert model["sources"] == browser["sources"]
    assert model["count"] == len(browser["sources"])
