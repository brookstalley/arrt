"""What Library › Topics offers before anything is held, and how a topic's works reach the page without the wait.

`OFFERED_TOPICS` is listed on the index whether or not a work is in it, each
once: a held one under its count, never again beside it. Its kept answers are
warmed on the topic sweep's thread, a topic at a time, so the first open of the
16th century reads them rather than waiting on Wikidata; and a topic that is
not warm is yielded in stages, its works before their makers.
"""

import threading
import time

import pytest
from fakes import FakeRegistry, NothingWanted

from arrt.library.registry import (
    ItemId,
    RegistryCreator,
    RegistryText,
    RegistryTopic,
    RegistryTopicWork,
    RegistryTopicWorksStage,
    RegistryUnavailable,
    TopicKind,
)
from arrt.library.services.artists import REGISTRY_KEPT_FOR
from arrt.library.services.catalogue import FacetClaim
from arrt.library.services.topic_sweep import SOURCE_NOTE, TopicSweep, start_topic_sweep
from arrt.library.services.topics import OFFERED_TOPICS, TopicService, TopicState
from arrt.persistence.kept import KeptAnswers
from arrt.persistence.records import VocabularyKind

SIXTEENTH = "Q7017"
NINETEENTH = "Q6955"
IMPRESSIONISM = "Q40415"
BRUEGEL = RegistryCreator(qid=ItemId("Q43270"), name=RegistryText("Pieter Bruegel the Elder"))
HUNTERS = RegistryTopicWork(
    qid=ItemId("Q500985"), title=RegistryText("The Hunters in the Snow"), sitelinks=39, creators=(BRUEGEL,)
)


def _topic(offer) -> RegistryTopic:
    return RegistryTopic(qid=ItemId(offer.qid), label=RegistryText(offer.label), kinds=(offer.kind,))


class Registry:
    """Every offered topic known, each with one work, counting what it was asked; `refuse_at` fails that question on."""

    def __init__(self, *, refuse_at=None, staged=False):
        self.topics = {offer.qid: _topic(offer) for offer in OFFERED_TOPICS}
        self.asked: list[tuple[str, str]] = []
        self.refuse_at = refuse_at
        self.staged = staged
        self.makers_gate = threading.Event()

    def _ask(self, question, qid):
        self.asked.append((question, qid))
        if self.refuse_at is not None and len(self.asked) >= self.refuse_at:
            raise RegistryUnavailable("Wikidata answered HTTP 429.")

    def topic(self, qid):
        self._ask("topic", qid)
        return self.topics.get(qid)

    def topic_works(self, topic, *, limit):
        self._ask("topic_works", topic.qid)
        return [HUNTERS]

    def topic_works_in_stages(self, topic, *, limit):
        works = tuple(self.topic_works(topic, limit=limit))
        if self.staged:
            unnamed = tuple(RegistryTopicWork(work.qid, work.title, work.sitelinks) for work in works)
            yield RegistryTopicWorksStage(works=unnamed, complete=False)
            self._ask("makers", topic.qid)
        yield RegistryTopicWorksStage(works=works, complete=True)


class Store:
    def circulating_ids_by_qid(self):
        return {}

    def list_artists(self):
        return []


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def _service(registry, kept=None):
    return TopicService(Store(), registry, kept=kept or KeptAnswers.in_memory(), wanted=NothingWanted())


# -- the list itself ---------------------------------------------------------------


def test_the_centuries_run_from_the_13th_to_the_21st_and_the_movements_are_at_most_twelve():
    centuries = [offer.label for offer in OFFERED_TOPICS if offer.kind is TopicKind.PERIOD]
    movements = [offer for offer in OFFERED_TOPICS if offer.kind is TopicKind.MOVEMENT]

    assert centuries == [f"{n}{'st' if n == 21 else 'th'} century" for n in range(13, 22)]
    assert 0 < len(movements) <= 12
    assert {offer.kind for offer in OFFERED_TOPICS} == {TopicKind.PERIOD, TopicKind.MOVEMENT}
    qids = [offer.qid for offer in OFFERED_TOPICS]
    assert len(qids) == len(set(qids))


# -- the index ---------------------------------------------------------------------


class TestTheIndexOffers:
    @pytest.fixture
    def registry(self):
        return FakeRegistry(failing=True)

    def test_an_empty_library_is_offered_every_century_and_movement(self, services):
        index = services.topics.index()

        offered = {group.kind: [offer.qid for offer in group.offered] for group in index.groups}
        assert offered == {
            TopicKind.PERIOD: [offer.qid for offer in OFFERED_TOPICS if offer.kind is TopicKind.PERIOD],
            TopicKind.MOVEMENT: [offer.qid for offer in OFFERED_TOPICS if offer.kind is TopicKind.MOVEMENT],
            TopicKind.SUBJECT: [],
            TopicKind.MEDIUM: [],
        }
        assert SIXTEENTH in offered[TopicKind.PERIOD]

    def test_a_held_topic_is_listed_once_with_its_count_and_not_offered(self, services, service):
        work = service.add_artwork(title="Impression, Sunrise")
        service.replace_sourced_facets(
            work.id,
            source_note=SOURCE_NOTE,
            claims=(
                FacetClaim(kind=VocabularyKind.ERA, value="19th century", value_qid=NINETEENTH),
                # Held as a subject here, and offered as a movement: by QID it is the same topic.
                FacetClaim(kind=VocabularyKind.SUBJECT, value="Impressionism", value_qid=IMPRESSIONISM),
            ),
        )

        groups = {group.kind: group for group in services.topics.index().groups}

        assert [topic.qid for topic in groups[TopicKind.PERIOD].topics] == [NINETEENTH]
        assert NINETEENTH not in [offer.qid for offer in groups[TopicKind.PERIOD].offered]
        assert SIXTEENTH in [offer.qid for offer in groups[TopicKind.PERIOD].offered]
        assert IMPRESSIONISM not in [offer.qid for group in groups.values() for offer in group.offered]
        everything = [topic.qid for group in groups.values() for topic in (*group.topics, *group.offered)]
        assert everything.count(NINETEENTH) == 1


def test_without_a_registry_nothing_is_offered(services):
    """Every page an offer opened would say only that topics need Wikidata."""
    index = services.topics.index()

    assert index.state is TopicState.NOT_CONFIGURED
    assert all(group.offered == () for group in index.groups)


# -- the works, in stages ----------------------------------------------------------


def test_a_topic_not_kept_yields_its_works_before_their_makers_and_keeps_only_the_whole():
    registry = Registry(staged=True)
    service = _service(registry)
    stages = service.works_in_stages(SIXTEENTH)

    first = next(stages)
    assert ("makers", SIXTEENTH) not in registry.asked
    assert (first.state, first.complete, [entry.work.qid for entry in first.works]) == (TopicState.KNOWN, False, [HUNTERS.qid])
    assert first.works[0].work.creators == ()

    last = next(stages)
    assert last.complete is True
    assert last.works[0].work.creators == (BRUEGEL,)
    assert next(stages, None) is None

    # Kept whole: the next visit is one complete view, and asks nothing.
    registry.asked.clear()
    assert [(view.complete, view.works[0].work.creators) for view in service.works_in_stages(SIXTEENTH)] == [(True, (BRUEGEL,))]
    assert registry.asked == []


def test_a_topic_whose_makers_fail_ends_unavailable_and_keeps_nothing():
    registry = Registry(staged=True, refuse_at=3)  # topic, works, then the makers' question
    service = _service(registry)

    views = list(service.works_in_stages(SIXTEENTH))

    assert [(view.state, view.complete) for view in views] == [(TopicState.KNOWN, False), (TopicState.UNAVAILABLE, True)]
    registry.refuse_at = None
    registry.asked.clear()
    list(service.works_in_stages(SIXTEENTH))
    assert ("topic_works", SIXTEENTH) in registry.asked


# -- warming -----------------------------------------------------------------------


def test_a_warmed_topic_opens_without_asking_wikidata_again():
    registry = Registry(staged=True)
    service = _service(registry)

    warming = service.warm_offered()
    assert (warming.warmed, warming.fresh, warming.stopped) == (len(OFFERED_TOPICS), 0, False)
    # One topic at a time, in the list's order: its item, then its works.
    assert registry.asked == [(question, offer.qid) for offer in OFFERED_TOPICS for question in ("topic", "topic_works")]

    registry.asked.clear()
    views = list(service.works_in_stages(SIXTEENTH))
    assert [(view.complete, [entry.work.qid for entry in view.works]) for view in views] == [(True, [HUNTERS.qid])]
    assert service.topic(SIXTEENTH).known == registry.topics[SIXTEENTH]
    assert registry.asked == []


def test_a_fresh_entry_is_skipped_and_a_stale_one_asked_again():
    clock = Clock()
    registry = Registry()
    service = _service(registry, kept=KeptAnswers.in_memory(clock=clock))
    service.warm_offered()

    registry.asked.clear()
    clock.now += REGISTRY_KEPT_FOR.total_seconds() - 60
    fresh = service.warm_offered()
    assert (fresh.warmed, fresh.fresh) == (0, len(OFFERED_TOPICS))
    assert registry.asked == []

    clock.now += 120
    stale = service.warm_offered()
    assert (stale.warmed, stale.fresh) == (len(OFFERED_TOPICS), 0)
    assert ("topic_works", SIXTEENTH) in registry.asked


def test_a_topic_a_curator_opened_is_fresh_and_not_asked_for_by_the_warming():
    registry = Registry()
    service = _service(registry)
    service.works(SIXTEENTH)

    registry.asked.clear()
    warming = service.warm_offered()

    assert warming.fresh == 1
    assert not [asked for asked in registry.asked if asked[1] == SIXTEENTH]


def test_an_unavailable_registry_stops_the_pass():
    registry = Registry(refuse_at=4)  # the first topic's two questions answer; the second's works are refused
    service = _service(registry)

    warming = service.warm_offered()

    assert (warming.warmed, warming.stopped) == (1, True)
    assert warming.reason == "Wikidata answered HTTP 429."
    assert len(registry.asked) == 4
    # The next pass asks for what this one did not reach, and not the one it did.
    registry.refuse_at = None
    registry.asked.clear()
    after = service.warm_offered()
    assert (after.warmed, after.fresh, after.stopped) == (len(OFFERED_TOPICS) - 1, 1, False)
    assert ("topic", OFFERED_TOPICS[0].qid) not in registry.asked


def test_nothing_is_asked_when_the_sweep_is_off():
    """No registry, so the sweep starts no thread; and its warming, called anyway, asks nothing."""
    registry = Registry()
    asked_with = _service(registry)
    sweep = TopicSweep(store=None, catalogue=None, registry=None, warm=asked_with.warm_offered)

    warming = sweep.warm()

    assert (warming.warmed, warming.fresh, warming.stopped) == (0, 0, False)
    assert registry.asked == []
    assert _service(None).warm_offered().warmed == 0


class TestTheSweepWarms:
    @pytest.fixture
    def registry(self):
        offer = next(offer for offer in OFFERED_TOPICS if offer.qid == SIXTEENTH)
        return FakeRegistry(topics={SIXTEENTH: _topic(offer)}, topic_works={SIXTEENTH: [HUNTERS]})

    def test_the_containers_sweep_warms_the_offered_topics_and_logs_one_line(self, services, registry, caplog):
        caplog.set_level("INFO", logger="arrt.library.services.topic_sweep")

        services.topic_sweep.warm()

        assert ("works", SIXTEENTH) in registry.topic_sections_asked
        lines = [record for record in caplog.records if getattr(record, "event", None) == "topics.warmed"]
        assert len(lines) == 1
        # The fake knows one offered item; the rest are not items, and are counted as asked, not fresh.
        assert (lines[0].warmed, lines[0].fresh, lines[0].stopped_early) == (len(OFFERED_TOPICS), 0, False)

        registry.topic_sections_asked.clear()
        list(services.topics.works_in_stages(SIXTEENTH))
        assert registry.topic_sections_asked == []

    def test_the_running_sweep_warms_after_its_pass(self, services, registry):
        halt = start_topic_sweep(services.topic_sweep)
        try:
            deadline = time.monotonic() + 5
            while ("works", SIXTEENTH) not in registry.topic_sections_asked:
                assert time.monotonic() < deadline, "the sweep's thread never warmed the offered topics"
                time.sleep(0.01)
        finally:
            halt()
