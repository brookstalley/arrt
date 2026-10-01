"""The curator's word on a work's or an artist's Wikidata item, on both surfaces.

Matching is a hand-run command (`python -m arrt.identify`); what a click
and an agent can do is set the identity, or say there is none, and read it back.
Both surfaces are driven for real because the claim is that the field reaches a
reader, and a service test passes with the field never serialised.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads("".join(block.text for block in result.content if block.type == "text")), bool(result.isError)


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def dali(seeded_service):
    entries = seeded_service.list_artworks().entries
    work = next(entry.artwork for entry in entries if entry.artwork.title == "The Persistence of Memory")
    return work, work.artist_id


class TestTheBrowserSurface:
    def test_a_work_is_identified_by_hand_and_the_listing_says_so(self, http, dali):
        work, _artist_id = dali

        dossier = http.post(f"/api/works/{work.id}/wikidata", json={"qid": " q5579 "}).raise_for_status().json()

        assert (dossier["work"]["wikidata_qid"], dossier["work"]["wikidata_qid_set_by"]) == ("Q5579", "curator")
        listed = http.get("/api/works", params={"q": "persistence"}).raise_for_status().json()["works"][0]
        assert listed["wikidata_qid"] == "Q5579"

    def test_saying_there_is_none_is_recorded_as_the_curators(self, http, dali):
        work, _artist_id = dali

        dossier = http.post(f"/api/works/{work.id}/wikidata", json={"qid": None}).raise_for_status().json()

        assert (dossier["work"]["wikidata_qid"], dossier["work"]["wikidata_qid_set_by"]) == (None, "curator")

    def test_an_artist_is_identified_by_hand(self, http, dali):
        _work, artist_id = dali

        artist = http.post(f"/api/artists/{artist_id}/wikidata", json={"qid": "Q5577"}).raise_for_status().json()

        assert (artist["wikidata_qid"], artist["wikidata_qid_set_by"]) == ("Q5577", "curator")

    def test_a_url_is_refused_with_what_an_id_looks_like(self, http, dali):
        work, _artist_id = dali

        refused = http.post(f"/api/works/{work.id}/wikidata", json={"qid": "https://www.wikidata.org/wiki/Q5579"})

        assert refused.status_code == 400
        assert "Q160149" in refused.json()["error"]

    def test_an_unknown_artist_is_refused_by_name(self, http):
        refused = http.post("/api/artists/nobody/wikidata", json={"qid": "Q1"})

        assert refused.status_code == 400
        assert "nobody" in refused.json()["error"]


class TestTheToolSurface:
    async def test_an_agent_identifies_a_work(self, server_url, dali):
        work, _artist_id = dali

        payload, errored = await call(server_url, "art_catalogue", action="set_work_qid", artwork_id=work.id, qid="Q5579")

        assert errored is False
        assert payload["artwork"]["wikidata_qid"] == "Q5579"
        got, _ = await call(server_url, "art_catalogue", action="get", artwork_id=work.id)
        assert (got["artwork"]["wikidata_qid"], got["artwork"]["wikidata_qid_set_by"]) == ("Q5579", "curator")

    async def test_an_agent_says_an_artist_has_none(self, server_url, dali):
        _work, artist_id = dali

        payload, errored = await call(server_url, "art_catalogue", action="set_artist_qid", artist_id=artist_id, qid="None")

        assert errored is False
        assert (payload["artist"]["wikidata_qid"], payload["artist"]["wikidata_qid_set_by"]) == (None, "curator")
