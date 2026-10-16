"""The fixed list Library › Topics offers, and a topic's works streamed as they arrive, over the real HTTP surface.

`GET /api/topics` carries each kind's `offered` beside its held `topics`, a
held one never in both. `GET /api/topics/{qid}/works` asked for as NDJSON
answers one line per stage of Wikidata's answer; asked for any other way it
answers the last line alone, as it always has.
"""

import json
import threading

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.registry import (
    ItemId,
    RegistryCreator,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    TopicKind,
)
from arrt.library.services.topics import OFFERED_TOPICS

SIXTEENTH = "Q7017"
NINETEENTH = "Q6955"
HUNTERS = "Q500985"
BRUEGEL = RegistryCreator(qid=ItemId("Q43270"), name=RegistryText("Pieter Bruegel the Elder"))
NDJSON = {"accept": "application/x-ndjson"}


@pytest.fixture
def registry():
    return FakeRegistry(
        topics={
            SIXTEENTH: RegistryTopic(
                qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kinds=(TopicKind.PERIOD,), start=1501, end=1600
            )
        },
        topic_works={
            SIXTEENTH: [
                RegistryTopicWork(
                    qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39, creators=(BRUEGEL,)
                )
            ]
        },
    )


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def test_an_empty_library_is_offered_the_fixed_list_by_kind(http):
    kinds = {group["kind"]: group for group in http.get("/api/topics").raise_for_status().json()["kinds"]}

    assert [offer["qid"] for offer in kinds["period"]["offered"]] == [o.qid for o in OFFERED_TOPICS if o.kind is TopicKind.PERIOD]
    assert {"qid": SIXTEENTH, "label": "16th century"} in kinds["period"]["offered"]
    assert [offer["qid"] for offer in kinds["movement"]["offered"]] == [
        o.qid for o in OFFERED_TOPICS if o.kind is TopicKind.MOVEMENT
    ]
    assert kinds["subject"]["offered"] == kinds["medium"]["offered"] == []


def test_a_held_century_is_listed_under_topics_and_not_offered(http, services, service, registry):
    registry.work_topics = {
        "Q1": [RegistryTopicRef(qid=ItemId(NINETEENTH), label=RegistryText("19th century"), kind=TopicKind.PERIOD)]
    }
    service.add_artwork(title="Impression, Sunrise", wikidata_qid="Q1")
    services.topic_sweep.run()

    period = http.get("/api/topics").raise_for_status().json()["kinds"][0]

    assert [topic["qid"] for topic in period["topics"]] == [NINETEENTH]
    assert NINETEENTH not in [offer["qid"] for offer in period["offered"]]


def test_the_works_stream_a_line_per_stage_and_the_first_comes_before_the_makers(http, server_url, registry):
    registry.makers_gate = threading.Event()
    lines: list[dict] = []
    with (
        httpx.Client(base_url=server_url, timeout=30.0) as client,
        client.stream("GET", f"/api/topics/{SIXTEENTH}/works", headers=NDJSON) as response,
    ):
        assert response.headers["content-type"].startswith("application/x-ndjson")
        stream = response.iter_lines()
        first = json.loads(next(line for line in stream if line))
        # Read before the makers are allowed to answer: the stream is not buffered to its end.
        assert (first["state"], first["complete"]) == ("known", False)
        assert [(w["qid"], w["creators"], w["creator_unknown"]) for w in first["works"]] == [(HUNTERS, [], False)]
        registry.makers_gate.set()
        lines.extend(json.loads(line) for line in stream if line)

    assert [line["complete"] for line in lines] == [True]
    assert [creator["name"] for creator in lines[0]["works"][0]["creators"]] == ["Pieter Bruegel the Elder"]


def test_a_kept_answer_is_one_complete_line(http, registry):
    http.get(f"/api/topics/{SIXTEENTH}/works").raise_for_status()
    registry.topic_sections_asked.clear()
    # Never set: answered in stages, the line would be incomplete until the fake gave up waiting.
    registry.makers_gate = threading.Event()

    body = http.get(f"/api/topics/{SIXTEENTH}/works", headers=NDJSON).raise_for_status().text

    assert [json.loads(line)["complete"] for line in body.splitlines() if line] == [True]
    assert registry.topic_sections_asked == []


def test_without_ndjson_the_answer_is_the_last_line_alone_as_json(http):
    answer = http.get(f"/api/topics/{SIXTEENTH}/works").raise_for_status()

    assert answer.headers["content-type"] == "application/json"
    assert answer.json()["complete"] is True
    assert [creator["name"] for creator in answer.json()["works"][0]["creators"]] == ["Pieter Bruegel the Elder"]


def test_an_outage_streams_one_unavailable_line(http, registry):
    registry.failing = True

    body = http.get(f"/api/topics/{SIXTEENTH}/works", headers=NDJSON).raise_for_status().text

    lines = [json.loads(line) for line in body.splitlines() if line]
    assert [(line["state"], line["complete"]) for line in lines] == [("unavailable", True)]


def test_a_malformed_qid_is_a_400_either_way(http):
    assert http.get("/api/topics/Impressionism/works", headers=NDJSON).status_code == 400
    assert http.get("/api/topics/Impressionism/works").status_code == 400
