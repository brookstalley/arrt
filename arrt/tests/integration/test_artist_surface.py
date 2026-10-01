"""Library › Artists and the Artist page's two halves, over the real HTTP surface.

The page asks the library and the registry separately, so a registry that is
slow, absent, or down leaves the first half answering. These drive every state
the registry half can be in, with a fake registry installed where the entry
point would build Wikidata's.
"""

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.registry import RegistryArtist, RegistryHolding, RegistryWorkEntry

ROTHKO = "Q160149"


@pytest.fixture
def registry():
    return FakeRegistry(
        artists={
            ROTHKO: RegistryArtist(
                qid=ROTHKO,
                description="American painter (1903–1970)",
                movements=("abstract expressionism",),
                works=(RegistryWorkEntry(qid="Q2956755", title="Rothko Chapel", sitelinks=13, year=1971, image=None),),
                works_total=1276,
                holdings=(RegistryHolding(qid="Q214867", name="National Gallery of Art", works=1128),),
            )
        },
        # Below the most renowned, as the owner's own Rothkos are: listed only
        # because the library holds it.
        extra_works={
            "Q20270685": RegistryWorkEntry(qid="Q20270685", title="Untitled (Purple, White, and Red)", sitelinks=2, year=1953)
        },
    )


@pytest.fixture
def held(services, service):
    """Rothko with one work in the library carrying the QID Wikidata lists, and one archived."""
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    kept = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=rothko.id)
    gone = service.add_artwork(title="Untitled (Painting)", artist_id=rothko.id)
    service.archive_artwork(gone.id)
    services.identity.set_work_identity(kept.id, "Q20270685")
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    return rothko, kept


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


class TestTheIndex:
    def test_held_artists_by_name_with_works_in_circulation_counted(self, http, held):
        listed = http.get("/api/artists").raise_for_status().json()["artists"]
        names = {entry["artist"]["name"]: entry["held"] for entry in listed}

        # The seeded catalogue's own artists are there too; the archived Rothko is not counted.
        assert names["Mark Rothko"] == 1
        assert names["Salvador Dalí"] == 1
        assert list(names) == sorted(names, key=str.casefold)

    def test_a_query_ignores_accents(self, http, held):
        found = http.get("/api/artists", params={"q": "dali"}).raise_for_status().json()["artists"]

        assert [entry["artist"]["name"] for entry in found] == ["Salvador Dalí"]

    def test_an_artist_with_nothing_in_circulation_is_not_listed(self, http, service):
        ghost = service.add_artist(name="Nobody Held")
        work = service.add_artwork(title="Gone", artist_id=ghost.id)
        service.archive_artwork(work.id)

        names = [entry["artist"]["name"] for entry in http.get("/api/artists").raise_for_status().json()["artists"]]

        assert "Nobody Held" not in names


class TestOneArtist:
    def test_the_library_half_answers_alone(self, http, held):
        rothko, _kept = held

        page = http.get(f"/api/artists/{rothko.id}").raise_for_status().json()

        assert (page["artist"]["name"], page["artist"]["wikidata_qid"], page["held"]) == ("Mark Rothko", ROTHKO, 1)

    def test_what_the_registry_knows_with_the_held_work_marked(self, http, held):
        rothko, kept = held

        view = http.get(f"/api/artists/{rothko.id}/registry").raise_for_status().json()

        assert view["state"] == "known"
        assert view["note"] is None
        assert view["movements"] == ["abstract expressionism"]
        assert view["works_total"] == 1276
        assert {work["title"]: work["held_artwork_id"] for work in view["works"]} == {
            "Rothko Chapel": None,
            "Untitled (Purple, White, and Red)": kept.id,
        }
        assert view["holdings"] == [{"qid": "Q214867", "name": "National Gallery of Art", "works": 1128}]

    def test_the_registry_is_asked_once_per_artist(self, http, held, registry):
        rothko, _kept = held

        http.get(f"/api/artists/{rothko.id}/registry").raise_for_status()
        http.get(f"/api/artists/{rothko.id}/registry").raise_for_status()

        assert registry.asked_about == [ROTHKO]

    def test_an_artist_with_no_qid_says_so(self, http, service):
        nobody = service.add_artist(name="Unmatched Painter")
        service.add_artwork(title="Something", artist_id=nobody.id)

        view = http.get(f"/api/artists/{nobody.id}/registry").raise_for_status().json()

        assert (view["state"], view["works"]) == ("no_identity", [])
        assert "not matched to Wikidata" in view["note"]

    def test_an_outage_degrades_and_is_not_remembered(self, http, held, registry):
        rothko, _kept = held
        registry.failing = True

        view = http.get(f"/api/artists/{rothko.id}/registry").raise_for_status().json()

        assert view["state"] == "unavailable"
        assert "could not be asked" in view["note"]
        registry.failing = False
        assert http.get(f"/api/artists/{rothko.id}/registry").json()["state"] == "known"

    def test_an_unknown_artist_is_refused_by_name(self, http):
        refused = http.get("/api/artists/nobody")

        assert refused.status_code == 400
        assert "nobody" in refused.json()["error"]


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_the_page_says_wikidata_is_not_configured(self, http, held):
        rothko, _kept = held

        view = http.get(f"/api/artists/{rothko.id}/registry").raise_for_status().json()

        assert view["state"] == "not_configured"
        assert "WIKIDATA_USER_AGENT" in view["note"]
