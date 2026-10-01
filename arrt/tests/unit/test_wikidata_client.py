"""The Wikidata client against stated answers: what it sends, and what it refuses to believe.

The live suite holds the service to its recorded shapes; this holds the client to
its own promises without a network: an outage and a redirect are reported as an
outage rather than as "no match", an unknown creator is skipped rather than
misread, and a name with a quote in it cannot end the string it is placed in.
"""

import json
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
