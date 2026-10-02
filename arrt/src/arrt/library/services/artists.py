"""The artists the library holds, and what a registry knows about each.

The Artist page's two halves (`build-plan-ia-foundations.md` Chunk 04): what the
library holds, which is always answerable, and what Wikidata knows, which may
not be. They are separate calls so that a registry that is slow, absent or down
leaves the first half working and says which of those it was.

**What Wikidata lists is capped and kept.** An artist can have thousands of
items there and a query takes seconds (`wikidata-findings.md`), so the page asks
for the most renowned, says how many more there are, and the answer is kept per
artist for a week, across restarts (`persistence/kept.py`). A failure is not
kept, so the next visit asks again.

**An artist the library does not hold has a page too**, addressed by QID: the
registry half alone, with every listed work still marked *Held* where the
library holds it. A QID that names an artist the library does hold answers with
that artist's id, so the page can send the curator to the full one.

**The works the library holds are always listed**, after the most renowned, so
they can be marked *Held*. Run against the owner's catalogue the first version
listed only the top fifty by renown, and none of the owner's Rothkos or their
Dalí was among them: the page that exists to say what is held said it of nothing.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Final

from arrt.library.registry import Registry, RegistryArtist, RegistrySimilar, RegistryUnavailable
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, REMEMBERED, checked_qid
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.folding import search_fold
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers
from arrt.persistence.records import Artist, ArtworkStatus
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)

#: How many of an artist's registry works the page lists: the most renowned.
WORKS_SHOWN: Final[int] = 50

#: How many holding collections it lists.
HOLDINGS_SHOWN: Final[int] = 10

#: How many similar artists it lists: enough for a next step, few enough that
#: the query (one to seven seconds, `wikidata-findings.md`) stays bounded.
SIMILAR_SHOWN: Final[int] = 12

#: How long every registry page section keeps an answer. Long enough that a
#: restart or a week of browsing asks nothing twice; short enough that an edit
#: made on Wikidata reaches the page within a week. The registry's sections share
#: it, so the Artist page and the pages it links to agree about how old they are.
REGISTRY_KEPT_FOR: Final[timedelta] = timedelta(days=7)

#: How many of the artist's own works are read to find the QIDs to list. Above
#: any one artist's holding at the owner's scale.
_THEIRS: Final[int] = 500


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
    #: Asked for by QID, and the library holds this artist: their own page is the
    #: answer, and the registry is not asked.
    HELD = "held"


@dataclass(frozen=True, slots=True)
class RegistryView:
    """The registry half of an Artist page."""

    state: RegistryState
    #: A sentence for the curator when the state is not `KNOWN`.
    note: str | None = None
    known: RegistryArtist | None = None
    #: The library's works in circulation for each registry work it holds, by
    #: QID. Usually one; several when held works share a QID, which is a
    #: duplicate the page shows rather than hides (`data-model.md` § Artwork).
    held: Mapping[str, Sequence[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimilarView:
    """The *Similar artists* section: who, or why there is nobody to show."""

    state: RegistryState
    note: str | None = None
    people: Sequence[RegistrySimilar] = ()
    #: The library's artist for each similar artist it holds, by QID.
    held: Mapping[str, str] = field(default_factory=dict)


class ArtistService:
    """Read the artists the library holds, and ask the registry about one."""

    def __init__(self, store: CatalogueStore, registry: Registry | None, *, kept: KeptAnswers) -> None:
        self._store = store
        self._registry = registry
        self._known_artists: Kept[tuple[str, tuple[str, ...]], RegistryArtist] = kept.namespace(
            "registry.artist", codec=JsonCodec(RegistryArtist), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._similar: Kept[str, tuple[RegistrySimilar, ...]] = kept.namespace(
            "registry.similar", codec=JsonCodec(tuple[RegistrySimilar, ...]), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

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
        theirs = self._store.list_artworks(
            WorkQuery(status=ArtworkStatus.ACCEPTED, artist_id=artist.id), limit=_THEIRS, offset=0
        ).artworks
        mine = sorted({work.wikidata_qid for work in theirs if work.wikidata_qid})
        return self._view(
            artist.wikidata_qid,
            mine,
            unavailable="Wikidata could not be asked just now. What the library holds is above; try again later.",
        )

    def registry_view_by_qid(self, qid: str) -> tuple[str | None, RegistryView]:
        """An artist the curator reached by QID: the library's artist with it, or what the registry knows.

        A held artist is answered from the library alone, so the page that sends
        the curator to their own page never waits on the registry.
        """
        held = artist_ids_by_qid(self._store).get(checked_qid(qid))
        if held is not None:
            return held, RegistryView(state=RegistryState.HELD, note="The library holds this artist.")
        return None, self._view(qid, (), unavailable="Wikidata could not be asked just now. Try again later.")

    def similar(self, qid: str) -> SimilarView:
        """Visual artists sharing a movement with this one, each marked where the library holds them.

        Kept per artist for a week, as the rest of the registry half is; a
        failure is not.
        """
        qid = checked_qid(qid)
        if self._registry is None:
            return SimilarView(
                state=RegistryState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
            )
        people = self._similar.get(qid)
        if people is None:
            try:
                people = tuple(self._registry.similar_to(qid, limit=SIMILAR_SHOWN))
            except RegistryUnavailable as exc:
                log.warning("Could not ask Wikidata for artists like %s: %s", qid, exc)
                return SimilarView(state=RegistryState.UNAVAILABLE, note="Wikidata could not be asked just now.")
            self._similar.put(qid, people)
        ours = artist_ids_by_qid(self._store)
        return SimilarView(
            state=RegistryState.KNOWN,
            people=people,
            held={person.qid: ours[person.qid] for person in people if person.qid in ours},
        )

    def _view(self, qid: str, mine: Sequence[str], *, unavailable: str) -> RegistryView:
        if self._registry is None:
            return RegistryView(
                state=RegistryState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
            )
        # "Held" means in circulation, as *In your library* does, so an archived
        # work is neither listed there nor marked here.
        holdings = self._store.circulating_ids_by_qid()
        try:
            known = self._known(qid, mine, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about %s: %s", qid, exc)
            return RegistryView(state=RegistryState.UNAVAILABLE, note=unavailable)
        return RegistryView(
            state=RegistryState.KNOWN,
            known=known,
            held={entry.qid: holdings[entry.qid] for entry in known.works if entry.qid in holdings},
        )

    def _known(self, qid: str, mine: Sequence[str], registry: Registry) -> RegistryArtist:
        # Keyed by what the library holds as well as by the artist, so a work
        # matched since the last visit is listed rather than served from memory.
        key = (qid, tuple(mine))
        kept = self._known_artists.get(key)
        if kept is not None:
            return kept
        # Asked between `get` and `put`, under no lock: a query takes seconds, and
        # another artist's page must not wait for this one's.
        known = registry.artist(qid, works=WORKS_SHOWN, holdings=HOLDINGS_SHOWN, include=mine)
        self._known_artists.put(key, known)
        return known


def artist_ids_by_qid(store: CatalogueStore) -> dict[str, str]:
    """Every catalogue artist carrying a QID, by it. Read whole: a few hundred rows at the library's scale.

    One artist per QID is what the identity service now enforces, for the curator
    and the matcher both. A catalogue written before that may hold two; then the
    first by name answers, every time, rather than whichever the store returned
    last, and the identity control is how the curator separates them.
    """
    found: dict[str, str] = {}
    for artist in sorted(store.list_artists(), key=lambda artist: (artist.name.casefold(), artist.id)):
        if artist.wikidata_qid:
            found.setdefault(artist.wikidata_qid, artist.id)
    return found
