"""Reading: from a URL a plugin recognises to how its image is fetched.

A finder answers "where is an image of this work"; a reader answers "given this
page, how are its pixels got". They depend on different things, the holder and the
protocol, which is why a plugin may provide either (`source-plugins.md` § Finding
and reading are different jobs). Arrt does the fetching itself, through its own
address checks and size bounds, so a reader says *how* and never fetches the image.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class LocatorKind(StrEnum):
    """How Arrt is to fetch what a reader found."""

    #: An image URL, fetched over HTTP.
    DIRECT = "direct"
    #: A URL `dezoomify-rs` reads: a IIIF `info.json`, a Google Arts & Culture
    #: page, or another format it supports.
    TILES = "tiles"
    #: The page is the one the reader expected, and it shows no image. Not the
    #: same as could-not-be-asked: the holder answered, and said there is nothing.
    NONE = "none"


@dataclass(frozen=True, slots=True)
class FetchLocator:
    """A reader's answer: what to fetch, and how; or why there is nothing to fetch."""

    kind: LocatorKind
    #: The address to fetch. Set for `DIRECT` and `TILES`, never for `NONE`.
    url: str | None = None
    #: Why a `NONE` page shows no image, in the holder's terms.
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is LocatorKind.NONE) != (self.url is None):
            raise ValueError("A locator carries a URL to fetch exactly when it is not NONE.")
        if self.kind is LocatorKind.NONE and not self.reason:
            raise ValueError("A NONE locator says why the page shows no image.")

    @classmethod
    def direct(cls, url: str) -> FetchLocator:
        return cls(LocatorKind.DIRECT, url=url)

    @classmethod
    def tiles(cls, url: str) -> FetchLocator:
        return cls(LocatorKind.TILES, url=url)

    @classmethod
    def none(cls, reason: str) -> FetchLocator:
        return cls(LocatorKind.NONE, reason=reason)


@runtime_checkable
class Reader(Protocol):
    """A plugin's reader: the URLs its plugin claims, turned into something Arrt can fetch.

    Which URLs those are is declared on the plugin (`SourcePlugin.claims`), not
    here, because Arrt needs to know which plugin a URL needs even when that
    plugin is not loaded: an Art Institute source with no `ARTIC_USER_AGENT` set
    is a fault in this deployment, and saying so means naming the plugin.
    """

    def read(self, url: str) -> FetchLocator:
        """How the image at a claimed URL is fetched.

        Raises `ImageSearchFailure` when the holder could not be asked, or answered
        with something other than the page expected (a page saying "this site is
        unavailable" is that, never "no image"). May do I/O; it is called once per
        acquisition, not to decide whether the URL is this plugin's.
        """
