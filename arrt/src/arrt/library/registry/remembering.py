"""The registry the plugins and phase 2 are handed: Wikidata, with each work's pages asked once.

**One Get asks every finder at once, and most of them begin with the same
question**: which pages does the work's Wikidata item record (`pages_about`)?
Asked of a bare registry, that is one identical query to the query service per
finder, all in the same moment, and the service limits how many one client may
run at once. A throttled answer reads as "could not be asked", so every plugin
added made every Get likelier to wait.

So the answer is remembered per item for `PAGES_REMEMBERED_SECONDS`, and the
finders asking for one item at the same moment share one request: the first
asks, and the rest wait for its answer. Ten minutes outlasts a run's phase 2,
which asks again after its finders, and is short enough that an edit on Wikidata
is seen in the same session.

**A failure is shared, never remembered.** The finders waiting on a request that
failed are told it failed, since the next request a moment later would most
likely fail the same way; the next ask after that asks again, because an outage
is not an answer about the item.

Every other question passes straight to the registry underneath: they are asked
by one caller at a time, and what each answers changes with what is asked.
"""

import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Final

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    MuseumIdentifier,
    Registry,
    RegistryArtist,
    RegistryImageSize,
    RegistryPerson,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicsOf,
    RegistryTopicWork,
    RegistryTopicWorksStage,
    RegistryUnavailable,
    RegistryWork,
    RegistryWorkMatch,
    WorkPage,
)
from arrt.library.registry.identifiers import IdentifierScheme

#: How long one item's pages are remembered (the owner's ten minutes).
PAGES_REMEMBERED_SECONDS: Final[float] = 600.0

#: How long a caller waits for another caller's request for the same item before
#: it is told the registry could not be asked. As long as a finder's own deadline
#: (`library/sources/loading.py`), past which nobody is listening anyway.
SHARED_WAIT_SECONDS: Final[float] = 60.0


class RememberingRegistry:
    """A `Registry` that remembers `pages_about` per item, and asks it once for callers asking together."""

    def __init__(
        self,
        inner: Registry,
        *,
        remember_for: float = PAGES_REMEMBERED_SECONDS,
        shared_wait: float = SHARED_WAIT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._remember_for = remember_for
        self._shared_wait = shared_wait
        self._clock = clock
        self._lock = threading.Lock()
        #: Item → when its pages were answered, and what they were.
        self._kept: dict[str, tuple[float, tuple[WorkPage, ...]]] = {}
        #: Item → the request for its pages now under way, which later askers wait on.
        self._asking: dict[str, Future[tuple[WorkPage, ...]]] = {}

    @property
    def inner(self) -> Registry:
        """The registry every question reaches in the end."""
        return self._inner

    def pages_about(self, qid: str) -> Sequence[WorkPage]:
        with self._lock:
            kept = self._kept.get(qid)
            if kept is not None and self._clock() - kept[0] < self._remember_for:
                # A list of its own each time, so a caller that changes its copy
                # changes nobody else's.
                return list(kept[1])
            asking = self._asking.get(qid)
            first = asking is None
            if asking is None:
                asking = self._asking[qid] = Future()
        if not first:
            try:
                return list(asking.result(timeout=self._shared_wait))
            except FutureTimeout:
                raise RegistryUnavailable(
                    f"The registry did not answer another caller's question about {qid} within {self._shared_wait:g} seconds."
                ) from None
        try:
            pages = tuple(self._inner.pages_about(qid))
        except BaseException as exc:
            with self._lock:
                del self._asking[qid]
            asking.set_exception(exc)
            raise
        with self._lock:
            now = self._clock()
            # Forgotten as they expire, so what is kept is at most the items
            # asked about in the last ten minutes.
            for item in [item for item, (at, _pages) in self._kept.items() if now - at >= self._remember_for]:
                del self._kept[item]
            self._kept[qid] = (now, pages)
            del self._asking[qid]
        asking.set_result(pages)
        return list(pages)

    # Everything else is the registry's own, unchanged.

    def works_by_identifier(
        self, scheme: IdentifierScheme, values: Sequence[str]
    ) -> Mapping[MuseumIdentifier, frozenset[ItemId]]:
        return self._inner.works_by_identifier(scheme, values)

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[ItemId, frozenset[ItemId]]:
        return self._inner.creators_of(work_qids)

    def people_named(self, name: str) -> Sequence[RegistryPerson]:
        return self._inner.people_named(name)

    def artist(self, qid: str, *, works: int, holdings: int, include: Sequence[str] = ()) -> RegistryArtist:
        return self._inner.artist(qid, works=works, holdings=holdings, include=include)

    def work(self, qid: str) -> RegistryWork | None:
        return self._inner.work(qid)

    def image_size(self, image: CommonsFile) -> RegistryImageSize | None:
        return self._inner.image_size(image)

    def label_of(self, qid: str) -> RegistryText | None:
        return self._inner.label_of(qid)

    def similar_to(self, qid: str, *, limit: int) -> Sequence[RegistrySimilar]:
        return self._inner.similar_to(qid, limit=limit)

    def works_matching(self, words: Sequence[str], *, prefix: bool, limit: int) -> Sequence[RegistryWorkMatch]:
        return self._inner.works_matching(words, prefix=prefix, limit=limit)

    def topic(self, qid: str) -> RegistryTopic | None:
        return self._inner.topic(qid)

    def topic_works(self, topic: RegistryTopic, *, limit: int) -> Sequence[RegistryTopicWork]:
        return self._inner.topic_works(topic, limit=limit)

    def topic_works_in_stages(self, topic: RegistryTopic, *, limit: int) -> Iterator[RegistryTopicWorksStage]:
        return self._inner.topic_works_in_stages(topic, limit=limit)

    def topic_artists(self, topic: RegistryTopic, *, limit: int) -> Sequence[RegistrySimilar]:
        return self._inner.topic_artists(topic, limit=limit)

    def topics_named(self, text: str) -> Sequence[RegistryTopic]:
        return self._inner.topics_named(text)

    def topics_of(self, work_qids: Sequence[str], artist_qids: Sequence[str]) -> RegistryTopicsOf:
        return self._inner.topics_of(work_qids, artist_qids)

    def creator_names(self, qid: str) -> Mapping[ItemId, frozenset[RegistryText]]:
        return self._inner.creator_names(qid)
