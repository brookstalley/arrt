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
from arrt.library.registry.wikidata import COMMONS_API, COMMONS_TIMEOUT_SECONDS, SPARQL_ENDPOINT, WikidataRegistry

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


def test_a_works_creators_names_come_back_by_creator_labels_and_aliases_alike():
    """Lowry's item labels him "L. S. Lowry"; Art UK writes his alias "Laurence Stephen Lowry"."""
    seen = []

    def handler(request):
        seen.append(_sent_query(request))
        return _results(
            {"creator": _uri("Q1354277"), "name": {"value": "L. S. Lowry", "xml:lang": "en"}},
            {"creator": _uri("Q1354277"), "name": {"value": "Laurence Stephen Lowry", "xml:lang": "en"}},
            {"creator": _uri("Q1354277"), "name": {"value": "L. S. Lowry", "xml:lang": "fr"}},
            {"creator": _uri("Q9"), "name": {"value": "Somebody Else"}},
        )

    names = _registry(handler).creator_names("Q119294634")

    assert names == {
        "Q1354277": frozenset({"L. S. Lowry", "Laurence Stephen Lowry"}),
        "Q9": frozenset({"Somebody Else"}),
    }
    assert "wd:Q119294634 wdt:P170 ?creator" in seen[0]
    assert "rdfs:label" in seen[0]
    assert "skos:altLabel" in seen[0]
    # Every language: the Pompidou writes "Vassily Kandinsky", a French form.
    assert "LANG(" not in seen[0]


def test_an_unknown_creator_and_an_empty_name_carry_no_names():
    """An unknown creator is a blank node with no name to compare; a blank name compares with nothing."""

    def handler(request):
        return _results(
            {
                "creator": {"type": "uri", "value": "http://www.wikidata.org/.well-known/genid/abc"},
                "name": {"value": "Anonymous"},
            },
            {"creator": _uri("Q7"), "name": {"value": "  "}},
            {"creator": _uri("Q7")},
        )

    assert _registry(handler).creator_names("Q1") == {}


def test_a_creator_names_query_refuses_anything_that_is_not_an_item_id():
    with pytest.raises(ValueError, match="not a Wikidata item id"):
        _registry(lambda request: _results()).creator_names("Q1 } UNION { ?x ?y ?z")


def test_a_creator_names_outage_is_an_outage():
    with pytest.raises(RegistryUnavailable):
        _registry(lambda request: httpx.Response(503)).creator_names("Q1")


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
    assert "wd:Q2" in by_id
    assert "wd:Q1 " not in by_id


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
    assert "?maker rdfs:label ?makerLabel" in asked[-1]
    assert "LANG(?makerLabel)" not in asked[-1]


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


def test_a_works_size_comes_back_in_centimetres():
    """Wikidata normalises each measurement to metres, whatever unit it was entered in."""
    work = _registry(lambda request: _results(_row(workLabel="W", links="0", height="0.794", width="0.54"))).work("Q1")

    assert (work.height_cm, work.width_cm) == (79.4, 54.0)


def test_two_heights_that_disagree_give_no_height_and_leave_the_width():
    """Two sources measuring 80 and 81.5 cm have no answer to pick; the agreed width still stands."""
    rows = [_row(workLabel="W", links="0", height=height, width="0.6") for height in ("0.8", "0.815")]

    work = _registry(lambda request: _results(*rows)).work("Q1")

    assert (work.height_cm, work.width_cm) == (None, 60.0)


def test_one_height_repeated_across_rows_is_still_one_height():
    """Two media make two rows carrying the same height: that is one measurement, not a disagreement."""
    rows = [_row(workLabel="W", links="0", mediumLabel=medium, height="1.45", width="1.13") for medium in ("oil", "canvas")]

    work = _registry(lambda request: _results(*rows)).work("Q1")

    assert (work.height_cm, work.width_cm) == (145.0, 113.0)


def test_a_work_with_no_size_has_none():
    work = _registry(lambda request: _results(_row(workLabel="W", links="0"))).work("Q1")

    assert (work.height_cm, work.width_cm) == (None, None)


def test_the_size_asked_for_is_the_works_own_best_measurement_and_not_a_parts():
    """A frame's height is recorded with *applies to part* = frame, and a deprecated one is not the best rank.

    The canvas is a part too, and the commonest one a painting's own height is
    recorded with, so only what surrounds the work is left out."""
    seen = []

    def handler(request):
        seen.append(_sent_query(request))
        return _results()

    _registry(handler).work("Q1")

    for prop in ("P2048", "P2049"):
        clause = re.search(rf"OPTIONAL \{{[^{{}}]*p:{prop}[^{{}}]*\{{[^{{}}]*\}}[^{{}}]*\}}", seen[0])
        assert clause is not None, f"no measurement clause for {prop}"
        assert f"psn:{prop}" in clause.group(0)
        assert "wikibase:BestRank" in clause.group(0)
        assert "pq:P518" in clause.group(0)
        for around in ("wd:Q860792", "wd:Q101698846", "wd:Q107105674"):
            assert around in clause.group(0)
        assert "wd:Q4259259" not in clause.group(0), "the canvas is the work's own size"


def test_an_item_the_registry_does_not_have_is_none():
    assert _registry(lambda request: _results()).work("Q999999999999") is None


def test_a_work_qid_is_checked_before_it_reaches_a_query():
    with pytest.raises(ValueError, match="is not a Wikidata item id"):
        _registry(lambda request: _results()).work("Q1 } UNION {")


def test_a_work_search_asks_the_index_for_artworks_and_caps_its_paging():
    """Without the cap the query service read every page of hits: 44 s for `david` (`wikidata-findings.md`)."""
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    _registry(handler).works_matching(["hunters", "snow"], prefix=False, limit=5)

    assert 'mwapi:srsearch "hunters snow haswbstatement:P31=Q3305213|' in asked[0]
    assert "wikibase:limit 50" in asked[0]
    assert "LIMIT 5" in asked[0]


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


def test_similar_artists_come_back_ranked_with_their_image_counts():
    asked = []

    def handler(request):
        query = _sent_query(request)
        asked.append(query)
        if "VALUES ?person" in query:
            return _results({"person": _uri("Q37571"), "n": {"value": "0"}}, {"person": _uri("Q153739"), "n": {"value": "35"}})
        return _results(
            {
                "other": _uri("Q37571"),
                "otherLabel": {"value": "Jackson Pollock"},
                "links": {"value": "118"},
                "born": {"value": "1912"},
            },
            {"other": _uri("Q153739"), "otherLabel": {"value": "Arshile Gorky"}, "links": {"value": "44"}},
        )

    found = _registry(handler).similar_to("Q160149", limit=12)

    assert [(p.name, p.born, p.images) for p in found] == [("Jackson Pollock", 1912, 0), ("Arshile Gorky", None, 35)]
    assert "ORDER BY DESC(?links)" in asked[0]
    assert "SELECT ?other ?otherLabel ?links " in asked[0]
    assert "wdt:P106/wdt:P279* wd:Q3391743" in asked[0]
    assert "LIMIT 12" in asked[0]
    assert "wd:Q37571 wd:Q153739" in asked[1]


def test_no_similar_artists_asks_no_second_question():
    asked = []

    def handler(request):
        asked.append(request)
        return _results()

    assert _registry(handler).similar_to("Q160149", limit=12) == []
    assert len(asked) == 1


def test_a_similar_artists_qid_is_checked_before_it_reaches_a_query():
    with pytest.raises(ValueError, match="is not a Wikidata item id"):
        _registry(lambda request: _results()).similar_to("Q1 } UNION {", limit=1)


def test_people_are_asked_for_most_renowned_first():
    """The typeahead keeps the first three, so an unranked list could keep namesakes and drop the painter."""
    asked = []

    def handler(request):
        asked.append(_sent_query(request))
        return _results()

    _registry(handler).people_named("dali")

    assert "ORDER BY DESC(?links)" in asked[0]
    # Selected, not only grouped by, or the service ignores the order.
    assert "SELECT ?item ?itemLabel ?links " in asked[0]


def test_the_servers_registry_gives_up_sooner_than_the_matchers():
    """A curator waits on the pages; the hand-run matcher has nobody waiting."""
    from types import SimpleNamespace

    from arrt.__main__ import _registry
    from arrt.library.registry.wikidata import INTERACTIVE_TIMEOUT_SECONDS, TIMEOUT_SECONDS

    # `_registry` reads one setting; the rest of `Settings` is the server's.
    server = _registry(SimpleNamespace(wikidata_user_agent=UA))
    matcher = WikidataRegistry(user_agent=UA)

    assert server._http.timeout.read == INTERACTIVE_TIMEOUT_SECONDS < TIMEOUT_SECONDS == matcher._http.timeout.read


COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/Robert%20Delaunay%2C%20Rythmes%2C%201934.jpg"


def _commons(info=None, *, missing=False):
    page = {"title": "File:X.jpg", "missing": True} if missing else {"title": "File:X.jpg", "imageinfo": [info]}
    return httpx.Response(200, json={"query": {"pages": [page]}})


def test_a_files_size_is_asked_of_commons_by_its_name():
    seen = []

    def handler(request):
        seen.append(request)
        return _commons({"width": 2081, "height": 2668, "mime": "image/jpeg"})

    size = _registry(handler).image_size(COMMONS_FILE)

    assert (size.width, size.height) == (2081, 2668)
    assert str(seen[0].url).startswith(COMMONS_API + "?")
    assert seen[0].url.params["titles"] == "File:Robert Delaunay, Rythmes, 1934.jpg"
    assert seen[0].headers["user-agent"] == UA


def test_a_file_commons_does_not_have_has_no_size():
    assert _registry(lambda request: _commons(missing=True)).image_size(COMMONS_FILE) is None


@pytest.mark.parametrize("mime", ["image/svg+xml", "application/pdf", None])
def test_a_file_that_is_not_a_raster_picture_has_no_size(mime):
    """An SVG has a nominal size that says nothing about how sharp it hangs."""
    info = {"width": 512, "height": 512, "mime": mime}

    assert _registry(lambda request: _commons(info)).image_size(COMMONS_FILE) is None


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(302, headers={"location": "https://elsewhere.example/"}),
        httpx.Response(503),
        httpx.Response(200, json={"error": "nope"}),
        httpx.Response(200, json={"query": {"pages": [{"title": "File:X.jpg", "imageinfo": [{"mime": "image/jpeg"}]}]}}),
    ],
    ids=["redirect", "outage", "unrecognised", "no-size"],
)
def test_commons_not_answering_the_size_is_an_outage_not_no_file(answer):
    with pytest.raises(RegistryUnavailable):
        _registry(lambda request: answer).image_size(COMMONS_FILE)


def test_a_file_that_is_not_a_commons_path_is_refused_before_anything_is_sent():
    seen = []

    with pytest.raises(ValueError, match="not a Commons file"):
        _registry(lambda request: seen.append(request) or _commons()).image_size("https://elsewhere.example/x.jpg")
    assert seen == []


def test_the_registry_sizes_exactly_the_files_a_get_can_take():
    """The page judges a picture only if the Commons source would fetch it; the two sets are copies."""
    from arrt.library.registry import RASTER_TYPES
    from arrt.library.sources import commons

    assert commons._RASTER == RASTER_TYPES


def test_commons_is_given_a_short_wait_because_a_page_waits_on_it():
    seen = []

    def handler(request):
        seen.append(request)
        return _commons({"width": 1, "height": 1, "mime": "image/png"})

    _registry(handler).image_size(COMMONS_FILE)

    assert seen[0].extensions["timeout"]["read"] == COMMONS_TIMEOUT_SECONDS <= 5
