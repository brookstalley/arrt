"""The recorded Wikidata findings, as a test rather than as prose.

`wikidata-findings.md` is a snapshot of a live probe, and the matcher leans on
four of its measurements: a museum identifier names exactly the item the owner's
catalogue was matched to, an item's creator is recorded, a name search with
life dates tells two Joan Mirós apart, and a search for a culture's name finds a
painter that only the missing dates keep out. Wikidata is edited by anyone, so
the durable form of those measurements is a test that fails when one stops
holding.

**Deselected by default** and free: the query service is unmetered, and the test
is marked `live_museum` with its siblings because it needs the network, not
because it spends. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_wikidata_shapes_are_still_real.py
"""

import pytest

from arrt.library.registry.identifiers import IdentifierScheme
from arrt.library.registry.wikidata import WikidataRegistry

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"


@pytest.fixture(scope="module")
def registry():
    client = WikidataRegistry(user_agent=USER_AGENT)
    yield client
    client.close()


def test_an_art_institute_id_names_one_item(registry):
    """If this drifts, `works_by_identifier` is reading the wrong property, and works stop matching."""
    found = registry.works_by_identifier(IdentifierScheme.ARTIC, ["102581", "100472"])

    assert found == {"102581": frozenset({"Q20266396"}), "100472": frozenset({"Q20270685"})}


def test_a_google_arts_and_culture_id_names_one_item(registry):
    """Juan Gris's *Portrait of Pablo Picasso*, the one Google Arts & Culture work the probe matched."""
    found = registry.works_by_identifier(IdentifierScheme.GOOGLE_ARTS, ["RgGPipJ4FxSBiw"])

    assert len(found.get("RgGPipJ4FxSBiw", ())) == 1


def test_a_matched_items_creator_is_recorded(registry):
    """The route an artist is identified by when their work is: Franz Kline, and Mark Rothko."""
    assert registry.creators_of(["Q20266396", "Q20270685"]) == {
        "Q20266396": frozenset({"Q374492"}),
        "Q20270685": frozenset({"Q160149"}),
    }


def test_a_namesake_comes_back_with_dates_that_tell_them_apart(registry):
    found = {person.qid: person for person in registry.people_named("Joan Miró")}

    assert (found["Q152384"].born, found["Q152384"].died) == (1893, 1983)


def test_a_cultures_name_finds_a_person_only_dates_keep_out(registry):
    """The case that makes a name alone untrustworthy. If this ever finds nobody, the rule is merely cautious."""
    found = registry.people_named("Moche")

    assert found, "the search no longer turns 'Moche' into a person; the undated rule is now belt and braces"


def test_a_name_with_only_a_language_neutral_label_is_still_a_name(registry):
    """Mark Rothko's name is a `mul` label, with no `en` one (measured 2026-10-01)."""
    found = {person.qid: person.label for person in registry.people_named("Mark Rothko")}

    assert found.get("Q160149") == "Mark Rothko"


def test_one_work_pairs_its_number_with_its_holder(registry):
    """The owner's held Rothko, ARTIC 100472 above, as its own page reads it."""
    work = registry.work("Q20270685")

    assert work is not None
    assert [c.name for c in work.creators] == ["Mark Rothko"]
    assert [(h.name, h.inventory) for h in work.holders] == [("Art Institute of Chicago", "1983.509")]


def test_a_title_search_finds_the_painting_and_not_the_tv_series(registry):
    """The index filter on artwork classes, measured 2026-10-01 (`wikidata-findings.md`)."""
    found = registry.works_matching(["the", "persistence"], prefix=True, limit=5)

    assert found
    assert found[0].qid == "Q25729"
    assert found[0].creator is not None
    assert found[0].creator.name == "Salvador Dalí"
    assert not any(
        match.title in {"Kojak", "Power Girl", "Wikidata"} for match in registry.works_matching(["starr"], prefix=True, limit=5)
    )


def test_similar_artists_come_back_with_image_counts(registry):
    """Rothko's list began with Pollock, who has no free image (measured 2026-10-01)."""
    found = registry.similar_to("Q160149", limit=12)

    assert len(found) >= 5
    assert any(person.name == "Jackson Pollock" and person.images == 0 for person in found)


def test_an_item_that_exists_is_named_and_one_that_does_not_is_none(registry):
    assert registry.label_of("Q160149") == "Mark Rothko"
    assert registry.label_of("Q999999999999") is None


def test_a_works_item_gives_its_holders_page(registry):
    """*Drowning Girl*'s MoMA ID (P2014), put into its property's formatter URL: the recorded fixture's page, still real.

    The Wikidata finder offers only what `pages_about` builds, so if this drifts
    the sightings count loses its museum-page holders without any test noticing.
    """
    assert "https://www.moma.org/collection/works/80249" in registry.pages_about("Q5308687")
