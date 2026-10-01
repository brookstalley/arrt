"""The artists the library holds, and what a registry knows about each.

The Artist page's two halves (`build-plan-ia-foundations.md` Chunk 04): what the
library holds, which is always answerable, and what Wikidata knows, which may
not be. They are separate calls so that a registry that is slow, absent or down
leaves the first half working and says which of those it was.

**What Wikidata lists is capped and remembered.** An artist can have thousands of
items there and a query takes seconds (`wikidata-findings.md`), so the page asks
for the most renowned, says how many more there are, and the answer is kept per
artist for the life of the process. A failure is not kept, so the next visit asks
again.

**The works the library holds are always listed**, after the most renowned, so
they can be marked *Held*. Run against the owner's catalogue the first version
listed only the top fifty by renown, and none of the owner's Rothkos or their
Dalí was among them: the page that exists to say what is held said it of nothing.
"""

import logging
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from arrt.library.registry import Registry, RegistryArtist, RegistryUnavailable
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.folding import search_fold
from arrt.persistence.records import Artist
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How many of an artist's registry works the page lists: the most renowned.
WORKS_SHOWN: Final[int] = 50

#: How many holding collections it lists.
HOLDINGS_SHOWN: Final[int] = 10

#: How many of the artist's own works are read to find the QIDs to list. Above
#: any one artist's holding at the owner's scale.
_THEIRS: Final[int] = 500

#: How many artists' registry answers are remembered. Above the library's artist
#: count by a margin, so a curator browsing artists never evicts the one they
#: came from.
_REMEMBERED: Final[int] = 512


@dataclass(frozen=True, slots=True)
class HeldArtist:
    """An artist the library holds, and how many of their works are in circulation."""

    artist: Artist
    held: int


class RegistryState(StrEnum):
    """Why the registry half of the page says what it says."""

    #: The registry answered.
    KNOWN = "known"
    #: The artist carries no QID, so there is nothing to ask about.
    NO_IDENTITY = "no_identity"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RegistryView:
    """The registry half of an Artist page."""

    state: RegistryState
    #: A sentence for the curator when the state is not `KNOWN`.
    note: str | None = None
    known: RegistryArtist | None = None
    #: The library's work for each registry work it holds, by QID.
    held: Mapping[str, str] = field(default_factory=dict)


class ArtistService:
    """Read the artists the library holds, and ask the registry about one."""

    def __init__(self, store: CatalogueStore, registry: Registry | None) -> None:
        self._store = store
        self._registry = registry
        self._remembered: OrderedDict[tuple[str, tuple[str, ...]], RegistryArtist] = OrderedDict()
        self._lock = threading.Lock()

    def index(self, q: str | None = None) -> Sequence[HeldArtist]:
        """Every artist with a work in circulation, by name; narrowed to names containing `q`, ignoring accents."""
        held = [HeldArtist(artist=artist, held=count) for artist, count in self._store.held_artists()]
        if not q or not q.strip():
            return held
        wanted = search_fold(q.strip())
        return [entry for entry in held if wanted in search_fold(entry.artist.name)]

    def get(self, artist_id: str) -> HeldArtist:
        """One artist, and how many of their works are in circulation (which may be none)."""
        artist = self._store.get_artist(artist_id)
        if artist is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        held = next((count for found, count in self._store.held_artists() if found.id == artist_id), 0)
        return HeldArtist(artist=artist, held=held)

    def registry_view(self, artist_id: str) -> RegistryView:
        """What the registry knows about this artist, or why there is nothing to show."""
        artist = self.get(artist_id).artist
        if artist.wikidata_qid is None:
            return RegistryView(
                state=RegistryState.NO_IDENTITY,
                note="This artist is not matched to Wikidata, so there is nothing more to show about them yet.",
            )
        if self._registry is None:
            return RegistryView(
                state=RegistryState.NOT_CONFIGURED,
                note="Wikidata is not configured on this server (WIKIDATA_USER_AGENT is unset).",
            )
        holdings = self._store.artwork_ids_by_qid()
        theirs = self._store.list_artworks(WorkQuery(artist_id=artist.id), limit=_THEIRS, offset=0).artworks
        mine = sorted({work.wikidata_qid for work in theirs if work.wikidata_qid})
        try:
            known = self._known(artist.wikidata_qid, mine, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about %s (%s): %s", artist.name, artist.wikidata_qid, exc)
            return RegistryView(
                state=RegistryState.UNAVAILABLE,
                note="Wikidata could not be asked just now. What the library holds is above; try again later.",
            )
        return RegistryView(
            state=RegistryState.KNOWN,
            known=known,
            held={entry.qid: holdings[entry.qid] for entry in known.works if entry.qid in holdings},
        )

    def _known(self, qid: str, mine: Sequence[str], registry: Registry) -> RegistryArtist:
        # Keyed by what the library holds as well as by the artist, so a work
        # matched since the last visit is listed rather than served from memory.
        key = (qid, tuple(mine))
        with self._lock:
            if key in self._remembered:
                self._remembered.move_to_end(key)
                return self._remembered[key]
        # Asked outside the lock: a query takes seconds, and another artist's page
        # must not wait for this one's.
        known = registry.artist(qid, works=WORKS_SHOWN, holdings=HOLDINGS_SHOWN, include=mine)
        with self._lock:
            self._remembered[key] = known
            while len(self._remembered) > _REMEMBERED:
                self._remembered.popitem(last=False)
        return known
