"""The acquisition queue: every accepted work that holds no image is fetched, then prepared.

Two kinds of test, for two kinds of claim. The first class drives the queue the
container builds, started by the application as the entry point starts it, over
a transport serving canned bytes: acceptance must end with a work that can go on
a wall, and nothing else in the suite would notice if the wiring between them
were missing. The rest drive a queue over the same catalogue with doubles behind
`acquire` and `prepare` and a clock the test moves, because the policy (retries,
giving up, partial results, the pause) is about outcomes no transport double
produces on demand and about days no test can wait.
"""

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from arrt.app import create_app
from arrt.library.acquisition.dezoomify import DezoomifyUnavailable
from arrt.library.acquisition.preparation import PreparationOutcome, PreparationResult
from arrt.library.acquisition.queue import (
    ACQUISITION_QUEUE_THREAD_NAME,
    GIVE_UP_AFTER,
    IDLE_SECONDS,
    PAUSED_RETRY_SECONDS,
    AcquisitionPhase,
    AcquisitionQueue,
    run_acquisition_queue,
    start_acquisition_queue,
)
from arrt.library.acquisition.service import AcquisitionOutcome, AcquisitionResult
from arrt.library.acquisition.space import NotEnoughSpace
from arrt.library.events import WorkChange
from arrt.library.readiness import PlayableWork
from arrt.persistence.discovery_records import Verdict
from arrt.persistence.records import AcquisitionMethod, FetchStatus, QueuedAcquisition, RightsStatus, SourceClass
from arrt.services.errors import ServiceError

_A_MOMENT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


def _jpeg(width: int = 1600, height: int = 1200) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (70, 50, 120)).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


class Clock:
    def __init__(self) -> None:
        self.now = _A_MOMENT

    def __call__(self) -> datetime:
        return self.now


def until(condition, *, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the queue did not get there in time")
        time.sleep(0.01)


def _queue_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == ACQUISITION_QUEUE_THREAD_NAME and thread.is_alive()]


# -- through the container, as the entry point starts it -----------------------


@pytest.fixture
def open_stream():
    """A museum serving one decodable image for every URL, and counting the requests."""
    served: list[str] = []

    @contextmanager
    def _open(url: str):
        served.append(url)
        yield iter([_jpeg()])

    _open.served = served
    return _open


def _accept_a_direct_work(discovery, run, title="The Persistence of Memory"):
    """Propose, find one directly fetchable image, and accept: what a curator's Accept does."""
    work = discovery.propose_work(
        run_id=run.id, proposed_title=title, rationale="The intent asked for it.", work_dedup_key=title.lower()
    )
    discovery.record_image(
        candidate_work_id=work.id,
        url=f"https://gallery.example.com/{title.replace(' ', '-').lower()}.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        confidence=0.9,
    )
    discovery.record_resolution(work.id)
    return discovery.set_verdict(work.id, Verdict.ACCEPTED).work.artwork_id


class TestThroughTheApplication:
    async def test_an_accepted_work_is_fetched_prepared_and_can_go_on_a_wall(self, services, discovery, run, open_stream):
        app = create_app(services, acquire_queue=True)

        async with app.router.lifespan_context(app):
            artwork_id = _accept_a_direct_work(discovery, run)
            until(lambda: isinstance(services.library.playable([artwork_id])[artwork_id], PlayableWork))
            until(lambda: services.acquisition_queue.state_of([artwork_id]) == {})

        assert len(open_stream.served) == 1

    async def test_a_work_accepted_while_the_queue_was_stopped_is_fetched_at_the_next_start(
        self, services, discovery, run, open_stream
    ):
        artwork_id = _accept_a_direct_work(discovery, run)
        assert open_stream.served == [], "nothing should fetch before the queue is started"
        app = create_app(services, acquire_queue=True)

        async with app.router.lifespan_context(app):
            until(lambda: isinstance(services.library.playable([artwork_id])[artwork_id], PlayableWork))

    async def test_an_application_not_asked_to_starts_no_queue(self, services, discovery, run, open_stream):
        app = create_app(services)

        async with app.router.lifespan_context(app):
            _accept_a_direct_work(discovery, run)
            assert not _queue_threads()

        assert open_stream.served == []

    async def test_the_queue_stops_when_the_application_does(self, services):
        app = create_app(services, acquire_queue=True)

        async with app.router.lifespan_context(app):
            # Pinned from both sides: a renamed thread would make the check after
            # the block pass vacuously.
            assert _queue_threads(), "no thread by that name was running, so the assertion below would pass vacuously"

        assert not _queue_threads()


# -- the policy, over doubles and a clock the test moves -------------------------


@dataclass
class FakeAcquisition:
    """Stands where `AcquisitionService.acquire` does, recording an original when it succeeds.

    `answers` is consumed in order; when it runs out every fetch succeeds. An
    answer is an `AcquisitionOutcome` or an exception to raise.
    """

    service: object
    answers: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    gate: threading.Event | None = None
    in_flight: int = 0
    most_in_flight: int = 0

    def acquire(self, artwork_id, *, source_id=None):
        self.calls.append((artwork_id, source_id))
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            if self.gate is not None:
                assert self.gate.wait(10), "the test never released the fetch"
            answer = self.answers.pop(0) if self.answers else AcquisitionOutcome.ACQUIRED
            if isinstance(answer, Exception):
                raise answer
            source = self.service.list_sources(artwork_id)[0]
            if answer in (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.PARTIAL):
                self.service.record_original(
                    artwork_id=artwork_id,
                    source_id=source.id,
                    path=f"raw/{artwork_id}.jpg",
                    width=4000,
                    height=3000,
                    byte_size=1_000,
                    content_hash=f"hash-{len(self.calls)}",
                    fetch_status=FetchStatus.OK if answer is AcquisitionOutcome.ACQUIRED else FetchStatus.PARTIAL_TILES,
                )
            return AcquisitionResult(artwork_id=artwork_id, source_id=source.id, outcome=answer, detail=f"a {answer.value} fetch")
        finally:
            self.in_flight -= 1


@dataclass
class FakePreparation:
    """Stands where `PreparationService.prepare` does. `failures` refusals come first."""

    failures: int = 0
    calls: list = field(default_factory=list)

    def prepare(self, artwork_id, *, force=False):  # noqa: ARG002 - the queue never forces
        self.calls.append(artwork_id)
        if self.failures:
            self.failures -= 1
            raise ServiceError("the canvas would not encode")
        return PreparationResult(
            artwork_id=artwork_id, outcome=PreparationOutcome.PREPARED, detail="composed", mat_hex="#202020", mat_method="manual"
        )


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def fetcher(service):
    return FakeAcquisition(service)


@pytest.fixture
def preparer():
    return FakePreparation()


@pytest.fixture
def queue(store, service, fetcher, preparer, clock) -> AcquisitionQueue:
    return AcquisitionQueue(store, service, fetcher, preparer, clock=clock)


@pytest.fixture
def work(service):
    """An accepted work with one primary source and no image: what acceptance leaves."""

    def _work(title="Nighthawks"):
        artwork = service.add_artwork(title=title)
        service.add_source(
            artwork_id=artwork.id,
            url=f"https://gallery.example.com/{artwork.id}.jpg",
            provider="gallery_site",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
            is_primary=True,
        )
        return artwork.id

    return _work


def _phase(queue, artwork_id):
    return queue.state_of([artwork_id])[artwork_id].phase


class TestAPass:
    def test_it_fetches_then_prepares_and_then_owes_the_work_nothing(self, queue, work, fetcher, preparer, store):
        artwork_id = work()
        assert _phase(queue, artwork_id) is AcquisitionPhase.QUEUED

        result = queue.run()

        assert (result.due, result.acquired) == (1, 1)
        assert fetcher.calls == [(artwork_id, None)]
        assert preparer.calls == [artwork_id]
        assert queue.state_of([artwork_id]) == {}
        assert store.get_queued_acquisition(artwork_id) is None

    def test_works_are_taken_oldest_acceptance_first(self, queue, work, fetcher):
        first, second, third = work("One"), work("Two"), work("Three")

        queue.run()

        assert [artwork_id for artwork_id, _ in fetcher.calls] == [first, second, third]

    def test_a_work_holding_an_image_is_not_fetched(self, queue, ready_work, fetcher, preparer):
        ready_work()

        assert queue.run().due == 0
        assert fetcher.calls == preparer.calls == []

    def test_an_archived_work_is_not_fetched_and_has_no_state(self, queue, work, service, fetcher):
        artwork_id = work()
        service.archive_artwork(artwork_id)

        assert queue.run().due == 0
        assert fetcher.calls == []
        assert queue.state_of([artwork_id]) == {}

    def test_a_partial_result_counts_as_acquired_and_is_not_retried(self, queue, work, fetcher, preparer, clock):
        artwork_id = work()
        fetcher.answers = [AcquisitionOutcome.PARTIAL]

        assert queue.run().acquired == 1
        clock.now += timedelta(days=30)

        assert queue.run().due == 0
        assert len(fetcher.calls) == 1
        assert preparer.calls == [artwork_id]

    def test_every_pass_is_logged_at_info_even_with_nothing_to_do(self, queue, caplog):
        with caplog.at_level(logging.INFO, logger="arrt.library.acquisition.queue"):
            queue.run()

        passes = [record for record in caplog.records if getattr(record, "event", None) == "acquisition.queue_pass"]
        assert len(passes) == 1
        assert passes[0].levelno == logging.INFO


class TestFailuresAndRetries:
    def test_a_failure_is_retried_after_an_hour_a_day_and_three_days_then_given_up(self, queue, work, fetcher, clock, caplog):
        artwork_id = work()
        fetcher.answers = [AcquisitionOutcome.FAILED] * GIVE_UP_AFTER
        started = clock.now

        for waited, due_after in (
            (timedelta(0), timedelta(hours=1)),
            (timedelta(hours=1), timedelta(days=1)),
            (timedelta(days=1), timedelta(days=3)),
        ):
            clock.now += waited
            assert queue.run().failed == 1
            state = queue.state_of([artwork_id])[artwork_id]
            assert state.phase is AcquisitionPhase.FAILED
            assert state.next_try_at == clock.now + due_after
            assert state.detail == "a failed fetch"
            # Not a moment before.
            clock.now += due_after - timedelta(seconds=1)
            assert queue.run().due == 0
            clock.now -= due_after - timedelta(seconds=1)

        clock.now += timedelta(days=3)
        with caplog.at_level(logging.WARNING, logger="arrt.library.acquisition.queue"):
            assert queue.run().gave_up == 1

        state = queue.state_of([artwork_id])[artwork_id]
        assert (state.phase, state.failures, state.detail) == (AcquisitionPhase.GAVE_UP, 4, "a failed fetch")
        assert [
            record.artwork_id for record in caplog.records if getattr(record, "event", None) == "acquisition.queue_gave_up"
        ] == [artwork_id]
        clock.now = started + timedelta(days=365)
        assert queue.run().due == 0
        assert len(fetcher.calls) == GIVE_UP_AFTER

    def test_a_refusal_about_the_work_is_a_failure_with_its_reason(self, queue, service, fetcher):
        """No source to fetch from is the work's problem, not the deployment's, so it counts."""
        artwork_id = service.add_artwork(title="Sourceless").id
        fetcher.answers = [ServiceError(f"Artwork {artwork_id!r} has no source to acquire from.")]

        assert queue.run().failed == 1
        assert "no source to acquire from" in queue.state_of([artwork_id])[artwork_id].detail

    def test_a_preparation_that_fails_is_retried_by_preparing_alone(self, queue, work, fetcher, preparer, clock):
        artwork_id = work()
        preparer.failures = 1

        assert queue.run().failed == 1
        state = queue.state_of([artwork_id])[artwork_id]
        assert state.phase is AcquisitionPhase.FAILED
        assert "could not be prepared" in state.detail
        clock.now += timedelta(hours=1)

        assert queue.run().acquired == 1
        assert len(fetcher.calls) == 1, "the held image was fetched again"
        assert preparer.calls == [artwork_id, artwork_id]
        assert queue.state_of([artwork_id]) == {}

    def test_a_success_after_failures_clears_them(self, queue, work, fetcher, clock, store):
        artwork_id = work()
        fetcher.answers = [AcquisitionOutcome.FAILED, AcquisitionOutcome.FAILED]
        queue.run()
        clock.now += timedelta(hours=1)
        queue.run()
        clock.now += timedelta(days=1)

        assert queue.run().acquired == 1
        assert store.get_queued_acquisition(artwork_id) is None


class TestRetry:
    def test_retry_forgets_the_failures_and_the_next_pass_takes_it_first(self, queue, work, fetcher, store):
        older = work("Accepted first")
        retried = work("Given up on")
        store.set_queued_acquisition(QueuedAcquisition(artwork_id=retried, failures=GIVE_UP_AFTER, detail="gone"))
        assert _phase(queue, retried) is AcquisitionPhase.GAVE_UP

        state = queue.retry(retried)
        result = queue.run()

        assert (state.phase, state.failures, state.detail) == (AcquisitionPhase.QUEUED, 0, None)
        assert result.acquired == 2
        assert [artwork_id for artwork_id, _ in fetcher.calls] == [retried, older]

    def test_retry_never_fetches_in_the_call(self, queue, work, fetcher):
        artwork_id = work()

        queue.retry(artwork_id)

        assert fetcher.calls == []

    def test_a_named_source_is_used_for_the_next_fetch_even_for_a_work_holding_an_image(
        self, queue, ready_work, service, fetcher, preparer, store
    ):
        artwork_id = ready_work().id
        other = service.add_source(
            artwork_id=artwork_id,
            url="https://other.example.com/a.jpg",
            provider="other",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
            is_primary=False,
        )

        queue.retry(artwork_id, source_id=other.id)
        queue.run()

        assert fetcher.calls == [(artwork_id, other.id)]
        assert preparer.calls == [artwork_id]
        assert store.get_queued_acquisition(artwork_id) is None

    def test_a_named_source_fetched_once_is_not_fetched_again_when_preparation_fails(
        self, queue, ready_work, service, fetcher, preparer, clock
    ):
        """The retry after a failed preparation prepares the image the named source gave; it fetches nothing."""
        artwork_id = ready_work().id
        other = service.add_source(
            artwork_id=artwork_id,
            url="https://other.example.com/a.jpg",
            provider="other",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
            is_primary=False,
        )
        preparer.failures = 1

        queue.retry(artwork_id, source_id=other.id)
        assert queue.run().failed == 1
        clock.now += timedelta(hours=1)

        assert queue.run().acquired == 1
        assert fetcher.calls == [(artwork_id, other.id)], "the named source was fetched a second time"
        assert preparer.calls == [artwork_id, artwork_id]

    def test_a_source_of_another_work_is_refused(self, queue, work, service):
        artwork_id, stranger = work("One"), work("Two")
        [foreign] = service.list_sources(stranger)

        with pytest.raises(ServiceError, match="does not belong"):
            queue.retry(artwork_id, source_id=foreign.id)

    def test_an_archived_work_is_refused(self, queue, work, service):
        artwork_id = work()
        service.archive_artwork(artwork_id)

        with pytest.raises(ServiceError, match="archived"):
            queue.retry(artwork_id)


class TestThePause:
    def test_a_short_disk_pauses_without_counting_an_attempt_and_resumes_when_space_returns(
        self, queue, work, fetcher, store, caplog
    ):
        first, second = work("One"), work("Two")
        fetcher.answers = [NotEnoughSpace("3.1 GB free, 4 GB wanted")]

        with caplog.at_level(logging.WARNING, logger="arrt.library.acquisition.queue"):
            result = queue.run()

        assert result.paused is not None and result.paused.condition == "NotEnoughSpace"
        # The pass stopped: the second work was not tried against the same disk.
        assert [artwork_id for artwork_id, _ in fetcher.calls] == [first]
        state = queue.state_of([first])[first]
        assert (state.phase, state.failures, state.condition) == (AcquisitionPhase.PAUSED, 0, "NotEnoughSpace")
        assert state.detail == "3.1 GB free, 4 GB wanted"
        assert queue.state_of([second])[second].phase is AcquisitionPhase.PAUSED
        assert [
            record.condition for record in caplog.records if getattr(record, "event", None) == "acquisition.queue_paused"
        ] == ["NotEnoughSpace"]

        # Space returns: the next pass needs no clock movement, since no attempt was counted.
        result = queue.run()

        assert (result.paused, result.acquired) == (None, 2)
        assert queue.pause is None
        assert store.get_queued_acquisition(first) is None

    @pytest.mark.parametrize("fault", [NotEnoughSpace("short"), DezoomifyUnavailable("no dezoomify-rs on PATH")])
    def test_every_deployment_fault_pauses_rather_than_failing_the_work(self, queue, work, fetcher, fault):
        artwork_id = work()
        fetcher.answers = [fault]

        queue.run()

        assert queue.pause is not None and queue.pause.condition == type(fault).__name__
        assert queue.state_of([artwork_id])[artwork_id].failures == 0

    def test_a_paused_queue_tries_again_within_a_quarter_of_an_hour(self, queue, work, fetcher):
        work()
        fetcher.answers = [NotEnoughSpace("short")]
        queue.run()

        assert queue._seconds_until_due() == PAUSED_RETRY_SECONDS

    def test_a_failed_work_wakes_the_queue_when_its_retry_is_due(self, queue, work, fetcher, clock):
        """The running worker sleeps until the next retry, not for a day: this is what makes 1 h happen."""
        work()
        fetcher.answers = [AcquisitionOutcome.FAILED]
        queue.run()
        clock.now += timedelta(minutes=10)

        assert queue._seconds_until_due() == pytest.approx(50 * 60)

    def test_with_nothing_owed_the_queue_sleeps_for_the_idle_interval(self, queue):
        assert queue.run().due == 0

        assert queue._seconds_until_due() == IDLE_SECONDS

    def test_a_work_given_up_on_never_wakes_the_queue(self, queue, work, store, clock):
        artwork_id = work()
        store.set_queued_acquisition(
            QueuedAcquisition(
                artwork_id=artwork_id, failures=GIVE_UP_AFTER, next_try_at=clock.now + timedelta(minutes=5), detail="gone"
            )
        )

        assert queue._seconds_until_due() == IDLE_SECONDS

    def test_an_unexpected_error_from_one_work_counts_against_it_and_the_next_is_still_fetched(self, queue, work, fetcher, clock):
        """One work that always raises must not hold every work behind it, and must not spin.

        Counted as that work's failure, it waits an hour like any other, and the
        pass carries on to the work behind it. A pause here would have left it
        first in line, met again on every pass.
        """
        failing, behind = work("Raises"), work("Behind it")
        fetcher.answers = [OSError("disk I/O error")]

        result = queue.run()

        assert (result.failed, result.acquired) == (1, 1)
        assert queue.pause is None
        state = queue.state_of([failing])[failing]
        assert state.phase is AcquisitionPhase.FAILED
        assert "OSError" in state.detail and "disk I/O error" in state.detail
        assert state.next_try_at == clock.now + timedelta(hours=1)
        assert queue.state_of([behind]) == {}

    def test_an_error_outside_any_work_pauses_rather_than_spinning(self, queue, work, store, monkeypatch):
        """Nothing is in hand to blame, so the loop pauses: going straight back would raise as fast as it could log."""
        artwork_id = work()

        def broken():
            raise OSError("database disk image is malformed")

        monkeypatch.setattr(store, "works_to_acquire", broken)
        stop = threading.Event()

        def after_pass():
            stop.set()
            # Paused, the loop would otherwise wait a quarter of an hour before
            # it next looked at `stop`; a shutdown nudges it the same way.
            queue.nudge()

        run_acquisition_queue(queue, stop=stop, after_pass=after_pass)
        monkeypatch.undo()

        assert queue.pause is not None and queue.pause.condition == "OSError"
        assert queue.state_of([artwork_id])[artwork_id].phase is AcquisitionPhase.PAUSED


class TestTheListing:
    def test_the_work_being_fetched_leads_then_a_retry_then_oldest_acceptance(self, queue, work, clock):
        work("Accepted first")
        retried, fetching = work("Retried"), work("Being fetched")
        queue.retry(retried)
        # What the worker sets while it holds a work.
        queue._fetching = (fetching, clock.now)

        listing = queue.listing()

        assert [entry.title for entry in listing.entries] == ["Being fetched", "Retried", "Accepted first"]
        assert listing.entries[0].state.phase is AcquisitionPhase.FETCHING
        assert listing.pause is None


class TestTheWorkerSurvives:
    def test_an_error_while_waiting_pauses_rather_than_ending_the_thread(self, queue, work, monkeypatch, caplog):
        """Waiting reads the store; a failed read there must not end the worker silently."""
        work()
        failing_once = {"left": 1}
        real = queue._seconds_until_due

        def seconds():
            if failing_once["left"]:
                failing_once["left"] -= 1
                raise OSError("database disk image is malformed")
            return real()

        monkeypatch.setattr(queue, "_seconds_until_due", seconds)
        stop = threading.Event()
        passes = []

        def after_pass():
            passes.append(1)
            if len(passes) == 2:
                stop.set()
            # A paused wait would otherwise hold for a quarter of an hour.
            queue.nudge()

        run_acquisition_queue(queue, stop=stop, after_pass=after_pass)

        assert len(passes) == 2, "the worker ended after the failed wait instead of passing again"
        errors = [record for record in caplog.records if getattr(record, "event", None) == "acquisition.queue_error"]
        assert len(errors) == 1 and "could not wait" in errors[0].getMessage(), "the failed wait was not journalled"


class TestTheRunningQueue:
    def test_two_acceptances_during_a_fetch_are_both_fetched_one_at_a_time(self, store, service, work, preparer):
        gate = threading.Event()
        fetcher = FakeAcquisition(service, gate=gate)
        queue = AcquisitionQueue(store, service, fetcher, preparer)
        # As the container subscribes it: woken by acceptance alone.
        service.subscribe(lambda event: queue.nudge() if event.change is WorkChange.ACCEPTED else None)
        first = work("First")
        halt = start_acquisition_queue(queue)
        try:
            until(lambda: queue.state_of([first]).get(first) is not None and _phase(queue, first) is AcquisitionPhase.FETCHING)
            second, third = work("Second"), work("Third")
            assert _phase(queue, second) is AcquisitionPhase.QUEUED
            gate.set()
            until(lambda: len(preparer.calls) == 3)
        finally:
            halt()

        assert [artwork_id for artwork_id, _ in fetcher.calls] == [first, second, third]
        assert fetcher.most_in_flight == 1
        assert queue.state_of([first, second, third]) == {}
        assert not _queue_threads()

    def test_a_state_says_since_when_a_work_has_been_fetching(self, store, service, work, preparer, clock):
        gate = threading.Event()
        queue = AcquisitionQueue(store, service, FakeAcquisition(service, gate=gate), preparer, clock=clock)
        artwork_id = work()
        halt = start_acquisition_queue(queue)
        try:
            until(lambda: _phase(queue, artwork_id) is AcquisitionPhase.FETCHING)
            assert queue.state_of([artwork_id])[artwork_id].since == clock.now
            with pytest.raises(ServiceError, match="being fetched now"):
                queue.retry(artwork_id)
            gate.set()
            until(lambda: queue.state_of([artwork_id]) == {})
        finally:
            halt()
