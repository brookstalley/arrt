"""The Wikidata picker over real HTTP and MCP: the matches offered, and the curator's pick.

`tests/unit/test_wikidata_match.py` holds the rules: what is searched, in what
order, and that nothing is stored but the pick. This holds the routes a browser
and an agent call, against a real server with a fake registry behind it, so no
test reaches Wikidata.
"""

import json

import httpx
import pytest
from fakes import FakeRegistry
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWorkMatch

DALI = RegistryCreator(qid=ItemId("Q5577"), name=RegistryText("Salvador Dalí"))


@pytest.fixture
def registry():
    """What Wikidata answered for *Lobster Telephone* on 2026-10-02: two Dalí items, the famous one first."""
    return FakeRegistry(
        matches={
            "Lobster Telephone Salvador Dalí": [
                RegistryWorkMatch(qid=ItemId("Q2990594"), title=RegistryText("Lobster Telephone"), sitelinks=13, creator=DALI),
                RegistryWorkMatch(qid=ItemId("Q63109663"), title=RegistryText("Lobster Telephone"), sitelinks=0, creator=DALI),
            ]
        }
    )


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def test_the_matches_route_offers_the_registry_s_items_and_stores_nothing(http, propose, discovery):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    body = http.get(f"/api/candidates/{work.id}/wikidata-matches").json()

    assert body["state"] == "known"
    assert [match["qid"] for match in body["matches"]] == ["Q2990594", "Q63109663"]
    assert body["matches"][0] == {
        "qid": "Q2990594",
        "title": "Lobster Telephone",
        "creator": "Salvador Dalí",
        "sitelinks": 13,
        "has_image": False,
        "by_proposed_artist": True,
    }
    assert discovery.get_candidate_work(work.id).wikidata_qid is None


def test_picking_an_item_records_it_and_answers_with_the_work(http, propose, discovery):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    answer = http.put(f"/api/candidates/{work.id}/wikidata-item", json={"qid": "Q2990594"})

    assert answer.status_code == 200
    assert answer.json()["wikidata_qid"] == "Q2990594"
    assert discovery.get_candidate_work(work.id).wikidata_qid == "Q2990594"


def test_a_pick_that_is_not_an_item_is_refused_with_why(http, propose):
    work = propose("Lobster Telephone (1938)")

    answer = http.put(f"/api/candidates/{work.id}/wikidata-item", json={"qid": "lobster"})

    assert answer.status_code >= 400
    assert "not a Wikidata item id" in answer.text


async def test_an_agent_is_offered_the_same_matches_and_can_pick_one(server_url, propose, discovery):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    offered, errored = await call(server_url, "art_review", action="wikidata_matches", work_id=work.id)
    assert errored is False
    assert [match["qid"] for match in offered["matches"]] == ["Q2990594", "Q63109663"]

    picked, errored = await call(server_url, "art_review", action="set_wikidata_item", work_id=work.id, qid="Q2990594")
    assert errored is False
    assert picked["wikidata_qid"] == "Q2990594"
    assert discovery.get_candidate_work(work.id).wikidata_qid == "Q2990594"
