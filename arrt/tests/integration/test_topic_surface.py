"""Library › Topics and the Topic page, over the real HTTP surface and the real MCP surface.

The library's half (`GET /api/topics`, `GET /api/topics/{qid}`, and their twins
`art_catalogue(action='topics'|'topic')`) reads the facet rows the topic sweep
writes and never waits on Wikidata; the registry's half (`/registry`, `/works`,
`/artists`) is asked for separately, as the Artist page's is. The sweep runs
here by hand, over a fake registry installed where the entry point builds
Wikidata's.
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
    RegistryCreator,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    TopicKind,
)

IMPRESSIONISM = "Q40415"
MONET = "Q296"
SUNRISE = "Q1187013"
LUNCHEON = "Q1050155"


def ref(qid: str, label: str, kind: TopicKind) -> RegistryTopicRef:
    return RegistryTopicRef(qid=ItemId(qid), label=RegistryText(label), kind=kind)


@pytest.fixture
def registry():
    return FakeRegistry(
        work_topics={SUNRISE: [ref("Q6955", "19th century", TopicKind.PERIOD), ref("Q3305213", "painting", TopicKind.MEDIUM)]},
        artist_topics={MONET: [ref(IMPRESSIONISM, "Impressionism", TopicKind.MOVEMENT)]},
        topics={
            IMPRESSIONISM: RegistryTopic(
                qid=ItemId(IMPRESSIONISM),
                label=RegistryText("Impressionism"),
                kinds=(TopicKind.MOVEMENT,),
                description=RegistryText("art movement"),
            )
        },
        topic_works={
            IMPRESSIONISM: [
                RegistryTopicWork(
                    qid=ItemId(SUNRISE),
                    title=RegistryText("Impression, Sunrise"),
                    sitelinks=60,
                    year=1872,
                    image=CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/Sunrise.jpg"),
                    creators=(RegistryCreator(qid=ItemId(MONET), name=RegistryText("Claude Monet")),),
                ),
                RegistryTopicWork(
                    qid=ItemId(LUNCHEON),
                    title=RegistryText("Luncheon on the Grass"),
                    sitelinks=50,
                    creator_unknown=True,
                ),
            ]
        },
        topic_artists={
            IMPRESSIONISM: [RegistrySimilar(qid=ItemId(MONET), name=RegistryText("Claude Monet"), sitelinks=155, images=1286)]
        },
        topics_found={
            "impression": [
                RegistryTopic(qid=ItemId(IMPRESSIONISM), label=RegistryText("Impressionism"), kinds=(TopicKind.MOVEMENT,))
            ]
        },
    )


@pytest.fixture
def held(services, service):
    """Monet and *Impression, Sunrise* in the library, identified, with their topics swept."""
    monet = service.add_artist(name="Claude Monet")
    services.identity.set_artist_identity(monet.id, MONET)
    sunrise = service.add_artwork(title="Impression, Sunrise", artist_id=monet.id, wikidata_qid=SUNRISE)
    services.topic_sweep.run()
    return monet, sunrise


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


class TestTheLibrarysHalf:
    def test_the_index_lists_each_kind_with_its_topics_and_counts(self, http, held):
        index = http.get("/api/topics").raise_for_status().json()

        assert (index["state"], index["note"]) == ("known", None)
        # What each kind also offers from the fixed list is `test_topics_offered_surface.py`'s.
        assert [{"kind": group["kind"], "topics": group["topics"]} for group in index["kinds"]] == [
            {"kind": "period", "topics": [{"qid": "Q6955", "label": "19th century", "works": 1}]},
            {"kind": "movement", "topics": [{"qid": IMPRESSIONISM, "label": "Impressionism", "works": 1}]},
            {"kind": "subject", "topics": []},
            {"kind": "medium", "topics": [{"qid": "Q3305213", "label": "painting", "works": 1}]},
        ]

    def test_a_topic_page_lists_your_works_in_it_as_grid_cards(self, http, held):
        _monet, sunrise = held

        page = http.get(f"/api/topics/{IMPRESSIONISM}").raise_for_status().json()

        assert (page["qid"], page["label"], page["kinds"]) == (IMPRESSIONISM, "Impressionism", ["movement"])
        assert [work["artwork_id"] for work in page["works"]] == [sunrise.id]
        assert page["works"][0]["image"]["available"] is False

    def test_neither_waits_on_wikidata(self, http, held, registry):
        registry.failing = True

        assert http.get("/api/topics").raise_for_status().json()["state"] == "known"
        assert len(http.get(f"/api/topics/{IMPRESSIONISM}").raise_for_status().json()["works"]) == 1

    def test_a_malformed_qid_is_a_400(self, http):
        assert http.get("/api/topics/Impressionism").status_code == 400

    def test_a_works_facets_carry_the_topic_they_open(self, http, held):
        _monet, sunrise = held

        facets = http.get(f"/api/works/{sunrise.id}").raise_for_status().json()["facets"]

        assert {(f["kind"], f["value"], f["value_qid"], f["derivation"], f["source_note"]) for f in facets} == {
            ("era", "19th century", "Q6955", "sourced", "Wikidata"),
            ("medium", "painting", "Q3305213", "sourced", "Wikidata"),
            ("movement", "Impressionism", IMPRESSIONISM, "sourced", "Wikidata"),
        }

    def test_the_artworks_rail_offers_the_swept_values_with_counts(self, http, held):
        listing = http.get("/api/works", params={"movement": "Impressionism"}).raise_for_status().json()

        rail = {group["kind"]: {o["value"]: o["count"] for o in group["options"]} for group in listing["facets"]}
        assert (rail["movement"], rail["era"], rail["medium"]) == (
            {"Impressionism": 1},
            {"19th century": 1},
            {"painting": 1},
        )
        assert listing["total"] == 1


class TestTheRegistrysHalf:
    def test_the_head_is_what_wikidata_says_the_topic_is(self, http, held):
        head = http.get(f"/api/topics/{IMPRESSIONISM}/registry").raise_for_status().json()

        assert head == {
            "state": "known",
            "note": None,
            "qid": IMPRESSIONISM,
            "label": "Impressionism",
            "kinds": ["movement"],
            "description": "art movement",
            "start": None,
            "end": None,
        }

    def test_representative_works_mark_a_held_work_by_its_qid(self, http, held):
        monet, sunrise = held

        works = http.get(f"/api/topics/{IMPRESSIONISM}/works").raise_for_status().json()["works"]

        assert [(w["qid"], w["state"], w["held_artwork_ids"]) for w in works] == [
            (SUNRISE, "held", [sunrise.id]),
            (LUNCHEON, "no_image", []),
        ]
        assert works[0]["creators"] == [{"qid": MONET, "name": "Claude Monet", "artist_id": monet.id}]
        assert (works[1]["creators"], works[1]["creator_unknown"]) == ([], True)

    def test_a_held_work_whose_qid_differs_is_not_marked(self, http, held, services):
        _monet, sunrise = held
        services.identity.set_work_identity(sunrise.id, LUNCHEON)

        works = http.get(f"/api/topics/{IMPRESSIONISM}/works").raise_for_status().json()["works"]

        assert [(w["qid"], w["state"], w["held_artwork_ids"]) for w in works] == [
            (SUNRISE, "image_found", []),
            (LUNCHEON, "held", [sunrise.id]),
        ]

    def test_representative_works_mark_a_wanted_work_beside_its_state(self, http, held, discovery, propose):
        """Wanted travels beside `state`, so held, image found and no image keep their meaning."""
        luncheon = propose("Luncheon of the Boating Party")
        discovery.want(luncheon.id)
        discovery.set_wikidata_item(luncheon.id, LUNCHEON)

        works = http.get(f"/api/topics/{IMPRESSIONISM}/works").raise_for_status().json()["works"]

        assert [(w["qid"], w["state"], w["wanted"]) for w in works] == [
            (SUNRISE, "held", False),
            (LUNCHEON, "no_image", True),
        ]

    def test_artists_carry_the_librarys_artist_where_held(self, http, held):
        monet, _sunrise = held

        artists = http.get(f"/api/topics/{IMPRESSIONISM}/artists").raise_for_status().json()

        assert artists["state"] == "known"
        assert [(a["qid"], a["artist_id"], a["images"]) for a in artists["artists"]] == [(MONET, monet.id, 1286)]

    def test_an_outage_says_so_in_each_section(self, http, registry):
        registry.failing = True
        for section in ("registry", "works", "artists"):
            answer = http.get(f"/api/topics/{IMPRESSIONISM}/{section}").raise_for_status().json()
            assert answer["state"] == "unavailable", section
            assert "could not be asked" in answer["note"]

    def test_a_search_finds_topics_by_name(self, http):
        found = http.get("/api/registry/topics", params={"q": "impression"}).raise_for_status().json()

        assert found["state"] == "known"
        assert [(t["qid"], t["label"], t["kinds"]) for t in found["topics"]] == [(IMPRESSIONISM, "Impressionism", ["movement"])]


class TestWithNoUserAgent:
    @pytest.fixture
    def registry(self):
        return None

    def test_every_topic_route_says_topics_need_one(self, http):
        for path in (
            "/api/topics",
            f"/api/topics/{IMPRESSIONISM}",
            f"/api/topics/{IMPRESSIONISM}/registry",
            f"/api/topics/{IMPRESSIONISM}/works",
            f"/api/topics/{IMPRESSIONISM}/artists",
            "/api/registry/topics?q=x",
        ):
            answer = http.get(path).raise_for_status().json()
            assert answer["state"] == "not_configured", path
            assert "WIKIDATA_USER_AGENT" in answer["note"], path


class TestTheToolSurface:
    async def test_topics_returns_what_the_http_index_returns(self, server_url, held):
        payload, errored = await call(server_url, "art_catalogue", action="topics")
        async with httpx.AsyncClient(base_url=server_url) as client:
            index = (await client.get("/api/topics")).raise_for_status().json()

        assert errored is False
        assert {key: value for key, value in payload.items() if key != "success"} == index

    async def test_topic_returns_the_http_pages_fields_and_the_same_works(self, server_url, held):
        _monet, sunrise = held

        payload, errored = await call(server_url, "art_catalogue", action="topic", qid=IMPRESSIONISM)
        async with httpx.AsyncClient(base_url=server_url) as client:
            page = (await client.get(f"/api/topics/{IMPRESSIONISM}")).raise_for_status().json()

        assert errored is False
        assert set(payload) - {"success"} == set(page)
        assert {key: payload[key] for key in page if key != "works"} == {key: page[key] for key in page if key != "works"}
        # The works are each surface's own projection of a work, as everywhere
        # (`test_surface_parity.py`): a card for the browser, a summary for a model.
        assert [w["artwork_id"] for w in payload["works"]] == [w["artwork_id"] for w in page["works"]] == [sunrise.id]

    async def test_a_malformed_qid_is_refused_by_name(self, server_url):
        payload, _ = await call(server_url, "art_catalogue", action="topic", qid="Impressionism")

        assert payload["success"] is False
        assert "not a Wikidata item id" in payload["error"]
