"""Sightings: pages about a work that no installed plugin reads, and the hosts they are on.

A finder that knows a page only by its address, as the Wikidata finder knows
MoMA's from an identifier, offers it as a `FoundPage`. Each is given to the
installed plugins' claims, and one that none claims is recorded here, keyed by
the work's item (`source-plugins.md` § Sightings). A page a plugin claims is that
plugin's to find, and is journalled and left to it: turning a page into an image
needs a reader that reports the image's size, which no reader does yet.

**Only question 1 is answered here**: which hosts hold pages for the works still
open, so that the next reader to build is chosen by a count rather than by hand.
Questions 2 and 3 are readings the stored rows allow and nothing asks yet.

**A sighting's URL never leaves the server.** It came from a registry anyone can
edit, so the answer below names hosts and counts works, and carries no address
(`security-model.md` § Direction).
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from arrt.library.discovery.images import FoundPage
from arrt.library.sources.loading import Route
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import Sighting

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HostCount:
    """One host, and how many open works it has a page for that nothing here reads."""

    host: str
    works: int


class SightingService:
    """Record the pages no installed plugin claims, and count them by host."""

    def __init__(self, store: DiscoveryStore, catalogue: CatalogueStore, *, route: Callable[[str], Route]) -> None:
        self._store = store
        self._catalogue = catalogue
        #: Which installed plugin, if any, claims a URL: the same routing
        #: acquisition uses, so a page a plugin claims is never counted as one
        #: nothing reads.
        self._route = route

    def record(self, qid: str | None, pages: Sequence[FoundPage], *, work_title: str) -> int:
        """Store each page no installed plugin claims, once. How many were new.

        A work with no item has no key to store a sighting under, so its pages
        are journalled and not stored. Only the Wikidata finder offers pages
        today, and it answers only for a work with an item.
        """
        if not pages:
            return 0
        if qid is None:
            log.info(
                "pages were found for a work with no Wikidata item; a sighting is keyed by the item, so none is kept",
                extra={"event": "sightings.no_item", "work_title": work_title, "pages": len(pages)},
            )
            return 0
        new = 0
        for page in pages:
            claimant = self._route(page.url).plugin
            if claimant is not None:
                log.info(
                    "a page found for a work is claimed by the %s plugin, and left to it",
                    claimant,
                    extra={"event": "sightings.claimed", "plugin": claimant, "host": _host(page.url), "work_title": work_title},
                )
                continue
            new += self._store.add_sighting(Sighting(wikidata_qid=qid, url=page.url))
        log.info(
            "recorded the pages no installed plugin reads",
            extra={"event": "sightings.recorded", "work_title": work_title, "pages": len(pages), "new": new},
        )
        return new

    def hosts(self) -> Sequence[HostCount]:
        """Each host with a page for a work still open, by how many such works, most first.

        Open means wanted, or unresolved with no verdict yet. A work the catalogue
        holds is left out, whatever its other runs say, and so is a page an
        installed plugin claims now: a reader installed since the page was seen
        has already answered the question this count asks.
        """
        held = set(self._catalogue.circulating_ids_by_qid())
        works: dict[str, set[str]] = {}
        for sighting in self._store.list_open_sightings():
            if sighting.wikidata_qid in held or self._route(sighting.url).plugin is not None:
                continue
            host = _host(sighting.url)
            if host is not None:
                works.setdefault(host, set()).add(sighting.wikidata_qid)
        counted = [HostCount(host=host, works=len(items)) for host, items in works.items()]
        return sorted(counted, key=lambda entry: (-entry.works, entry.host))


def _host(url: str) -> str | None:
    """The host a page is on, as a name, lowercased; None for a URL with none."""
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None
