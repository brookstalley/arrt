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

**A source that could not be asked is reported, not folded into the answer.** An
empty list from a source means it was asked and holds nothing; a failure means
nothing is known about what it holds. The pool keeps the two apart all the way
to phase 2, because only the judgement there can say whether what the other
sources found is enough to call the work resolved. A work called unresolved
because one server was down would tell a curator the painting is not out there.
"""

import contextvars
import logging
import threading
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum

from arrt.library.discovery.images import (
    Finder,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    offers_images,
)

log = logging.getLogger(__name__)


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
    """

    images: Sequence[FoundImage]
    unreachable: tuple[str, ...]
    pages: tuple[FoundPage, ...] = ()


class AskOutcome(StrEnum):
    """How one source took one question: the three answers the pool keeps apart."""

    #: It was asked and answered, with whatever it holds, nothing included.
    ANSWERED = "answered"
    #: It cannot look a work like this one up (`ImageQueryUnanswerable`):
    #: neither "holds none" nor "down".
    DECLINED = "declined"
    #: It could not be asked (`ImageSearchFailure`): nothing is known about
    #: what it holds.
    UNREACHABLE = "unreachable"


@dataclass(frozen=True, slots=True)
class SourceAnswer:
    """What one source said about one work, sorted the way the pool sorts every answer.

    `images` and `pages` are what it handed over before it answered or failed:
    a finder that yields some results and then raises has said those, and the
    pool has always kept them.
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


class ImageSourcePool:
    """The image sources phase 2 asks, in order of preference."""

    def __init__(self, sources: Sequence[Finder]) -> None:
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

    def find_images(self, query: ImageQuery) -> PoolAnswer:
        """Ask every source for the work at once, and say which could not be asked.

        A source that cannot look a work like this up is left out, as if not
        wired. Raises `ImageSearchFailure` only when no source answered, because
        then there is no answer at all. A source raising anything other than
        `ImageSearchFailure` is a fault in that source and propagates. A plugin's
        finder never gets that far: the loader wraps it so that a fault arrives
        here as `ImageSearchFailure` (`library/sources/loading.py`). A finder
        handed to the pool directly, as in most tests, still propagates.
        """
        with ThreadPoolExecutor(max_workers=len(self._sources), thread_name_prefix="image-source") as workers:
            # Each call runs in a copy of the caller's context, so what a source
            # logs from its worker thread still carries the run it is working for.
            pending = []
            for source in self._sources:
                # Counted here, before the worker starts, so a look asking in
                # the gap between this call and the worker sees the run already.
                with self._runs_done:
                    self._run_asks[source.provider] += 1
                pending.append(workers.submit(contextvars.copy_context().run, self._ask_for_a_run, source.provider, query))
            images: list[FoundImage] = []
            pages: dict[FoundPage, None] = {}
            answered: list[str] = []
            pages_only: list[str] = []
            unreachable: list[str] = []
            declined: list[str] = []
            for future in pending:
                answer = future.result()
                images.extend(answer.images)
                for page in answer.pages:
                    pages[page] = None
                if answer.outcome is AskOutcome.ANSWERED:
                    # A finder of pages answering says nothing about whether an
                    # image exists, so it is not a source that answered.
                    (answered if answer.offers_images else pages_only).append(answer.provider)
                elif answer.outcome is AskOutcome.DECLINED:
                    # Not asked, in effect: this source has nothing to say about
                    # works like this one, which is neither "holds none" nor "down".
                    declined.append(answer.provider)
                else:
                    log.warning(
                        "an image source could not be asked for a work: %s",
                        answer.failure,
                        extra={"event": "image_pool.unreachable", "provider": answer.provider, "work_title": query.title},
                    )
                    # Only a source of images leaves the work in doubt. A finder
                    # of pages that could not be asked holds no image either way,
                    # and counting it would keep a work waiting that every source
                    # of images has answered for.
                    (unreachable if answer.offers_images else pages_only).append(answer.provider)
        if not answered:
            # No source of images answered. Nothing is known about the work, so
            # it is not recorded as held by nobody; it waits, as when every source
            # is down. The pages found are dropped with the answer, and a later
            # search of the work finds them again.
            if unreachable:
                raise ImageSearchFailure(f"No image source could be asked: {', '.join(unreachable)}.")
            cannot = [*(f"{name} cannot" for name in declined), *(f"{name} finds pages only" for name in pages_only)]
            raise NoSourceCanAnswer(f"No image source can look this work up: {'; '.join(cannot)}.")
        return PoolAnswer(images=tuple(images), unreachable=tuple(unreachable), pages=tuple(pages))

    def ask(self, provider: str, query: ImageQuery) -> SourceAnswer:
        """Ask one source about one work, and sort its answer as the pool sorts every answer.

        `find_images` is this, at every source at once, folded together; a look
        asks one source at a time with it. A source raising anything other than
        `ImageSearchFailure` (or `ImageQueryUnanswerable`) propagates, as it does
        from `find_images`.
        """
        source = self._source(provider)
        images: list[FoundImage] = []
        pages: list[FoundPage] = []
        offers = offers_images(source)
        try:
            for found in source.find_images(query):
                (pages if isinstance(found, FoundPage) else images).append(found)
        except ImageQueryUnanswerable:
            outcome, failure = AskOutcome.DECLINED, None
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

    def _ask_for_a_run(self, provider: str, query: ImageQuery) -> SourceAnswer:
        """`ask`, for a run, releasing the source to waiting looks however it ends."""
        try:
            return self.ask(provider, query)
        finally:
            with self._runs_done:
                self._run_asks[provider] -= 1
                if self._run_asks[provider] <= 0:
                    del self._run_asks[provider]
                    self._runs_done.notify_all()

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
