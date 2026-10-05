"""The pages of works and artists the library may not hold, over the real HTTP surface.

Ruling 2: a work or artist Wikidata knows has a page here, addressed by QID,
whether or not the library holds it. These drive the two routes those pages read
through every state the registry can be in, with a fake registry installed where
the entry point would build Wikidata's.
"""

from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fakes import FakeRegistry, NothingWanted

from arrt.library.registry import (
    ItemId,
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryImageSize,
    RegistrySimilar,
    RegistryText,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.library.services.artists import ArtistService, RegistryState
from arrt.library.services.display_fit import DisplayFit, assess_display_fit
from arrt.library.services.registry_search import RegistrySearchService, RegistrySearchState
from arrt.library.services.registry_works import RegistryWorkService, RegistryWorkState
from arrt.persistence.kept import KeptAnswers

ROTHKO = "Q160149"
BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HELD_ROTHKO = "Q20270685"
HUNTERS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
SMALL_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/Small.jpg"
SMALL = "Q7000001"


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: RegistryWork(
                qid=HUNTERS,
                title="The Hunters in the Snow",
                sitelinks=39,
                year=1565,
                image=HUNTERS_FILE,
                creators=(RegistryCreator(qid=BRUEGEL, name="Pieter Brueghel the Elder"),),
                media=("oil paint", "panel"),
                holders=(RegistryHolder(qid="Q95569", name="Kunsthistorisches Museum", inventory="GG_1838"),),
                height_cm=117.0,
                width_cm=162.0,
            ),
            SMALL: RegistryWork(qid=SMALL, title="A postcard of it", sitelinks=0, image=SMALL_FILE),
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
        image_sizes={
            HUNTERS_FILE: RegistryImageSize(width=6000, height=4400),
            SMALL_FILE: RegistryImageSize(width=300, height=200),
        },
        similar={
            BRUEGEL: [
                RegistrySimilar(qid="Q5598", name="Rembrandt", sitelinks=200, born=1606, died=1669, images=900),
                RegistrySimilar(qid=ROTHKO, name="Mark Rothko", sitelinks=150, born=1903, died=1970, images=1),
            ]
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

    def test_a_work_says_how_big_it_is_and_how_big_its_picture_is(self, http):
        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["height_cm"], page["width_cm"]) == (117.0, 162.0)
        assert (page["image_width"], page["image_height"]) == (6000, 4400)
        assert page["fit"]["verdict"] == "native"

    def test_a_picture_too_small_for_the_wall_is_judged_as_the_review_grid_judges_it(self, http, settings):
        page = http.get(f"/api/registry/works/{SMALL}").raise_for_status().json()

        expected = assess_display_fit(width=300, height=200, box=settings.tv_artwork_box)
        assert page["fit"]["verdict"] == "below_floor"
        assert page["fit"]["rendered_long_edge_inches"] == expected.rendered_long_edge_inches
        assert (page["height_cm"], page["width_cm"]) == (None, None)

    def test_a_work_with_no_picture_asks_commons_nothing(self, http, registry):
        page = http.get("/api/registry/works/Q16682090").raise_for_status().json()

        assert (page["image_width"], page["image_height"], page["fit"]) == (None, None, None)
        assert registry.sizes_asked == []

    def test_a_size_that_disagrees_with_its_picture_is_not_shown(self, http, registry):
        """Wikidata's sides swapped, as corpus row 33's are: the picture is wider than tall, the size says taller."""
        registry.works[HUNTERS] = replace(registry.works[HUNTERS], height_cm=162.0, width_cm=117.0)

        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["height_cm"], page["width_cm"]) == (None, None)
        assert page["image_width"] == 6000, "the picture's own size is not in doubt"

    def test_a_held_work_does_not_wait_on_commons(self, http, held, registry):
        """Its page goes to the library's own, so Commons is not asked how big Wikidata's picture is."""
        registry.works[HELD_ROTHKO] = replace(registry.works[HUNTERS], qid=HELD_ROTHKO)

        page = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()

        assert page["held_artwork_ids"]
        assert registry.sizes_asked == []

    def test_a_pictures_size_is_asked_once(self, http, registry):
        for _ in range(2):
            http.get(f"/api/registry/works/{HUNTERS}").raise_for_status()

        assert registry.sizes_asked == [HUNTERS_FILE]

    def test_commons_down_leaves_the_work_known_without_a_size_and_is_asked_again(self, http, registry):
        registry.sizes_failing = True
        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["state"], page["title"], page["height_cm"]) == ("known", "The Hunters in the Snow", 117.0)
        assert (page["image_width"], page["image_height"], page["fit"]) == (None, None, None)

        registry.sizes_failing = False
        assert http.get(f"/api/registry/works/{HUNTERS}").json()["image_width"] == 6000
        assert registry.sizes_asked == [HUNTERS_FILE, HUNTERS_FILE]

    def test_a_file_commons_does_not_have_gives_no_size(self, http, registry):
        registry.image_sizes.clear()

        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["state"], page["image_width"], page["fit"]) == ("known", None, None)

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

    def test_similar_artists_say_wikidata_is_not_configured(self, http):
        page = http.get(f"/api/registry/artists/{BRUEGEL}/similar").raise_for_status().json()

        assert (page["state"], page["artists"]) == ("not_configured", [])

    def test_both_pages_say_wikidata_is_not_configured_and_the_library_still_answers(self, http, held):
        rothko, kept = held

        work = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()
        artist = http.get(f"/api/registry/artists/{ROTHKO}").raise_for_status().json()

        assert (work["state"], work["held_artwork_ids"]) == ("not_configured", [kept.id])
        assert (artist["state"], artist["artist_id"]) == ("held", rothko.id)
        assert "WIKIDATA_USER_AGENT" in work["note"]


class TestAHeldArtistByQid:
    def test_the_library_answers_and_the_registry_is_not_asked(self, http, held, registry):
        """The redirect to the library's page must not wait on Wikidata, as a held work's does not."""
        rothko, _kept = held
        registry.failing = True

        page = http.get(f"/api/registry/artists/{ROTHKO}").raise_for_status().json()

        assert (page["state"], page["artist_id"]) == ("held", rothko.id)
        assert registry.asked_about == []


class TestSimilarArtists:
    def test_they_come_back_with_image_counts_and_the_held_one_marked(self, http, held):
        rothko, _kept = held

        page = http.get(f"/api/registry/artists/{BRUEGEL}/similar").raise_for_status().json()

        assert (page["state"], page["note"]) == ("known", None)
        assert page["artists"] == [
            {"qid": "Q5598", "name": "Rembrandt", "born": 1606, "died": 1669, "images": 900, "artist_id": None},
            {"qid": ROTHKO, "name": "Mark Rothko", "born": 1903, "died": 1970, "images": 1, "artist_id": rothko.id},
        ]

    def test_they_are_asked_once_per_artist_and_an_outage_is_not_remembered(self, http, registry):
        registry.failing = True
        assert http.get(f"/api/registry/artists/{BRUEGEL}/similar").json()["state"] == "unavailable"
        registry.failing = False
        http.get(f"/api/registry/artists/{BRUEGEL}/similar").raise_for_status()
        http.get(f"/api/registry/artists/{BRUEGEL}/similar").raise_for_status()

        assert registry.similar_asked == [BRUEGEL]

    def test_a_malformed_qid_is_refused_by_name(self, http):
        refused = http.get("/api/registry/artists/bruegel/similar")

        assert refused.status_code == 400
        assert "bruegel" in refused.json()["error"]


class TestAfterARestart:
    """What the next process finds: the answers this one was given, and none of its failures.

    The page is driven over HTTP; the restart is a second set of services over
    the same catalogue and the same kept answers file, as the entry point builds
    them, with a registry that is down.
    """

    @pytest.fixture
    def restarted(self, store, settings):
        """The services a restart builds for the registry pages, over a registry that is down."""
        down = FakeRegistry(failing=True)
        kept = KeptAnswers(settings.kept_answers_path)
        yield SimpleNamespace(
            registry=down,
            artists=ArtistService(store, down, kept=kept, wanted=NothingWanted()),
            registry_works=RegistryWorkService(store, down, kept=kept, wanted=NothingWanted(), box=settings.tv_artwork_box),
            registry_search=RegistrySearchService(store, down, kept=kept, wanted=NothingWanted()),
        )
        kept.close()

    def test_an_artist_page_section_answers_from_the_kept_answer_with_the_registry_down(self, http, held, registry, restarted):
        rothko, _kept_work = held
        http.get(f"/api/registry/artists/{BRUEGEL}").raise_for_status()
        http.get(f"/api/registry/artists/{BRUEGEL}/similar").raise_for_status()
        http.get(f"/api/registry/works/{HUNTERS}").raise_for_status()
        http.get("/api/registry/search", params={"q": "hunters"}).raise_for_status()

        _, artist = restarted.artists.registry_view_by_qid(BRUEGEL)
        similar = restarted.artists.similar(BRUEGEL)
        work = restarted.registry_works.view(HUNTERS)
        search = restarted.registry_search.search("hunters", prefix=False)

        assert (artist.state, artist.known) == (RegistryState.KNOWN, registry.artists[BRUEGEL])
        assert (similar.state, similar.people) == (RegistryState.KNOWN, tuple(registry.similar[BRUEGEL]))
        # Held is the library's to say, read fresh, not kept with the answer.
        assert similar.held == {ROTHKO: rothko.id}
        assert (work.state, work.known) == (RegistryWorkState.KNOWN, registry.works[HUNTERS])
        assert (work.image_size, work.fit.fit) == (registry.image_sizes[HUNTERS_FILE], DisplayFit.NATIVE)
        assert restarted.registry.sizes_asked == []
        assert search.state is RegistrySearchState.KNOWN
        assert (restarted.registry.asked_about, restarted.registry.similar_asked, restarted.registry.works_asked) == ([], [], [])

    def test_a_held_mark_made_since_the_answer_was_kept_is_shown(self, http, held, service, services, restarted):
        http.get(f"/api/registry/works/{HUNTERS}").raise_for_status()
        rothko, _ = held
        hunters = service.add_artwork(title="The Hunters in the Snow", artist_id=rothko.id)
        services.identity.set_work_identity(hunters.id, HUNTERS)

        assert restarted.registry_works.view(HUNTERS).held == (hunters.id,)

    def test_a_failure_is_not_kept_for_the_next_process(self, http, registry, restarted):
        registry.failing = True
        for address in (
            f"/api/registry/artists/{BRUEGEL}",
            f"/api/registry/artists/{BRUEGEL}/similar",
            f"/api/registry/works/{HUNTERS}",
            "/api/registry/search?q=hunters",
        ):
            assert http.get(address).json()["state"] == "unavailable", address

        assert restarted.artists.registry_view_by_qid(BRUEGEL)[1].state is RegistryState.UNAVAILABLE
        assert restarted.artists.similar(BRUEGEL).state is RegistryState.UNAVAILABLE
        assert restarted.registry_works.view(HUNTERS).state is RegistryWorkState.UNAVAILABLE
        assert restarted.registry_search.search("hunters", prefix=False).state is RegistrySearchState.UNAVAILABLE


class TestAWantedWorkIsMarkedWhereverRegistryWorksAreListed:
    """The owner's ruling on #172: held, wanted and not held read apart wherever registry works are listed.

    A work wanted through Review names its Wikidata item once matched, and every
    answer that says which works the library holds also says which are wanted.
    Each fixture wants a second item that is not listed, so a route that marked
    everything once anything is wanted fails.
    """

    @pytest.fixture
    def wanted(self, discovery, propose):
        hunters = propose("The Hunters in the Snow", proposed_artist="Pieter Brueghel the Elder")
        discovery.want(hunters.id)
        discovery.set_wikidata_item(hunters.id, HUNTERS)
        elsewhere = propose("Lobster Telephone", proposed_artist="Salvador Dalí")
        discovery.want(elsewhere.id)
        discovery.set_wikidata_item(elsewhere.id, "Q2990594")
        # Wanted with no item: names nothing, so marks nothing.
        discovery.want(propose("Mountain Lake").id)

    def test_a_works_page(self, http, wanted):
        assert http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()["wanted"] is True
        assert http.get("/api/registry/works/Q16682090").raise_for_status().json()["wanted"] is False

    def test_a_works_page_says_so_whatever_the_registry_does(self, http, wanted, registry):
        registry.failing = True

        page = http.get(f"/api/registry/works/{HUNTERS}").raise_for_status().json()

        assert (page["state"], page["wanted"]) == ("unavailable", True)

    def test_an_artists_works(self, http, wanted, registry):
        # A second listed work nobody wants, so a route marking every work fails.
        bruegel = registry.artists[BRUEGEL]
        registry.artists[BRUEGEL] = replace(
            bruegel, works=(*bruegel.works, RegistryWorkEntry(qid="Q1170284", title="The Harvesters", sitelinks=25, year=1565))
        )

        page = http.get(f"/api/registry/artists/{BRUEGEL}").raise_for_status().json()

        assert [(work["qid"], work["wanted"]) for work in page["works"]] == [(HUNTERS, True), ("Q1170284", False)]

    def test_the_search(self, http, wanted, registry):
        registry.matches["hunters"] = [
            RegistryWorkMatch(qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39),
            RegistryWorkMatch(qid=ItemId("Q16682090"), title=RegistryText("Hunters, untitled"), sitelinks=1),
        ]

        found = http.get("/api/registry/search", params={"q": "hunters"}).raise_for_status().json()

        assert [(work["qid"], work["wanted"]) for work in found["works"]] == [(HUNTERS, True), ("Q16682090", False)]

    def test_held_and_wanted_are_both_reported_and_the_page_decides(self, http, held, discovery, propose):
        """A wanted work since acquired: the answer carries both facts; the page shows it held."""
        _rothko, kept = held
        work = propose("Untitled (Purple, White, and Red)")
        discovery.want(work.id)
        discovery.set_wikidata_item(work.id, HELD_ROTHKO)

        page = http.get(f"/api/registry/works/{HELD_ROTHKO}").raise_for_status().json()

        assert (page["held_artwork_ids"], page["wanted"]) == ([kept.id], True)
