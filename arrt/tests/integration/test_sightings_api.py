"""Question 1 over real HTTP and MCP: hosts by count, and no sighting's address in either answer.

`tests/unit/test_sightings.py` holds the rules: what is a sighting, and which
works are counted. This holds the two surfaces that answer, against a real
server, and a Get on the threaded path recording what it found, through the
runner the plane itself wires. A sighting's URL came from a registry anyone can
edit, so neither surface may carry it, as a link or as anything else
(`security-model.md` § Direction): the host is reported as a name.
"""

import json

import httpx
import pytest
from async_http import request
from fakes import FakeFinder, FakeRegistry, a_roster
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.discovery.images import FoundPage
from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.previews import PreviewSettings
from arrt.library.sources.wikidata import WikidataFinder
from arrt.persistence.discovery_records import CandidateWork, RunStatus, Verdict
from arrt.services.container import Services

DROWNING_GIRL = ItemId("Q5308687")

#: A page whose path and query would show if the address leaked.
PAGE = "https://www.moma.org/collection/works/80249?leak=sighting-path-marker"

#: An Art Institute object page: its plugin's, so never a sighting.
ARTIC_PAGE = "https://www.artic.edu/artworks/27992/a-sunday-on-la-grande-jatte-1884"


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(
        works={
            DROWNING_GIRL: RegistryWork(
                qid=DROWNING_GIRL,
                title=RegistryText("Drowning Girl"),
                sitelinks=10,
                creators=(RegistryCreator(qid=ItemId("Q151679"), name=RegistryText("Roy Lichtenstein")),),
            )
        },
        pages={DROWNING_GIRL: [PAGE, ARTIC_PAGE]},
    )


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, registry):
    """The plane with a museum holding only near-matches, and the Wikidata finder over the registry."""
    return Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        sources=a_roster(FakeFinder(), WikidataFinder(registry=registry)),
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
        registry=registry,
    )


@pytest.fixture
def sighted(services, discovery_store, run):
    discovery_store.add_candidate_work(
        CandidateWork(
            id="drowning-girl",
            discovery_run_id=run.id,
            proposed_title="Drowning Girl",
            rationale="Asked for.",
            work_dedup_key="drowning girl",
            wikidata_qid="Q5308687",
            verdict=Verdict.WANTED,
        )
    )
    services.sightings.record("Q5308687", [FoundPage(url=PAGE)], work_title="Drowning Girl")


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def test_the_route_counts_hosts_and_carries_no_address(sighted, http):
    answer = http.get("/api/sightings/hosts")

    assert answer.status_code == 200
    assert answer.json() == {"hosts": [{"host": "www.moma.org", "works": 1}]}
    assert "/collection/works" not in answer.text
    assert "sighting-path-marker" not in answer.text


def test_the_route_answers_an_empty_list_when_nothing_was_sighted(http):
    assert http.get("/api/sightings/hosts").json() == {"hosts": []}


async def test_the_mcp_action_names_the_same_facts_and_no_address(sighted, server_url):
    payload, errored = await call(server_url, "art_review", action="sighting_hosts")

    assert errored is False
    assert payload["hosts"] == [{"host": "www.moma.org", "works": 1}]
    assert payload["count"] == 1
    assert "sighting-path-marker" not in json.dumps(payload)
    assert "/collection/works" not in json.dumps(payload)


async def test_a_get_records_what_it_found_through_the_runner_the_plane_wires(server_url):
    """The museum holds only a near-match, so the work is left open, and MoMA's page is counted."""
    started = await request("POST", f"{server_url}/api/gets", json={"qids": [DROWNING_GIRL]}, timeout=10)
    assert started.status_code == 200, started.text
    assert (await finished(server_url, started.json()["run"]["run_id"]))["status"] == "completed"

    assert (await request("GET", f"{server_url}/api/sightings/hosts", timeout=10)).json() == {
        "hosts": [{"host": "www.moma.org", "works": 1}]
    }


async def finished(server_url: str, run_id: str) -> dict:
    """Poll the surface's own long-poll until the run stops moving."""
    for _ in range(8):
        payload, _errored = await call(server_url, "art_discovery", action="status", run_id=run_id)
        if RunStatus(payload["status"]).is_terminal:
            return payload
    raise AssertionError(f"run {run_id} never finished: {payload}")
