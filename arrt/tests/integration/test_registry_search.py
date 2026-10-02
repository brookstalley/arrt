"""The registry's half of one-world search, over the real HTTP surface.

Ruling 2: the top-bar search covers the library and the registry together, each
match with its state. This drives `GET /api/registry/search` through every state
with a fake registry installed where the entry point would build Wikidata's.
"""

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.registry import RegistryCreator, RegistryPerson, RegistryWorkMatch

ROTHKO = "Q160149"
DALI = "Q5577"
HELD_ROTHKO = "Q20270685"


@pytest.fixture
def registry():
    return FakeRegistry(
        people={
            "rothko": [RegistryPerson(qid=ROTHKO, label="Mark Rothko", born=1903, died=1970)],
            "dali": [RegistryPerson(qid=DALI, label="Salvador Dalí", born=1904, died=1989)],
        },
        matches={
            "rothko": [
                RegistryWorkMatch(
                    qid="Q2956755", title="Rothko Chapel", sitelinks=13, creator=RegistryCreator(qid=ROTHKO, name="Mark Rothko")
                ),
                RegistryWorkMatch(qid=HELD_ROTHKO, title="Untitled (Purple, White, and Red)", sitelinks=0),
            ],
            "dali": [
                RegistryWorkMatch(
                    qid="Q25729",
                    title="The Persistence of Memory",
                    sitelinks=48,
                    image="https://commons.wikimedia.org/wiki/Special:FilePath/P.jpg",
                    creator=RegistryCreator(qid=DALI, name="Salvador Dalí"),
                )
            ],
        },
    )


@pytest.fixture
def held(services, service):
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    kept = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=rothko.id)
    services.identity.set_work_identity(kept.id, HELD_ROTHKO)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    return rothko, kept


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def _search(http, q, **params):
    return http.get("/api/registry/search", params={"q": q, **params}).raise_for_status().json()


def test_artists_and_works_come_back_marked_where_the_library_holds_them(http, held):
    rothko, kept = held

    found = _search(http, "rothko", prefix="true")

    assert found["state"] == "known"
    assert found["artists"] == [{"qid": ROTHKO, "name": "Mark Rothko", "born": 1903, "died": 1970, "artist_id": rothko.id}]
    assert [(w["title"], w["held_artwork_ids"]) for w in found["works"]] == [
        ("Rothko Chapel", []),
        ("Untitled (Purple, White, and Red)", [kept.id]),
    ]
    assert found["works"][0]["creator"] == {"qid": ROTHKO, "name": "Mark Rothko", "artist_id": rothko.id}


def test_an_unheld_match_carries_no_library_ids(http, held):
    found = _search(http, "dali")

    assert found["artists"][0]["artist_id"] is None
    assert found["works"][0]["creator"]["artist_id"] is None
    assert found["works"][0]["image"].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")


def test_the_last_word_is_a_prefix_only_when_asked(http, registry):
    _search(http, "rothko", prefix="true")
    _search(http, "dali")

    assert registry.matched == [("rothko", True), ("dali", False)]


def test_a_query_is_cut_into_words_before_it_is_asked(http, registry):
    """Search syntax is not words: `:` and `"` never reach the registry."""
    _search(http, 'haswbstatement:P31="Q5" rothko')

    assert registry.matched == [("haswbstatement P31 Q5 rothko", False)]


def test_a_leading_hyphen_is_not_kept_and_does_not_count_as_a_letter(http, registry):
    """The index reads `-snow` as "not snow"; the service cuts words from their first letter."""
    _search(http, "-snow rothko")
    found = _search(http, "-ab")

    assert registry.matched == [("snow rothko", False)]
    assert found["state"] == "too_short"


def test_the_same_query_is_asked_once(http, registry):
    _search(http, "Dali")
    _search(http, "dalí")

    assert registry.matched == [("Dali", False)]


@pytest.mark.parametrize("q", ["", "da", " d a "])
def test_fewer_than_three_letters_asks_nothing(http, registry, q):
    found = _search(http, q)

    assert (found["state"], found["artists"], found["works"]) == ("too_short", [], [])
    assert registry.matched == [] and registry.searched == []


def test_an_outage_says_so_and_is_not_remembered(http, registry):
    registry.failing = True
    found = _search(http, "dali")
    assert (found["state"], found["works"]) == ("unavailable", [])
    assert "could not be searched" in found["note"]

    registry.failing = False
    assert _search(http, "dali")["state"] == "known"


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_it_says_only_the_library_is_searched(self, http):
        found = _search(http, "dali")

        assert found["state"] == "not_configured"
        assert "only your library is searched" in found["note"]
