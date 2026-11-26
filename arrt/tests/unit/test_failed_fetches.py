"""The failed fetches the health reading counts, from the real queue, with the newest failure's age.

Driven through a real `AcquisitionQueue` over the catalogue, with a fetcher that
fails and a clock the test moves. The newest failure's instant is the queue's
own `failed_at`, written at every failure whatever its outcome; only a row
written before that column existed has its instant read back from the retry
schedule (the queue's `failure_instant`, beside the schedule), so those rows are seeded
here as such a release left them.
"""

import ast
import pathlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from arrt.library.acquisition.queue import GIVE_UP_AFTER, AcquisitionQueue, failure_instant
from arrt.library.acquisition.service import AcquisitionOutcome, AcquisitionResult
from arrt.persistence.records import AcquisitionMethod, FetchOutcome, QueuedAcquisition, RightsStatus, SourceClass
from arrt.services import health as health_module
from arrt.services.health import HealthService, failed_fetches


def _services_clock() -> datetime:
    raise AssertionError("the services' clock is read only inside a test (`_now_is_the_services`)")


@pytest.fixture(autouse=True)
def _now_is_the_services(shared_clock, monkeypatch):
    """`_now` reads the services' clock (`shared_clock`), so what a test writes beside them is on their time."""
    monkeypatch.setitem(globals(), "_services_clock", shared_clock)


def _now() -> datetime:
    return _services_clock()


START = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Failing:
    """Stands where `AcquisitionService.acquire` does, and every fetch fails."""

    calls: list = field(default_factory=list)

    def acquire(self, artwork_id, *, source_id=None):
        self.calls.append(artwork_id)
        return AcquisitionResult(artwork_id=artwork_id, source_id=None, outcome=AcquisitionOutcome.FAILED, detail="a 404")


class NeverPrepared:
    def prepare(self, artwork_id, *, force=False):
        raise AssertionError("nothing is fetched, so nothing is prepared")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def queue(store, service, clock):
    return AcquisitionQueue(store, service, Failing(), NeverPrepared(), clock=clock)


@pytest.fixture
def work(service):
    def _work(title, qid=None):
        artwork = service.add_artwork(title=title, wikidata_qid=qid)
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


def _fail_until_due_again(queue, clock, *, passes: int) -> None:
    """Run the queue `passes` times, moving the clock to the next try before each pass after the first."""
    for index in range(passes):
        if index:
            due = [entry.state.next_try_at for entry in queue.listing().entries if entry.state.next_try_at is not None]
            clock.now = max(due)
        queue.run()


def test_no_failed_work_is_no_observation(queue, clock):
    assert failed_fetches(queue.failed_states(), now=clock.now) is None


def test_the_newest_failures_age_is_the_real_queues_record_of_it(queue, clock, work):
    """Two works fail at different instants: the count is both, the age the later one's."""
    work("Nighthawks")
    queue.run()
    clock.now = START + timedelta(minutes=30)
    work("Automat")
    queue.run()
    clock.now = START + timedelta(minutes=50)

    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert (found.count, found.will_retry, found.given_up, found.age_unknown) == (2, 2, 0, 0)
    assert found.newest_failed_at == START + timedelta(minutes=30)
    assert found.newest_age_seconds == 20 * 60
    assert found.describe() == "The queue holds 2 works whose picture could not be fetched; the newest failed 20 minutes ago."


def test_a_work_failed_twice_is_aged_from_its_second_failure(queue, clock, work):
    """Each step of the schedule, not only the first: the second failure waits a day, not an hour."""
    work("Nighthawks")
    _fail_until_due_again(queue, clock, passes=2)
    second = clock.now
    clock.now = second + timedelta(hours=2)

    [state] = [entry.state for entry in queue.listing().entries]
    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert state.failures == 2
    assert found is not None
    assert found.newest_failed_at == second
    assert found.newest_age_seconds == 2 * 3600


def _as_before_the_column(store, artwork_id) -> None:
    """The work's queue row as a release that recorded no `failed_at` left it."""
    queued = store.get_queued_acquisition(artwork_id)
    store.set_queued_acquisition(replace(queued, failed_at=None))


def test_every_failed_work_given_up_on_is_aged_from_its_recorded_failure(queue, clock, work):
    """Given up on, so no next try to read an instant from: the queue's `failed_at` is what ages it."""
    work("Nighthawks")
    work("Automat")
    _fail_until_due_again(queue, clock, passes=GIVE_UP_AFTER)
    last = clock.now
    clock.now += timedelta(hours=3)

    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert (found.count, found.will_retry, found.given_up) == (2, 0, 2)
    assert (found.newest_failed_at, found.newest_age_seconds, found.age_unknown) == (last, 3 * 3600, 0)
    assert found.describe() == "The queue holds 2 works whose picture could not be fetched; the newest failed 3 hours ago."


def test_works_given_up_on_before_the_queue_recorded_when_are_counted_with_their_age_not_known(queue, clock, work, store):
    """'2 failed, when is not recorded' reads apart from '2 failed, newest an hour ago': no instant is guessed."""
    ids = [work("Nighthawks"), work("Automat")]
    _fail_until_due_again(queue, clock, passes=GIVE_UP_AFTER)
    for artwork_id in ids:
        _as_before_the_column(store, artwork_id)

    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert (found.count, found.will_retry, found.given_up) == (2, 0, 2)
    assert (found.newest_failed_at, found.newest_age_seconds, found.age_unknown) == (None, None, 2)
    assert found.describe() == (
        "The queue holds 2 works whose picture could not be fetched; when the newest failed is not recorded."
    )


def test_a_row_from_before_the_column_still_being_retried_is_aged_from_its_schedule(queue, clock, work, store):
    """The derivation kept for old rows: `next_try_at` less the schedule's step."""
    failed = work("Nighthawks")
    queue.run()
    _as_before_the_column(store, failed)
    clock.now += timedelta(minutes=10)

    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert (found.newest_failed_at, found.newest_age_seconds, found.age_unknown) == (START, 600, 0)


def test_a_mix_says_how_many_failed_at_a_time_not_recorded(queue, clock, work, store):
    old = work("Nighthawks")
    _fail_until_due_again(queue, clock, passes=GIVE_UP_AFTER)
    _as_before_the_column(store, old)
    work("Automat")
    queue.run()
    clock.now += timedelta(minutes=5)

    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert (found.count, found.age_unknown, found.newest_age_seconds) == (2, 1, 300)
    assert found.describe().endswith(
        "the newest whose time is recorded failed 5 minutes ago, and 1 failed at a time not recorded."
    )


@pytest.mark.parametrize("failures", range(1, GIVE_UP_AFTER))
def test_the_queue_reads_each_scheduled_failure_back_from_the_retry_it_wrote(queue, clock, work, failures):
    """The queue's own inverse of its schedule, at every step: a row's `next_try_at` less its step is its `failed_at`.

    Driven through the real queue, so the inverse is held to the writer
    (`_record_failure`), not to a copy of the schedule: each step of the
    schedule is reached and the row's recorded instant hidden, as a release
    before the column left it.
    """
    work("Nighthawks")
    _fail_until_due_again(queue, clock, passes=failures)
    [state] = queue.failed_states()

    assert state.failures == failures
    assert state.failed_at == clock.now
    assert failure_instant(replace(state, failed_at=None)) == clock.now


def test_the_health_model_asks_the_queue_when_a_work_failed_and_keeps_no_schedule_of_its_own():
    """The retry schedule's inverse is the queue's, beside the schedule: the health module imports neither half of it."""
    tree = ast.parse(pathlib.Path(health_module.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}

    assert "RETRY_AFTER" not in imported
    assert not hasattr(health_module, "RETRY_AFTER")
    assert health_module.failure_instant is failure_instant


@dataclass
class Saying:
    """Stands where `AcquisitionService.acquire` does: each work's fetch fails saying its own outcome, at one plugin.

    A work the test did not name (the served deployment seeds some) fails saying
    `otherwise`, and is kept in `others` so a count can include it.
    """

    outcomes: dict = field(default_factory=dict)
    otherwise: FetchOutcome = FetchOutcome.FAILED
    others: list = field(default_factory=list)

    def acquire(self, artwork_id, *, source_id=None):
        if artwork_id not in self.outcomes:
            self.others.append(artwork_id)
            self.outcomes[artwork_id] = self.otherwise
        return AcquisitionResult(
            artwork_id=artwork_id,
            source_id=None,
            outcome=AcquisitionOutcome.FAILED,
            detail="it said so",
            fetch_outcome=self.outcomes[artwork_id],
            plugin="tate",
        )


#: Every outcome a failure can say (`FetchOutcome` less the two that hold an image).
FAILURES = tuple(outcome for outcome in FetchOutcome if outcome not in {FetchOutcome.OK, FetchOutcome.PARTIAL_TILES})


def test_the_queues_failed_states_are_its_listings_failed_and_given_up_entries(store, service, clock, work):
    """The cheap read and the Queue page's, alike: one work per outcome, settled ones with and without an item, one in line.

    A settled work with a Wikidata item is compared against the item its row
    was settled on, which the cheap read takes from `works_to_acquire`'s row.
    """
    fetcher = Saying()
    queue = AcquisitionQueue(store, service, fetcher, NeverPrepared(), clock=clock)
    for outcome in FAILURES:
        fetcher.outcomes[work(f"Said {outcome}")] = outcome
    for index, outcome in enumerate((FetchOutcome.NONE_HELD, FetchOutcome.LINK_GONE)):
        fetcher.outcomes[work(f"Settled on an item, {outcome}", qid=f"Q{index + 1}")] = outcome
    queue.run()
    in_line = work("Not tried yet")
    fetcher.outcomes[in_line] = FetchOutcome.FAILED

    listed = {
        entry.state.artwork_id: replace(entry.state, detail=None) for cause in queue.listing().causes for entry in cause.entries
    }
    states = {state.artwork_id: replace(state, detail=None) for state in queue.failed_states()}

    assert set(listed) == set(fetcher.outcomes) - {in_line}, "the listing itself changed: rebuild the case"
    assert states == listed


def test_the_queues_failed_states_read_no_title(store, service, clock, work, monkeypatch):
    """What makes it cheap: not one `get_artwork` per work, which the listing needs for each title."""
    fetcher = Saying()
    queue = AcquisitionQueue(store, service, fetcher, NeverPrepared(), clock=clock)
    for outcome in FAILURES:
        fetcher.outcomes[work(f"Said {outcome}")] = outcome
    queue.run()
    reads = []
    original = store.get_artwork
    monkeypatch.setattr(store, "get_artwork", lambda artwork_id: reads.append(artwork_id) or original(artwork_id))

    assert len(queue.failed_states()) == len(FAILURES)
    assert reads == []


@pytest.mark.parametrize("outcome", FAILURES, ids=str)
def test_through_the_route_every_recorded_failure_is_aged_whatever_it_said(outcome, server_url, store, service, work):
    """`GET /api/health`, one work failing with `outcome` and one given up on before `failed_at` was recorded.

    Under the retry rules an `unasked` or `faulted` failure has no next try and
    a `none_held` or `link_gone` one is settled, so none of them can be aged
    from the schedule: only the queue's `failed_at` ages them. The old row is
    the one whose age truly is not recorded.
    """
    old = work("Before the column")
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=old, failures=GIVE_UP_AFTER, detail="a 404.", failed_at=None))
    # After the server's queue was made, so a fault recorded now is under this load.
    at = _now()
    fetcher = Saying({work(f"Said {outcome}"): outcome}, otherwise=outcome)
    AcquisitionQueue(store, service, fetcher, NeverPrepared(), clock=lambda: at).run()

    found = httpx.get(f"{server_url}/api/health", timeout=30.0).json()["failed_fetches"]

    assert (found["count"], found["age_unknown"]) == (2 + len(fetcher.others), 1)
    assert datetime.fromisoformat(found["newest_failed_at"]) == at
    assert found["newest_age_seconds"] == pytest.approx((_now() - at).total_seconds(), abs=30)


def test_through_the_route_only_the_row_from_before_the_column_is_unaged(server_url, store, service, work):
    """Every outcome at once: six failed works, and one counted as not recorded."""
    old = work("Before the column")
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=old, failures=GIVE_UP_AFTER, detail="a 404.", failed_at=None))
    fetcher = Saying()
    for outcome in FAILURES:
        fetcher.outcomes[work(f"Said {outcome}")] = outcome
    AcquisitionQueue(store, service, fetcher, NeverPrepared()).run()

    found = httpx.get(f"{server_url}/api/health", timeout=30.0).json()["failed_fetches"]
    queued = httpx.get(f"{server_url}/api/acquisitions", timeout=30.0).json()

    assert (found["count"], found["age_unknown"]) == (len(FAILURES) + 1 + len(fetcher.others), 1)
    assert found["count"] == queued["failing"]


def test_the_count_is_the_queue_pages_own(queue, clock, work):
    """The badge's count and Queue's 'Failed (N)' cannot disagree: both are the listing's causes."""
    for title in ("Nighthawks", "Automat", "Chop Suey"):
        work(title)
    queue.run()

    listing = queue.listing()
    found = failed_fetches(queue.failed_states(), now=clock.now)

    assert found is not None
    assert found.count == sum(cause.failed + cause.gave_up for cause in listing.causes) == 3


def test_the_health_service_observes_the_queue_it_is_given(queue, clock, work, services):
    """Through `HealthService.observe`, the call both routes make, with the queue handed in."""
    work("Nighthawks")
    queue.run()
    clock.now += timedelta(minutes=7)
    health = HealthService(
        services.display,
        backup_receipt_path=services.health._backup_receipt_path,
        sources=services.health._sources,
        yields=dict,
        pictures=services.health._pictures,
        watches=services.health._watches,
        queue=queue.failed_states,
        now=clock,
    )

    reading = health.observe()

    assert reading.failed_fetches is not None
    assert (reading.failed_fetches.count, reading.failed_fetches.newest_age_seconds) == (1, 7 * 60)
    assert [trouble.words for trouble in reading.troubles() if trouble.about == "failed_fetches"] == [
        "1 work could not fetch a picture"
    ]
