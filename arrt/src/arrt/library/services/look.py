"""A look: what the image sources hold of a work the library does not, before any Get.

The owner, 2026-10-06: a work's page should show what it looks like before
anyone presses Get, and "hitting multiple sources is fine, as long as we cache
the result so repeated similar searches don't do too many queries."
(`build-plan-look-before-get.md`.)

**A look asks what a Get would ask and judges as a Get judges.** The question is
built by Get's own builders (`get.chosen_work`, `runner.image_query`), each
source is asked through the pool's own `ask`, and each answer is judged by
phase 2's own `judge` and ordered by its `rank`. So a picture shown here is one a
Get of the work would find, refused or kept for the same reasons, and a test
holds the two questions equal.

**It writes nothing to the catalogue.** No run, no candidate work, no instance:
a look is a question about the sources' present, and its answers live in this
process's memory. Its pictures are the exception the store's norm makes of every
outside picture (`data-model.md` § Direction): kept for good under
`ART_ROOT/pictures/`, outside the catalogue.

**What is kept, and for how long.** Per work and per source:

- an answer, "holds nothing" and "can't look this work up" included, for
  `ANSWER_KEPT_FOR`;
- "could not be asked" for `UNREACHABLE_KEPT_FOR`, and never as "holds nothing",
  which would tell a curator the painting is not out there because a server was
  down;
- at most `MAX_LOOKS` works, the least recently looked at dropped first.

Not across restarts: the pictures persist in the store, and an answer describes
the moment it was given.

**Politeness.** One look at a time asks each source, in the order the asks were
made; a second look at a work already being asked joins it. An ask still queued
for a work nobody has looked at for `UNWATCHED_AFTER` is dropped before it starts,
since nobody is waiting for it; one that has started always finishes and is kept.
**A run asks first**: a look's ask to a source a run is using waits until the run
is done with it (`ImageSourcePool.wait_for_runs`), because a run is what a curator
pressed Get for. A Get does not reuse a look's answers: its journal records its
own per-result lines, and a kept answer would tie it to an age it cannot see.

**Pictures are served by key, never by URL.** A find's key is the picture
store's own (`picture_key`), computed here from the source's answer, and a
picture is served only for a key the work's current look names. No surface takes
an address from a client, and a refused find has no key at all.
"""

import contextvars
import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from arrt.library.discovery.images import ImageQuery
from arrt.library.discovery.phase_two import JudgedImage, PhaseTwoEngine, WikidataLink
from arrt.library.discovery.pool import AskOutcome, ImageSourcePool, SourceAnswer
from arrt.library.services.discovery import DiscoveryService
from arrt.library.services.get import chosen_work
from arrt.library.services.pictures import PictureStore, picture_key
from arrt.library.services.previews import (
    BROWSER_MAX_EDGE_PX,
    ENLARGED_MAX_EDGE_PX,
    InlinePreview,
    RenderedPreview,
    inline_preview,
    kept_preview,
)
from arrt.library.services.registry_works import RegistryWorkService, RegistryWorkState
from arrt.library.services.runner import image_query
from arrt.logs import look_context
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.services.errors import ServiceError
from arrt.services.fields import require_text

log = logging.getLogger(__name__)

#: How long a source's answer about a work is kept, whatever it found. Long
#: enough that a curator going back and forth between a work and its artist asks
#: nothing twice in an evening; short enough that a museum adding a scan is seen
#: the same day.
ANSWER_KEPT_FOR: Final[timedelta] = timedelta(hours=6)

#: How long "could not be asked" is kept before the source is asked again. Short,
#: because a server that was down is usually back soon, and long enough that a
#: page polling every two seconds does not hammer one that is not.
UNREACHABLE_KEPT_FOR: Final[timedelta] = timedelta(minutes=10)

#: The most works whose looks are kept. A look holds a few short rows per source,
#: so this bounds memory, not requests; the least recently looked at goes first.
MAX_LOOKS: Final[int] = 256

#: How long a work nobody has looked at keeps its queued asks. The page polls
#: every two seconds, so ten missed polls means the curator has left it.
UNWATCHED_AFTER: Final[timedelta] = timedelta(seconds=20)

#: How often an ask waiting behind a run checks whether anyone still wants it.
_RECHECK_SECONDS: Final[float] = 1.0

#: How many of a look's pictures travel inline with the MCP answer: the page's
#: first screenful, at the model's inline size (`INLINE_MAX_EDGE_PX`).
INLINED: Final[int] = 6

#: How long the model's look holds for the sources to answer, and its whole
#: budget, picture fetches included. A client abandons a single tool call at 60
#: seconds; `STATUS_HOLD_SECONDS` was sized for a call that does nothing after its
#: hold, and this one then fetches pictures, so the two are its own and leave a
#: third of the minute spare.
LOOK_HOLD_SECONDS: Final[float] = 30.0
MODEL_LOOK_BUDGET_SECONDS: Final[float] = 40.0

#: What a held look waits on, at most, between checks that the hold is over.
_HOLD_STEP_SECONDS: Final[float] = 1.0


class LookState(StrEnum):
    """What a look at a work is doing, or why it asks nothing."""

    #: At least one source is still being asked.
    ASKING = "asking"
    #: Every source has answered, or could not be asked and will be again later.
    ANSWERED = "answered"
    #: The library holds the work: its page is the library's own, and nothing is asked.
    HELD = "held"
    #: A Get under way is already asking the sources about it.
    BEING_GOT = "being_got"
    #: No image source is wired, so there is nothing to ask.
    NO_SOURCES = "no_sources"
    #: No registry is configured, so the work's title and maker are unknown.
    NOT_CONFIGURED = "not_configured"
    #: Wikidata has no such item.
    NOT_FOUND = "not_found"
    #: Wikidata could not be asked.
    UNAVAILABLE = "unavailable"


#: What a look says when the registry page could not name the work, by the page's
#: own state. Stated rather than derived from the spelling, so a state the page
#: gains later is refused by name here instead of failing as a bare lookup.
_REGISTRY_STATES: Final[Mapping[RegistryWorkState, LookState]] = {
    RegistryWorkState.NOT_FOUND: LookState.NOT_FOUND,
    RegistryWorkState.NOT_CONFIGURED: LookState.NOT_CONFIGURED,
    RegistryWorkState.UNAVAILABLE: LookState.UNAVAILABLE,
}


class SourceState(StrEnum):
    """What one source said about the work."""

    ASKING = "asking"
    #: It holds at least one instance phase 2 would keep.
    FOUND = "found"
    #: It answered, and nothing it holds is the work.
    HOLDS_NONE = "holds_none"
    #: It holds a work by this title, or on the item's page, by another artist,
    #: which phase 2 refuses; not shown.
    REFUSED = "refused"
    #: It could not be asked; asked again after `UNREACHABLE_KEPT_FOR`.
    UNREACHABLE = "unreachable"
    #: It cannot look a work like this one up.
    CANNOT = "cannot"


@dataclass(frozen=True, slots=True)
class LookPicture:
    """One instance a source holds, judged as phase 2 judges it.

    `key` is the picture store's key for it, by which the picture route serves
    it, or `None` when the source gave no preview to keep.
    """

    key: str | None
    judged: JudgedImage


@dataclass(frozen=True, slots=True)
class SourceLook:
    """What one source said about the work, and when."""

    provider: str
    state: SourceState
    #: Its kept instances, best first.
    pictures: tuple[LookPicture, ...] = ()
    #: The gates that turned the rest of its results away (`UnresolvedReason`).
    refusals: frozenset[UnresolvedReason] = frozenset()
    answered_at: datetime | None = None
    #: When a source that could not be asked will be asked again.
    retry_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LookView:
    """A look at one work: each source's answer, and every picture found, best first."""

    qid: str
    state: LookState
    #: A sentence for the curator, where the state needs one.
    note: str | None = None
    #: The library's works in circulation that are this one.
    held: tuple[str, ...] = ()
    sources: tuple[SourceLook, ...] = ()
    pictures: tuple[LookPicture, ...] = ()


@dataclass(frozen=True, slots=True)
class Inlined:
    """The pictures a model's look carries inline, by key, and the ones it does not.

    `deferred` were not kept yet and did not arrive within the call's budget:
    their fetches go on into the store, so the next call carries them.
    `failed` were fetched and could not be kept or read.
    """

    previews: Mapping[str, InlinePreview]
    deferred: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


@dataclass(slots=True)
class _Slot:
    """One source's part in one look: its answer, or that an ask is queued or under way."""

    answer: SourceLook | None = None
    expires_at: datetime | None = None
    queued: bool = False


@dataclass(slots=True)
class _Look:
    """One work's look, held in memory: the question, its link, and each source's slot."""

    qid: str
    query: ImageQuery
    link: WikidataLink
    polled_at: datetime
    slots: dict[str, _Slot] = field(default_factory=dict)
    #: Held MCP calls waiting on this look, which count as somebody watching it.
    watchers: int = 0


def _daemon_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="look", daemon=True).start()


class LookService:
    """Ask every image source about a work the library does not hold, and keep what they say."""

    def __init__(
        self,
        *,
        works: RegistryWorkService,
        discovery: DiscoveryService,
        pool: ImageSourcePool | None,
        judge: PhaseTwoEngine | None,
        pictures: PictureStore,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        spawn: Callable[[Callable[[], None]], None] = _daemon_thread,
    ) -> None:
        if (pool is None) != (judge is None):
            raise ServiceError("A look needs both the image sources and phase 2's judge, or neither.")
        self._works = works
        self._discovery = discovery
        self._pool = pool
        self._judge = judge
        self._pictures = pictures
        self._now = now
        self._spawn = spawn
        #: Guards every look, slot and lane, and wakes a held look when any
        #: source answers.
        self._changed = threading.Condition()
        self._looks: OrderedDict[str, _Look] = OrderedDict()
        #: The asks waiting at each source, in the order they were made, and
        #: which sources have a thread working through theirs.
        self._lanes: dict[str, deque[_Look]] = {}
        self._draining: set[str] = set()

    # -- the look ----------------------------------------------------------------

    def look(self, qid: str, *, hold: float = 0.0) -> LookView:
        """What every image source holds of the work, starting or joining the asking.

        Answers at once with each source's state; `hold` waits up to that many
        seconds for every source to answer, as `art_discovery(action='status')`
        holds. A malformed QID is refused.
        """
        known = self._works.known(qid)
        if known.held:
            return LookView(
                qid=qid,
                state=LookState.HELD,
                note="The library holds this work, so its page is the library's own.",
                held=tuple(known.held),
            )
        pool, judge = self._pool, self._judge
        if pool is None or judge is None:
            return LookView(qid=qid, state=LookState.NO_SOURCES, note="No image source is configured to ask.")
        if known.state is not RegistryWorkState.KNOWN or known.known is None:
            state = _REGISTRY_STATES.get(known.state)
            if state is None:
                raise ServiceError(f"The registry page answered {qid} with a state a look has no words for: {known.state}.")
            return LookView(qid=qid, state=state, note=known.note)
        if qid in self._discovery.items_being_got():
            return LookView(
                qid=qid,
                state=LookState.BEING_GOT,
                note="A Get is already asking the sources about this work.",
            )
        chosen = chosen_work(qid, known.known)
        # As the Get's row records it, and as its run asks: the title as
        # `start_get_run` stores it, and no pages, since a Get's run cites none.
        query = image_query(require_text(chosen.title, field="title"), chosen.artist, chosen.qid)
        # Wall time, not the cache's clock: a hold is how long a caller waits.
        deadline = time.monotonic() + hold
        with self._changed:
            entry = self._entry(qid, query, judge)
            entry.polled_at = self._now()
            started = self._schedule(entry, pool, query, judge)
            if started:
                with look_context(qid):
                    log.info(
                        "looking at what the image sources hold of a work",
                        extra={"event": "look.started", "work_title": query.title, "providers": started},
                    )
            view = self._view(entry, pool, judge)
            entry.watchers += 1
            try:
                while view.state is LookState.ASKING and (left := deadline - time.monotonic()) > 0:
                    self._changed.wait(timeout=min(left, _HOLD_STEP_SECONDS))
                    entry.polled_at = self._now()
                    view = self._view(entry, pool, judge)
            finally:
                entry.watchers -= 1
        return view

    def _entry(self, qid: str, query: ImageQuery, judge: PhaseTwoEngine) -> _Look:
        """This work's look, made if there is none, as the most recently looked at. Holds `_changed`."""
        entry = self._looks.get(qid)
        if entry is None:
            entry = _Look(qid=qid, query=query, link=judge.link(query), polled_at=self._now())
            self._looks[qid] = entry
            while len(self._looks) > MAX_LOOKS:
                self._looks.popitem(last=False)
        self._looks.move_to_end(qid)
        return entry

    def _schedule(self, entry: _Look, pool: ImageSourcePool, query: ImageQuery, judge: PhaseTwoEngine) -> list[str]:
        """Queue an ask at every source with no live answer and none queued; the sources queued. Holds `_changed`.

        **A fan-out starts from today's question and a fresh link.** The entry
        outlives its answers, and a link remembers a registry that could not be
        asked; reused, one outage would judge every later ask of the work.
        """
        now = self._now()
        due = [
            provider
            for provider in pool.image_providers
            if not (slot := entry.slots.get(provider, _Slot())).queued
            and not (slot.expires_at is not None and slot.expires_at > now)
        ]
        if due:
            entry.query, entry.link = query, judge.link(query)
        for provider in due:
            slot = entry.slots.setdefault(provider, _Slot())
            slot.answer, slot.expires_at, slot.queued = None, None, True
            self._lanes.setdefault(provider, deque()).append(entry)
            if provider not in self._draining:
                try:
                    self._spawn(lambda provider=provider: self._drain(provider))
                except Exception as exc:  # prawduct:allow prawduct/broad-except -- an unstarted thread must not leave rows asking
                    log.warning(
                        "could not start the thread that asks an image source for looks",
                        extra={"event": "look.source_unreachable", "provider": provider, "reason": str(exc)},
                        exc_info=True,
                    )
                    self._give_up(provider)
                    continue
                # Marked only once the thread exists, so a start that failed is
                # retried by the next ask rather than waited on for good.
                self._draining.add(provider)
        return due

    def _give_up(self, provider: str, serving: _Look | None = None) -> None:
        """Answer every ask waiting at a source, and the one being served, as "could not be asked". Holds `_changed`.

        For a source whose thread stopped or never started: its rows leave
        "asking" and are asked again after `UNREACHABLE_KEPT_FOR`, as any source
        that could not be asked is.
        """
        now = self._now()
        lane = self._lanes.pop(provider, deque())
        for entry in [serving, *lane]:
            if entry is None:
                continue
            slot = entry.slots.setdefault(provider, _Slot())
            slot.answer = _stamped(
                SourceLook(provider=provider, state=SourceState.UNREACHABLE),
                answered_at=now,
                kept_for=UNREACHABLE_KEPT_FOR,
            )
            slot.expires_at, slot.queued = now + UNREACHABLE_KEPT_FOR, False
        self._draining.discard(provider)
        self._changed.notify_all()

    def _drain(self, provider: str) -> None:
        """Work through one source's queued asks, one at a time, then stop.

        A thread that fails outside the ask itself answers the work it was
        serving, and every work still waiting at the source, as "could not be
        asked" (`_give_up`), so no row is left asking for a thread that is gone.
        """
        serving: _Look | None = None
        try:
            while True:
                with self._changed:
                    lane = self._lanes.get(provider)
                    if not lane:
                        # Under the lock that queues asks, so one queued now
                        # either is seen here or finds no thread and starts one.
                        self._draining.discard(provider)
                        return
                    serving = lane.popleft()
                with look_context(serving.qid):
                    self._serve(serving, provider)
                serving = None
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a dead thread must not leave rows asking
            log.warning(
                "the thread asking an image source for looks stopped; its asks are answered as could not be asked",
                extra={"event": "look.source_unreachable", "provider": provider, "reason": type(exc).__name__},
                exc_info=True,
            )
            with self._changed:
                self._give_up(provider, serving)
        except BaseException:
            with self._changed:
                self._give_up(provider, serving)
            raise

    def _serve(self, entry: _Look, provider: str) -> None:
        """Ask one source about one work, unless nobody wants it any more, and keep the answer."""
        pool, judge = self._pool, self._judge
        if pool is None or judge is None:
            return
        while True:
            dropped = self._dropped(entry)
            if dropped is not None:
                if self._abandon(entry, provider, dropped):
                    return
                continue
            if pool.wait_for_runs(provider, timeout=_RECHECK_SECONDS):
                break
        outage = False
        try:
            with self._changed:
                query, link = entry.query, entry.link
            answer = pool.ask(provider, query)
            result = self._judged(query, link, answer, judge)
            # Judged without the item's pages or its creators' names, because
            # Wikidata could not be asked: what was found stands, but "none" is
            # kept no longer than an outage.
            outage = link.unavailable and not result.pictures
        except Exception as exc:  # prawduct:allow prawduct/broad-except -- a fault must not leave a row asking
            # A plugin's finder arrives wrapped, so a fault here is a finder
            # handed in directly or a defect in judging. Kept as "could not be
            # asked", which is what is known, and logged with its traceback.
            log.warning(
                "a look could not ask an image source about a work",
                extra={"event": "look.source_unreachable", "provider": provider, "reason": type(exc).__name__},
                exc_info=True,
            )
            result = SourceLook(provider=provider, state=SourceState.UNREACHABLE)
            answer = None
        now = self._now()
        kept_for = UNREACHABLE_KEPT_FOR if result.state is SourceState.UNREACHABLE or outage else ANSWER_KEPT_FOR
        result = _stamped(result, answered_at=now, kept_for=kept_for)
        # Logged before the answer is published, so the line is in the journal
        # by the time anyone can see the answer it describes.
        if answer is not None and answer.outcome is AskOutcome.UNREACHABLE:
            log.warning(
                "an image source could not be asked about a work; asked again in ten minutes: %s",
                answer.failure,
                extra={"event": "look.source_unreachable", "provider": provider, "reason": answer.failure},
            )
        elif answer is not None:
            log.info(
                "an image source answered a look",
                extra={
                    "event": "look.source_answered",
                    "provider": provider,
                    "state": str(result.state),
                    "found": len(result.pictures),
                    "refused_at": sorted(str(reason) for reason in result.refusals),
                    "registry_unavailable": outage,
                },
            )
        with self._changed:
            slot = entry.slots.setdefault(provider, _Slot())
            slot.answer, slot.expires_at, slot.queued = result, now + kept_for, False
            self._changed.notify_all()

    def _dropped(self, entry: _Look) -> str | None:
        """Why a queued ask is no longer wanted, or `None` while it is."""
        with self._changed:
            return self._unwanted(entry)

    def _unwanted(self, entry: _Look) -> str | None:
        """`_dropped`'s answer. Holds `_changed`."""
        if self._looks.get(entry.qid) is not entry:
            return "forgotten"
        if entry.watchers == 0 and self._now() - entry.polled_at > UNWATCHED_AFTER:
            return "unwatched"
        return None

    def _abandon(self, entry: _Look, provider: str, why: str) -> bool:
        """Drop a queued ask before it starts, unless somebody now wants it; whether it was dropped.

        **Decided again here, under the lock that deletes the slot.** A look can
        arrive between `_dropped` and this, and would see the ask queued and not
        queue it again; dropping it anyway would lose the source from that look.
        """
        with self._changed:
            still = self._unwanted(entry)
            if still is None:
                return False
            slot = entry.slots.get(provider)
            if slot is not None and slot.answer is None:
                del entry.slots[provider]
            self._changed.notify_all()
        log.info(
            "dropped an ask nobody is waiting for before it started",
            extra={"event": "look.abandoned", "provider": provider, "reason": still or why},
        )
        return True

    def _judged(self, query: ImageQuery, link: WikidataLink, answer: SourceAnswer, judge: PhaseTwoEngine) -> SourceLook:
        """One source's answer, judged as phase 2 judges every answer."""
        if answer.outcome is AskOutcome.UNREACHABLE:
            return SourceLook(provider=answer.provider, state=SourceState.UNREACHABLE)
        if answer.outcome is AskOutcome.DECLINED:
            return SourceLook(provider=answer.provider, state=SourceState.CANNOT)
        kept: list[JudgedImage] = []
        refusals: set[UnresolvedReason] = set()
        for found in answer.images:
            outcome = judge.judge(query, found, link)
            if isinstance(outcome, UnresolvedReason):
                refusals.add(outcome)
            else:
                kept.append(outcome)
        kept.sort(key=judge.rank)
        if kept:
            state = SourceState.FOUND
        elif UnresolvedReason.IDENTITY_REFUSED in refusals:
            state = SourceState.REFUSED
        else:
            state = SourceState.HOLDS_NONE
        return SourceLook(
            provider=answer.provider,
            state=state,
            pictures=tuple(LookPicture(key=_key(entry_), judged=entry_) for entry_ in kept),
            refusals=frozenset(refusals),
        )

    def _view(self, entry: _Look, pool: ImageSourcePool, judge: PhaseTwoEngine) -> LookView:
        """The look as it stands: a row for every configured image source. Holds `_changed`.

        A source with no answer reads "asking", whatever its slot says, so a
        source is never missing from a look and a look never reads as finished
        while any source has not answered.
        """
        sources: list[SourceLook] = []
        for provider in pool.image_providers:
            slot = entry.slots.get(provider)
            answer = None if slot is None else slot.answer
            sources.append(answer if answer is not None else SourceLook(provider=provider, state=SourceState.ASKING))
        pictures = tuple(
            sorted((picture for source in sources for picture in source.pictures), key=lambda p: judge.rank(p.judged))
        )
        asking = any(source.state is SourceState.ASKING for source in sources)
        note = None
        if not asking and not pictures:
            note = (
                "No image source that answered holds a picture of this work now."
                if any(source.state is SourceState.UNREACHABLE for source in sources)
                else "No image source holds a picture of this work now."
            )
        return LookView(
            qid=entry.qid,
            state=LookState.ASKING if asking else LookState.ANSWERED,
            note=note,
            sources=tuple(sources),
            pictures=pictures,
        )

    # -- pictures ------------------------------------------------------------------

    def picture(self, qid: str, key: str, *, enlarged: bool = False) -> RenderedPreview | None:
        """A picture this work's current look found, from the picture store, as bytes a browser paints.

        `None` when the key is not one the work's current look names: another
        work's, a refused find's, or one from a look no longer kept. Refused
        (`ServiceError`) when the key is this look's and no picture could be
        kept or read, as a review card's picture is. Every line it logs, the
        store's included, carries the look's QID.
        """
        with look_context(qid):
            path = self._kept(qid, key, max_edge=ENLARGED_MAX_EDGE_PX if enlarged else BROWSER_MAX_EDGE_PX)
            if path is None:
                return None
            rendered = kept_preview(path)
            if rendered is None:
                raise ServiceError("The picture this source gave could not be read. Look again later.")
            log.info(
                "served a picture a look found",
                extra={"event": "look.picture_served", "key": key, "size": "large" if enlarged else "card"},
            )
            return rendered

    def look_for_a_model(
        self, qid: str, *, hold: float = LOOK_HOLD_SECONDS, budget: float = MODEL_LOOK_BUDGET_SECONDS
    ) -> tuple[LookView, Inlined]:
        """The look, held for the sources, and its best pictures inline, all within `budget` seconds.

        For `art_discovery(action='look')`, whose client abandons a call at a
        minute. The hold is the smaller of `hold` and the budget; what is left
        fetches the pictures not kept yet, together, and a picture that has not
        arrived when the budget runs out is `deferred`: its fetch goes on into
        the store, and the next call carries it.
        """
        deadline = time.monotonic() + budget
        view = self.look(qid, hold=min(hold, budget))
        return view, self._inline(view, deadline=deadline)

    def _inline(self, view: LookView, *, deadline: float) -> Inlined:
        """The first `INLINED` pictures, read from the store, fetching those it lacks in parallel until `deadline`."""
        with look_context(view.qid):
            previews: dict[str, InlinePreview] = {}
            failed: list[str] = []
            wanted = [picture for picture in view.pictures[:INLINED] if picture.key is not None]
            missing: list[LookPicture] = []
            for picture in wanted:
                path = self._already_kept(picture)
                if path is None:
                    missing.append(picture)
                    continue
                preview = inline_preview(path)
                (previews.__setitem__(picture.key, preview) if preview is not None else failed.append(picture.key))
            deferred: list[str] = []
            if missing:
                fetching = ThreadPoolExecutor(max_workers=len(missing), thread_name_prefix="look-picture")
                futures = {
                    fetching.submit(contextvars.copy_context().run, self._fetched, view.qid, picture): picture.key
                    for picture in missing
                }
                done, waiting = wait(futures, timeout=max(0.0, deadline - time.monotonic()))
                # Not waited for: a fetch still under way finishes into the store.
                fetching.shutdown(wait=False)
                for future in done:
                    preview = future.result()
                    (previews.__setitem__(futures[future], preview) if preview is not None else failed.append(futures[future]))
                deferred = [futures[future] for future in waiting]
            order = [picture.key for picture in wanted]
            return Inlined(
                previews={key: previews[key] for key in order if key in previews},
                deferred=tuple(key for key in order if key in deferred),
                failed=tuple(key for key in order if key in failed),
            )

    def _already_kept(self, picture: LookPicture) -> Path | None:
        """The store's file for a find at the inline size, if it keeps one, without fetching."""
        found = picture.judged.found
        try:
            return self._pictures.find_for(found.provider, found.url, max_edge=BROWSER_MAX_EDGE_PX)
        except OSError:
            return None

    def _fetched(self, qid: str, picture: LookPicture) -> InlinePreview | None:
        """A find's picture, fetched into the store and made small enough to travel; `None` when none could be."""
        try:
            path = self._kept(qid, picture.key or "", max_edge=BROWSER_MAX_EDGE_PX)
        except ServiceError:
            return None
        return None if path is None else inline_preview(path)

    def _kept(self, qid: str, key: str, *, max_edge: int) -> Path | None:
        """The kept file for a key this work's live look names, fetched into the store on a miss."""
        found = self._named(qid, key)
        if found is None:
            return None
        image = found.judged.found
        if image.preview_url is None:
            raise ServiceError("This source gave no picture of the work to show.")
        # The store answers from what it keeps, and fetches the preview once if
        # it keeps nothing yet. It never raises.
        stored = self._pictures.keep(image.provider, image.url, image.preview_url)
        path = None if stored is None else self._pictures.find(stored, max_edge=max_edge)
        if path is None:
            raise ServiceError("The source did not give a picture of this work that could be kept. Look again later.")
        return path

    def _named(self, qid: str, key: str) -> LookPicture | None:
        """The picture a work's look names by this key, in an answer still kept, or `None`."""
        now = self._now()
        with self._changed:
            entry = self._looks.get(qid)
            if entry is None:
                return None
            for slot in entry.slots.values():
                if slot.answer is None or slot.expires_at is None or slot.expires_at <= now:
                    continue
                for picture in slot.answer.pictures:
                    if picture.key is not None and picture.key == key:
                        return picture
        return None


def _key(judged: JudgedImage) -> str | None:
    """The store's key for a kept instance with a preview to keep; none for one without."""
    found = judged.found
    return None if found.preview_url is None else picture_key(found.provider, found.url)


def _stamped(result: SourceLook, *, answered_at: datetime, kept_for: timedelta) -> SourceLook:
    """An answer with when it was given and, for one that could not be asked, when it will be asked again."""
    return SourceLook(
        provider=result.provider,
        state=result.state,
        pictures=result.pictures,
        refusals=result.refusals,
        answered_at=answered_at,
        retry_at=answered_at + kept_for if result.state is SourceState.UNREACHABLE else None,
    )
