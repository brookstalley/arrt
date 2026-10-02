"""The topic sweep: the library's works' topics as facet rows, replaced and never merely added.

A work's own QID gives its century, subjects and kind of work; its artist's QID
gives the artist's movements. Each lands as a `sourced` facet with `source_note` "Wikidata" and the
topic's QID beside the label. Driven against `FakeRegistry` through the services
the entry point wires, so the sweep under test is the one the container builds.
"""

import logging
import threading
import time

import pytest
from fakes import FakeRegistry

from arrt.library.registry import ItemId, RegistryText, RegistryTopicRef, TopicKind
from arrt.library.services.topic_sweep import (
    SOURCE_NOTE,
    TOPIC_SWEEP_THREAD_NAME,
    TopicSweep,
    start_topic_sweep,
)
from arrt.persistence.records import FacetDerivation, VocabularyKind

HUNTERS = "Q500985"
ROTHKO_WORK = "Q20270685"
BRUEGEL = "Q43270"
ROTHKO = "Q160149"


def ref(qid: str, label: str, kind: TopicKind) -> RegistryTopicRef:
    return RegistryTopicRef(qid=ItemId(qid), label=RegistryText(label), kind=kind)


C16 = ref("Q7017", "16th century", TopicKind.PERIOD)
C20 = ref("Q6927", "20th century", TopicKind.PERIOD)
WINTER = ref("Q1311", "winter", TopicKind.SUBJECT)
LANDSCAPE = ref("Q191163", "landscape art", TopicKind.SUBJECT)
PAINTING = ref("Q3305213", "painting", TopicKind.MEDIUM)
NORTHERN = ref("Q1474884", "Northern Renaissance", TopicKind.MOVEMENT)
ABEX = ref("Q103985", "abstract expressionism", TopicKind.MOVEMENT)
COLOR_FIELD = ref("Q1094916", "color field painting", TopicKind.MOVEMENT)


@pytest.fixture
def registry():
    return FakeRegistry(
        work_topics={HUNTERS: [C16, WINTER, PAINTING], ROTHKO_WORK: [C20, PAINTING]},
        artist_topics={BRUEGEL: [NORTHERN], ROTHKO: [ABEX, COLOR_FIELD]},
    )


@pytest.fixture
def sweep(services) -> TopicSweep:
    return services.topic_sweep


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def timed(store, service, registry, clock) -> TopicSweep:
    """A sweep over the same catalogue whose clock the test moves, with an interval of 100 seconds."""
    return TopicSweep(store, service, registry, interval_seconds=100, clock=clock)


@pytest.fixture
def bruegel(service, services):
    artist = service.add_artist(name="Pieter Bruegel the Elder")
    services.identity.set_artist_identity(artist.id, BRUEGEL)
    return artist


def rows(service, work_id):
    """A work's facets as (kind, value, derivation, source_note, value_qid), in the store's order."""
    return [(str(f.kind), f.value, str(f.derivation), f.source_note, f.value_qid) for f in service.facets_for(work_id)]


class TestWhatASweepWrites:
    def test_one_sourced_row_per_work_kind_and_value_with_the_topics_qid(self, sweep, service, bruegel):
        hunters = service.add_artwork(title="The Hunters in the Snow", artist_id=bruegel.id, wikidata_qid=HUNTERS)

        sweep.run()

        assert sorted(rows(service, hunters.id)) == sorted(
            [
                ("era", "16th century", "sourced", "Wikidata", "Q7017"),
                ("subject", "winter", "sourced", "Wikidata", "Q1311"),
                ("medium", "painting", "sourced", "Wikidata", "Q3305213"),
                ("movement", "Northern Renaissance", "sourced", "Wikidata", "Q1474884"),
            ]
        )

    def test_a_work_with_no_qid_whose_artist_has_one_gets_movements_only(self, sweep, service, services, registry):
        rothko = service.add_artist(name="Mark Rothko")
        services.identity.set_artist_identity(rothko.id, ROTHKO)
        unmatched = service.add_artwork(title="Untitled", artist_id=rothko.id)

        sweep.run()

        assert {(kind, value) for kind, value, *_ in rows(service, unmatched.id)} == {
            ("movement", "abstract expressionism"),
            ("movement", "color field painting"),
        }
        # Asked about the artist and nothing about the work, which has no item.
        assert registry.topics_asked == [((), (ROTHKO,))]

    def test_a_work_with_no_qid_and_no_artist_qid_asks_nothing_and_gets_nothing(self, sweep, service, registry):
        lone = service.add_artwork(title="Anonymous")

        result = sweep.run()

        assert rows(service, lone.id) == []
        assert registry.topics_asked == []
        assert (result.due, result.asked) == (1, 0)

    def test_two_items_of_one_kind_with_one_name_are_one_value_the_first_kept(self, sweep, service, registry):
        """The store holds a value once per work; the QID beside it must not flip between passes."""
        registry.work_topics[HUNTERS] = [WINTER, ref("Q99999", "Winter", TopicKind.SUBJECT)]
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)

        sweep.run()

        assert rows(service, hunters.id) == [("subject", "winter", "sourced", "Wikidata", "Q1311")]


class TestASecondAnswerReplacesTheFirst:
    def test_a_changed_answer_replaces_rather_than_adds(self, timed, clock, service, registry):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        timed.run()
        registry.work_topics[HUNTERS] = [C16, LANDSCAPE]
        clock.now += 100

        result = timed.run()

        assert sorted((kind, value) for kind, value, *_ in rows(service, hunters.id)) == [
            ("era", "16th century"),
            ("subject", "landscape art"),
        ]
        assert (result.withdrawn, result.written) == (3, 2)

    def test_an_inferred_row_survives_a_sweep_and_keeps_its_derivation(self, timed, clock, service, registry):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        # One inferred value the registry also gives, and one it does not.
        service.record_facet(
            artwork_id=hunters.id, kind=VocabularyKind.SUBJECT, value="Winter", derivation=FacetDerivation.INFERRED
        )
        service.record_facet(
            artwork_id=hunters.id, kind=VocabularyKind.SUBJECT, value="hunting", derivation=FacetDerivation.INFERRED
        )
        # Inferred by reading Wikidata, and noted so: the note alone must not
        # make an inferred row the sweep's to replace.
        service.record_facet(
            artwork_id=hunters.id,
            kind=VocabularyKind.MEDIUM,
            value="oil on panel",
            derivation=FacetDerivation.INFERRED,
            source_note=SOURCE_NOTE,
        )

        timed.run()
        # The registry's "winter" did not relabel the inferred "Winter" as sourced.
        assert [row for row in rows(service, hunters.id) if row[0] == "subject"] == [
            ("subject", "hunting", "inferred", None, None),
            ("subject", "Winter", "inferred", None, None),
        ]
        registry.work_topics[HUNTERS] = []
        clock.now += 100
        timed.run()

        assert sorted(rows(service, hunters.id)) == [
            ("medium", "oil on panel", "inferred", "Wikidata", None),
            ("subject", "Winter", "inferred", None, None),
            ("subject", "hunting", "inferred", None, None),
        ]

    def test_a_row_another_source_published_is_left_alone(self, sweep, service):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        service.record_facet(
            artwork_id=hunters.id,
            kind=VocabularyKind.MEDIUM,
            value="oil paintings (visual works)",
            derivation=FacetDerivation.SOURCED,
            source_note="artic:classification_title",
        )

        sweep.run()

        assert ("medium", "oil paintings (visual works)", "sourced", "artic:classification_title", None) in rows(
            service, hunters.id
        )

    def test_a_cleared_qid_takes_the_works_rows_away_without_asking(self, sweep, service, services, registry):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        sweep.run()
        services.identity.set_work_identity(hunters.id, None)

        sweep.run()

        assert rows(service, hunters.id) == []
        assert len(registry.topics_asked) == 1


class TestWhichWorksAPassAsksAbout:
    def test_an_unchanged_work_inside_the_interval_is_not_asked_again(self, sweep, service, registry):
        service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        sweep.run()

        result = sweep.run()

        assert (result.due, len(registry.topics_asked)) == (0, 1)

    def test_a_work_whose_qid_changed_is_asked_again_alone(self, sweep, service, services, registry):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        service.add_artwork(title="Untitled (Purple)", wikidata_qid=ROTHKO_WORK)
        sweep.run()

        services.identity.set_work_identity(hunters.id, ROTHKO_WORK)
        sweep.run()

        assert registry.topics_asked[-1] == ((ROTHKO_WORK,), ())
        assert {value for _, value, *_ in rows(service, hunters.id)} == {"20th century", "painting"}

    def test_an_artist_whose_qid_changed_has_their_works_asked_again(self, sweep, service, services, bruegel, registry):
        service.add_artwork(title="The Hunters in the Snow", artist_id=bruegel.id, wikidata_qid=HUNTERS)
        sweep.run()

        services.identity.set_artist_identity(bruegel.id, ROTHKO)
        sweep.run()

        assert registry.topics_asked[-1] == ((HUNTERS,), (ROTHKO,))

    def test_a_work_older_than_the_interval_is_asked_again(self, timed, clock, service):
        service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        timed.run()
        clock.now += 99
        assert timed.run().due == 0

        clock.now += 1

        assert timed.run().due == 1

    def test_an_outage_replaces_nothing_and_the_next_pass_asks_again(self, timed, clock, service, registry):
        hunters = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        timed.run()
        before = rows(service, hunters.id)
        registry.work_topics[HUNTERS] = [C16]
        clock.now += 100
        registry.failing = True

        result = timed.run()

        assert result.unavailable is True
        assert rows(service, hunters.id) == before
        # Not remembered as asked, so the very next pass asks again.
        registry.failing = False
        assert timed.run().due == 1
        assert [value for _, value, *_ in rows(service, hunters.id)] == ["16th century"]


class TestWithNoRegistry:
    @pytest.fixture
    def registry(self):
        return None

    def test_a_pass_does_nothing(self, sweep, service):
        work = service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)

        assert sweep.run().due == 0
        assert rows(service, work.id) == []

    def test_starting_it_says_topics_are_off_once_and_starts_no_thread(self, sweep, caplog):
        with caplog.at_level(logging.INFO, logger="arrt.library.services.topic_sweep"):
            halt = start_topic_sweep(sweep)
            sweep.nudge()
            sweep.run()
            halt()

        off = [record for record in caplog.records if getattr(record, "event", None) == "topics.off"]
        assert len(off) == 1
        assert "WIKIDATA_USER_AGENT" in off[0].getMessage()
        assert [record for record in caplog.records if record is not off[0]] == []
        assert TOPIC_SWEEP_THREAD_NAME not in {thread.name for thread in threading.enumerate()}


class TestTheRunningSweep:
    """The thread the application starts: a pass at once, then a pass whenever the library changes."""

    def test_it_sweeps_at_start_and_again_after_an_acceptance_and_a_qid_change_to_a_work_or_an_artist(
        self, sweep, service, services, registry
    ):
        service.add_artwork(title="The Hunters in the Snow", wikidata_qid=HUNTERS)
        rothko = service.add_artist(name="Mark Rothko")
        service.add_artwork(title="Untitled", artist_id=rothko.id)
        halt = start_topic_sweep(sweep)
        try:
            until(lambda: len(registry.topics_asked) == 1)
            assert registry.topics_asked == [((HUNTERS,), ())]

            # The interval is a day, so only the acceptance can have woken it.
            purple = service.add_artwork(title="Untitled (Purple)", wikidata_qid=ROTHKO_WORK)
            until(lambda: len(registry.topics_asked) == 2)
            assert registry.topics_asked[1] == ((ROTHKO_WORK,), ())

            services.identity.set_work_identity(purple.id, HUNTERS)
            until(lambda: len(registry.topics_asked) == 3)
            assert registry.topics_asked[2] == ((HUNTERS,), ())

            # A work with no QID is asked about through its artist's, so
            # matching the artist is a change the sweep must hear of too. The
            # work was there before the sweep started, so only the match can
            # have woken it.
            services.identity.set_artist_identity(rothko.id, ROTHKO)
            until(lambda: len(registry.topics_asked) == 4)
            assert registry.topics_asked[3] == ((), (ROTHKO,))
        finally:
            halt()
        assert TOPIC_SWEEP_THREAD_NAME not in {thread.name for thread in threading.enumerate()}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def until(condition, *, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the sweep did not get there in time")
        time.sleep(0.01)
