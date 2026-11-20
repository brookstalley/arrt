"""A source still owing one work's answer is not asked about the next while it does.

A run answers within its window (`ANSWER_WINDOW_SECONDS`) and leaves a source
still asking as *owed*, its call running on to the plugin's own deadline. Going
from work to work, a run would otherwise start a new call at that source for
every work while the last still runs: about deadline / window calls at once at
one museum, where the private browser plugins declare 1,012 s and 2,044 s. The
rule (`library/discovery/pool.py`, `library/sources/loading.py`): while one of a
plugin's calls is owed, a run does not start another at it, and neither does a
pass of the queue; the work is not asked, as a pass's hold-back leaves a work,
with no search recorded and its queue row as it was.

Held on both paths that go from work to work: a run's, through the pool, and the
acquisition queue's pass, through its reader. Each plugin is contained by
`SourceRoster.of` as a loaded plugin is, and answers only when the test opens
its gate, so nothing here waits on a clock: the window is nought, and "still
asking" is a call the test has not let go.
"""

import logging
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fakes import a_decodable_jpeg, an_image

from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.sources.loading import Deadlines, SourceRoster
from arrt.library.sources.reading import FetchLocator
from arrt.persistence.discovery_records import SearchOutcome, SourceSearch
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

#: How many works a run goes through here: enough that "one at a time" and
#: "one per work" cannot be mistaken for each other.
WORKS = 8
#: How long a test waits for something another thread does, at most. Never a
#: sleep: each wait ends the moment what it waits for happens.
SETTLE = 10.0
#: A deadline the test never reaches: every call here is inside it, owed and not late.
LONG = Deadlines(finder=600.0, reader=600.0)
#: When the work's earlier search was recorded, before this run.
_EARLIER = datetime(2026, 11, 1, tzinfo=UTC)


class Museum:
    """A plugin's finder and reader at one museum, counting how many of its calls are under way at once.

    A search waits for `gate`; a read answers at once, so the queue's pass is
    never held by the test, only counted.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.gate = threading.Event()
        self.changed = threading.Condition()
        self.inside = 0
        self.most = 0
        self.searches = 0
        self.reads = 0

    @property
    def provider(self) -> str:
        return self.name

    def claims(self, url: str) -> bool:
        return url.startswith(f"https://{self.name}.example/")

    @contextmanager
    def _under_way(self):
        with self.changed:
            self.inside += 1
            self.most = max(self.most, self.inside)
            self.changed.notify_all()
        try:
            yield
        finally:
            with self.changed:
                self.inside -= 1
                self.changed.notify_all()

    def find_images(self, query: ImageQuery):
        with self._under_way():
            with self.changed:
                self.searches += 1
                self.changed.notify_all()
            assert self.gate.wait(SETTLE), "the test never let the search go"
            return ()

    def read(self, url: str) -> FetchLocator:
        with self._under_way():
            self.reads += 1
            return FetchLocator.direct(url)

    def fetch_preview(self, url: str) -> bytes | None:
        return None

    def searched(self, times: int) -> None:
        """Wait until `times` searches have reached the museum."""
        with self.changed:
            assert self.changed.wait_for(lambda: self.searches >= times, timeout=SETTLE), "a search never arrived"

    def let_go(self) -> None:
        """Answer every search under way, and wait until none is."""
        self.gate.set()
        with self.changed:
            assert self.changed.wait_for(lambda: self.inside == 0, timeout=SETTLE), "a call never ended"


class Quick:
    """A source of images that answers at once, so a run has heard one when its window ends."""

    provider = "quick"
    offers_images = True

    def find_images(self, query: ImageQuery) -> tuple[FoundImage, ...]:
        return (an_image(query.title, provider="quick", url=f"https://quick.example/{query.title}"),)

    def fetch_preview(self, url: str) -> bytes | None:
        return None


class Kept:
    """A search record in memory."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], SourceSearch] = {}
        self.lock = threading.Lock()

    def record_search(self, search: SourceSearch) -> None:
        with self.lock:
            self.rows[(search.candidate_work_id, search.provider)] = search

    def searches_of(self, candidate_work_id: str):
        with self.lock:
            return {provider: search for (work, provider), search in self.rows.items() if work == candidate_work_id}


@pytest.fixture
def slow() -> Museum:
    museum = Museum("slow")
    yield museum
    museum.let_go()


@pytest.fixture
def sources(slow) -> SourceRoster:
    return SourceRoster.of(finders=[slow], readers={"slow": (slow.claims, slow)}, deadlines=LONG)


@pytest.fixture
def open_stream():
    @contextmanager
    def _open(url: str):
        yield iter([a_decodable_jpeg()])

    return _open


def a_run(sources: SourceRoster, kept: Kept | None = None) -> ImageSourcePool:
    """A pool over the slow museum's contained finder and a quick source, answering the moment the quick one has."""
    return ImageSourcePool([*sources.finders, Quick()], window_seconds=0.0, searches=kept)


def ask_about_every_work(pool: ImageSourcePool, slow: Museum, works: int = WORKS):
    """A run's works, one after another, as phase 2 goes through them; each answer in turn."""
    answers = []
    started = 0
    for n in range(works):
        answer = pool.find_images(ImageQuery(title=f"Study {n}"), work_id=f"c{n}")
        answers.append(answer)
        if "slow" in answer.owed:
            # Started and still asking: wait until its call has reached the
            # museum, so the next work is asked with it truly under way.
            started += 1
            slow.searched(started)
    return answers


# -- through the pool: a run going from work to work ---------------------------------------


def test_a_run_asks_a_source_still_owing_an_answer_about_no_other_work(sources, slow):
    answers = ask_about_every_work(a_run(sources), slow)

    assert slow.most == 1, f"{slow.most} searches were under way at once at one museum"
    assert slow.searches == 1
    assert answers[0].owed == ("slow",)
    assert all(answer.owed == () and answer.unreachable == ("slow",) for answer in answers[1:]), [
        (answer.owed, answer.unreachable) for answer in answers
    ]


def test_a_work_not_asked_because_its_source_still_owes_another_is_recorded_as_not_asked(sources, slow, caplog):
    """No search is written for it, so its record is as it was, and the journal says why with how many are owed."""
    kept = Kept()
    kept.record_search(
        SourceSearch(candidate_work_id="c1", provider="slow", asked_at=_EARLIER, outcome=SearchOutcome.ANSWERED, images=0)
    )

    with caplog.at_level(logging.INFO, logger="arrt.library.discovery.pool"):
        ask_about_every_work(a_run(sources, kept), slow, works=2)

    assert kept.rows[("c0", "slow")].outcome is SearchOutcome.OWED
    assert kept.rows[("c1", "slow")].asked_at == _EARLIER, "the work not asked had its search record rewritten"
    assert kept.rows[("c1", "quick")].outcome is SearchOutcome.ANSWERED
    (line,) = [record for record in caplog.records if getattr(record, "event", None) == "image_pool.still_asking"]
    assert (line.provider, line.work_title, line.owed) == ("slow", "Study 1", 1)
    assert not [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "image_pool.unreachable" and record.provider == "slow"
    ], "a source not asked was journalled as one that could not be asked"


def test_once_the_owed_answer_has_come_the_next_work_asks_the_source_again(sources, slow):
    pool = a_run(sources)
    ask_about_every_work(pool, slow, works=2)
    slow.let_go()

    answer = pool.find_images(ImageQuery(title="Study after"), work_id="c-after")

    assert slow.searches == 2
    assert answer.unreachable == ()


# -- through the queue's pass: from work to work over its reader --------------------------


def accepted(service, museum: Museum, title: str):
    work = service.add_artwork(title=title)
    service.add_source(
        artwork_id=work.id,
        url=f"https://{museum.name}.example/{work.id}",
        provider=museum.name,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    return work


def test_a_queue_pass_does_not_read_at_a_museum_a_run_still_owes_an_answer_and_leaves_the_work_as_it_was(
    services, service, store, sources, slow, caplog
):
    works = [accepted(service, slow, f"Fetched {n}") for n in range(3)]
    ask_about_every_work(a_run(sources), slow, works=1)

    with caplog.at_level(logging.INFO, logger="arrt.library.sources.loading"):
        result = services.acquisition_queue.run()

    assert slow.most == 1, f"{slow.most} calls were under way at once at one museum"
    assert slow.reads == 0
    assert result.failed == result.acquired == 0
    assert all(store.get_queued_acquisition(work.id) is None for work in works), "a work not asked was given a row"
    lines = [record for record in caplog.records if getattr(record, "event", None) == "source.plugin_still_asking"]
    assert [(line.plugin, line.operation, line.owed) for line in lines] == [("slow", "read", 1)] * len(works)


def test_once_the_owed_answer_has_come_the_queue_reads_there_again(services, service, sources, slow):
    works = [accepted(service, slow, f"Fetched {n}") for n in range(2)]
    ask_about_every_work(a_run(sources), slow, works=1)
    slow.let_go()

    assert services.acquisition_queue.run().acquired == len(works)
    assert slow.reads == len(works)
