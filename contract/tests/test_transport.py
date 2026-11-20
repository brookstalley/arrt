"""`transport.json` describes every route `routes.json` names, in terms a Player can act on.

The table's truth about the server is Arrt's suite's to hold
(`arrt/tests/contract/test_transport_table.py` drives a real server through every
row). What this file holds is that the table is complete and well-formed, so the
server's test and a Player's double are each iterating over something whole: a
route with no answers would be a route both sides test by reading nothing.
"""

import pytest

from arrt_contract import routes, schema, specification, transport

TABLE = transport()
ROUTES = routes()
BODIES = {"document", "error", "framework", "media", "none"}


def test_the_table_describes_exactly_the_routes_a_player_may_request():
    assert set(TABLE["routes"]) == set(ROUTES)


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_each_route_names_its_answers_once_each_with_a_known_body(name):
    answers = TABLE["routes"][name]["answers"]
    cases = [answer["case"] for answer in answers]

    assert answers, name
    assert len(cases) == len(set(cases)), f"{name} names a case twice: {cases}"
    for answer in answers:
        assert isinstance(answer["status"], int), answer
        assert 200 <= answer["status"] < 500, answer
        assert answer["body"] in BODIES, answer
        assert answer["means"].strip(), answer
        assert answer["player"].strip(), answer


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_a_route_that_serves_a_document_names_its_schema_and_its_bound(name):
    route = TABLE["routes"][name]
    serves_a_document = any(answer["body"] == "document" for answer in route["answers"])

    assert ("schema" in route) is serves_a_document, name
    assert ("max_bytes" in route) is serves_a_document, name
    if serves_a_document:
        assert schema(route["schema"])["$id"].endswith(route["schema"].removeprefix("schemas/"))
        assert isinstance(route["max_bytes"], int)
        assert route["max_bytes"] > 0


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_a_route_that_takes_a_body_names_the_schema_of_it(name):
    route = TABLE["routes"][name]

    assert ("request_schema" in route) is (ROUTES[name]["method"] == "POST"), name
    if "request_schema" in route:
        assert schema(route["request_schema"])["$id"].endswith(route["request_schema"].removeprefix("schemas/"))


def test_every_route_says_what_a_missing_or_unknown_token_is():
    """Every route takes the client's token (§ Transport), so every route has its 401."""
    for name, route in TABLE["routes"].items():
        assert 401 in {answer["status"] for answer in route["answers"]}, name


def test_the_conditional_routes_answer_200_and_304_and_are_the_ones_that_serve_documents():
    conditional = set(TABLE["conditional_get"]["routes"])

    assert conditional == {name for name, route in TABLE["routes"].items() if "schema" in route}
    for name in conditional:
        statuses = {answer["status"] for answer in TABLE["routes"][name]["answers"]}
        assert {200, 304} <= statuses, name
    for name in set(ROUTES) - conditional:
        assert 304 not in {answer["status"] for answer in TABLE["routes"][name]["answers"]}, name


def test_the_conditional_cases_cover_a_match_a_change_and_a_stranger():
    """The three ways a tag can meet a document, and the first request that sends none."""
    cases = TABLE["conditional_get"]["cases"]
    shapes = {(case["document"], case["if_none_match"], case["status"]) for case in cases}

    assert ("A", None, 200) in shapes
    assert ("A", "etag(A)", 304) in shapes
    assert ("B", "etag(A)", 200) in shapes
    assert any(case["status"] == 200 and case["if_none_match"] not in {None, "etag(A)"} for case in cases)
    for case in cases:
        assert case["etag"] == f"etag({case['document']})", case


def test_an_error_body_is_one_key():
    assert TABLE["error_body"]["required"] == ["error"]


def test_the_specification_points_at_the_table():
    """§ Transport says the table is the statement of its rules, so a reader of either finds the other."""
    assert "`contract/transport.json`" in specification().read_text(encoding="utf-8")
