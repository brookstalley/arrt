"""Matching held works and artists to Wikidata, and the curator's word over it.

Every rule here leans towards storing nothing, because a wrong QID marks the
wrong work *Held* on an artist's page. The cases are the ones
`wikidata-findings.md` measured on the owner's catalogue: generic titles, two
painters sharing a name, and a culture whose name a search turns into a person.
"""

import pytest
from fakes import FakeRegistry

from arrt.library.registry import RegistryPerson
from arrt.library.registry.identifiers import IdentifierScheme
from arrt.library.services.identity import IdentityService
from arrt.persistence.records import AcquisitionMethod, IdentitySetBy, RightsStatus, SourceClass
from arrt.services.errors import ServiceError


def artic(number: int) -> str:
    return f"https://www.artic.edu/artworks/{number}/a-slug"


@pytest.fixture
def add_work(service):
    def _add(title, *, artist=None, urls=()):
        work = service.add_artwork(title=title, artist_id=None if artist is None else artist.id)
        for url in urls:
            service.add_source(
                artwork_id=work.id,
                url=url,
                provider="artic",
                source_class=SourceClass.INSTITUTIONAL,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                rights_status=RightsStatus.PUBLIC_DOMAIN,
            )
        return work

    return _add


def identity(store, registry):
    return IdentityService(store, registry)


class TestWorks:
    def test_a_work_is_matched_through_its_museum_identifier(self, store, service, add_work):
        rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
        work = add_work("Untitled (Purple, White, and Red)", artist=rothko, urls=[artic(100472)])
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "100472"): {"Q20270685"}})

        report = identity(store, registry).match()

        assert (store.get_artwork(work.id).wikidata_qid, store.get_artwork(work.id).wikidata_qid_set_by) == (
            "Q20270685",
            IdentitySetBy.MATCHED,
        )
        assert report.works_matched == 1

    def test_two_untitled_works_by_one_artist_each_get_their_own_item(self, store, service, add_work):
        """The title cannot tell them apart; the identifiers can."""
        rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
        first = add_work("Untitled", artist=rothko, urls=[artic(1)])
        second = add_work("Untitled", artist=rothko, urls=[artic(2)])
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1"}, (IdentifierScheme.ARTIC, "2"): {"Q2"}})

        identity(store, registry).match()

        assert [store.get_artwork(w.id).wikidata_qid for w in (first, second)] == ["Q1", "Q2"]

    def test_an_untitled_work_with_no_identifier_stores_nothing_whatever_the_registry_holds(self, store, service, add_work):
        rothko = service.add_artist(name="Mark Rothko", born=1903, died=1970)
        work = add_work("Untitled", artist=rothko, urls=["https://museum.example/untitled"])
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1"}})

        report = identity(store, registry).match()

        assert store.get_artwork(work.id).wikidata_qid is None
        assert report.works_without_identifier == 1

    def test_two_sources_naming_different_items_store_nothing(self, store, service, add_work):
        work = add_work(
            "Target",
            urls=[artic(1), "https://artsandculture.google.com/asset/target/AbC123"],
        )
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1"}, (IdentifierScheme.GOOGLE_ARTS, "AbC123"): {"Q2"}})

        report = identity(store, registry).match()

        assert store.get_artwork(work.id).wikidata_qid is None
        assert report.works_ambiguous == ("Target",)

    def test_one_identifier_naming_two_items_stores_nothing(self, store, add_work):
        work = add_work("Seascape", urls=[artic(1)])
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1", "Q2"}})

        identity(store, registry).match()

        assert store.get_artwork(work.id).wikidata_qid is None

    def test_an_identifier_the_registry_does_not_know_stores_nothing(self, store, add_work):
        work = add_work("Blue Half Circle", urls=[artic(1)])

        report = identity(store, FakeRegistry()).match()

        assert store.get_artwork(work.id).wikidata_qid is None
        assert report.works_unknown == 1


class TestArtists:
    def test_the_one_creator_of_their_matched_works_is_the_artist(self, store, service, add_work):
        """No name search at all: the identifier's certainty carries over."""
        kline = service.add_artist(name="Franz Kline")
        add_work("Painting", artist=kline, urls=[artic(102581)])
        registry = FakeRegistry(
            items={(IdentifierScheme.ARTIC, "102581"): {"Q20266396"}},
            creators={"Q20266396": {"Q374492"}},
        )

        identity(store, registry).match()

        assert store.get_artist(kline.id).wikidata_qid == "Q374492"
        assert registry.searched == []

    def test_when_their_works_name_two_creators_only_those_two_are_candidates(self, store, service, add_work):
        """A collaboration, or a workshop piece: the name search may not reach outside it."""
        artist = service.add_artist(name="Robert Delaunay", born=1885, died=1941)
        add_work("Rhythm", artist=artist, urls=[artic(1)])
        add_work("Windows", artist=artist, urls=[artic(2)])
        registry = FakeRegistry(
            items={(IdentifierScheme.ARTIC, "1"): {"Q1"}, (IdentifierScheme.ARTIC, "2"): {"Q2"}},
            creators={"Q1": {"QA"}, "Q2": {"QB"}},
            people={"Robert Delaunay": [RegistryPerson(qid="QC", label="Robert Delaunay", born=1885, died=1941)]},
        )

        report = identity(store, registry).match()

        assert store.get_artist(artist.id).wikidata_qid is None
        assert report.artists_unknown == ("Robert Delaunay",)

    def test_a_namesake_is_told_apart_by_life_dates(self, store, service):
        miro = service.add_artist(name="Joan Miró", born=1893, died=1983)
        registry = FakeRegistry(
            people={
                "Joan Miró": [
                    RegistryPerson(qid="Q152384", label="Joan Miró", born=1893, died=1983),
                    RegistryPerson(qid="Q58984496", label="Joan Lawrence"),
                ]
            }
        )

        identity(store, registry).match()

        assert store.get_artist(miro.id).wikidata_qid == "Q152384"

    def test_a_name_alone_is_never_enough(self, store, service):
        """*Moche* is a culture; the search finds one painter born in 1633."""
        moche = service.add_artist(name="Moche")
        registry = FakeRegistry(people={"Moche": [RegistryPerson(qid="Q515222", label="Frederik de Moucheron", born=1633)]})

        report = identity(store, registry).match()

        assert store.get_artist(moche.id).wikidata_qid is None
        assert report.artists_undated == ("Moche",)

    def test_dates_that_disagree_match_nothing(self, store, service):
        andrieu = service.add_artist(name="Pierre Andrieu", born=1821, died=1892)
        registry = FakeRegistry(
            people={"Pierre Andrieu": [RegistryPerson(qid="Q1", label="Pierre Andrieu", born=1567, died=1633)]}
        )

        report = identity(store, registry).match()

        assert store.get_artist(andrieu.id).wikidata_qid is None
        assert report.artists_unknown == ("Pierre Andrieu",)

    def test_two_candidates_whose_dates_both_agree_match_nothing(self, store, service):
        artist = service.add_artist(name="John Smith", born=1900)
        registry = FakeRegistry(
            people={
                "John Smith": [
                    RegistryPerson(qid="Q1", label="John Smith", born=1900),
                    RegistryPerson(qid="Q2", label="John Smith", born=1901),
                ]
            }
        )

        report = identity(store, registry).match()

        assert store.get_artist(artist.id).wikidata_qid is None
        assert report.artists_ambiguous == ("John Smith",)

    def test_an_artist_matched_while_the_work_title_matches_nothing(self, store, service, add_work):
        """The artist is found and the work is not: the two are independent."""
        dali = service.add_artist(name="Salvador Dalí", born=1904, died=1989)
        work = add_work("Untitled (Desert Landscape)", artist=dali, urls=[artic(999)])
        registry = FakeRegistry(
            people={"Salvador Dalí": [RegistryPerson(qid="Q5577", label="Salvador Dalí", born=1904, died=1989)]}
        )

        identity(store, registry).match()

        assert store.get_artist(dali.id).wikidata_qid == "Q5577"
        assert store.get_artwork(work.id).wikidata_qid is None


class TestTheCuratorsWord:
    def test_a_qid_set_by_hand_is_never_overwritten(self, store, service, add_work):
        work = add_work("Painting", urls=[artic(1)])
        IdentityService(store, None).set_work_identity(work.id, "Q42")
        registry = FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1"}})

        identity(store, registry).match()

        assert (store.get_artwork(work.id).wikidata_qid, store.get_artwork(work.id).wikidata_qid_set_by) == (
            "Q42",
            IdentitySetBy.CURATOR,
        )

    def test_a_curators_none_is_never_filled(self, store, service, add_work):
        artist = service.add_artist(name="Joan Miró", born=1893, died=1983)
        IdentityService(store, None).set_artist_identity(artist.id, None)
        registry = FakeRegistry(people={"Joan Miró": [RegistryPerson(qid="Q152384", label="Joan Miró", born=1893)]})

        identity(store, registry).match()

        assert store.get_artist(artist.id).wikidata_qid is None
        assert registry.searched == []

    def test_a_second_pass_against_a_changed_registry_overwrites_nothing(self, store, service, add_work):
        """Idempotent with the inputs varied, not just repeated: a match stands until somebody changes it."""
        work = add_work("Painting", urls=[artic(1)])
        identity(store, FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q1"}})).match()

        report = identity(store, FakeRegistry(items={(IdentifierScheme.ARTIC, "1"): {"Q2"}})).match()

        assert store.get_artwork(work.id).wikidata_qid == "Q1"
        assert report.works_matched == 0

    def test_a_qid_is_checked_and_normalised(self, store, add_work):
        work = add_work("Painting")
        service = IdentityService(store, None)

        assert service.set_work_identity(work.id, " q160149 ").wikidata_qid == "Q160149"
        with pytest.raises(ServiceError, match="not a Wikidata item id"):
            service.set_work_identity(work.id, "https://www.wikidata.org/wiki/Q160149")

    def test_matching_without_a_registry_says_how_to_configure_one(self, store):
        with pytest.raises(ServiceError, match="WIKIDATA_USER_AGENT"):
            IdentityService(store, None).match()
