"""The Wikidata client against stated answers: what it sends, and what it refuses to believe.

The live suite holds the service to its recorded shapes; this holds the client to
its own promises without a network: an outage and a redirect are reported as an
outage rather than as "no match", an unknown creator is skipped rather than
misread, and a name with a quote in it cannot end the string it is placed in.
"""

import json
import re
from urllib.parse import parse_qs

import httpx
import pytest

from arrt.library.registry import RegistryUnavailable
from arrt.library.registry.identifiers import IdentifierScheme
from arrt.library.registry.wikidata import SPARQL_ENDPOINT, WikidataRegistry

UA = "arrt test (+https://example.org)"


def _registry(handler):
    return WikidataRegistry(user_agent=UA, client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


def _results(*rows):
    return httpx.Response(200, json={"results": {"bindings": list(rows)}})


def _uri(qid):
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


def _sent_query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["query"][0]


def test_it_names_itself_and_asks_the_one_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        return _results()

    _registry(handler).works_by_identifier(IdentifierScheme.ARTIC, ["1"])

    assert str(seen[0].url) == SPARQL_ENDPOINT
    assert seen[0].headers["user-agent"] == UA
    assert "wdt:P4610" in _sent_query(seen[0])


def test_identifiers_come_back_keyed_by_what_was_asked():
    def handler(request):
        return _results({"id": {"value": "1"}, "item": _uri("Q1")}, {"id": {"value": "1"}, "item": _uri("Q2")})

    assert _registry(handler).works_by_identifier(IdentifierScheme.ARTIC, ["1", "2"]) == {"1": frozenset({"Q1", "Q2"})}


def test_an_unknown_creator_is_skipped_rather_than_misread():
    """Wikidata records "somebody, unknown" as a blank node, which is not an item."""

    def handler(request):
        return _results(
            {"item": _uri("Q1"), "creator": _uri("Q7")},
            {"item": _uri("Q2"), "creator": {"type": "uri", "value": "http://www.wikidata.org/.well-known/genid/abc"}},
        )

    assert _registry(handler).creators_of(["Q1", "Q2"]) == {"Q1": frozenset({"Q7"})}


def test_a_name_with_a_quote_stays_inside_its_string():
    seen = []

    def handler(request):
        seen.append(_sent_query(request))
        return _results()

    _registry(handler).people_named("Georgia O'Keeffe\" } ; DROP")

    assert 'mwapi:search "Georgia O\'Keeffe\\" } ; DROP"' in seen[0]


def test_people_come_back_with_their_years():
    def handler(request):
        return _results(
            {
                "item": _uri("Q152384"),
                "itemLabel": {"value": "Joan Miró"},
                "bornYear": {"value": "1893"},
                "diedYear": {"value": "1983"},
            },
            {"item": _uri("Q5"), "itemLabel": {"value": "Somebody"}},
        )

    people = _registry(handler).people_named("Joan Miró")

    assert [(p.qid, p.born, p.died) for p in people] == [("Q152384", 1893, 1983), ("Q5", None, None)]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        # A body that would parse, so only the refusal to follow can stop it.
        httpx.Response(302, headers={"location": "http://127.0.0.1/sparql"}, json={"results": {"bindings": []}}),
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json={"head": {}}),
    ],
    ids=["unavailable", "a redirect", "not json", "no results"],
)
def test_anything_but_an_answer_is_an_outage_not_an_empty_result(response):
    with pytest.raises(RegistryUnavailable):
        _registry(lambda request: response).works_by_identifier(IdentifierScheme.ARTIC, ["1"])


def test_a_transport_failure_is_an_outage():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(RegistryUnavailable, match="could not be reached"):
        _registry(handler).creators_of(["Q1"])


def test_a_creator_query_refuses_anything_that_is_not_an_item_id():
    with pytest.raises(ValueError, match="not a Wikidata item id"):
        _registry(lambda request: _results()).creators_of(["Q1 } UNION { ?x ?y ?z"])


def test_large_lists_are_asked_in_batches():
    asked = []

    def handler(request):
        asked.append(_sent_query(request).count('"'))
        return httpx.Response(200, content=json.dumps({"results": {"bindings": []}}).encode())

    _registry(handler).works_by_identifier(IdentifierScheme.ARTIC, [str(n) for n in range(450)])

    assert len(asked) == 3


def test_only_a_commons_file_survives_as_an_image():
    """An image URL becomes an `img` source in the curator's browser, so nothing else gets through."""

    def handler(request):
        query = _sent_query(request)
        if "wikibase:sitelinks" in query:
            return _results(
                {
                    "work": _uri("Q1"),
                    "workLabel": {"value": "Kept"},
                    "links": {"value": "9"},
                    "img": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/A%20b.jpg"},
                },
                {
                    "work": _uri("Q2"),
                    "workLabel": {"value": "Dropped"},
                    "links": {"value": "3"},
                    "img": {"value": "javascript:alert(1)"},
                },
                {
                    "work": _uri("Q3"),
                    "workLabel": {"value": "Elsewhere"},
                    "links": {"value": "1"},
                    "img": {"value": "https://evil.example/wiki/Special:FilePath/x.jpg"},
                },
            )
        return _results()

    known = _registry(handler).artist("Q160149", works=3, holdings=1)

    assert [(work.title, work.image) for work in known.works] == [
        ("Kept", "https://commons.wikimedia.org/wiki/Special:FilePath/A%20b.jpg"),
        ("Dropped", None),
        ("Elsewhere", None),
    ]


def test_an_artist_qid_is_checked_before_it_reaches_a_query():
    with pytest.raises(ValueError, match="not a Wikidata item id"):
        _registry(lambda request: _results()).artist("Q1 } UNION {", works=1, holdings=1)


def test_held_works_beyond_the_most_renowned_are_asked_for_by_id():
    """Only the ones the first list missed: a held work already among the most renowned is not fetched twice."""
    asked = []

    def handler(request):
        query = _sent_query(request)
        asked.append(query)
        if "VALUES ?work" in query:
            return _results({"work": _uri("Q2"), "workLabel": {"value": "Held, obscure"}, "links": {"value": "1"}})
        if "wikibase:sitelinks" in query:
            return _results({"work": _uri("Q1"), "workLabel": {"value": "Famous"}, "links": {"value": "40"}})
        return _results()

    known = _registry(handler).artist("Q160149", works=1, holdings=1, include=["Q1", "Q2"])

    assert [work.title for work in known.works] == ["Famous", "Held, obscure"]
    by_id = next(query for query in asked if "VALUES ?work" in query)
    assert "wd:Q2" in by_id and "wd:Q1 " not in by_id


def test_no_held_works_means_no_extra_question():
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    _registry(handler).artist("Q160149", works=1, holdings=1)

    assert not any("VALUES ?work" in query for query in asked)


def test_names_are_asked_for_in_the_language_neutral_label_too():
    """Mark Rothko has a `mul` label and no `en` one: asked for English alone, the registry named him Q160149."""
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    registry = _registry(handler)
    registry.people_named("Mark Rothko")
    registry.artist("Q160149", works=1, holdings=1)
    registry.work("Q20270685")
    registry.works_matching(["hunters"], prefix=False, limit=5)

    # Every query that reads a name, which is every one but the artist's count.
    named = [query for query in asked if "Label" in query]
    assert len(named) == len(asked) - 1
    assert all('wikibase:language "en,mul"' in query for query in named)
    # No name is taken from a label filtered by language: that is what kept
    # `mul` names out (a description has no `mul` form, so its filter stays).
    assert not [query for query in named if re.search(r"LANG\(\?\w*Label\)", query)]
    # A maker's name from the label service, not from a filter accepting `en` or
    # `mul`, which let SAMPLE pick either: "Pieter Bruegel" one run, "Pieter
    # Brueghel the Elder" the next (measured live, 2026-10-01).
    assert "?maker rdfs:label ?makerLabel" in asked[-1] and "LANG(?makerLabel)" not in asked[-1]


def test_an_artist_comes_back_named_and_dated():
    def handler(request):
        if "?itemLabel" in _sent_query(request):
            return _results({"itemLabel": {"value": "Mark Rothko"}, "bornYear": {"value": "1903"}, "diedYear": {"value": "1970"}})
        return _results()

    known = _registry(handler).artist("Q160149", works=1, holdings=1)

    assert (known.name, known.born, known.died) == ("Mark Rothko", 1903, 1970)


def _row(**values):
    return {
        name: (_uri(value) if name in {"creator", "collection", "inventoryAt"} else {"value": value})
        for name, value in values.items()
    }


def test_one_work_is_read_back_from_its_combinations():
    """Two collections each with its own number, two media and one creator arrive as eight rows; they are one work."""
    rows = [
        _row(
            workLabel="Held twice",
            links="12",
            year="1890",
            creator="Q7",
            creatorLabel="A Painter",
            mediumLabel=medium,
            collection=collection,
            collectionLabel=name,
            inventory=number,
            inventoryAt=at,
        )
        for medium in ("oil paint", "canvas")
        for collection, name in (("Q100", "Zeta Museum"), ("Q200", "Alpha Gallery"))
        for number, at in (("Z-1", "Q100"), ("A-9", "Q200"))
    ]

    work = _registry(lambda request: _results(*rows)).work("Q42")

    assert (work.qid, work.title, work.sitelinks, work.year) == ("Q42", "Held twice", 12, 1890)
    assert [(c.qid, c.name) for c in work.creators] == [("Q7", "A Painter")]
    assert work.media == ("canvas", "oil paint")
    assert [(h.name, h.inventory) for h in work.holders] == [("Alpha Gallery", "A-9"), ("Zeta Museum", "Z-1")]


def test_an_unqualified_number_belongs_only_to_a_sole_collection():
    """Which of two collections an unqualified number belongs to is unknowable, so neither gets it."""
    sole = _registry(
        lambda r: _results(_row(workLabel="W", links="0", collection="Q100", collectionLabel="Only", inventory="N-1"))
    ).work("Q1")
    shared = _registry(
        lambda r: _results(
            _row(workLabel="W", links="0", collection="Q100", collectionLabel="One", inventory="N-1"),
            _row(workLabel="W", links="0", collection="Q200", collectionLabel="Two", inventory="N-1"),
        )
    ).work("Q1")

    assert [h.inventory for h in sole.holders] == ["N-1"]
    assert [h.inventory for h in shared.holders] == [None, None]


def test_an_item_the_registry_does_not_have_is_none():
    assert _registry(lambda request: _results()).work("Q999999999999") is None


def test_a_work_qid_is_checked_before_it_reaches_a_query():
    with pytest.raises(ValueError):
        _registry(lambda request: _results()).work("Q1 } UNION {")


def test_a_work_search_asks_the_index_for_artworks_and_caps_its_paging():
    """Without the cap the query service read every page of hits: 44 s for `david` (`wikidata-findings.md`)."""
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    _registry(handler).works_matching(["hunters", "snow"], prefix=False, limit=5)

    assert 'mwapi:srsearch "hunters snow haswbstatement:P31=Q3305213|' in asked[0]
    assert "wikibase:limit 50" in asked[0] and "LIMIT 5" in asked[0]


def test_only_the_last_word_is_a_prefix_and_only_when_asked():
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    registry = _registry(handler)
    registry.works_matching(["the", "persist"], prefix=True, limit=5)
    registry.works_matching(["the", "persist"], prefix=False, limit=5)

    assert '"the persist* haswbstatement:' in asked[0]
    assert '"the persist haswbstatement:' in asked[1]


@pytest.mark.parametrize("word", ["haswbstatement:P31=Q5", 'a"b', "x*", "(y)", "intitle:z", ""])
def test_search_syntax_typed_by_a_curator_never_reaches_the_index(word):
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    found = _registry(handler).works_matching([word], prefix=False, limit=5)

    assert (found, asked) == ([], [])


def test_a_work_match_comes_back_with_its_creator_and_only_a_commons_image():
    def handler(request):
        return _results(
            {
                "item": _uri("Q500985"),
                "itemLabel": {"value": "The Hunters in the Snow"},
                "links": {"value": "39"},
                "img": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/H.jpg"},
                "creator": _uri("Q43270"),
                "creatorLabel": {"value": "Pieter Brueghel the Elder"},
            },
            {
                "item": _uri("Q2"),
                "itemLabel": {"value": "Unattributed"},
                "links": {"value": "1"},
                "img": {"value": "https://evil.example/x.jpg"},
            },
        )

    found = _registry(handler).works_matching(["hunters"], prefix=False, limit=5)

    assert [(m.qid, m.sitelinks, m.creator and m.creator.name, m.image) for m in found] == [
        ("Q500985", 39, "Pieter Brueghel the Elder", "https://commons.wikimedia.org/wiki/Special:FilePath/H.jpg"),
        ("Q2", 1, None, None),
    ]


@pytest.mark.parametrize(
    ("typed", "sent"),
    [(["-snow"], None), (["NOT", "snow"], '"not snow haswbstatement:'), (["Hunters"], '"hunters haswbstatement:')],
)
def test_words_the_index_would_read_as_operators_are_not_sent_as_them(typed, sent):
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    _registry(handler).works_matching(typed, prefix=False, limit=5)

    assert (asked == []) if sent is None else (sent in asked[0])


def test_a_movement_with_no_readable_name_is_left_out():
    """The label service names it by its QID, which would read as a movement called `Q123`."""

    def handler(request):
        if "?movementLabel" in _sent_query(request):
            return _results({"movements": {"value": "surrealism␞Q123"}})
        return _results()

    assert _registry(handler).artist("Q5577", works=1, holdings=1).movements == ("surrealism",)
