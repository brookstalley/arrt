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
from dataclasses import dataclass, field, replace
from datetime import timedelta
from enum import StrEnum
from typing import Final, Protocol

from arrt.library.registry import Registry, RegistryArtist, RegistryPerson, RegistrySimilar, RegistryUnavailable
from arrt.library.services.identity import open_to_match, years_agree
from arrt.library.services.remembered import NOT_CONFIGURED_NOTE, REMEMBERED, checked_qid
from arrt.library.services.twins import AwaitingReview, InReview, Twins
from arrt.persistence.catalogue import CatalogueStore, WorkQuery
from arrt.persistence.folding import search_fold
from arrt.persistence.kept import JsonCodec, Kept, KeptAnswers
from arrt.persistence.records import Artist, ArtworkStatus, IdentitySetBy
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

#: How many of Wikidata's people an unlinked artist's page offers as who they
#: might be. A name search answers by renown, so the person meant is near the
#: top or the name is too common for a list to settle it.
CANDIDATES_SHOWN: Final[int] = 5

#: How many of the artist's own works are read to find the QIDs to list. Above
#: any one artist's holding at the owner's scale.
_THEIRS: Final[int] = 500


@dataclass(frozen=True, slots=True)
class HeldArtist:
    """An artist the library holds, and how many of their works are in circulation."""

    artist: Artist
    held: int
    #: The work the Artists index pictures them by: their first accepted work in
    #: circulation that holds a master image, else their first accepted work.
    #: None for an artist with nothing in circulation (`get` only).
    pictured: str | None = None


class RegistryState(StrEnum):
    """Why the registry half of the page says what it says."""

    #: The registry answered.
    KNOWN = "known"
    #: The artist carries no QID, so their works cannot be listed; the view may
    #: name who Wikidata says they might be (`RegistryView.candidates`).
    NO_IDENTITY = "no_identity"
    #: No registry is configured (`WIKIDATA_USER_AGENT` unset).
    NOT_CONFIGURED = "not_configured"
    #: The registry was asked and could not answer.
    UNAVAILABLE = "unavailable"
    #: Asked for by QID, and the library holds this artist: their own page is the
    #: answer, and the registry is not asked.
    HELD = "held"


@dataclass(frozen=True, slots=True)
class ArtistCandidate:
    """One person an unlinked artist might be, and whether their years agree with the library's."""

    person: RegistryPerson
    #: The matcher's own test (`identity.years_agree`): a year compared, and
    #: every one compared within a year. False when the library holds no years.
    years_agree: bool


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
    #: The QIDs among the listed works that a wanted work names.
    wanted: frozenset[str] = frozenset()
    #: The proposed work awaiting a verdict that each listed work not held is, by QID.
    waiting: Mapping[str, InReview] = field(default_factory=dict)
    #: For a library artist with no QID: who Wikidata's name search says they
    #: might be, those whose years agree with the library's first. Proposed,
    #: never stored: the curator's click stores one (`data-model.md` § Registry
    #: identity).
    candidates: Sequence[ArtistCandidate] = ()
    #: For an artist reached by QID: the library's artists of the same name who
    #: carry no QID, so the page can offer to link them to this one.
    unlinked: Sequence[Artist] = ()


@dataclass(frozen=True, slots=True)
class SimilarView:
    """The *Similar artists* section: who, or why there is nobody to show."""

    state: RegistryState
    note: str | None = None
    people: Sequence[RegistrySimilar] = ()
    #: The library's artist for each similar artist it holds, by QID.
    held: Mapping[str, str] = field(default_factory=dict)


class WantedItems(Protocol):
    """The one thing a page of registry works needs from discovery: which items are wanted.

    A work wanted through Review names a Wikidata item once it is matched, and
    every list of registry works marks it *Wanted* beside *Held* — the owner's
    ruling on #172 that the three states read apart. Taken as this one method,
    as the conversation takes its two, so these services do not depend on the
    whole discovery service.
    """

    def wanted_qids(self) -> frozenset[str]: ...


class ArtistService:
    """Read the artists the library holds, and ask the registry about one."""

    def __init__(
        self,
        store: CatalogueStore,
        registry: Registry | None,
        *,
        kept: KeptAnswers,
        wanted: WantedItems,
        awaiting: AwaitingReview,
    ) -> None:
        self._store = store
        self._registry = registry
        self._wanted = wanted
        self._awaiting = awaiting
        self._known_artists: Kept[tuple[str, tuple[str, ...]], RegistryArtist] = kept.namespace(
            "registry.artist", codec=JsonCodec(RegistryArtist), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._similar: Kept[str, tuple[RegistrySimilar, ...]] = kept.namespace(
            "registry.similar", codec=JsonCodec(tuple[RegistrySimilar, ...]), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )
        self._people: Kept[str, tuple[RegistryPerson, ...]] = kept.namespace(
            "registry.people", codec=JsonCodec(tuple[RegistryPerson, ...]), max_age=REGISTRY_KEPT_FOR, size=REMEMBERED
        )

    def index(self, q: str | None = None) -> Sequence[HeldArtist]:
        """Every artist with a work in circulation, by surname; narrowed to names containing `q`, ignoring accents.

        By surname, as a library shelves them (the owner's ruling on #173):
        `surname_key` says how a surname is found.
        """
        held = sorted(
            (HeldArtist(artist=artist, held=count, pictured=pictured) for artist, count, pictured in self._store.held_artists()),
            key=lambda entry: surname_key(entry.artist),
        )
        if not q or not q.strip():
            return held
        wanted = search_fold(q.strip())
        return [entry for entry in held if wanted in search_fold(entry.artist.name)]

    def get(self, artist_id: str) -> HeldArtist:
        """One artist, and how many of their works are in circulation (which may be none)."""
        artist = self._store.get_artist(artist_id)
        if artist is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        held, pictured = next(
            ((count, first) for found, count, first in self._store.held_artists() if found.id == artist_id), (0, None)
        )
        return HeldArtist(artist=artist, held=held, pictured=pictured)

    def registry_view(self, artist_id: str) -> RegistryView:
        """What the registry knows about this artist, or why there is nothing to show."""
        artist = self.get(artist_id).artist
        if artist.wikidata_qid is None:
            return self._unlinked_view(artist)
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
        view = self._view(qid, (), unavailable="Wikidata could not be asked just now. Try again later.")
        if view.known is None or not view.known.name:
            return None, view
        # Folded, as search folds a name: the library's "Aleksandra Ekster" and
        # Wikidata's are one spelling only once accents and case are set aside.
        wanted = search_fold(view.known.name)
        namesakes = tuple(
            artist
            for artist in sorted(self._store.list_artists(), key=lambda artist: (artist.name.casefold(), artist.id))
            if open_to_match(artist) and search_fold(artist.name) == wanted
        )
        return None, replace(view, unlinked=namesakes)

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

    def _unlinked_view(self, artist: Artist) -> RegistryView:
        """The registry half for an artist with no QID: who they might be, or why nobody is offered."""
        if artist.wikidata_qid_set_by is IdentitySetBy.CURATOR:
            return RegistryView(
                state=RegistryState.NO_IDENTITY,
                note="You said Wikidata has no item for this artist, so there is nothing more to show about them.",
            )
        unmatched = "This artist is not matched to Wikidata yet, so their other works cannot be listed."
        if self._registry is None:
            return RegistryView(state=RegistryState.NO_IDENTITY, note=unmatched)
        people = self._people.get(artist.name)
        if people is None:
            try:
                people = tuple(self._registry.people_named(artist.name))
            except RegistryUnavailable as exc:
                log.warning("Could not ask Wikidata who %s might be: %s", artist.name, exc)
                return RegistryView(
                    state=RegistryState.NO_IDENTITY,
                    note=f"{unmatched} Wikidata could not be asked who they might be just now.",
                )
            self._people.put(artist.name, people)
        # One item, one artist, as the identity service enforces: an item
        # another library artist carries would be refused if chosen.
        taken = artist_ids_by_qid(self._store)
        open_people = [person for person in people if person.qid not in taken]
        # Stable, so within each half the registry's renown order stands.
        ranked = sorted(open_people, key=lambda person: not years_agree(artist, person))
        return RegistryView(
            state=RegistryState.NO_IDENTITY,
            note=unmatched,
            candidates=tuple(
                ArtistCandidate(person=person, years_agree=years_agree(artist, person)) for person in ranked[:CANDIDATES_SHOWN]
            ),
        )

    def _view(self, qid: str, mine: Sequence[str], *, unavailable: str) -> RegistryView:
        if self._registry is None:
            return RegistryView(
                state=RegistryState.NOT_CONFIGURED,
                note=NOT_CONFIGURED_NOTE,
            )
        try:
            known = self._known(qid, mine, self._registry)
        except RegistryUnavailable as exc:
            log.warning("Could not ask Wikidata about %s: %s", qid, exc)
            return RegistryView(state=RegistryState.UNAVAILABLE, note=unavailable)
        wanted = self._wanted.wanted_qids()
        # "Held" means in circulation, as *In your library* does, so an archived
        # work is neither listed there nor marked here. Matched by QID, or by
        # title and this artist for a held work with none (`twins.py`).
        twins = Twins(self._store, self._awaiting)
        held: dict[str, Sequence[str]] = {}
        waiting: dict[str, InReview] = {}
        for entry in known.works:
            if found := twins.held_work(entry.qid, entry.title, maker=known.name, maker_qid=known.qid):
                held[entry.qid] = found
            elif (review := twins.waiting_work(entry.qid, entry.title, maker=known.name, maker_qid=known.qid)) is not None:
                waiting[entry.qid] = review
        return RegistryView(
            state=RegistryState.KNOWN,
            known=known,
            held=held,
            wanted=frozenset(entry.qid for entry in known.works if entry.qid in wanted),
            waiting=waiting,
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


#: What follows a name and is not its surname: "the Younger" in Hans Holbein
#: the Younger. Matched as whole trailing words, folded.
GENERATIONAL_SUFFIXES: Final = (("the", "elder"), ("the", "younger"), ("jr",), ("sr",), ("jr.",), ("sr.",))


def surname_key(artist: Artist) -> tuple[str, str, str]:
    """Where an artist sorts on a surname shelf: by surname, then whole name, then id.

    The surname is the stored `family_name` where the catalogue holds one (the
    seed and the catalogue write it for the wall label); otherwise the last
    word once a generational suffix is set aside, so *Hans Holbein the Younger*
    sorts under H, *Vincent van Gogh* under G (a particle such as "van" is never
    the last word, so it never decides), and a single name such as *Moche*
    under itself. Folded, so accents and case do not move anyone.
    """
    folded = search_fold(artist.name)
    if artist.family_name:
        surname = search_fold(artist.family_name)
    else:
        words = folded.replace(",", " ").split()
        for suffix in GENERATIONAL_SUFFIXES:
            if tuple(words[-len(suffix) :]) == suffix:
                words = words[: -len(suffix)]
                break
        surname = words[-1] if words else folded
    return (surname, folded, artist.id)


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
