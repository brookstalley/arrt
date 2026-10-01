"""The pages of works and artists the library may not hold, over the real HTTP surface.

Ruling 2: a work or artist Wikidata knows has a page here, addressed by QID,
whether or not the library holds it. These drive the two routes those pages read
through every state the registry can be in, with a fake registry installed where
the entry point would build Wikidata's.
"""

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryWork,
    RegistryWorkEntry,
)

ROTHKO = "Q160149"
BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HELD_ROTHKO = "Q20270685"


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: RegistryWork(
                qid=HUNTERS,
                title="The Hunters in the Snow",
                sitelinks=39,
                year=1565,
                image="https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg",
                creators=(RegistryCreator(qid=BRUEGEL, name="Pieter Brueghel the Elder"),),
                media=("oil paint", "panel"),
                holders=(RegistryHolder(qid="Q95569", name="Kunsthistorisches Museum", inventory="GG_1838"),),
            ),
            "Q16682090": RegistryWork(
                qid="Q16682090",
                title="Q16682090",
                sitelinks=1,
                year=1964,
                creators=(RegistryCreator(qid=ROTHKO, name="Mark Rothko"),),
            ),
        },
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name="Pieter Brueghel the Elder",
                born=1525,
                died=1569,
                movements=("Northern Renaissance",),
                works=(RegistryWorkEntry(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, year=1565),),
                works_total=125,
            ),
            ROTHKO: RegistryArtist(qid=ROTHKO, name="Mark Rothko"),
        },
    )


@pytest.fixture
def held(services, service):
    """Rothko in the library, matched, with one work in circulation carrying a QID."""
    rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    kept = service.add_artwork(title="Untitled (Purple, White, and Red)", artist_id=rothko.id)
    services.identity.set_work_identity(kept.id, HELD_ROTHKO)
    services.identity.set_artist_identity(rothko.id, ROTHKO)
    return rothko, kept


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


class TestAWorkByQid:
    def test_a_work_the_library_does_not_hold(self, http, held):
        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["state"], page["note"], page["title"], page["year"]) == ("known", None, "The Hunters in the Snow", 1565)
        assert page["held_artwork_ids"] == []
        assert page["creators"] == [{"qid": BRUEGEL, "name": "Pieter Brueghel the Elder", "artist_id": None}]
        assert page["media"] == ["oil paint", "panel"]
        assert page["holders"] == [{"qid": "Q95569", "name": "Kunsthistorisches Museum", "inventory": "GG_1838"}]
        assert page["image"].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")

    def test_a_held_creator_links_to_the_library_artist(self, http, held):
        rothko, _kept = held

        page = http.get("/api/registry/works/Q16682090").raise_for_status().json()

        assert page["creators"] == [{"qid": ROTHKO, "name": "Mark Rothko", "artist_id": rothko.id}]

    def test_a_held_work_names_the_library_works_that_are_it_whatever_the_registry_does(self, http, held, registry):
        """The redirect to the library's own page must not wait on, or fail with, Wikidata."""
        _rothko, kept = held
        registry.failing = True

        page = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()

        assert (page["state"], page["held_artwork_ids"]) == ("unavailable", [kept.id])

    def test_an_archived_work_is_not_held(self, http, held, service):
        _rothko, kept = held
        service.archive_artwork(kept.id)

        page = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()

        assert page["held_artwork_ids"] == []

    def test_an_item_wikidata_does_not_have(self, http):
        page = http.get("/api/registry/works/Q999999999999").raise_for_status().json()

        assert (page["state"], page["title"], page["creators"]) == ("not_found", None, [])
        assert "Q999999999999" in page["note"]

    def test_a_known_work_is_asked_once_and_a_missing_one_every_time(self, http, registry):
        for _ in range(2):
            http.get(f"/api/registry/works/{HUNTERS}").raise_for_status()
            http.get("/api/registry/works/Q999999999999").raise_for_status()

        assert registry.works_asked == [HUNTERS, "Q999999999999", "Q999999999999"]

    def test_an_outage_says_so_and_is_not_remembered(self, http, registry):
        registry.failing = True
        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()
        assert (page["state"], page["title"]) == ("unavailable", None)
        assert "could not be asked" in page["note"]

        registry.failing = False
        assert http.get(f"/api/registry/works/{HUNTERS}").json()["state"] == "known"

    @pytest.mark.parametrize("address", ["nothing", "Q0", "q500985", "Q1x"])
    def test_an_address_that_is_not_a_qid_is_refused_by_name(self, http, address):
        refused = http.get(f"/api/registry/works/{address}")

        assert refused.status_code == 400
        assert address in refused.json()["error"]


class TestAnArtistByQid:
    def test_an_artist_the_library_does_not_hold(self, http, held):
        page = http.get(f"/api/registry/artists/{BRUEGEL}").raise_for_status().json()

        assert (page["state"], page["artist_id"]) == ("known", None)
        assert (page["name"], page["born"], page["died"]) == ("Pieter Brueghel the Elder", 1525, 1569)
        assert [(work["qid"], work["held_artwork_ids"]) for work in page["works"]] == [(HUNTERS, [])]

    def test_a_held_artist_names_their_library_page(self, http, held):
        rothko, _kept = held

        page = http.get(f"/api/registry/artists/{ROTHKO}").raise_for_status().json()

        assert page["artist_id"] == rothko.id

    def test_the_library_artists_own_route_names_no_other_page(self, http, held):
        rothko, _kept = held

        assert http.get(f"/api/artists/{rothko.id}/registry").raise_for_status().json()["artist_id"] is None

    def test_an_outage_says_so(self, http, registry):
        registry.failing = True

        page = http.get(f"/api/registry/artists/{BRUEGEL}").raise_for_status().json()

        assert page["state"] == "unavailable"
        assert "could not be asked" in page["note"]

    def test_an_address_that_is_not_a_qid_is_refused_by_name(self, http):
        refused = http.get("/api/registry/artists/bruegel")

        assert refused.status_code == 400
        assert "bruegel" in refused.json()["error"]


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_both_pages_say_wikidata_is_not_configured_and_the_library_still_answers(self, http, held):
        rothko, kept = held

        work = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()
        artist = http.get(f"/api/registry/artists/{ROTHKO}").raise_for_status().json()

        assert (work["state"], work["held_artwork_ids"]) == ("not_configured", [kept.id])
        assert (artist["state"], artist["artist_id"]) == ("not_configured", rothko.id)
        assert "WIKIDATA_USER_AGENT" in work["note"]
