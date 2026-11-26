"""Every image source asked at once, and a source that could not be asked kept apart.

The pool's promise has three halves: the sources are asked in parallel, a source
that could not be asked never reads as one that holds nothing, and each instance's
preview goes back to the source that found it (its tiles go to the plugin that
claims its URL, `test_acquisition_reading.py`). The engine-level tests at
the bottom are where the second half matters, because only phase 2's judgement
can say whether what the reachable sources found settles the work.
"""

import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime

import pytest
from fakes import an_image

from arrt.config import DEFAULT_QUALITY_MINIMUM_PX
from arrt.library.discovery.images import FoundImage, ImageQuery, ImageQueryUnanswerable, ImageSearchFailure, LinkGone
from arrt.library.discovery.phase_two import PhaseTwoEngine
from arrt.library.discovery.pool import (
    ANSWER_WINDOW_SECONDS,
    RECORDED,
    AskOutcome,
    ImageSourcePool,
    NoSourceCanAnswer,
    SourcesNotAsked,
)
from arrt.library.services.look import LOOK_HOLD_SECONDS
from arrt.library.services.quality import QualityProfile
from arrt.library.sources.loading import NotAskedThisPass
from arrt.persistence.discovery_records import SearchOutcome, SourceSearch

#: The engine tests' 42" geometry: the floor sits at about 1,260 px on the long edge.
PROFILE = QualityProfile(minimum_long_edge_px=DEFAULT_QUALITY_MINIMUM_PX)

TITLE = "The Elephants"
ARTIST = "Salvador Dalí"


class Source:
    """An image source with a name of its own, answering what it was built to answer."""

    def __init__(
        self,
        name: str,
        *instances: FoundImage,
        fails: bool = False,
        declines: bool = False,
        meet: threading.Barrier | None = None,
    ) -> None:
        self._name = name
        self._instances = instances
        self._fails = fails
        self._declines = declines
        self._meet = meet
        self.previews: list[str] = []

    @property
    def provider(self) -> str:
        return self._name

    def find_images(self, query: ImageQuery):
        if self._meet is not None:
            # Returns only once every source has been asked, so a pool that asks
            # one after another breaks the barrier instead of answering.
            self._meet.wait()
        if self._fails:
            raise ImageSearchFailure(f"{self._name} could not be reached")
        if self._declines:
            raise ImageQueryUnanswerable(f"{self._name} cannot look this up")
        return self._instances

    def fetch_preview(self, url: str) -> bytes | None:
        self.previews.append(url)
        return self._name.encode()


def found(provider: str, *, width: int = 6949, height: int = 8400, title: str = TITLE) -> FoundImage:
    return an_image(
        title, artist=ARTIST, width=width, height=height, provider=provider, url=f"https://{provider}.example/{width}"
    )


def query() -> ImageQuery:
    return ImageQuery(title=TITLE, artist=ARTIST)


def test_every_source_is_asked_at_once():
    meet = threading.Barrier(2, timeout=5)
    pool = ImageSourcePool([Source("first", found("first"), meet=meet), Source("second", found("second"), meet=meet)])

    answer = pool.find_images(query())

    assert {image.provider for image in answer.images} == {"first", "second"}
    assert answer.unreachable == ()


def test_a_source_that_holds_nothing_is_an_answer_not_a_failure():
    answer = ImageSourcePool([Source("first"), Source("second")]).find_images(query())

    assert answer.images == ()
    assert answer.unreachable == ()


def test_a_source_that_could_not_be_asked_is_named_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        answer = ImageSourcePool([Source("first", fails=True), Source("second", found("second"))]).find_images(query())

    assert [image.provider for image in answer.images] == ["second"]
    assert answer.unreachable == ("first",)
    assert [record.provider for record in caplog.records if getattr(record, "event", "") == "image_pool.unreachable"] == ["first"]


def test_no_source_answering_is_a_failure():
    with pytest.raises(ImageSearchFailure, match="first, second"):
        ImageSourcePool([Source("first", fails=True), Source("second", fails=True)]).find_images(query())


def test_a_preview_goes_back_to_the_source_that_found_it():
    first, second = Source("first"), Source("second")
    pool = ImageSourcePool([first, second])

    assert pool.fetch_preview("second", "https://second.example/p.jpg") == b"second"
    assert (first.previews, second.previews) == ([], ["https://second.example/p.jpg"])


def test_a_source_the_pool_does_not_hold_is_refused_by_name():
    with pytest.raises(ValueError, match="'elsewhere'"):
        ImageSourcePool([Source("first")]).fetch_preview("elsewhere", "https://elsewhere.example/p.jpg")


def test_two_sources_may_not_share_a_name():
    with pytest.raises(ValueError, match="first"):
        ImageSourcePool([Source("first"), Source("first")])


def test_a_pool_needs_a_source():
    with pytest.raises(ValueError, match="at least one source"):
        ImageSourcePool([])


def resolve(*sources: Source):
    return PhaseTwoEngine(ImageSourcePool(list(sources)), profile=PROFILE).resolve(query())


def test_a_tie_goes_to_the_source_listed_first():
    """Identical instances from two sources rank level, so preference decides.

    The first-listed source's URL sorts after the other's, so a ranking that fell
    through to the URL would pick the second.
    """
    top, _other = resolve(Source("zeta", found("zeta")), Source("alpha", found("alpha"))).instances

    assert top.found.provider == "zeta"


def test_preference_never_outranks_a_better_image():
    """The first source's smaller image loses to the second's larger one."""
    top, _other = resolve(Source("first", found("first", width=2000, height=2400)), Source("second", found("second"))).instances

    assert top.found.provider == "second"


def test_a_down_source_does_not_stop_an_image_another_source_found():
    resolution = resolve(Source("first", fails=True), Source("second", found("second")))

    assert [entry.found.provider for entry in resolution.instances] == ["second"]


def test_a_down_source_leaves_a_work_the_others_did_not_find_unsettled():
    """Nothing found while a source was down is not "nobody holds it"."""
    with pytest.raises(ImageSearchFailure, match="first"):
        resolve(Source("first", fails=True), Source("second"))


def test_a_down_source_leaves_a_work_with_only_a_small_image_unsettled():
    """The source that was down may hold the image that clears the floor."""
    with pytest.raises(ImageSearchFailure, match="first"):
        resolve(Source("first", fails=True), Source("second", found("second", width=600, height=700)))


def test_a_work_nobody_holds_is_settled_when_every_source_answered():
    resolution = resolve(Source("first"), Source("second"))

    assert resolution.instances == []


def test_a_source_that_cannot_answer_leaves_the_others_answer_standing():
    """One source declining is not one source down: the other's empty answer settles the work."""
    answer = ImageSourcePool([Source("first", declines=True), Source("second")]).find_images(query())

    assert (answer.images, answer.unreachable) == ((), ())


def test_when_no_source_can_answer_nothing_is_known():
    """Every source declining is no answer at all, never "nobody holds it"."""
    with pytest.raises(ImageSearchFailure, match="cannot"):
        ImageSourcePool([Source("first", declines=True)]).find_images(query())


def test_a_source_down_and_one_declining_is_still_a_failure_to_ask():
    with pytest.raises(ImageSearchFailure, match="second"):
        ImageSourcePool([Source("first", declines=True), Source("second", fails=True)]).find_images(query())


def test_what_a_source_logs_on_its_worker_carries_the_run_it_works_for():
    """The run id is bound in the caller's context; a worker thread would otherwise start without it."""
    from arrt.logs import current_run_id, run_context

    seen: list[str | None] = []

    class Seeing(Source):
        def find_images(self, query: ImageQuery):
            seen.append(current_run_id())
            return ()

    with run_context("run-7"):
        ImageSourcePool([Seeing("first"), Seeing("second")]).find_images(query())

    assert seen == ["run-7", "run-7"]


# -- 1.6: a source answering that the work's pages at it are gone --------------------


class GoneSource(Source):
    """Answers that every page the work's item links at it is gone (`LinkGone`)."""

    offers_images = True

    def find_images(self, query: ImageQuery):
        raise LinkGone(f"every {self._name} page for this work answered 404")


class GonePages(GoneSource):
    """A finder of pages only, answering the same."""

    offers_images = False


def test_a_source_whose_pages_are_gone_answered_and_is_named_apart(caplog):
    with caplog.at_level(logging.INFO):
        answer = ImageSourcePool([GoneSource("first"), Source("second")]).find_images(query())

    assert (answer.images, answer.unreachable, answer.gone) == ((), (), ("first",))
    assert [record.provider for record in caplog.records if getattr(record, "event", "") == "image_pool.link_gone"] == ["first"]


def test_a_source_whose_pages_are_gone_is_an_answer_even_alone():
    """Every source of images answering "gone" is every source answering: nobody holds it now."""
    answer = ImageSourcePool([GoneSource("only")]).find_images(query())

    assert (answer.images, answer.unreachable, answer.gone) == ((), (), ("only",))


def test_a_finder_of_pages_answering_gone_says_nothing_about_an_image():
    with pytest.raises(NoSourceCanAnswer, match="pages only"):
        ImageSourcePool([GonePages("pages")]).find_images(query())


def test_one_source_asked_alone_answers_link_gone_as_itself():
    """What a look reads (`ImageSourcePool.ask`): its own outcome, never "could not be asked"."""
    said = ImageSourcePool([GoneSource("first")]).ask("first", query())

    assert (said.outcome, said.failure) == (AskOutcome.LINK_GONE, "every first page for this work answered 404")


def test_a_work_only_a_gone_source_might_hold_is_settled_as_held_by_nobody():
    """Such a work once waited for ever, as if the source were down."""
    resolution = resolve(GoneSource("first"), Source("second"))

    assert resolution.instances == []


def test_beside_a_source_that_is_down_a_gone_one_still_leaves_the_work_unsettled():
    with pytest.raises(ImageSearchFailure, match="second"):
        resolve(GoneSource("first"), Source("second", fails=True))


# -- the window, and the search record -------------------------------------------------

#: A window a test can pass in a moment, and how long the slow source takes: past it.
WINDOW = 0.3
SLOW = 1.5
#: How long a test waits for something on another thread, at most.
SETTLE = 10.0


class Slow(Source):
    """A source that answers its instances only once its gate opens, or after `SLOW` seconds."""

    def __init__(self, name: str, *instances: FoundImage, fails: bool = False) -> None:
        super().__init__(name, *instances, fails=fails)
        self.gate = threading.Event()
        self.calls = 0

    def find_images(self, query: ImageQuery):
        self.calls += 1
        self.gate.wait(SLOW)
        return super().find_images(query)


class Kept:
    """A search record in memory, which says on which thread and when each search was written."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], SourceSearch] = {}
        self.written: list[tuple[SourceSearch, str, float]] = []
        self.lock = threading.Lock()

    def record_search(self, search: SourceSearch) -> None:
        with self.lock:
            self.rows[(search.candidate_work_id, search.provider)] = search
            self.written.append((search, threading.current_thread().name, time.monotonic()))

    def searches_of(self, candidate_work_id: str):
        with self.lock:
            return {provider: search for (work, provider), search in self.rows.items() if work == candidate_work_id}


def until(condition, *, within: float = SETTLE) -> None:
    ends = time.monotonic() + within
    while not condition():
        assert time.monotonic() < ends, "it never got there"
        time.sleep(0.01)


def test_the_runs_window_is_the_looks_hold():
    """One value, two homes: the pool states it because the look imports the pool, and this holds them equal."""
    assert ANSWER_WINDOW_SECONDS == LOOK_HOLD_SECONDS


def test_a_source_slower_than_the_window_does_not_hold_the_others_answer():
    slow = Slow("slow", found("slow"))
    pool = ImageSourcePool([slow, Source("quick", found("quick"))], window_seconds=WINDOW, deadline_seconds=SETTLE)

    started = time.monotonic()
    answer = pool.find_images(query())
    took = time.monotonic() - started
    slow.gate.set()

    assert took < SLOW, f"the run waited {took:.1f} s, for the slow source, past its {WINDOW} s window"
    assert [image.provider for image in answer.images] == ["quick"]
    assert (answer.owed, answer.unreachable) == (("slow",), ())


def test_with_no_source_of_images_answered_the_window_waits_for_the_first_that_does():
    """A deployment whose every source is slower than the window still gets an answer, not a failure at the window."""
    slow = Slow("slow", found("slow"))
    pool = ImageSourcePool([slow, Source("down", fails=True)], window_seconds=WINDOW, deadline_seconds=SETTLE)

    answer = pool.find_images(query())

    assert [image.provider for image in answer.images] == ["slow"]
    assert (answer.owed, answer.unreachable) == ((), ("down",))


def test_a_late_answer_is_recorded_on_the_sources_worker_after_the_run_answered_and_the_next_pass_waits_for_it():
    kept = Kept()
    slow = Slow("slow", found("slow", width=7000), found("slow", width=7100))
    quick = Source("quick", found("quick"))
    pool = ImageSourcePool([slow, quick], window_seconds=WINDOW, deadline_seconds=SETTLE, searches=kept)

    first = pool.find_images(query(), work_id="c1")
    returned = time.monotonic()
    assert first.owed == ("slow",)
    assert kept.rows[("c1", "slow")].outcome is SearchOutcome.OWED
    slow.gate.set()
    until(lambda: kept.rows[("c1", "slow")].outcome is SearchOutcome.ANSWERED)

    late, thread, written = kept.written[-1]
    assert (late.provider, late.images, late.late) == ("slow", 2, True)
    assert thread == "image-source-slow", "the late answer was written by the run, not the source's worker"
    assert written > returned, "the late answer was written before the run answered"
    assert kept.rows[("c1", "quick")] == SourceSearch(
        candidate_work_id="c1",
        provider="quick",
        asked_at=late.asked_at,
        outcome=SearchOutcome.ANSWERED,
        answered_at=kept.rows[("c1", "quick")].answered_at,
        images=1,
        late=False,
    )

    # The next pass reads the record: the work owes the slow source an answer, so
    # the run waits for it past the window and judges what it holds.
    slow.gate.clear()
    threading.Timer(WINDOW * 3, slow.gate.set).start()
    second = pool.find_images(query(), work_id="c1")
    assert sorted(image.provider for image in second.images) == ["quick", "slow", "slow"]
    assert second.owed == ()
    assert kept.rows[("c1", "slow")].late is False


def test_another_work_owes_the_slow_source_nothing_and_is_answered_at_the_window():
    """The record is per work: a source late for one work is waited for on that work's next pass only."""
    kept = Kept()
    kept.record_search(
        SourceSearch(candidate_work_id="c1", provider="slow", asked_at=datetime.now(UTC), outcome=SearchOutcome.OWED)
    )
    slow = Slow("slow", found("slow"))
    pool = ImageSourcePool([slow, Source("quick", found("quick"))], window_seconds=WINDOW, deadline_seconds=SETTLE, searches=kept)

    answer = pool.find_images(query(), work_id="c2")
    slow.gate.set()

    assert answer.owed == ("slow",)


def test_a_late_answer_the_store_refuses_is_dropped_by_name_and_raises_on_no_thread(caplog, monkeypatch):
    """A store closed at shutdown, or a work it does not hold: the worker journals it and ends quietly."""
    raised: list[BaseException] = []
    monkeypatch.setattr(threading, "excepthook", lambda hook: raised.append(hook.exc_value))

    class Closed(Kept):
        def record_search(self, search: SourceSearch) -> None:
            if search.late:
                raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
            super().record_search(search)

    kept = Closed()
    slow = Slow("slow", found("slow"))
    pool = ImageSourcePool([slow, Source("quick", found("quick"))], window_seconds=WINDOW, deadline_seconds=SETTLE, searches=kept)

    with caplog.at_level(logging.WARNING, logger="arrt.library.discovery.pool"):
        pool.find_images(query(), work_id="c1")
        slow.gate.set()
        until(lambda: any(getattr(r, "event", None) == "image_pool.search_unrecorded" for r in caplog.records))

    (line,) = [r for r in caplog.records if getattr(r, "event", None) == "image_pool.search_unrecorded"]
    assert (line.provider, line.reason, line.outcome) == ("slow", "ProgrammingError", "answered")
    assert raised == []
    assert kept.rows[("c1", "slow")].outcome is SearchOutcome.OWED


@pytest.mark.parametrize("outcome", list(AskOutcome))
def test_every_answer_of_the_pools_has_a_word_in_the_record(outcome):
    assert RECORDED[outcome].value == outcome.value


def test_a_source_the_pass_held_back_is_could_not_be_asked_and_writes_no_search():
    kept = Kept()

    class HeldBack(Source):
        def find_images(self, query: ImageQuery):
            raise NotAskedThisPass("held", 3)

    pool = ImageSourcePool([HeldBack("held"), Source("quick", found("quick"))], searches=kept)

    answer = pool.find_images(query(), work_id="c1")

    assert answer.unreachable == ("held",)
    assert set(kept.rows) == {("c1", "quick")}


def test_phase_twos_sentence_names_the_museums_it_could_not_ask_and_those_still_owed():
    slow = Slow("tate")
    engine = PhaseTwoEngine(
        ImageSourcePool(
            [slow, Source("met", fails=True), Source("quick", found("quick", width=600, height=800))],
            window_seconds=WINDOW,
            deadline_seconds=SETTLE,
        ),
        profile=PROFILE,
    )

    with pytest.raises(SourcesNotAsked) as failure:
        engine.resolve(query())
    slow.gate.set()

    assert failure.value.sources == ("met", "tate")
    assert str(failure.value).startswith(
        "Metropolitan Museum of Art could not be asked; tate had not answered yet, and no other source"
    )
