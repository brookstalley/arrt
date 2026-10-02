"""Matching a wanted work to its Wikidata item: offered by the registry, picked by the curator.

The fake registry answers what Wikidata answered on 2026-10-02 for the Dalí
works an August Ask run left with no scan (`wikidata-findings.md` § Matching a
wanted work): the right item first for most titles; two Dalí items for *Lobster
Telephone*; and a *Mountain Lake* that only the search with the artist's name
finds. Nothing here stores a match on its own (`data-model.md` § Registry
identity): the curator's pick is the only write.
"""

import pytest
from fakes import FakeRegistry

from arrt.library.registry import ItemId, RegistryCreator, RegistryText, RegistryWorkMatch
from arrt.library.services.wikidata_match import WikidataMatchService, WorkMatchState
from arrt.persistence.discovery_records import Verdict
from arrt.persistence.records import IdentitySetBy
from arrt.services.errors import ServiceError

DALI = RegistryCreator(qid=ItemId("Q5577"), name=RegistryText("Salvador Dalí"))
HEADE = RegistryCreator(qid=ItemId("Q1395543"), name=RegistryText("Martin Johnson Heade"))


def a_match(qid, title, creator=DALI, sitelinks=0):
    return RegistryWorkMatch(qid=ItemId(qid), title=RegistryText(title), sitelinks=sitelinks, creator=creator)


def service_over(discovery, registry):
    return WikidataMatchService(discovery, registry)


def test_the_title_and_artist_are_searched_together_first_without_the_year(discovery, propose):
    registry = FakeRegistry(matches={"Lobster Telephone Salvador Dalí": [a_match("Q2990594", "Lobster Telephone", sitelinks=13)]})
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    found = service_over(discovery, registry).matches(work.id)

    assert registry.matched == [("Lobster Telephone Salvador Dalí", False)]
    assert found.state is WorkMatchState.KNOWN
    assert [str(entry.match.qid) for entry in found.matches] == ["Q2990594"]


def test_the_title_alone_is_asked_when_the_narrower_search_finds_nothing(discovery, propose):
    registry = FakeRegistry(matches={"Portrait of my Sister": [a_match("Q3937747", "Portrait of My Sister")]})
    work = propose("Portrait of my Sister (1925)", proposed_artist="Dali")

    found = service_over(discovery, registry).matches(work.id)

    assert [words for words, _ in registry.matched] == ["Portrait of my Sister Dali", "Portrait of my Sister"]
    assert [str(entry.match.qid) for entry in found.matches] == ["Q3937747"]


def test_the_proposed_artist_s_matches_lead_and_the_registry_s_order_holds_within_each(discovery, propose):
    registry = FakeRegistry(
        matches={
            "Mountain Lake": [
                a_match("Q113858978", "Orchid and Hummingbirds near a Mountain Lake", creator=HEADE, sitelinks=1),
                a_match("Q120132099", "A Mountain Lake Scene", creator=None),
                a_match("Q28555476", "Mountain Lake"),
                a_match("Q999", "Mountain Lake, second Dalí"),
            ]
        }
    )
    # "with Edward James": the run's artist need only contain the creator's name.
    work = propose("Mountain Lake (1938)", proposed_artist="Salvador Dali (with Edward James)")

    found = service_over(discovery, registry).matches(work.id)

    assert [str(entry.match.qid) for entry in found.matches] == ["Q28555476", "Q999", "Q113858978", "Q120132099"]
    assert [entry.by_proposed_artist for entry in found.matches] == [True, True, False, False]


def test_without_a_registry_the_picker_says_matching_needs_one(discovery, propose):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    found = service_over(discovery, None).matches(work.id)

    assert found.state is WorkMatchState.NOT_CONFIGURED
    assert "WIKIDATA_USER_AGENT" in found.note
    assert found.matches == ()


def test_a_registry_that_cannot_answer_is_said_and_nothing_is_offered(discovery, propose):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    found = service_over(discovery, FakeRegistry(failing=True)).matches(work.id)

    assert found.state is WorkMatchState.UNAVAILABLE
    assert "HTTP 503" in found.note


def test_asking_for_matches_stores_nothing(discovery, propose):
    registry = FakeRegistry(matches={"Lobster Telephone Salvador Dalí": [a_match("Q2990594", "Lobster Telephone")]})
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    service_over(discovery, registry).matches(work.id)

    assert discovery.get_candidate_work(work.id).wikidata_qid is None


def test_the_curator_s_pick_is_recorded_on_the_work(discovery, propose):
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    picked = service_over(discovery, None).pick(work.id, "Q2990594")

    assert picked.wikidata_qid == "Q2990594"
    assert discovery.get_candidate_work(work.id).wikidata_qid == "Q2990594"


def test_a_pick_that_is_not_an_item_id_is_refused(discovery, propose):
    work = propose("Lobster Telephone (1938)")

    with pytest.raises(ServiceError, match="not a Wikidata item id"):
        service_over(discovery, None).pick(work.id, "https://www.wikidata.org/wiki/Q2990594")


@pytest.mark.parametrize("verdict", [Verdict.ACCEPTED, Verdict.REJECTED])
def test_a_pick_on_a_decided_work_is_refused(discovery, resolved_work, verdict):
    work = resolved_work("Lobster Telephone")
    discovery.set_verdict(work.id, verdict)

    with pytest.raises(ServiceError, match=f"already {verdict}"):
        service_over(discovery, None).pick(work.id, "Q2990594")


def test_the_picked_item_becomes_the_artwork_s_as_the_curator_s_at_acceptance(discovery, resolved_work, service):
    """The multi-hop half: what the pick is for is the artwork's identity, and a re-search's Commons ask."""
    work = resolved_work("Lobster Telephone")
    service_over(discovery, None).pick(work.id, "Q2990594")

    outcome = discovery.set_verdict(work.id, Verdict.ACCEPTED)

    artwork = service.get_artwork(outcome.work.artwork_id).artwork
    assert (artwork.wikidata_qid, artwork.wikidata_qid_set_by) == ("Q2990594", IdentitySetBy.CURATOR)


def test_a_word_touching_punctuation_is_still_searched_for(discovery, propose):
    registry = FakeRegistry()
    work = propose("Soft Construction with Boiled Beans (Premonition of Civil War)", proposed_artist="Salvador Dalí")

    service_over(discovery, registry).matches(work.id)

    asked, _ = registry.matched[0]
    assert "Premonition" in asked.split() and "War" in asked.split()


def test_a_wanted_work_s_item_can_be_picked(discovery, propose):
    """The case the picker exists for: a work wanted with no scan, which Search again needs an item for."""
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")
    discovery.want(work.id)

    picked = service_over(discovery, None).pick(work.id, "Q2990594")

    assert (picked.verdict, picked.wikidata_qid) == (Verdict.WANTED, "Q2990594")


def test_a_creator_with_an_empty_name_is_not_taken_for_the_proposed_artist(discovery, propose):
    blank = RegistryCreator(qid=ItemId("Q1"), name=RegistryText(""))
    registry = FakeRegistry(matches={"Lobster Telephone Salvador Dalí": [a_match("Q9", "Lobster Telephone", creator=blank)]})
    work = propose("Lobster Telephone (1938)", proposed_artist="Salvador Dalí")

    found = service_over(discovery, registry).matches(work.id)

    assert [entry.by_proposed_artist for entry in found.matches] == [False]
