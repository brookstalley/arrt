"""Which held work or artist a registry row is, and which registry work already waits in To review.

**A registry row is its held twin wherever the stored Wikidata ID matches**
(ruling 7 of 2026-10-01, `ia-proposal.md`). Until every held work and artist
carries one, a held work with no ID is matched by its normalised title and
artist (`work_dedup_key`, the key discovery already dedups by), and a held
artist with no ID by name and life dates (`identity.years_agree`). A held work
or artist that does carry an ID is matched by it alone: a different ID names a
different item, whatever the title says. One the curator said has no item is
never matched: they said it is no registry row.

The title-and-artist key inherits that key's limit: two works by one artist
sharing a title ("Untitled") read as one, so a held *Untitled* folds every
registry *Untitled* by the same artist until it carries its ID.

**A work waits for review** when a run found an image for it and it has no
verdict yet, the works *To review* counts. A registry work matches one by the
item the work was chosen by, or, for a work proposed by name, by the same title
and artist key. Such a work is not offered for a Get: a run has already found
it, and a second would pay for it twice.

Read once per answer: a handful of reads, each one row per work or artist,
which at the library's scale is thousands of rows at most.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from arrt.library.discovery.dedup import artist_key, work_dedup_key
from arrt.library.registry import RegistryPerson
from arrt.library.services.identity import open_to_match, years_agree
from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.discovery_records import CandidateWork
from arrt.persistence.folding import search_fold
from arrt.persistence.records import Artist


@dataclass(frozen=True, slots=True)
class InReview:
    """A proposed work waiting for a verdict: the run whose review it is on, and the work there."""

    run_id: str
    candidate_work_id: str


class AwaitingReview(Protocol):
    """The one thing a page of registry rows needs from discovery to mark what waits for review."""

    def works_awaiting_review(self) -> Sequence[CandidateWork]: ...


class Twins:
    """The library's holdings and the works awaiting review, indexed to match registry rows against."""

    def __init__(self, store: CatalogueStore, awaiting: AwaitingReview) -> None:
        self._held_by_qid = store.circulating_ids_by_qid()
        artists = sorted(store.list_artists(), key=lambda artist: (artist.name.casefold(), artist.id))
        names = {artist.id: artist.name for artist in artists}
        #: Every artist carrying a QID, by it: the first by name where a catalogue
        #: written before one-artist-per-item holds two (`artist_ids_by_qid`).
        self._artist_names_by_qid: dict[str, str] = {}
        for artist in artists:
            if artist.wikidata_qid:
                self._artist_names_by_qid.setdefault(artist.wikidata_qid, artist.name)
        self._held_by_key: dict[str, list[str]] = {}
        for artwork_id, title, artist_id in store.circulating_without_qid():
            key = work_dedup_key(title=title, artist=names.get(artist_id) if artist_id else None)
            self._held_by_key.setdefault(key, []).append(artwork_id)
        self._open_artists: tuple[Artist, ...] = tuple(artist for artist in artists if open_to_match(artist))
        waiting = awaiting.works_awaiting_review()
        self._waiting_by_qid: dict[str, CandidateWork] = {}
        self._waiting_by_key: dict[str, CandidateWork] = {}
        self._waiting_by_artist: dict[str, CandidateWork] = {}
        for work in waiting:
            if work.wikidata_qid:
                self._waiting_by_qid.setdefault(work.wikidata_qid, work)
            else:
                # Recomputed rather than read from the stored key, so a row and
                # a proposal are compared by one derivation of today's rule.
                self._waiting_by_key.setdefault(work_dedup_key(title=work.proposed_title, artist=work.proposed_artist), work)
            if work.proposed_artist and (folded := artist_key(work.proposed_artist)):
                self._waiting_by_artist.setdefault(folded, work)

    def held_work(self, qid: str, title: str, *, maker: str | None, maker_qid: str | None) -> Sequence[str]:
        """The library's works in circulation that are this registry work: by QID, else by title and artist.

        The artist is asked by the registry's name for the maker and, where the
        library holds the maker by QID, by the library's own name for them, so a
        spelling the two disagree on does not keep a held work apart.
        """
        by_qid = self._held_by_qid.get(qid)
        if by_qid:
            return by_qid
        found: list[str] = []
        for key in self._keys(title, maker=maker, maker_qid=maker_qid):
            found.extend(artwork_id for artwork_id in self._held_by_key.get(key, ()) if artwork_id not in found)
        return found

    def waiting_work(self, qid: str, title: str, *, maker: str | None, maker_qid: str | None) -> InReview | None:
        """The proposed work awaiting a verdict that is this registry work, if one does."""
        work = self._waiting_by_qid.get(qid)
        if work is None:
            work = next(
                (
                    self._waiting_by_key[key]
                    for key in self._keys(title, maker=maker, maker_qid=maker_qid)
                    if key in self._waiting_by_key
                ),
                None,
            )
        return None if work is None else InReview(run_id=work.discovery_run_id, candidate_work_id=work.id)

    def held_artist(self, person: RegistryPerson) -> str | None:
        """The library artist with no QID who is this person, by name and life dates; never one who carries a QID.

        A registry person the library holds by QID is the caller's to find
        (`artist_ids_by_qid`). An artist the curator said has no Wikidata item
        is never folded: they said this person is not anyone Wikidata knows.
        """
        name = search_fold(person.label)
        return next(
            (artist.id for artist in self._open_artists if search_fold(artist.name) == name and years_agree(artist, person)),
            None,
        )

    def waiting_artist(self, name: str) -> InReview | None:
        """A proposed work by this artist awaiting a verdict, the first by title, if there is one."""
        folded = artist_key(name)
        work = self._waiting_by_artist.get(folded) if folded else None
        return None if work is None else InReview(run_id=work.discovery_run_id, candidate_work_id=work.id)

    def _keys(self, title: str, *, maker: str | None, maker_qid: str | None) -> Iterable[str]:
        names = dict.fromkeys(
            name for name in (maker, self._artist_names_by_qid.get(maker_qid) if maker_qid else None) if name is not None
        )
        return [work_dedup_key(title=title, artist=name) for name in names] or [work_dedup_key(title=title)]
