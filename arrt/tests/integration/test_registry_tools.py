"""The registry's pages as `art_discovery` actions, compared whole against the routes they twin.

Ask's agent finds art with these, so each must say what the browser's page says:
the same field names and the same values, held rows marked the same way. A test
per action compares the tool's payload to the route's JSON entire, so a field
added to either surface and not the other fails here by name.

The one deliberate difference is `artist` on a held artist: the page's route
answers "go to their own page" and asks Wikidata nothing, while an agent wants
what else there is of theirs, so the tool answers as the held artist's own
`/registry` route does, with `artist_id` naming them.
"""

import json

import httpx
import pytest
from fakes import FakeRegistry
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryPerson,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicWork,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
    TopicKind,
)

BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1050250"
ROTHKO = "Q160149"
HELD_ROTHKO = "Q20270685"
RENAISSANCE = "Q4692"
HUNTERS_FILE = CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg")


@pytest.fixture
def registry():
    bruegel = RegistryCreator(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Brueghel the Elder"))
    return FakeRegistry(
        people={
            "bruegel": [
                RegistryPerson(qid=ItemId(BRUEGEL), label=RegistryText("Pieter Brueghel the Elder"), born=1525, died=1569)
            ],
            "rothko": [RegistryPerson(qid=ItemId(ROTHKO), label=RegistryText("Mark Rothko"), born=1903, died=1970)],
        },
        matches={
            "bruegel": [
                RegistryWorkMatch(
                    qid=ItemId(HUNTERS),
                    title=RegistryText("The Hunters in the Snow"),
                    sitelinks=39,
                    image=HUNTERS_FILE,
                    creator=bruegel,
                ),
                RegistryWorkMatch(qid=ItemId(HARVESTERS), title=RegistryText("The Harvesters"), sitelinks=30, creator=bruegel),
            ]
        },
        works={
            HUNTERS: RegistryWork(
                qid=ItemId(HUNTERS),
                title=RegistryText("The Hunters in the Snow"),
                sitelinks=39,
                year=1565,
                creators=(bruegel,),
                media=("oil paint", "panel"),
                holders=(
                    RegistryHolder(qid=ItemId("Q95569"), name=RegistryText("Kunsthistorisches Museum"), inventory="GG_1838"),
                ),
            ),
        },
        artists={
            BRUEGEL: RegistryArtist(
                qid=ItemId(BRUEGEL),
                name=RegistryText("Pieter Brueghel the Elder"),
                born=1525,
                died=1569,
                movements=("Northern Renaissance",),
                works=(
                    RegistryWorkEntry(
                        qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39, year=1565
                    ),
                ),
                works_total=125,
            ),
            ROTHKO: RegistryArtist(
                qid=ItemId(ROTHKO),
                name=RegistryText("Mark Rothko"),
                works=(RegistryWorkEntry(qid=ItemId(HELD_ROTHKO), title=RegistryText("Untitled"), sitelinks=3),),
                works_total=800,
            ),
        },
        similar={
            BRUEGEL: [RegistrySimilar(qid=ItemId(ROTHKO), name=RegistryText("Mark Rothko"), sitelinks=150, images=1)],
        },
        topics={
            RENAISSANCE: RegistryTopic(
                qid=ItemId(RENAISSANCE),
                label=RegistryText("Renaissance"),
                kinds=(TopicKind.MOVEMENT,),
                description=RegistryText("era"),
            )
        },
        topic_works={
            RENAISSANCE: [
                RegistryTopicWork(
                    qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39, creators=(bruegel,)
                )
            ]
        },
        topic_artists={
            RENAISSANCE: [
                RegistrySimilar(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Brueghel the Elder"), sitelinks=90, images=40)
            ]
        },
        topics_found={
            "renaissance": [
                RegistryTopic(qid=ItemId(RENAISSANCE), label=RegistryText("Renaissance"), kinds=(TopicKind.MOVEMENT,))
            ]
        },
    )


@pytest.fixture
def held(services, service):
    """Rothko in the library, identified, with one work in circulation carrying a QID."""
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    kept = service.add_artwork(title="Untitled", artist_id=rothko.id)
    services.identity.set_work_identity(kept.id, HELD_ROTHKO)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    return rothko, kept


async def call(server_url: str, **arguments) -> dict:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_discovery", arguments)
    payload = json.loads(result.content[0].text)
    assert payload.pop("success") is True, payload
    return payload


async def route(server_url: str, path: str, **params) -> dict:
    async with httpx.AsyncClient(base_url=server_url, timeout=30.0) as client:
        return (await client.get(path, params=params)).raise_for_status().json()


async def test_search_is_the_results_pages_search(server_url, held):
    payload = await call(server_url, action="search", q="bruegel")

    assert payload == await route(server_url, "/api/registry/search", q="bruegel", wide="true")
    assert [work["qid"] for work in payload["works"]] == [HUNTERS, HARVESTERS]


async def test_find_topics_is_the_topic_search(server_url):
    payload = await call(server_url, action="find_topics", q="renaissance")

    assert payload == await route(server_url, "/api/registry/topics", q="renaissance")
    assert [topic["qid"] for topic in payload["topics"]] == [RENAISSANCE]


async def test_an_artist_not_held_is_their_page_by_qid(server_url, held):
    payload = await call(server_url, action="artist", qid=BRUEGEL)

    assert payload == await route(server_url, f"/api/registry/artists/{BRUEGEL}")
    assert payload["artist_id"] is None
    assert [work["qid"] for work in payload["works"]] == [HUNTERS]


async def test_a_held_artist_is_their_own_pages_registry_half_naming_them(server_url, held):
    rothko, kept = held

    payload = await call(server_url, action="artist", qid=ROTHKO)
    page = await route(server_url, f"/api/artists/{rothko.id}/registry")

    # The page by QID says only "held" and asks nothing; the tool must not.
    assert payload["state"] == "known"
    assert payload == {**page, "artist_id": rothko.id}
    assert [(work["qid"], work["held_artwork_ids"]) for work in payload["works"]] == [(HELD_ROTHKO, [kept.id])]


async def test_similar_artists_are_the_pages_section(server_url, held):
    rothko, _kept = held

    payload = await call(server_url, action="similar_artists", qid=BRUEGEL)

    assert payload == await route(server_url, f"/api/registry/artists/{BRUEGEL}/similar")
    assert [(artist["qid"], artist["artist_id"]) for artist in payload["artists"]] == [(ROTHKO, rothko.id)]


async def test_a_work_is_its_page_by_qid(server_url):
    payload = await call(server_url, action="work", qid=HUNTERS)

    assert payload == await route(server_url, f"/api/registry/works/{HUNTERS}")
    assert payload["holders"] == [{"qid": "Q95569", "name": "Kunsthistorisches Museum", "inventory": "GG_1838"}]


async def test_a_topic_is_the_pages_three_registry_sections_in_one(server_url):
    payload = await call(server_url, action="topic", qid=RENAISSANCE)

    works = payload.pop("works")
    artists = payload.pop("artists")
    assert payload == await route(server_url, f"/api/topics/{RENAISSANCE}/registry")
    assert works == await route(server_url, f"/api/topics/{RENAISSANCE}/works")
    assert artists == await route(server_url, f"/api/topics/{RENAISSANCE}/artists")
    assert [work["qid"] for work in works["works"]] == [HUNTERS]
    assert [artist["qid"] for artist in artists["artists"]] == [BRUEGEL]


@pytest.mark.parametrize("action", ["artist", "similar_artists", "work", "topic"])
async def test_a_malformed_qid_is_refused_by_name(server_url, action):
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_discovery", {"action": action, "qid": "Bruegel"})
    payload = json.loads(result.content[0].text)

    assert payload["success"] is False
    assert "not a Wikidata item id" in payload["error"]
