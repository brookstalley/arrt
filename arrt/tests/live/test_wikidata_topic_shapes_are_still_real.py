"""The recorded topic findings, as a test rather than as prose.

`wikidata-findings.md` § Topics records what the query service answered to the
topic questions on 2026-10-02, and the client leans on these shapes: the classes
that make Baroque a movement and a period, and Romanticism a movement only though
it has years; a kind of work found as the class its works are instances of; a
maker recorded as unknown arriving as a blank node; artists counted by their
works in the topic; a search that ranks a political party first and nothing
depicts, and offers a music movement no maker of visual art belongs to; and the
routes from a held work and artist to their topics. Wikidata is edited by anyone,
so this fails when one stops holding.

**Deselected by default**, and free: marked `live_museum` with its siblings
because it needs the network. It asks nothing about a period's works, which take
eight seconds to a minute and can be refused for the minute after; the unit tests
hold that query's text. Run deliberately, one process:

    uv run pytest -m live_museum -n0 tests/live/test_wikidata_topic_shapes_are_still_real.py
"""

import pytest

from arrt.library.registry import TopicKind
from arrt.library.registry.wikidata import WikidataRegistry

pytestmark = pytest.mark.live_museum

USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"


@pytest.fixture(scope="module")
def registry():
    client = WikidataRegistry(user_agent=USER_AGENT)
    yield client
    client.close()


def test_baroque_is_a_movement_and_a_period_and_a_century_has_years(registry):
    """If the classes move, the kind rule assigns something else, and the page finds the wrong works."""
    baroque = registry.topic("Q37853")
    century = registry.topic("Q7017")

    assert baroque.kinds == (TopicKind.MOVEMENT, TopicKind.PERIOD)
    assert (century.kinds, century.start, century.end) == ((TopicKind.PERIOD,), 1501, 1600)


def test_romanticism_has_years_and_is_a_movement_only(registry):
    """Years alone make nothing a period: Romanticism was one by its start and end."""
    romanticism = registry.topic("Q37068")

    assert romanticism.kinds == (TopicKind.MOVEMENT,)
    assert romanticism.start is not None and romanticism.end is not None


def test_a_kind_of_works_works_are_its_instances_one_entry_each(registry):
    """Woodcut print: Dürer's *Rhinoceros*, and the *Flammarion engraving*, whose maker is recorded as unknown."""
    woodcut = registry.topic("Q18219090")
    assert woodcut.kinds == (TopicKind.MEDIUM,)

    works = {work.qid: work for work in registry.topic_works(woodcut, limit=50)}

    assert len(works) == 50
    assert [creator.name for creator in works["Q748518"].creators] == ["Albrecht Dürer"]
    flammarion = works["Q1426992"]
    assert flammarion.creator_unknown and flammarion.creators == ()


def test_a_movements_artists_are_its_own_with_image_counts(registry):
    people = {person.qid: person for person in registry.topic_artists(registry.topic("Q40415"), limit=12)}

    assert people["Q296"].name == "Claude Monet" and people["Q296"].images > 0


def test_a_topics_artists_are_counted_by_their_works_in_it(registry):
    """Woodcut print: ranked by renown, Benjamin Franklin came first for *Join, or Die*; by woodcuts, Dürer does."""
    people = [person.qid for person in registry.topic_artists(registry.topic("Q18219090"), limit=10)]

    assert people[0] == "Q5580"
    assert "Q34969" not in people


def test_a_topic_search_offers_the_movement_and_not_the_political_party(registry):
    found = {topic.qid: topic for topic in registry.topics_named("renaissance")}

    assert found["Q4692"].kinds[0] is TopicKind.MOVEMENT
    assert "Q23731823" not in found


def test_a_topic_search_offers_no_movement_of_music(registry):
    found = {topic.qid: topic for topic in registry.topics_named("impressionism")}

    assert found["Q40415"].kinds == (TopicKind.MOVEMENT,)
    assert "Q837182" not in found


def test_a_held_rothko_and_rothko_have_their_topics(registry):
    """The owner's held Rothko (ARTIC 100472), and Rothko himself, as the facet rail will read them."""
    found = registry.topics_of(["Q20270685"], ["Q160149"])

    assert [(ref.label, ref.kind) for ref in found.works["Q20270685"]] == [
        ("20th century", TopicKind.PERIOD),
        ("painting", TopicKind.MEDIUM),
    ]
    assert [(ref.label, ref.kind) for ref in found.artists["Q160149"]] == [("abstract expressionism", TopicKind.MOVEMENT)]
