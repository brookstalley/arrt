"""Every wired image source, asked at once, and the answers kept apart by source.

Phase 2 used to reach one museum. The owner asked for a pool instead, with no
source special-cased: each source is an `ImageSearch`, every one of them is asked
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
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from arrt.library.discovery.images import (
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearch,
    ImageSearchFailure,
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

    `unreachable` names the sources that could not be asked. It is empty when
    every source answered, which is the only case in which an empty `images`
    means no source holds the work.
    """

    images: Sequence[FoundImage]
    unreachable: tuple[str, ...]


class ImageSourcePool:
    """The image sources phase 2 asks, in order of preference."""

    def __init__(self, sources: Sequence[ImageSearch]) -> None:
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
        self._sources: tuple[ImageSearch, ...] = tuple(sources)
        self._by_name: dict[str, ImageSearch] = dict(zip(names, self._sources, strict=True))

    @property
    def providers(self) -> tuple[str, ...]:
        """The sources' names, most preferred first."""
        return tuple(self._by_name)

    def precedence(self, provider: str) -> int:
        """Where a source stands in the preference order; lower is preferred."""
        self._source(provider)
        return self.providers.index(provider)

    def find_images(self, query: ImageQuery) -> PoolAnswer:
        """Ask every source for the work at once, and say which could not be asked.

        A source that cannot look a work like this up is left out, as if not
        wired. Raises `ImageSearchFailure` only when no source answered, because
        then there is no answer at all. A source raising anything other than
        `ImageSearchFailure` is a fault in that source and propagates.
        """
        with ThreadPoolExecutor(max_workers=len(self._sources), thread_name_prefix="image-source") as workers:
            # Each call runs in a copy of the caller's context, so what a source
            # logs from its worker thread still carries the run it is working for.
            pending = [
                (source.provider, workers.submit(contextvars.copy_context().run, source.find_images, query))
                for source in self._sources
            ]
            images: list[FoundImage] = []
            unreachable: list[str] = []
            declined: list[str] = []
            for provider, future in pending:
                try:
                    images.extend(future.result())
                except ImageQueryUnanswerable:
                    # Not asked, in effect: this source has nothing to say about
                    # works like this one, which is neither "holds none" nor "down".
                    declined.append(provider)
                except ImageSearchFailure as exc:
                    log.warning(
                        "an image source could not be asked for a work: %s",
                        exc,
                        extra={"event": "image_pool.unreachable", "provider": provider, "work_title": query.title},
                    )
                    unreachable.append(provider)
        if len(unreachable) + len(declined) == len(self._sources):
            # No source answered. Nothing is known about the work, so it is not
            # recorded as held by nobody; it waits, as when every source is down.
            if unreachable:
                raise ImageSearchFailure(f"No image source could be asked: {', '.join(unreachable)}.")
            raise NoSourceCanAnswer(f"No image source can look this work up: {', '.join(declined)} cannot.")
        return PoolAnswer(images=tuple(images), unreachable=tuple(unreachable))

    def fetch_preview(self, provider: str, url: str) -> bytes | None:
        """The preview bytes, from the source the instance was recorded under."""
        return self._source(provider).fetch_preview(url)

    def tile_targets(self) -> Mapping[str, Callable[[str], str]]:
        """Each source's tile resolver, keyed by the name its instances carry."""
        return {name: source.tile_url for name, source in self._by_name.items()}

    def _source(self, provider: str) -> ImageSearch:
        try:
            return self._by_name[provider]
        except KeyError:
            # Every instance phase 2 records carries the name of a source in this
            # pool, so a name it does not know is a wiring fault. Guessing a
            # source would send one museum's URL to another.
            raise ValueError(
                f"No image source named {provider!r} is wired; the sources are {', '.join(self.providers)}."
            ) from None
