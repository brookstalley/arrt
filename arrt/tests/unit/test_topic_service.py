"""The topic service against a stated registry: what it remembers, what it marks, and what it says when it cannot ask.

The registry's own answers are held by `test_wikidata_topics.py`; this holds the
service to the Artist page's rules for a registry section: an answer is
remembered per topic and a failure is not, *Held* is read fresh from the
library on every call, and a server with no User-Agent says topics need one.
"""

from types import SimpleNamespace

import pytest

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicWork,
    RegistryUnavailable,
    TopicKind,
)
from arrt.library.services.topics import (
    TOPICS_NOT_CONFIGURED_NOTE,
    TopicService,
    TopicState,
    WorkState,
)
from arrt.services.errors import ServiceError

WINTER = RegistryTopic(qid=ItemId("Q1311"), label=RegistryText("winter"), kinds=(TopicKind.SUBJECT,))

HUNTERS = RegistryTopicWork(
    qid=ItemId("Q500985"),
    title=RegistryText("The Hunters in the Snow"),
    sitelinks=39,
    image=CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/H.jpg"),
)
MAGPIE = RegistryTopicWork(
    qid=ItemId("Q4429116"),
    title=RegistryText("The Magpie"),
    sitelinks=19,
    image=CommonsFile("https://commons.wikimedia.org/wiki/Special:FilePath/M.jpg"),
)
#: No image known: Miró's *The Farm*, as the 1920s answered on 2026-10-02.
UNSEEN = RegistryTopicWork(qid=ItemId("Q1192436"), title=RegistryText("The Farm"), sitelinks=14)

MATISSE = RegistrySimilar(qid=ItemId("Q5589"), name=RegistryText("Henri Matisse"), sitelinks=181, images=507)
MONET = RegistrySimilar(qid=ItemId("Q296"), name=RegistryText("Claude Monet"), sitelinks=155, images=1286)


class TopicRegistry:
    """The topic questions of a `Registry`, answering from tables and counting what it was asked."""

    def __init__(self, *, topics=(), works=None, artists=None, named=None, failing=False):
        self.topics = {topic.qid: topic for topic in topics}
        self.works = works or {}
        self.artists = artists or {}
        self.named = named or {}
        self.failing = failing
        self.asked: list[tuple[str, str]] = []

    def _ask(self, question, about):
        self.asked.append((question, about))
        if self.failing:
            raise RegistryUnavailable("Wikidata answered HTTP 503.")

    def topic(self, qid):
        self._ask("topic", qid)
        return self.topics.get(qid)

    def topic_works(self, topic, *, limit):
        self._ask("topic_works", topic.qid)
        return self.works.get(topic.qid, [])[:limit]

    def topic_artists(self, topic, *, limit):
        self._ask("topic_artists", topic.qid)
        return self.artists.get(topic.qid, [])[:limit]

    def topics_named(self, text):
        self._ask("topics_named", text)
        return self.named.get(text, [])


class Store:
    """The two things the service reads from the catalogue: held works by QID, and artists."""

    def __init__(self, *, held=None, artists=()):
        self.held = held or {}
        self.artists = list(artists)

    def circulating_ids_by_qid(self):
        return self.held

    def list_artists(self):
        return self.artists


def _service(registry, store=None):
    return TopicService(store or Store(), registry)


def test_a_topic_is_asked_once_and_remembered():
    registry = TopicRegistry(topics=[WINTER], works={"Q1311": [HUNTERS]}, artists={"Q1311": [MONET]})
    service = _service(registry)

    assert service.topic("Q1311").known == WINTER
    service.works("Q1311")
    service.works("Q1311")
    service.artists("Q1311")
    service.artists("Q1311")

    assert registry.asked == [("topic", "Q1311"), ("topic_works", "Q1311"), ("topic_artists", "Q1311")]


def test_a_failure_is_not_remembered_so_the_next_visit_asks_again():
    registry = TopicRegistry(topics=[WINTER], works={"Q1311": [HUNTERS]}, failing=True)
    service = _service(registry)

    assert service.works("Q1311").state is TopicState.UNAVAILABLE
    registry.failing = False
    view = service.works("Q1311")

    assert view.state is TopicState.KNOWN and [entry.work for entry in view.works] == [HUNTERS]


def test_an_item_the_registry_does_not_have_is_not_found_and_asked_about_again():
    registry = TopicRegistry()
    service = _service(registry)

    first, second = service.topic("Q999999999999"), service.works("Q999999999999")

    assert (first.state, second.state) == (TopicState.NOT_FOUND, TopicState.NOT_FOUND)
    assert "Q999999999999" in first.note
    assert registry.asked == [("topic", "Q999999999999"), ("topic", "Q999999999999")]


def test_each_work_says_whether_it_is_held_has_an_image_or_has_none():
    store = Store(held={"Q500985": ["w-1", "w-2"]})
    view = _service(TopicRegistry(topics=[WINTER], works={"Q1311": [HUNTERS, MAGPIE, UNSEEN]}), store).works("Q1311")

    assert [(entry.work.qid, entry.state, tuple(entry.held)) for entry in view.works] == [
        ("Q500985", WorkState.HELD, ("w-1", "w-2")),
        ("Q4429116", WorkState.IMAGE_FOUND, ()),
        ("Q1192436", WorkState.NO_IMAGE, ()),
    ]


def test_held_is_read_fresh_while_the_registrys_answer_is_remembered():
    """A work accepted after the first visit is marked on the second, without asking the registry again."""
    store = Store()
    registry = TopicRegistry(topics=[WINTER], works={"Q1311": [MAGPIE]})
    service = _service(registry, store)

    assert service.works("Q1311").works[0].state is WorkState.IMAGE_FOUND
    store.held = {"Q4429116": ["w-9"]}

    assert service.works("Q1311").works[0].state is WorkState.HELD
    assert registry.asked.count(("topic_works", "Q1311")) == 1


def test_an_artist_the_library_holds_is_marked_with_its_id():
    store = Store(
        artists=[
            SimpleNamespace(id="a-1", name="Claude Monet", wikidata_qid="Q296"),
            SimpleNamespace(id="a-2", name="Paul Gauguin", wikidata_qid="Q37693"),
        ]
    )
    view = _service(TopicRegistry(topics=[WINTER], artists={"Q1311": [MATISSE, MONET]}), store).artists("Q1311")

    assert [person.name for person in view.people] == ["Henri Matisse", "Claude Monet"]
    assert view.held == {"Q296": "a-1"}


@pytest.mark.parametrize("section", ["topic", "works", "artists", "named"])
def test_with_no_user_agent_every_section_says_topics_need_one(section):
    view = getattr(TopicService(Store(), None), section)("Q1311" if section != "named" else "winter")

    assert (view.state, view.note) == (TopicState.NOT_CONFIGURED, TOPICS_NOT_CONFIGURED_NOTE)
    assert "WIKIDATA_USER_AGENT" in view.note


def test_a_search_is_passed_through_and_an_empty_one_asks_nothing():
    registry = TopicRegistry(named={"winter": [WINTER]})
    service = _service(registry)

    assert service.named("  winter ").topics == (WINTER,)
    assert service.named("   ").topics == ()
    assert registry.asked == [("topics_named", "winter")]


def test_a_failed_search_says_so_rather_than_finding_nothing():
    view = _service(TopicRegistry(failing=True)).named("winter")

    assert view.state is TopicState.UNAVAILABLE and view.topics == ()


@pytest.mark.parametrize("section", ["topic", "works", "artists"])
def test_an_address_that_is_not_a_qid_is_refused(section):
    with pytest.raises(ServiceError):
        getattr(_service(TopicRegistry()), section)("Q1 } UNION {")
