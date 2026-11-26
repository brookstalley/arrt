"""Every installed source plugin, over real HTTP: `GET /api/sources` and `art_discovery(action='source_plugins')`.

The services are built over the plugins this interpreter has installed, read
through their real entry points, so the distribution and version each answers
are the installed metadata's and not a fixture's.
"""

import importlib.metadata
import json
from datetime import UTC, datetime, timedelta

import pytest
from async_http import request
from fakes import FakeRegistry
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.sources import API_VERSION, SourceContext
from arrt.library.sources.loading import SourceRoster, load_sources
from arrt.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    RunKind,
    RunStatus,
    SearchOutcome,
    SourceSearch,
)
from arrt.persistence.sqlite_discovery import SqliteDiscovery

ASKED = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)


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
        # Never searched: the search record holds nothing of it.
        "searched": 0,
        "searches_answered": 0,
        "searches_unasked": 0,
        "searches_owed": 0,
        "last_search_answered_at": None,
        "searches_with_images": 0,
        "searches_median_latency_seconds": None,
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
    # Every field alike, the counts since startup and the search record's
    # included: the tool carries them.
    assert model["sources"] == browser["sources"]
    assert model["count"] == len(browser["sources"])


def _searched(discovery_store: SqliteDiscovery, provider: str) -> None:
    """Five works searched at one source: three answered with images, one with none, one still owed.

    The answers took 2, 4 and 10 seconds, and the one with no image 4, so the
    median of what it answered is 4 s whichever middle is taken.
    """
    discovery_store.add_run(
        DiscoveryRun(
            id="r1",
            kind=RunKind.GET,
            initiated_by=InitiatedBy.WEB_UI,
            status=RunStatus.COMPLETED,
            approval_required=False,
            started_at=ASKED,
        )
    )
    answers = [(2, 3), (4, 1), (10, 2), (4, 0), (None, 0)]
    for n, (seconds, images) in enumerate(answers):
        discovery_store.add_candidate_work(
            CandidateWork(
                id=f"c{n}", discovery_run_id="r1", proposed_title=f"Study No. {n}", rationale="Chosen.", work_dedup_key=f"k{n}"
            )
        )
        asked = ASKED + timedelta(minutes=n)
        discovery_store.record_search(
            SourceSearch(
                candidate_work_id=f"c{n}",
                provider=provider,
                asked_at=asked,
                outcome=SearchOutcome.OWED if seconds is None else SearchOutcome.ANSWERED,
                answered_at=None if seconds is None else asked + timedelta(seconds=seconds),
                images=images,
            )
        )


async def test_the_route_and_the_tool_carry_status_s_three_columns(server_url, discovery_store):
    """Searches 5, a hit rate of 3 of the 4 it answered, and a median latency of 4 s, on both surfaces alike."""
    _searched(discovery_store, "met")

    browser = (await request("GET", f"{server_url}/api/sources")).json()
    met = next(source for source in browser["sources"] if source["name"] == "met")

    assert (met["searched"], met["searches_answered"], met["searches_with_images"], met["searches_owed"]) == (5, 4, 3, 1)
    assert met["searches_median_latency_seconds"] == 4.0
    model = await tool(server_url)
    assert next(source for source in model["sources"] if source["name"] == "met") == met
