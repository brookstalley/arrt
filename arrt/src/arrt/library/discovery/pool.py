"""Every wired image source, asked at once, and the answers kept apart by source.

Phase 2 used to reach one museum. The owner asked for a pool instead, with no
source special-cased: each source is a `Finder`, every one of them is asked
for every work in parallel, and adding one is a line in the wiring. Nothing above
the pool learns how many sources there are.

**The order sources are listed in is a preference, never an order of asking.**
Every source is asked at once. The order breaks a tie between two instances phase
2 ranks level, so the source listed first wins only when nothing else separates
them. A source asked only after another failed would be the special case the
pool exists to avoid.

**A run answers within a window, and waits for no source past its deadline.**
Once a source of images has answered and `ANSWER_WINDOW_SECONDS` have passed,
the run answers with the sources that answered; a source still asking then is
*owed* for this work (`PoolAnswer.owed`). Its answer, if it comes, lands in the
search record (`SourceSearch`, a row per work and source), and the work's next
pass reads the record and waits for that source as long as its deadline allows,
so a slow museum is heard on the next pass rather than holding every other
source's answer on this one. A run in which no source of images has answered by
the window waits on, for the first that does, and never past the slowest
deadline: a source still asking at that is "could not be asked" for this work,
so one hung source does not hold every Get. A plugin's finder reaches the pool
already bounded by its own deadline (`library/sources/loading.py`), which says
what becomes of a call that outlives it; the pool's is a backstop a little
longer than that, for any finder handed to it directly.

**A source still owing one work's answer is not asked about the next.** Going
from work to work, a run would otherwise start a call at a slow source for every
work while the last still ran: about its deadline over the window at once, at a
museum behind a crawl delay. So within a pass (`one_pass`, which phase 2 opens
over a run's works), while a plugin owes `OWED_CALLS_PER_PLUGIN` answers (its
`owing()`, `library/sources/loading.py`), a run does not ask it: the work is
answered with that source not asked, as a pass's hold-back answers it, no
search is written, and the journal says so once (`image_pool.still_asking`, with
how many it owes), whether this check or the plugin's own containment refused
it. The cost: such a work is not asked at that source on this pass, where
before it was asked and its answer owed, and waits for a later pass to ask it
there. Outside a pass nothing is refused for it, as the containment refuses
nothing then. A finder handed to the pool directly says nothing of what it
owes, and is asked for every work.

**The record is written on two threads, and never interleaves a pass's own
writes.** A search answered within the window is recorded by the run, on its
own thread, after the run stops waiting; a late one by the source's worker, when
it answers, after `find_images` has returned. Both go through the one store
every service shares, whose connection is serialised by its lock and whose
`transaction()` holds that lock for its whole body, so a late write waits for a
pass's transaction to end and never joins it. Each is one statement committed on
its own, holding the file's write lock for that statement alone. A write the
store refuses (it was closed at shutdown, the work is not in the file) is
dropped and journalled by name (`image_pool.search_unrecorded`), never raised on
a worker nobody watches. Which of the two writes a search is ordered by a lock
per ask, so an owed row never overwrites the late answer that replaced it.

**A source that could not be asked is reported, not folded into the answer.** An
empty list from a source means it was asked and holds nothing; a failure means
nothing is known about what it holds. The pool keeps the two apart all the way
to phase 2, because only the judgement there can say whether what the other
sources found is enough to call the work resolved. A work called unresolved
because one server was down would tell a curator the painting is not out there.
"""

import contextvars
import logging
import queue
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol

from arrt.library.discovery.images import (
    Finder,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    LinkGone,
    offers_images,
)
from arrt.library.sources.loading import (
    FINDER_DEADLINE_SECONDS,
    OWED_CALLS_PER_PLUGIN,
    NotAskedThisPass,
    StillAsking,
    caller_stops_waiting_when,
    in_a_pass,
)
from arrt.library.sources.names import museum_name
from arrt.persistence.discovery_records import SearchOutcome, SourceSearch

log = logging.getLogger(__name__)

#: Seconds past a source's own deadline that a run still waits for it, so a
#: plugin's finder, which answers "could not be asked" at its deadline in its own
#: words, is heard saying so before the run's backstop cuts in.
RUN_MARGIN_SECONDS: Final[float] = 5.0
#: Seconds a run waits for a source that states no deadline of its own: a finder
#: handed to the pool unwrapped, which nothing else bounds. A plugin's finder
#: states its own (`deadline_seconds`), which may be longer when the plugin
#: declared it, and the run waits for that and the margin instead.
RUN_DEADLINE_SECONDS: Final[float] = FINDER_DEADLINE_SECONDS + RUN_MARGIN_SECONDS
#: Seconds a run waits for the rest once a source of images has answered: the
#: look's hold (`library/services/look.py` `LOOK_HOLD_SECONDS`), so a run and a
#: look give a slow source the same time before answering without it. Stated
#: here because the look imports this module; `test_image_pool.py` holds the two
#: equal.
ANSWER_WINDOW_SECONDS: Final[float] = 30.0


class SourceSearches(Protocol):
    """Where the pool keeps the newest search of each work at each source (`DiscoveryStore`)."""

    def record_search(self, search: SourceSearch) -> None: ...

    def searches_of(self, candidate_work_id: str) -> Mapping[str, SourceSearch]: ...


class SourcesNotAsked(ImageSearchFailure):
    """No source of images answered: each could not be asked, or had not answered within the window.

    `sources` names them, by plugin id, so a caller counting which source a run
    could not ask (`DiscoveryRunner`) need not read it out of a sentence. The
    message names the museums.
    """

    def __init__(self, message: str, *, sources: Sequence[str]) -> None:
        super().__init__(message)
        self.sources: tuple[str, ...] = tuple(sources)


class NoSourceCanAnswer(ImageSearchFailure):
    """Every wired source declined the work: none can look a work like it up.

    A failure to ask, so the work waits as it does when every source is down,
    and a kind of its own, so the log can say "nothing here can search for this"
    rather than "the source was down" for every title-only work in a deployment
    whose only source answers by item.
    """


@dataclass(frozen=True, slots=True)
class PoolAnswer:
    """What every source said about one work.

    `unreachable` names the sources of images that could not be asked. It is
    empty when every one of them answered, which is the only case in which an
    empty `images` means no source holds the work. A finder of pages that could
    not be asked is never in it: it holds no image either way, so its silence
    leaves nothing in doubt.

    `pages` are the pages the sources found and do not read, each once, kept apart
    from the images because nothing about them can be judged (`FoundPage`).

    `gone` names the sources of images that answered that every page the work's
    item links at them is gone (`LinkGone`, interface 1.6). Each is an answer,
    holding nothing, and so never in `unreachable`: a work only they might have
    held settles rather than waiting for ever on a link that is dead.
    """

    images: Sequence[FoundImage]
    unreachable: tuple[str, ...]
    pages: tuple[FoundPage, ...] = ()
    gone: tuple[str, ...] = ()
    #: The sources of images still asking when the run stopped waiting at the
    #: window: not "could not be asked", and not an answer either. A work they
    #: might hold is in doubt as it is for `unreachable`, and its next pass waits
    #: for them (`SourceSearch`).
    owed: tuple[str, ...] = ()


class AskOutcome(StrEnum):
    """How one source took one question: the four answers the pool keeps apart."""

    #: It was asked and answered, with whatever it holds, nothing included.
    ANSWERED = "answered"
    #: It cannot look a work like this one up (`ImageQueryUnanswerable`):
    #: neither "holds none" nor "down".
    DECLINED = "declined"
    #: It could not be asked (`ImageSearchFailure`): nothing is known about
    #: what it holds.
    UNREACHABLE = "unreachable"
    #: It answered that every page the work's item links at it is gone
    #: (`LinkGone`, 1.6): an answer, holding nothing now, kept apart from
    #: `ANSWERED` so a dead link is reported as one.
    LINK_GONE = "link_gone"


@dataclass(frozen=True, slots=True)
class SourceAnswer:
    """What one source said about one work, sorted the way the pool sorts every answer.

    `images` and `pages` are what it handed over before it answered or failed:
    a finder that yields some results and then raises has said those, and the
    pool keeps them. A plugin's finder hands them over through its containment
    the same way (`loading._Said`), what it yielded before its deadline included.
    """

    provider: str
    outcome: AskOutcome
    #: Whether this source finds images at all (`offers_images`). A finder of
    #: pages that answered has said nothing about whether an image exists.
    offers_images: bool
    images: tuple[FoundImage, ...] = ()
    pages: tuple[FoundPage, ...] = ()
    #: The failure's own words, for the log, when it could not be asked.
    failure: str | None = None
    #: The pass held this source back (`NotAskedThisPass`): it was not asked at
    #: all, so it reads as could-not-be-asked here and no search is recorded.
    not_asked: bool = False
    #: When it was not asked because it still owes other works answers
    #: (`StillAsking`), how many it owes; 0 otherwise.
    still_asking: int = 0


#: What the record keeps for each of the pool's answers. Checked complete at
#: import, so an answer added to `AskOutcome` without a word here fails there.
RECORDED: Final[Mapping[AskOutcome, SearchOutcome]] = {
    AskOutcome.ANSWERED: SearchOutcome.ANSWERED,
    AskOutcome.DECLINED: SearchOutcome.DECLINED,
    AskOutcome.UNREACHABLE: SearchOutcome.UNREACHABLE,
    AskOutcome.LINK_GONE: SearchOutcome.LINK_GONE,
}
if _unrecorded := set(AskOutcome) - set(RECORDED):
    raise RuntimeError(f"The search record keeps no outcome for {sorted(_unrecorded)}.")


@dataclass(slots=True)
class _Ask:
    """One source's ask for one run: which of the run and the source's worker records it, decided under its lock."""

    index: int
    provider: str
    release: Callable[[], bool]
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: The worker has put its answer where the run hears it.
    delivered: bool = False
    #: The run stopped waiting for it; its answer, when it comes, is late.
    abandoned: bool = False


#: One source's answer for a run, or what it raised outside the interface.
type _Settled = tuple[SourceAnswer | None, BaseException | None]
#: Where a run's workers put what each source said, by the source's place in the pool.
type _Heard = queue.SimpleQueue[tuple[int, SourceAnswer | None, BaseException | None]]


def _owing(source: Finder) -> int:
    """How many answers a source owes other works now (a plugin's `owing()`), or 0 for one that does not say."""
    owing = getattr(source, "owing", None)
    if not callable(owing):
        return 0
    said = owing()
    return said if isinstance(said, int) and not isinstance(said, bool) else 0


def _own_deadline(source: Finder) -> float:
    """How long a source says its `find_images` is waited for, or the default when it says nothing usable."""
    own = getattr(source, "deadline_seconds", None)
    if isinstance(own, int | float) and not isinstance(own, bool) and own > 0:
        return float(own)
    return FINDER_DEADLINE_SECONDS


class ImageSourcePool:
    """The image sources phase 2 asks, in order of preference."""

    def __init__(
        self,
        sources: Sequence[Finder],
        *,
        deadline_seconds: float | None = None,
        margin_seconds: float = RUN_MARGIN_SECONDS,
        window_seconds: float | None = None,
        searches: SourceSearches | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not sources:
            # An empty pool would answer every work with nothing, which reads as
            # "no source holds it". A deployment with no source has no pool at
            # all, and phase 2 then says so in words.
            raise ValueError("An image-source pool needs at least one source; pass none at all when there is none.")
        names = [source.provider for source in sources]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            # Instances are recorded under their source's name, and previews and
            # tiles are routed back by it. Two sources sharing a name would send
            # one source's URLs to the other.
            raise ValueError(f"Two image sources share a name: {', '.join(duplicated)}.")
        self._sources: tuple[Finder, ...] = tuple(sources)
        self._by_name: dict[str, Finder] = dict(zip(names, self._sources, strict=True))
        #: How many asks a run (`find_images`) has under way at each source, so a
        #: look can wait behind them (`wait_for_runs`). Guarded by the condition
        #: that wakes a waiting look when a source's count falls to nothing.
        self._run_asks: Counter[str] = Counter()
        self._runs_done = threading.Condition()
        #: How long a run waits for its sources at most: the slowest source's own
        #: deadline and the margin, unless a test fixes it. A run that has heard
        #: a source of images answers at its window; one that has not, or one
        #: whose work is owed an answer, waits on, and never past this.
        self._deadline = (
            deadline_seconds
            if deadline_seconds is not None
            else max(_own_deadline(source) for source in self._sources) + margin_seconds
        )
        #: How long a run waits for the rest once a source of images answered:
        #: `ANSWER_WINDOW_SECONDS`, read when the pool is built, unless a test fixes it.
        self._window = ANSWER_WINDOW_SECONDS if window_seconds is None else window_seconds
        #: Where each search is recorded, and read back by the work's next pass.
        #: None keeps no record: every source is waited for only to the window,
        #: as no pass can say which is owed.
        self._searches = searches
        self._now = now

    @property
    def providers(self) -> tuple[str, ...]:
        """The sources' names, most preferred first."""
        return tuple(self._by_name)

    @property
    def image_providers(self) -> tuple[str, ...]:
        """The sources that find images, most preferred first: a finder of pages only is left out."""
        return tuple(source.provider for source in self._sources if offers_images(source))

    def precedence(self, provider: str) -> int:
        """Where a source stands in the preference order; lower is preferred."""
        self._source(provider)
        return self.providers.index(provider)

    def find_images(self, query: ImageQuery, *, work_id: str | None = None) -> PoolAnswer:
        """Ask every source for the work at once, and say which could not be asked and which are owed.

        A source that cannot look a work like this up is left out, as if not
        wired. Raises `ImageSearchFailure` only when no source answered, because
        then there is no answer at all (`SourcesNotAsked` when some could not be
        asked or were owed). A source raising anything other than
        `ImageSearchFailure` is a fault in that source and propagates. A plugin's
        finder never gets that far: the loader wraps it so that a fault arrives
        here as `ImageSearchFailure` (`library/sources/loading.py`). A finder
        handed to the pool directly, as in most tests, still propagates.

        `work_id`, the candidate work's, is what the search record is kept
        under; without one, or without a record, nothing is recorded or read.
        """
        images: list[FoundImage] = []
        pages: dict[FoundPage, None] = {}
        answered: list[str] = []
        pages_only: list[str] = []
        unreachable: list[str] = []
        declined: list[str] = []
        gone: list[str] = []
        answers, owed = self._every_answer(query, work_id)
        for answer in answers:
            images.extend(answer.images)
            for page in answer.pages:
                pages[page] = None
            if answer.outcome is AskOutcome.ANSWERED:
                # A finder of pages answering says nothing about whether an
                # image exists, so it is not a source that answered.
                (answered if answer.offers_images else pages_only).append(answer.provider)
            elif answer.outcome is AskOutcome.LINK_GONE:
                # The holder answered: the pages the item links are gone. For a
                # source of images that settles what it holds now (nothing), so
                # it counts as answering, and is named apart.
                log.info(
                    "an image source answered that every page the work's item links at it is gone: %s",
                    answer.failure,
                    extra={"event": "image_pool.link_gone", "provider": answer.provider, "work_title": query.title},
                )
                if answer.offers_images:
                    answered.append(answer.provider)
                    gone.append(answer.provider)
                else:
                    pages_only.append(answer.provider)
            elif answer.provider in owed:
                # Still asking at the window. Not "could not be asked", which
                # it may yet answer, and its answer goes to the record.
                log.info(
                    "an image source had not answered a work within the run's window; its answer is owed",
                    extra={"event": "image_pool.owed", "provider": answer.provider, "work_title": query.title},
                )
            elif answer.outcome is AskOutcome.DECLINED:
                # Not asked, in effect: this source has nothing to say about
                # works like this one, which is neither "holds none" nor "down".
                declined.append(answer.provider)
            else:
                _journal_unasked(answer, query)
                # Only a source of images leaves the work in doubt. A finder
                # of pages that could not be asked holds no image either way,
                # and counting it would keep a work waiting that every source
                # of images has answered for.
                (unreachable if answer.offers_images else pages_only).append(answer.provider)
        owed_images = [name for name in self.image_providers if name in owed]
        if not answered:
            # No source of images answered. Nothing is known about the work, so
            # it is not recorded as held by nobody; it waits, as when every source
            # is down. The pages found are dropped with the answer, and a later
            # search of the work finds them again.
            if unreachable or owed_images:
                raise SourcesNotAsked(_not_asked(unreachable, owed_images, self._window), sources=[*unreachable, *owed_images])
            cannot = [
                *(f"{museum_name(name)} cannot" for name in declined),
                *(f"{museum_name(name)} finds pages only" for name in pages_only),
            ]
            raise NoSourceCanAnswer(f"No image source can look this work up: {'; '.join(cannot)}.")
        return PoolAnswer(
            images=tuple(images),
            unreachable=tuple(unreachable),
            pages=tuple(pages),
            gone=tuple(gone),
            owed=tuple(owed_images),
        )

    def _every_answer(self, query: ImageQuery, work_id: str | None) -> tuple[list[SourceAnswer], frozenset[str]]:
        """Every source's answer, in preference order, and which sources the run stopped waiting for at the window.

        Waited for until every source has answered; or until the window has
        passed, a source of images has answered, and no source still asking is
        one the record says this work owes an answer; or until the run's
        deadline. A source still asking at the window is owed; one still asking
        at the deadline is "could not be asked" for this work. Either is no
        longer counted as asked by the run. What a source raised outside the
        interface propagates, as `find_images` says.
        """
        # With no record there is nothing to write or read: no work is named.
        work = work_id if self._searches is not None else None
        # The sources whose last search of this work was owed or answered late:
        # this pass waits for them as long as the deadline allows.
        patient = self._owed_by(work)
        asked_at = self._now()
        heard: _Heard = queue.SimpleQueue()
        asks, not_started = self._start(query, heard, work, asked_at)
        settled, at_window = self._wait(heard, patient, not_started)
        owed = self._stop_waiting(asks, settled, at_window=at_window, work_id=work, asked_at=asked_at)
        # What arrived between the wait and the stop stands.
        while True:
            try:
                index, said, raised = heard.get_nowait()
            except queue.Empty:
                break
            settled[index] = (said, raised)
        answers: list[SourceAnswer] = []
        for index, source in enumerate(self._sources):
            said, raised = settled.get(index, (None, None))
            if raised is not None:
                raise raised
            if said is not None and work is not None and not said.not_asked:
                self._record(_search_of(work, said, asked_at=asked_at, answered_at=self._now(), late=False))
            answers.append(said or self._not_heard(source, owed=source.provider in owed))
        return answers, owed

    def _start(
        self, query: ImageQuery, heard: _Heard, work_id: str | None, asked_at: datetime
    ) -> tuple[list[_Ask], dict[int, _Settled]]:
        """Ask every source on a worker of its own, counted as a run's ask before the worker starts; and those not asked.

        Within a pass, a source still owing other works answers (`_owing`) is
        not asked, and is answered here, on the run's thread, before any worker
        starts: so its answer is the run's to keep, never one that could arrive
        after the run stopped waiting and be written down as owed. Outside a
        pass it is asked, as the plugin's containment asks it then: the bound is
        a pass's, which goes from work to work.
        """
        asks: list[_Ask] = []
        not_started: dict[int, _Settled] = {}
        bounded = in_a_pass()
        for index, source in enumerate(self._sources):
            if bounded and (owing := _owing(source)) >= OWED_CALLS_PER_PLUGIN:
                refused = StillAsking(source.provider, owing)
                not_started[index] = (
                    SourceAnswer(
                        provider=source.provider,
                        outcome=AskOutcome.UNREACHABLE,
                        offers_images=offers_images(source),
                        failure=str(refused),
                        not_asked=True,
                        still_asking=owing,
                    ),
                    None,
                )
                continue
            # Counted here, before the worker starts, so a look asking in the gap
            # between this call and the worker sees the run already.
            asks.append(ask := _Ask(index=index, provider=source.provider, release=self._counted(source.provider)))
            # One daemon thread per source rather than an executor, because the
            # run must not wait for a hung source's worker on its way out, and a
            # daemon thread never holds the process open at exit either. Each runs
            # in a copy of the caller's context, so what a source logs from its
            # worker still carries the run it is working for, and a pass the
            # caller opened (`one_pass`) still counts its answers.
            threading.Thread(
                target=contextvars.copy_context().run,
                args=(self._ask_for_a_run, ask, query, heard, work_id, asked_at),
                name=f"image-source-{source.provider}",
                daemon=True,
            ).start()
        return asks, not_started

    def _wait(
        self, heard: _Heard, patient: frozenset[str], settled_already: Mapping[int, _Settled]
    ) -> tuple[dict[int, _Settled], bool]:
        """The answers heard before the run stops waiting, and whether it stopped at the window rather than the deadline.

        `settled_already` are the sources answered before any was asked (not
        asked at all), which the run never waits for.
        """
        settled: dict[int, _Settled] = dict(settled_already)
        started = time.monotonic()
        window, ends = started + self._window, started + self._deadline
        while len(settled) < len(self._sources):
            now = time.monotonic()
            if now >= ends:
                return settled, False
            if now >= window and self._may_answer(settled, patient):
                return settled, True
            try:
                index, said, raised = heard.get(timeout=min(window if now < window else ends, ends) - now)
            except queue.Empty:
                continue
            settled[index] = (said, raised)
        return settled, False

    def _stop_waiting(
        self, asks: Sequence[_Ask], settled: Mapping[int, _Settled], *, at_window: bool, work_id: str | None, asked_at: datetime
    ) -> frozenset[str]:
        """Stop waiting for every source not yet heard, and record each as owed or could-not-be-asked; the owed ones."""
        owed: set[str] = set()
        for ask in asks:
            if ask.index in settled:
                continue
            with ask.lock:
                if ask.delivered:
                    # It answered in the moment between the wait and the lock:
                    # its answer is in `heard`, and stands.
                    continue
                ask.abandoned = True
                # Stops counting it, so a look at this source is not left behind
                # a call that may never end. The call runs on, and its answer
                # goes to the record when it comes.
                ask.release()
                if at_window:
                    owed.add(ask.provider)
                if work_id is not None:
                    # Under the ask's lock, so the worker's late answer, written
                    # under it too, always lands after this and replaces it.
                    outcome = SearchOutcome.OWED if at_window else SearchOutcome.UNREACHABLE
                    self._record(
                        SourceSearch(candidate_work_id=work_id, provider=ask.provider, asked_at=asked_at, outcome=outcome)
                    )
        return frozenset(owed)

    def _not_heard(self, source: Finder, *, owed: bool) -> SourceAnswer:
        """A source the run stopped waiting for, as "could not be asked": still owed at the window, or past the deadline."""
        museum = museum_name(source.provider)
        return SourceAnswer(
            provider=source.provider,
            outcome=AskOutcome.UNREACHABLE,
            offers_images=offers_images(source),
            failure=(
                f"{museum} had not answered within {self._window:g} seconds"
                if owed
                else f"{museum} did not answer within {self._deadline:g} seconds"
            ),
        )

    def _may_answer(self, settled: Mapping[int, _Settled], patient: frozenset[str]) -> bool:
        """Whether a run past its window may answer now.

        Yes once a source of images has answered (or none is still asking) and
        no source still asking is one this work owes an answer.
        """
        answered = any(
            said is not None and said.offers_images and said.outcome in (AskOutcome.ANSWERED, AskOutcome.LINK_GONE)
            for said, _ in settled.values()
        )
        asking = [source for index, source in enumerate(self._sources) if index not in settled]
        if not answered and any(offers_images(source) for source in asking):
            return False
        return not any(source.provider in patient for source in asking)

    def _owed_by(self, work_id: str | None) -> frozenset[str]:
        """The sources whose last search of this work was still owed, or answered after the run stopped waiting."""
        if self._searches is None or work_id is None:
            return frozenset()
        return frozenset(
            provider
            for provider, search in self._searches.searches_of(work_id).items()
            if search.outcome is SearchOutcome.OWED or search.late
        )

    def _record(self, search: SourceSearch) -> None:
        """Keep one search in the record, or say by name why it could not be kept; never raise."""
        if self._searches is None:
            return
        try:
            self._searches.record_search(search)
        # A search the record cannot keep must not cost the run its answer, nor
        # raise on a worker nobody watches: a closed store, a work not in the file.
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- dropped and journalled by name
            log.warning(
                "a search of an image source could not be recorded: %s: %s",
                type(exc).__name__,
                exc,
                extra={
                    "event": "image_pool.search_unrecorded",
                    "provider": search.provider,
                    "candidate_work_id": search.candidate_work_id,
                    "outcome": str(search.outcome),
                    "reason": type(exc).__name__,
                },
            )

    def ask(self, provider: str, query: ImageQuery) -> SourceAnswer:
        """Ask one source about one work, and sort its answer as the pool sorts every answer.

        `find_images` is this, at every source at once, folded together; a look
        asks one source at a time with it. A source raising anything other than
        `ImageSearchFailure` (or `ImageQueryUnanswerable`) propagates, as it does
        from `find_images`. Waited for as long as the source takes: a plugin's
        finder is bounded by its own deadline, and a look asks one source at a
        time on a thread of its own.
        """
        source = self._source(provider)
        images: list[FoundImage] = []
        pages: list[FoundPage] = []
        offers = offers_images(source)
        try:
            for found in source.find_images(query):
                if isinstance(found, FoundPage):
                    pages.append(found)
                else:
                    images.append(found)
        except NotAskedThisPass as exc:
            # The pass held the plugin back, or it still owes another work an
            # answer (`StillAsking`): nothing was asked, so this source could not
            # be asked about this work, and no search is recorded.
            return SourceAnswer(
                provider=provider,
                outcome=AskOutcome.UNREACHABLE,
                offers_images=offers,
                failure=str(exc),
                not_asked=True,
                still_asking=exc.owed if isinstance(exc, StillAsking) else 0,
            )
        except ImageQueryUnanswerable:
            outcome, failure = AskOutcome.DECLINED, None
        # Before `ImageSearchFailure`, which it is: a dead link is an answer.
        except LinkGone as exc:
            outcome, failure = AskOutcome.LINK_GONE, str(exc)
        except ImageSearchFailure as exc:
            outcome, failure = AskOutcome.UNREACHABLE, str(exc)
        else:
            outcome, failure = AskOutcome.ANSWERED, None
        return SourceAnswer(
            provider=provider,
            outcome=outcome,
            offers_images=offers,
            images=tuple(images),
            pages=tuple(pages),
            failure=failure,
        )

    def wait_for_runs(self, provider: str, *, timeout: float) -> bool:
        """Wait until no run is asking this source, for at most `timeout` seconds; whether none is.

        A run asks first: a look's question to a source a run is using waits
        behind it, because the run is what a curator pressed Get for.
        """
        with self._runs_done:
            return self._runs_done.wait_for(lambda: self._run_asks[provider] == 0, timeout=timeout)

    def _counted(self, provider: str) -> Callable[[], bool]:
        """Count one run's ask at a source, and the one way to stop counting it: whether that call stopped it.

        Released once, by whichever comes first: the ask ending, or the run
        giving up on it at its deadline. A late ask ending after the run gave up
        releases nothing, so it cannot take a later run's ask off the count.
        """
        with self._runs_done:
            self._run_asks[provider] += 1
        released = False

        def release() -> bool:
            nonlocal released
            with self._runs_done:
                if released:
                    return False
                released = True
                self._run_asks[provider] -= 1
                if self._run_asks[provider] <= 0:
                    del self._run_asks[provider]
                    self._runs_done.notify_all()
                return True

        return release

    def _ask_for_a_run(
        self,
        ask: _Ask,
        query: ImageQuery,
        heard: _Heard,
        work_id: str | None,
        asked_at: datetime,
    ) -> None:
        """`ask`, for a run, on a worker of its own: the answer goes to `heard`, or to the record when the run stopped waiting."""
        # Read by the plugin's containment for every call this worker makes: once
        # the run has answered without this source, the call is owed.
        caller_stops_waiting_when(lambda: ask.abandoned)
        started = time.monotonic()
        said: SourceAnswer | None = None
        raised: BaseException | None = None
        try:
            said = self.ask(ask.provider, query)
        except BaseException as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- carried to the run's thread
            raised = exc
        with ask.lock:
            if not ask.abandoned:
                ask.delivered = True
                heard.put((ask.index, said, raised))
                ask.release()
                return
            # The run stopped waiting for it and has answered without it. What
            # it found reaches no run; what it said reaches the record, which
            # the work's next pass reads.
            late = said is not None and not said.not_asked and work_id is not None
            if late and said is not None and work_id is not None:
                self._record(_search_of(work_id, said, asked_at=asked_at, answered_at=self._now(), late=True))
        log.warning(
            "an image source answered %.0f seconds after it was asked, after the run stopped waiting; %s",
            time.monotonic() - started,
            "its answer is recorded for the work's next pass" if late else "discarded",
            extra={"event": "image_pool.late", "provider": ask.provider, "work_title": query.title, "recorded": late},
        )

    def fetch_preview(self, provider: str, url: str) -> bytes | None:
        """The preview bytes, from the source the instance was recorded under."""
        return self._source(provider).fetch_preview(url)

    def _source(self, provider: str) -> Finder:
        try:
            return self._by_name[provider]
        except KeyError:
            # Every instance phase 2 records carries the name of a source in this
            # pool, so a name it does not know is a wiring fault. Guessing a
            # source would send one museum's URL to another.
            raise ValueError(
                f"No image source named {provider!r} is wired; the sources are {', '.join(self.providers)}."
            ) from None


def _journal_unasked(answer: SourceAnswer, query: ImageQuery) -> None:
    """Say in the journal why a source has nothing to say about a work: it could not be asked, or was not.

    A source not asked because it still owes another work an answer
    (`SourceAnswer.still_asking`) is in doubt as one that could not be asked is,
    and journalled as what it is, with how many answers it owes.
    """
    if answer.still_asking:
        log.info(
            "an image source was not asked about a work: it still owes %d earlier %s an answer",
            answer.still_asking,
            "work" if answer.still_asking == 1 else "works",
            extra={
                "event": "image_pool.still_asking",
                "provider": answer.provider,
                "work_title": query.title,
                "owed": answer.still_asking,
            },
        )
        return
    log.warning(
        "an image source could not be asked for a work: %s",
        answer.failure,
        extra={"event": "image_pool.unreachable", "provider": answer.provider, "work_title": query.title},
    )


def _search_of(work_id: str, said: SourceAnswer, *, asked_at: datetime, answered_at: datetime, late: bool) -> SourceSearch:
    """One source's answer about one work, as the record keeps it."""
    return SourceSearch(
        candidate_work_id=work_id,
        provider=said.provider,
        asked_at=asked_at,
        outcome=RECORDED[said.outcome],
        answered_at=answered_at,
        images=len(said.images),
        late=late,
    )


def _not_asked(unreachable: Sequence[str], owed: Sequence[str], window: float) -> str:
    """Why no source of images answered, naming the museums: those that could not be asked, and those still owed."""
    said = []
    if unreachable:
        said.append(f"No image source could be asked: {', '.join(map(museum_name, unreachable))}.")
    if owed:
        said.append(
            f"{', '.join(map(museum_name, owed))} had not answered within {window:g} seconds; "
            "the work's next search waits for " + ("it." if len(owed) == 1 else "them.")
        )
    return " ".join(said)
