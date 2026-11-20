"""The failed fetches the health reading counts, from the real queue, with the newest failure's age.

Driven through a real `AcquisitionQueue` over the catalogue, with a fetcher that
fails and a clock the test moves, because the newest failure's instant is read
back from the queue's retry schedule (`services/health.py`'s `failure_instant`):
a change to that schedule must turn this red while the derivation lives.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from arrt.library.acquisition.queue import GIVE_UP_AFTER, AcquisitionQueue
from arrt.library.acquisition.service import AcquisitionOutcome, AcquisitionResult
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from arrt.services.health import HealthService, failed_fetches, failed_states

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
    def _work(title):
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


def _fail_until_due_again(queue, clock, *, passes: int) -> None:
    """Run the queue `passes` times, moving the clock to the next try before each pass after the first."""
    for index in range(passes):
        if index:
            due = [entry.state.next_try_at for entry in queue.listing().entries if entry.state.next_try_at is not None]
            clock.now = max(due)
        queue.run()


def test_no_failed_work_is_no_observation(queue, clock):
    assert failed_fetches(failed_states(queue.listing()), now=clock.now) is None


def test_the_newest_failures_age_is_read_from_the_real_queues_schedule(queue, clock, work):
    """Two works fail at different instants: the count is both, the age the later one's."""
    work("Nighthawks")
    queue.run()
    clock.now = START + timedelta(minutes=30)
    work("Automat")
    queue.run()
    clock.now = START + timedelta(minutes=50)

    found = failed_fetches(failed_states(queue.listing()), now=clock.now)

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
    found = failed_fetches(failed_states(queue.listing()), now=clock.now)

    assert state.failures == 2
    assert found is not None
    assert found.newest_failed_at == second
    assert found.newest_age_seconds == 2 * 3600


def test_every_failed_work_given_up_on_is_counted_with_its_age_not_known(queue, clock, work):
    """'2 failed, when is not recorded' reads apart from '2 failed, newest an hour ago'."""
    work("Nighthawks")
    work("Automat")
    _fail_until_due_again(queue, clock, passes=GIVE_UP_AFTER)

    found = failed_fetches(failed_states(queue.listing()), now=clock.now)

    assert found is not None
    assert (found.count, found.will_retry, found.given_up) == (2, 0, 2)
    assert (found.newest_failed_at, found.newest_age_seconds, found.age_unknown) == (None, None, 2)
    assert found.describe() == (
        "The queue holds 2 works whose picture could not be fetched; when the newest failed is not recorded."
    )


def test_a_mix_says_how_many_failed_at_a_time_not_recorded(queue, clock, work):
    work("Nighthawks")
    _fail_until_due_again(queue, clock, passes=GIVE_UP_AFTER)
    work("Automat")
    queue.run()
    clock.now += timedelta(minutes=5)

    found = failed_fetches(failed_states(queue.listing()), now=clock.now)

    assert found is not None
    assert (found.count, found.age_unknown, found.newest_age_seconds) == (2, 1, 300)
    assert found.describe().endswith(
        "the newest whose time is recorded failed 5 minutes ago, and 1 failed at a time not recorded."
    )


def test_the_count_is_the_queue_pages_own(queue, clock, work):
    """The badge's count and Queue's 'Failed (N)' cannot disagree: both are the listing's causes."""
    for title in ("Nighthawks", "Automat", "Chop Suey"):
        work(title)
    queue.run()

    listing = queue.listing()
    found = failed_fetches(failed_states(listing), now=clock.now)

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
        queue=queue.listing,
        now=clock,
    )

    reading = health.observe()

    assert reading.failed_fetches is not None
    assert (reading.failed_fetches.count, reading.failed_fetches.newest_age_seconds) == (1, 7 * 60)
    assert [trouble.words for trouble in reading.troubles() if trouble.about == "failed_fetches"] == [
        "1 work could not fetch a picture"
    ]
