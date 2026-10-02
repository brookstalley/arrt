"""The Wikidata client's topic questions, against answers recorded from the live service.

`tests/fixtures/wikidata_topics/answers.json` holds the bindings the query
service returned on 2026-10-02 to the client's own queries
(`wikidata-findings.md` § Topics), cut to the rows each test needs. The live
suite holds the service to those shapes; this holds the client to what it makes
of them: the kind each topic is given, one entry per work however many made it,
a maker nobody knows read as unknown rather than as its URL, and the route that
found a held work's topic deciding its kind.
"""

import json
import pathlib
import re
from urllib.parse import parse_qs

import httpx
import pytest

from arrt.library.registry import ItemId, RegistryText, RegistryTopic, TopicKind
from arrt.library.registry.wikidata import WikidataRegistry

ANSWERS = json.loads((pathlib.Path(__file__).parents[1] / "fixtures" / "wikidata_topics" / "answers.json").read_text())

UA = "arrt test (+https://example.org)"


def _sent_query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["query"][0]


def _answering(*answers, asked=None):
    """A registry whose service gives each recorded answer in turn, and records each query."""
    queue = list(answers)

    def handler(request):
        if asked is not None:
            asked.append(_sent_query(request))
        return httpx.Response(200, json={"results": {"bindings": queue.pop(0) if queue else []}})

    return WikidataRegistry(user_agent=UA, client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


def _topic(qid, *kinds, start=None, end=None):
    return RegistryTopic(qid=ItemId(qid), label=RegistryText(qid), kinds=kinds, start=start, end=end)


@pytest.mark.parametrize(
    ("qid", "kinds"),
    [
        ("Q7017", (TopicKind.PERIOD,)),
        ("Q40415", (TopicKind.MOVEMENT,)),
        # A subclass of *art style* as well as of visual artwork: a kind of work,
        # not a movement, because a movement is an instance of a style.
        ("Q18219090", (TopicKind.MEDIUM,)),
        ("Q1311", (TopicKind.SUBJECT,)),
        # A movement and a period: its works are found as a movement's.
        ("Q37853", (TopicKind.MOVEMENT, TopicKind.PERIOD)),
        # A movement with a start and an end, and so a period too, though not an
        # instance of one: the rule's last clause, which a person would not apply.
        ("Q37068", (TopicKind.MOVEMENT, TopicKind.PERIOD)),
    ],
)
def test_a_topics_kind_is_read_from_the_classes_above_it(qid, kinds):
    topic = _answering(ANSWERS[f"topic {qid}"]).topic(qid)

    assert topic.kinds == kinds and topic.kind is kinds[0]


def test_a_historical_period_with_no_years_recorded_is_still_a_period():
    """The Dutch Golden Age's recorded answer without its years: the class alone makes it one."""
    undated = [{name: value for name, value in row.items() if name not in {"start", "end"}} for row in ANSWERS["topic Q661566"]]

    topic = _answering(undated).topic("Q661566")

    assert (topic.kinds, topic.start, topic.end) == ((TopicKind.PERIOD,), None, None)


def test_a_period_carries_its_years():
    topic = _answering(ANSWERS["topic Q7017"]).topic("Q7017")

    assert (topic.label, topic.start, topic.end) == ("16th century", 1501, 1600)


def test_an_item_the_registry_does_not_have_is_no_topic():
    assert _answering([]).topic("Q999999999999") is None


def test_the_kind_roots_are_asked_for_from_the_item_upwards():
    """Asking whether the item sits under *visual artwork* walked down from the root: 3 to 14 s (`wikidata-findings.md`)."""
    asked = []
    _answering([], asked=asked).topic("Q1311")

    assert "?item wdt:P31/wdt:P279* ?root" in asked[0] and "?item wdt:P279* ?root" in asked[0]
    assert "FILTER(?root IN (" in asked[0]
    assert not re.search(r"wdt:P279\* wd:Q", asked[0])


@pytest.mark.parametrize(
    ("topic", "pattern"),
    [
        (_topic("Q40415", TopicKind.MOVEMENT), "?maker wdt:P135 wd:Q40415 . ?work wdt:P170 ?maker ."),
        (_topic("Q1311", TopicKind.SUBJECT), "{ ?work wdt:P180 wd:Q1311 } UNION { ?work wdt:P136 wd:Q1311 }"),
        (_topic("Q18219090", TopicKind.MEDIUM), "?work wdt:P31 wd:Q18219090 ."),
        (
            _topic("Q7017", TopicKind.PERIOD, start=1501, end=1600),
            'FILTER(?made >= "1501-01-01T00:00:00Z"^^xsd:dateTime && ?made < "1601-01-01T00:00:00Z"^^xsd:dateTime)',
        ),
    ],
    ids=["movement", "subject", "medium", "period"],
)
def test_a_topics_works_are_found_by_its_kind(topic, pattern):
    asked = []
    _answering([], asked=asked).topic_works(topic, limit=50)

    assert pattern in asked[0]
    assert "ORDER BY DESC(?links)" in asked[0] and "LIMIT 50" in asked[0]


def test_a_period_is_read_as_a_range_of_the_inception_index():
    """A filter on YEAR() timed out at a minute for the 16th century, where the range took 7 to 26 s (`wikidata-findings.md`)."""
    asked = []
    _answering([], asked=asked).topic_works(_topic("Q7017", TopicKind.PERIOD, start=1501, end=1600), limit=50)

    assert "hint:Prior hint:rangeSafe true" in asked[0] and "YEAR(?made)" not in asked[0]


def test_an_item_with_two_kinds_finds_its_works_as_its_first():
    asked = []
    _answering([], asked=asked).topic_works(_topic("Q37853", TopicKind.MOVEMENT, TopicKind.PERIOD, start=1590, end=1750), limit=5)

    assert "wdt:P135 wd:Q37853" in asked[0] and "rangeSafe" not in asked[0]


def test_one_entry_per_work_however_many_made_it():
    works = _answering(ANSWERS["works two makers"], ANSWERS["makers two makers"]).topic_works(
        _topic("Q7017", TopicKind.PERIOD, start=1501, end=1600), limit=50
    )

    qids = [work.qid for work in works]
    assert len(qids) == len(set(qids)) == len(ANSWERS["works two makers"])
    shared = next(work for work in works if work.qid == ANSWERS["two makers"]["work"])
    assert sorted(creator.name for creator in shared.creators) == sorted(ANSWERS["two makers"]["makers"])


def test_a_maker_recorded_as_unknown_is_an_unknown_maker_never_its_url():
    works = _answering(ANSWERS["works unknown maker"], ANSWERS["makers unknown maker"]).topic_works(
        _topic("Q18219090", TopicKind.MEDIUM), limit=50
    )

    unknown = next(work for work in works if work.qid == ANSWERS["unknown maker"]["work"])
    assert unknown.creator_unknown is True
    assert [creator.name for creator in unknown.creators] == ANSWERS["unknown maker"]["named makers"]
    assert not any("genid" in creator.name or "genid" in creator.qid for work in works for creator in work.creators)
    assert not any(work.creator_unknown for work in works if work.qid != ANSWERS["unknown maker"]["work"])


def test_a_work_with_no_readable_title_is_titled_by_its_qid():
    """As on the Artist page, which shows it as *No English title (Q…)*."""
    works = _answering(ANSWERS["works label-less"], []).topic_works(_topic("Q4", TopicKind.SUBJECT), limit=50)

    nameless = next(work for work in works if work.qid == ANSWERS["label-less work"])
    assert nameless.title == nameless.qid


def test_a_topic_with_no_works_asks_nothing_more():
    asked = []
    found = _answering([], asked=asked).topic_works(_topic("Q1311", TopicKind.SUBJECT), limit=50)

    assert (found, len(asked)) == ([], 1)


def test_a_period_with_no_years_has_no_works_and_asks_nothing():
    asked = []

    assert _answering(asked=asked).topic_works(_topic("Q1", TopicKind.PERIOD, start=1500), limit=50) == []
    assert _answering(asked=asked).topic_artists(_topic("Q1", TopicKind.PERIOD), limit=12) == []
    assert asked == []


def test_a_movements_artists_are_its_own_and_anyone_elses_are_the_makers_of_its_works():
    asked = []
    registry = _answering(asked=asked)
    registry.topic_artists(_topic("Q40415", TopicKind.MOVEMENT), limit=12)
    registry.topic_artists(_topic("Q1311", TopicKind.SUBJECT), limit=12)

    assert "?artist wdt:P135 wd:Q40415" in asked[0] and "wdt:P106/wdt:P279* wd:Q3391743" in asked[0]
    assert "?work wdt:P180 wd:Q1311" in asked[1] and "?work wdt:P170 ?artist" in asked[1]
    assert all("ORDER BY DESC(?links)" in query and "LIMIT 12" in query for query in asked)


def test_a_topics_artists_come_back_with_their_image_counts():
    people = _answering(ANSWERS["artists"], ANSWERS["artist images"]).topic_artists(
        _topic("Q40415", TopicKind.MOVEMENT), limit=12
    )

    assert [(person.qid, person.images) for person in people] == [tuple(pair) for pair in ANSWERS["artists expected"]]


def test_a_topic_search_offers_the_movement_and_not_the_political_party():
    """`renaissance`: the search ranks a French political party first; nothing depicts it, so it is no topic."""
    asked = []
    found = _answering(ANSWERS["named renaissance"], asked=asked).topics_named("renaissance")

    by_qid = {topic.qid: topic for topic in found}
    assert ANSWERS["renaissance party"] not in by_qid
    assert by_qid["Q4692"].kinds == (TopicKind.MOVEMENT, TopicKind.PERIOD)
    assert 'mwapi:search "renaissance"' in asked[0] and "wikibase:limit 20" in asked[0]


def test_a_subject_hit_is_kept_when_something_depicts_it():
    found = _answering(ANSWERS["named still life"]).topics_named("still life")

    assert [(topic.qid, topic.kinds) for topic in found] == [("Q170571", (TopicKind.SUBJECT,))]


def test_a_topic_search_offers_no_work_of_art():
    """`woodcut`: Kunisada's print *Woodcut* is an instance of a subclass of *art style*, which made it a movement."""
    found = {topic.qid: topic for topic in _answering(ANSWERS["named woodcut"]).topics_named("woodcut")}

    assert ANSWERS["woodcut work"] not in found
    assert found["Q18219090"].kinds == (TopicKind.MEDIUM,)


def test_a_search_text_stays_inside_its_string():
    asked = []
    _answering([], asked=asked).topics_named('baroque" } ; DROP')

    assert 'mwapi:search "baroque\\" } ; DROP"' in asked[0]


def test_a_held_works_topics_are_given_the_kind_of_the_route_that_found_them():
    found = _answering(ANSWERS["of works"], ANSWERS["of artists"]).topics_of(ANSWERS["of work qids"], ANSWERS["of artist qids"])

    assert {qid: [[ref.label, ref.kind.value] for ref in refs] for qid, refs in found.works.items()} == ANSWERS[
        "of works expected"
    ]
    assert {qid: [[ref.label, ref.kind.value] for ref in refs] for qid, refs in found.artists.items()} == ANSWERS[
        "of artists expected"
    ]


def test_a_held_works_century_is_a_gregorian_one():
    """The Islamic calendar's centuries are centuries too: *14th century AH* came back for every 20th-century work."""
    asked = []
    _answering(asked=asked).topics_of(["Q1"], [])

    assert "wdt:P361/wdt:P31 wd:Q36507" in asked[0]


def test_an_unknown_subject_and_an_item_not_asked_about_are_left_out():
    def uri(qid):
        return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}

    rows = [
        {"item": uri("Q1"), "subject": {"type": "uri", "value": "http://www.wikidata.org/.well-known/genid/abc"}},
        {"item": uri("Q2"), "subject": uri("Q3"), "subjectLabel": {"value": "not asked"}},
        {"item": uri("Q1"), "subject": uri("Q4"), "subjectLabel": {"value": "kept"}},
    ]
    found = _answering(rows).topics_of(["Q1"], [])

    assert {qid: [ref.label for ref in refs] for qid, refs in found.works.items()} == {"Q1": ["kept"]}


@pytest.mark.parametrize(
    "call",
    [
        lambda registry: registry.topic("Q1 } UNION {"),
        lambda registry: registry.topic_works(_topic("Q1 } UNION {", TopicKind.MEDIUM), limit=1),
        lambda registry: registry.topic_artists(_topic("Q1 } UNION {", TopicKind.MOVEMENT), limit=1),
        lambda registry: registry.topics_of(["Q1 } UNION {"], []),
        lambda registry: registry.topics_of([], ["Q1 } UNION {"]),
    ],
)
def test_a_qid_is_checked_before_it_reaches_a_query(call):
    with pytest.raises(ValueError, match="not a Wikidata item id"):
        call(_answering())
