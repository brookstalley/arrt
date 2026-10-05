"""The rules on a curator's Wikidata item hold on both surfaces, not only in the browser.

`architecture.md` puts operation logic in the service layer so a click and an
agent get the same answer. The browser's control refuses an item another artist
already has and shows an item before storing it; these drive the same refusals
through `POST /api/artists|works/{id}/wikidata` and through
`art_catalogue(action='set_*_qid')`, with a fake registry installed where the
entry point would build Wikidata's.
"""

import json

import httpx
import pytest
from fakes import FakeRegistry
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROTHKO = "Q160149"
MISSING = "Q999999999"


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    text = "".join(block.text for block in result.content if block.type == "text")
    try:
        return json.loads(text), bool(result.isError)
    except json.JSONDecodeError:
        return {"error": text}, bool(result.isError)


@pytest.fixture
def registry():
    return FakeRegistry(missing={MISSING})


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def two_artists(services, service):
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    service.add_artwork(title="Untitled", artist_id=rothko.id)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    other = service.add_artist(name="M. Rothko")
    work = service.add_artwork(title="Theirs", artist_id=other.id)
    return rothko, other, work


class TestAnItemAnotherArtistHas:
    def test_is_refused_over_http_naming_who_has_it(self, http, services, two_artists):
        _rothko, other, _work = two_artists

        refused = http.post(f"/api/artists/{other.id}/wikidata", json={"qid": ROTHKO})

        assert refused.status_code == 400
        assert refused.json()["error"] == f"Mark Rothko already has {ROTHKO}. Correct that artist first, or merge the two."
        assert services.artists.get(other.id).artist.wikidata_qid is None

    async def test_is_refused_to_an_agent_the_same_way(self, server_url, services, two_artists):
        _rothko, other, _work = two_artists

        answer, failed = await call(server_url, "art_catalogue", action="set_artist_qid", artist_id=other.id, qid=ROTHKO)

        assert failed
        assert "Mark Rothko already has" in json.dumps(answer)
        assert services.artists.get(other.id).artist.wikidata_qid is None

    def test_setting_it_again_on_the_artist_who_has_it_is_fine(self, http, two_artists):
        rothko, _other, _work = two_artists

        assert http.post(f"/api/artists/{rothko.id}/wikidata", json={"qid": ROTHKO}).status_code == 200


class TestAnItemWikidataDoesNotHave:
    def test_is_refused_for_a_work_over_http(self, http, services, two_artists):
        _rothko, _other, work = two_artists

        refused = http.post(f"/api/works/{work.id}/wikidata", json={"qid": MISSING})

        assert (refused.status_code, refused.json()["error"]) == (400, f"Wikidata has no item {MISSING}.")

    async def test_is_refused_for_an_artist_to_an_agent(self, server_url, two_artists):
        _rothko, other, _work = two_artists

        answer, failed = await call(server_url, "art_catalogue", action="set_artist_qid", artist_id=other.id, qid=MISSING)

        assert failed
        assert f"Wikidata has no item {MISSING}." in json.dumps(answer)

    def test_a_registry_that_cannot_be_asked_refuses_rather_than_passes(self, http, registry, two_artists):
        _rothko, _other, work = two_artists
        registry.failing = True

        refused = http.post(f"/api/works/{work.id}/wikidata", json={"qid": "Q5"})

        assert refused.status_code == 400
        assert "could not be checked" in refused.json()["error"]

    def test_there_is_none_needs_no_registry(self, http, registry, two_artists):
        _rothko, _other, work = two_artists
        registry.failing = True

        assert http.post(f"/api/works/{work.id}/wikidata", json={"qid": None}).status_code == 200


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_the_curators_word_stands_unchecked(self, http, two_artists):
        _rothko, _other, work = two_artists

        assert http.post(f"/api/works/{work.id}/wikidata", json={"qid": MISSING}).status_code == 200

    def test_the_duplicate_rule_still_holds(self, http, two_artists):
        _rothko, other, _work = two_artists

        assert http.post(f"/api/artists/{other.id}/wikidata", json={"qid": ROTHKO}).status_code == 400
