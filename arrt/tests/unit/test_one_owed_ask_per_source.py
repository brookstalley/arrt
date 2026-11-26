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
from datetime import UTC, datetime, timedelta

import pytest
from fakes import a_decodable_jpeg, an_image

from arrt.library.acquisition.queue import run_acquisition_queue
from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.sources.loading import DEADLINE_CEILING_SECONDS, Deadlines, SourceRoster, StillAsking, one_pass
from arrt.library.sources.reading import FetchLocator
from arrt.persistence.discovery_records import SearchOutcome, SourceSearch
from arrt.persistence.records import AcquisitionMethod, FetchOutcome, QueuedAcquisition, RightsStatus, SourceClass


def _services_clock() -> datetime:
    raise AssertionError("the services' clock is read only inside a test (`_now_is_the_services`)")


@pytest.fixture(autouse=True)
def _now_is_the_services(shared_clock, monkeypatch):
    """`_now` reads the services' clock (`shared_clock`), so what a test writes beside them is on their time."""
    monkeypatch.setitem(globals(), "_services_clock", shared_clock)


def _now() -> datetime:
    return _services_clock()


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
    """A run's works, one after another, as phase 2 goes through them, in one pass as phase 2 asks them; each answer in turn."""
    answers = []
    started = 0
    with one_pass():
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
    owed_no_more(sources)

    with one_pass():
        answer = pool.find_images(ImageQuery(title="Study after"), work_id="c-after")

    assert answer.unreachable == ()
    slow.searched(2)


def owed_no_more(sources: SourceRoster) -> None:
    """Wait until the containment counts the owed call ended: a moment after the museum's own call returned."""
    (contained,) = sources.finders
    ended = threading.Event()
    for _ in range(int(SETTLE / 0.01)):
        if contained.owing() == 0:
            return
        ended.wait(0.01)
    raise AssertionError("the containment still counts the call owed")


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
    owed_no_more(sources)

    assert services.acquisition_queue.run().acquired == len(works)
    assert slow.reads == len(works)


# -- when a work a pass did not ask is tried again -----------------------------------------


def a_due_retry(store, work, *, now: datetime) -> QueuedAcquisition:
    """A work whose last fetch failed by the schedule over an hour ago: its retry fell due before this pass."""
    row = QueuedAcquisition(
        artwork_id=work.id,
        failures=1,
        next_try_at=now - timedelta(hours=1),
        detail="the museum answered 500",
        outcome=FetchOutcome.FAILED,
        plugin="slow",
        failed_at=now - timedelta(hours=2),
    )
    store.set_queued_acquisition(row)
    return row


def passes_while_owed(queue, *, owed_for: float = DEADLINE_CEILING_SECONDS, most: int = 500) -> int:
    """How many passes the queue's loop runs while a call stays owed for `owed_for` seconds and nothing wakes it.

    The loop's own steps (`run`, then sleep `_seconds_until_due`), on time the
    test keeps: each sleep is added up rather than slept, so an hour costs no
    time. Counted to `most`, past which it is a busy loop whatever the bound.
    """
    elapsed, passes = 0.0, 0
    while elapsed < owed_for and passes < most:
        queue.run()
        passes += 1
        elapsed += queue._seconds_until_due()
    return passes


@pytest.mark.parametrize("tried_before", [False, True], ids=["never tried", "a due retry"])
def test_while_the_source_still_owes_an_answer_the_queue_neither_passes_again_and_again_nor_waits_a_day(
    services, service, store, sources, slow, tried_before
):
    """The refused work is due by the clock, but no pass can ask it until the owed call ends."""
    work = accepted(service, slow, "Fetched")
    row = a_due_retry(store, work, now=_now()) if tried_before else None
    ask_about_every_work(a_run(sources), slow, works=1)
    queue = services.acquisition_queue

    passes = passes_while_owed(queue)

    # An owed call lasts at most the longest deadline a plugin may declare. A
    # pass a minute at most over that is a bounded few, where a busy loop is
    # one a second; and a work left a day behind the release is stranded.
    assert passes <= 60, f"{passes} passes while one call was owed for {DEADLINE_CEILING_SECONDS:g} s"
    assert queue._seconds_until_due() < DEADLINE_CEILING_SECONDS, "a refused work waits longer than any owed call lasts"
    assert slow.reads == 0
    assert store.get_queued_acquisition(work.id) == row, "the work not asked had its row rewritten"


@pytest.mark.parametrize("tried_before", [False, True], ids=["never tried", "a due retry"])
def test_a_work_a_pass_did_not_ask_because_its_source_owed_an_answer_is_tried_as_soon_as_the_answer_comes(
    services, service, store, sources, slow, tried_before
):
    """Through the queue's own loop: it sleeps after the refused pass, and the owed call's end is what wakes it."""
    work = accepted(service, slow, "Fetched")
    if tried_before:
        a_due_retry(store, work, now=_now())
    ask_about_every_work(a_run(sources), slow, works=1)
    queue = services.acquisition_queue
    # Acceptance nudged the queue; taken here, so the loop's second pass is the
    # one the owed call's end wakes, and no nudge from before.
    queue.nudge()
    queue.wait_for_work()
    passes = threading.Semaphore(0)
    stop = threading.Event()
    loop = threading.Thread(
        target=run_acquisition_queue, args=(queue,), kwargs={"stop": stop, "after_pass": passes.release}, daemon=True
    )
    loop.start()
    try:
        assert passes.acquire(timeout=SETTLE), "the queue never ran its first pass"
        assert slow.reads == 0, "the first pass read at a museum that owed an answer"

        slow.let_go()

        assert passes.acquire(timeout=SETTLE), "the queue was not woken when the owed answer came"
        assert slow.reads == 1
        assert store.get_queued_acquisition(work.id) is None, "the work read after the release was not acquired"
    finally:
        stop.set()
        queue.nudge()
        loop.join(timeout=SETTLE)


# -- outside a pass ------------------------------------------------------------------------


def test_outside_a_pass_a_source_owing_an_answer_is_asked_by_the_run_and_by_its_containment(sources, slow):
    """Bounding the owed calls is a pass's, which goes from work to work; a question asked outside one is asked."""
    pool = a_run(sources)
    ask_about_every_work(pool, slow, works=1)

    answer = pool.find_images(ImageQuery(title="Asked outside a pass"), work_id="c-outside")

    assert answer.unreachable == (), "outside a pass a source owing an answer was not asked"
    assert answer.owed == ("slow",)
    slow.searched(2)


# -- one refusal, one line -----------------------------------------------------------------


class Unsaid:
    """The slow museum's contained finder, saying nothing of what it owes.

    So the run's own check before it asks reads none owed, as it does for a
    worker that got past that check just before another call became owed, and
    the refusal comes from the containment's count instead.
    """

    offers_images = True

    def __init__(self, inner) -> None:
        self._inner = inner
        self.provider = inner.provider

    def find_images(self, query: ImageQuery):
        return self._inner.find_images(query)

    def fetch_preview(self, url: str) -> bytes | None:
        return None


def test_a_refusal_the_containment_makes_for_a_run_is_journalled_once(sources, slow, caplog):
    ask_about_every_work(a_run(sources), slow, works=1)
    (contained,) = sources.finders
    racing = ImageSourcePool([Unsaid(contained), Quick()], window_seconds=0.0)

    with caplog.at_level(logging.INFO), one_pass():
        answer = racing.find_images(ImageQuery(title="Raced"), work_id="c-raced")

    assert answer.unreachable == ("slow",)
    assert slow.searches == 1, "the containment did not refuse the raced call"
    lines = [
        (record.name, record.event)
        for record in caplog.records
        if getattr(record, "event", None) in ("image_pool.still_asking", "source.plugin_still_asking")
    ]
    assert lines == [("arrt.library.discovery.pool", "image_pool.still_asking")], lines


def test_a_refusal_listened_to_after_the_owed_call_ended_calls_back_at_once(sources, slow):
    """The call can end between the refusal and the caller's listening: nobody would call back later, so it is now."""
    ask_about_every_work(a_run(sources), slow, works=1)
    reader = sources.route("https://slow.example/w1").reader
    with one_pass(), pytest.raises(StillAsking) as refused:
        reader.read("https://slow.example/w1")
    slow.let_go()
    owed_no_more(sources)
    heard = threading.Event()

    assert refused.value.when_answered(heard.set)
    assert heard.is_set(), "a listener that came after the owed call ended was never called back"


def test_a_refusal_listened_to_while_the_call_is_owed_calls_back_when_it_ends_and_not_before(sources, slow):
    ask_about_every_work(a_run(sources), slow, works=1)
    reader = sources.route("https://slow.example/w1").reader
    with one_pass(), pytest.raises(StillAsking) as refused:
        reader.read("https://slow.example/w1")
    heard = threading.Event()

    refused.value.when_answered(heard.set)
    assert not heard.is_set(), "called back while the call was still owed"
    slow.let_go()

    assert heard.wait(SETTLE), "never called back when the owed call ended"


def test_an_owed_call_that_passes_its_deadline_calls_back_as_one_that_answers_does(slow):
    """Past its deadline the call is a straggler, bounded apart, and owed no longer: the refused work may be asked."""
    short = SourceRoster.of(finders=[slow], readers={"slow": (slow.claims, slow)}, deadlines=Deadlines(finder=0.2, reader=600.0))
    ask_about_every_work(a_run(short), slow, works=1)
    with one_pass(), pytest.raises(StillAsking) as refused:
        short.route("https://slow.example/w1").reader.read("https://slow.example/w1")
    heard = threading.Event()

    refused.value.when_answered(heard.set)

    # Inside the time the museum holds the search, so only the deadline can end it.
    assert heard.wait(SETTLE / 2), "never called back when the owed call passed its deadline"
    assert slow.inside == 1, "the search answered; this was to be its deadline passing"
