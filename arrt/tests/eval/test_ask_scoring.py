"""How an Ask run is scored, on fabricated transcripts. Free: nothing here reaches a provider.

The numbers in `ask-agent-findings.md` are this scorer's, so a bug in it is a
wrong finding rather than a failing run.
"""

from ask import REQUESTS, passed, score
from driver import LOCAL, Outcome
from scenarios import Call, Transcript

SEARCH = {
    "success": True,
    # A search's people in `_registry_search`'s fields: years and `artist_id` are
    # what tell a person from a museum, which carries a name and a QID too.
    "artists": [
        {"qid": "Q485635", "name": "Keith Haring", "born": 1958, "died": 1990, "artist_id": None},
        {"qid": "Q151679", "name": "Roy Lichtenstein", "born": 1923, "died": 1997, "artist_id": None},
    ],
    "works": [
        {
            "qid": "Q4000955",
            "title": "Tuttomondo",
            "creator": {"qid": "Q485635", "name": "Keith Haring", "artist_id": None},
            "held_artwork_ids": [],
        },
        {
            "qid": "Q3567592",
            "title": "Whaam!",
            "creator": {"qid": "Q151679", "name": "Roy Lichtenstein", "artist_id": None},
            "held_artwork_ids": [],
        },
        {"qid": "Q25729", "title": "The Persistence of Memory", "creators": [], "held_artwork_ids": ["a1"]},
    ],
}

MORE = {"success": True, "works": [{"qid": "Q175036", "title": "Guernica", "creators": [], "held_artwork_ids": []}]}


def outcome(answer: str, *payloads: dict) -> Outcome:
    calls = [Call("art_discovery", "search", True, payload) for payload in payloads]
    return Outcome(transcript=Transcript(calls=calls), answer=answer, stopped_on_budget=False)


CHECK = {request.id: request.check for request in REQUESTS}


def test_an_item_no_tool_returned_is_invented_and_one_a_tool_returned_is_grounded():
    found = score(outcome("Whaam! [Q3567592] and Guernica [Q175036]", SEARCH))

    assert found.grounded == {"Q3567592"}
    assert found.invented == {"Q175036"}


def test_a_held_work_is_offered_but_not_gettable():
    found = score(outcome("[Q25729] [Q3567592]", SEARCH))

    assert found.works_offered == {"Q25729", "Q3567592"}
    assert found.gettable == {"Q3567592"}


def test_a_qid_in_a_web_result_grounds_an_item_but_makes_no_work():
    web = Call("web_search", LOCAL, True, {"success": True, "result": "wikidata.org/wiki/Q175036 Guernica"})
    found = score(Outcome(transcript=Transcript(calls=[web]), answer="Guernica [Q175036]", stopped_on_budget=False))

    assert found.grounded == {"Q175036"}
    assert found.works == {}


def test_more_like_passes_on_grounded_artists_and_fails_on_haring_or_his_work():
    artists = "[Q151679] [Q3567592] [Q25729]"

    assert CHECK["taste_exclusions"](score(outcome(artists, SEARCH))) is None
    assert "Q485635" in CHECK["taste_exclusions"](score(outcome(artists + " [Q485635]", SEARCH)))
    assert "Q4000955" in CHECK["taste_exclusions"](score(outcome(artists + " [Q4000955]", SEARCH)))
    assert "wanted 3" in CHECK["taste_exclusions"](score(outcome("[Q151679]", SEARCH)))


def test_a_run_naming_an_invented_item_has_not_passed_whatever_its_check_says():
    found = score(outcome("[Q151679] [Q3567592] [Q25729] [Q1230949]", SEARCH))

    assert CHECK["taste_exclusions"](found) is None
    assert passed(found, None) is False


def test_three_gettable_works_pass_and_held_ones_do_not_count():
    found = score(outcome("[Q3567592] [Q4000955] [Q25729]", SEARCH))

    assert "offered 2 gettable works" in CHECK["early_dali"](found)
    assert CHECK["early_dali"](score(outcome("[Q3567592] [Q4000955] [Q25729] [Q175036]", SEARCH, MORE))) is None


def test_the_held_request_passes_only_on_naming_the_held_work():
    assert CHECK["held_dali"](score(outcome("You hold The Persistence of Memory [Q25729].", SEARCH))) is None
    assert "Persistence of Memory" in CHECK["held_dali"](score(outcome("You hold nothing of his.", SEARCH)))
